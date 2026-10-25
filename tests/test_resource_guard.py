"""Fictional limit probes plus actual termination of harmless local workers."""

from dataclasses import replace
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace

import pytest

from watchlist.ingest import resource_guard as resource


class ManualClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def safe_snapshot(**changes):
    return replace(
        resource.ResourceSnapshot(20_000_000, 20 * resource.GIB, 0, 0.50, False),
        **changes,
    )


def small_ledger(clock=None):
    limits = dict(resource.STEP08_LIMITS)
    limits["opensanctions_un"] = replace(
        limits["opensanctions_un"], received_bytes=100, response_bytes=70
    )
    return resource.BudgetLedger(clock=clock or ManualClock(), limits=limits)


def test_exact_central_limits_and_unallocated_bytes_are_not_available():
    assert (
        sum(limit.received_bytes for limit in resource.STEP08_LIMITS.values())
        == 59_000_000
    )
    assert resource.TRANCHE_BYTES == 59_000_000
    assert resource.STEP08_LIMITS["metadata"].transactions == 16
    assert resource.STEP08_LIMITS["metadata"].response_bytes == 512_000
    assert resource.STEP08_LIMITS["wikidata_orgs"].transactions == 250
    assert resource.STEP08_LIMITS["wikidata_orgs"].response_bytes == 2_000_000
    assert resource.STEP08_LIMITS["eu_consolidated"].request_seconds == 180
    assert resource.STEP08_LIMITS["eu_consolidated"].source_seconds == 240
    with pytest.raises(TypeError):
        resource.STEP08_LIMITS["metadata"] = None


def test_failed_and_redirect_reads_share_the_remaining_source_allowance():
    ledger = small_ledger()
    ledger.begin_source("opensanctions_un")
    first = ledger.begin_request("opensanctions_un")
    ledger.charge_received(first, 60)
    ledger.finish_request(first)
    second = ledger.begin_request("opensanctions_un")
    assert ledger.remaining_bytes(second) == 40
    with pytest.raises(
        resource.ResourceStop, match="declared_length_exceeds_remaining"
    ):
        ledger.declare_length(second, 41)
    receipt = ledger.receipt()
    assert receipt["total_received_bytes"] == 60
    assert receipt["transactions"]["opensanctions_un"] == 2
    assert receipt["active_response_reservation"] == 40
    assert receipt["resume_supported"] is False


def test_bulk_only_session_cannot_spend_other_buckets_or_expand_approval():
    for bucket in ("metadata", "wikidata_orgs"):
        ledger = resource.BudgetLedger(
            total_received_limit=39_000_000,
            bulk_transaction_limit=3,
            allowed_buckets=resource.BULK_SOURCES,
        )
        with pytest.raises(resource.ResourceStop, match="bucket_not_authorized"):
            ledger.begin_source(bucket)
        assert sum(ledger.receipt()["transactions"].values()) == 0
        assert ledger.receipt()["tranche_bytes"] == 39_000_000
        assert ledger.receipt()["bulk_transaction_limit"] == 3
    for kwargs in (
        {"total_received_limit": resource.TRANCHE_BYTES + 1},
        {"bulk_transaction_limit": 10},
        {"allowed_buckets": frozenset({"un_consolidated"})},
        {"allowed_buckets": frozenset()},
    ):
        with pytest.raises(resource.ResourceStop):
            resource.BudgetLedger(**kwargs)


def test_tighter_total_budget_is_shared_across_sources():
    ledger = resource.BudgetLedger(
        total_received_limit=100,
        bulk_transaction_limit=3,
        allowed_buckets=resource.BULK_SOURCES,
    )
    ledger.begin_source("opensanctions_un")
    ticket = ledger.begin_request("opensanctions_un")
    ledger.charge_received(ticket, 60)
    ledger.finish_request(ticket)
    ledger.finish_source("opensanctions_un")
    ledger.begin_source("ofac_sdn")
    ticket = ledger.begin_request("ofac_sdn")
    assert ledger.remaining_bytes(ticket) == 40
    with pytest.raises(
        resource.ResourceStop, match="declared_length_exceeds_remaining"
    ):
        ledger.declare_length(ticket, 41)
    assert ledger.receipt()["total_received_bytes"] == 60


def test_tighter_transaction_limit_counts_empty_failed_attempts():
    ledger = resource.BudgetLedger(
        total_received_limit=39_000_000,
        bulk_transaction_limit=3,
        allowed_buckets=resource.BULK_SOURCES,
    )
    ledger.begin_source("opensanctions_un")
    for _ in range(3):
        ticket = ledger.begin_request("opensanctions_un")
        ledger.finish_request(ticket)
    ledger.finish_source("opensanctions_un")
    ledger.begin_source("ofac_sdn")
    with pytest.raises(resource.ResourceStop, match="bulk_transaction_limit"):
        ledger.begin_request("ofac_sdn")
    assert sum(ledger.receipt()["transactions"].values()) == 3
    assert ledger.receipt()["total_received_bytes"] == 0


def test_returned_oversized_bytes_are_charged_before_rejection():
    ledger = small_ledger()
    ledger.begin_source("opensanctions_un")
    request = ledger.begin_request("opensanctions_un")
    with pytest.raises(resource.ResourceStop, match="received_byte_limit"):
        ledger.charge_received(request, 101)
    assert ledger.receipt()["total_received_bytes"] == 101
    assert ledger.receipt()["transactions"]["opensanctions_un"] == 1


def test_late_bytes_are_charged_and_absolute_deadline_is_not_reset():
    clock = ManualClock()
    ledger = small_ledger(clock)
    ledger.begin_source("opensanctions_un")
    request = ledger.begin_request("opensanctions_un")
    clock.advance(20)
    assert ledger.remaining_seconds(request) == 10
    ledger.charge_received(request, 10)
    clock.advance(10)
    with pytest.raises(resource.ResourceStop, match="request_deadline"):
        ledger.charge_received(request, 7)
    assert ledger.receipt()["total_received_bytes"] == 17


def test_source_attempt_and_request_counts_cannot_reset():
    ledger = small_ledger()
    ledger.begin_source("opensanctions_un")
    for _ in range(3):
        request = ledger.begin_request("opensanctions_un")
        ledger.finish_request(request)
    with pytest.raises(resource.ResourceStop, match="transaction_limit"):
        ledger.begin_request("opensanctions_un")
    assert ledger.receipt()["transactions"]["opensanctions_un"] == 3
    other = small_ledger()
    other.begin_source("opensanctions_un")
    other.finish_source("opensanctions_un")
    with pytest.raises(resource.ResourceStop, match="source_attempt_already_used"):
        other.begin_source("opensanctions_un")


def test_sources_and_requests_are_serial():
    ledger = small_ledger()
    ledger.begin_source("opensanctions_un")
    with pytest.raises(resource.ResourceStop, match="concurrent_source_forbidden"):
        ledger.begin_source("ofac_sdn")
    ledger = small_ledger()
    ledger.begin_source("opensanctions_un")
    ledger.begin_request("opensanctions_un")
    with pytest.raises(resource.ResourceStop, match="request_outside_serial_source"):
        ledger.begin_request("opensanctions_un")


def test_source_and_session_deadlines_include_work_between_requests():
    clock = ManualClock()
    ledger = small_ledger(clock)
    ledger.begin_source("opensanctions_un")
    request = ledger.begin_request("opensanctions_un")
    ledger.finish_request(request)
    clock.advance(119)
    next_request = ledger.begin_request("opensanctions_un")
    assert ledger.remaining_seconds(next_request) == 1
    clock.advance(1)
    with pytest.raises(resource.ResourceStop, match="source_deadline"):
        ledger.remaining_seconds(next_request)
    clock = ManualClock()
    ledger = resource.BudgetLedger(clock=clock, session_seconds=5)
    clock.advance(5)
    with pytest.raises(resource.ResourceStop, match="session_deadline"):
        ledger.begin_source("metadata")


def test_expanded_or_invalid_budget_configuration_is_rejected():
    limits = dict(resource.STEP08_LIMITS)
    limits["ofac_sdn"] = replace(limits["ofac_sdn"], received_bytes=4_000_001)
    with pytest.raises(resource.ResourceStop, match="bucket_limit_exceeds_approval"):
        resource.BudgetLedger(limits=limits)
    with pytest.raises(resource.ResourceStop, match="invalid_session_limits"):
        resource.BudgetLedger(session_seconds=3601)
    with pytest.raises(resource.ResourceStop, match="invalid_received_bytes"):
        resource.BudgetLedger(
            limits={
                **resource.STEP08_LIMITS,
                "metadata": replace(
                    resource.STEP08_LIMITS["metadata"], received_bytes=True
                ),
            }
        )


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"aggregate_rss_bytes": 2 * resource.GIB}, "rss_hard_limit"),
        ({"aggregate_rss_bytes": 3 * resource.GIB // 2}, "rss_soft_limit"),
        ({"free_disk_bytes": 10 * resource.GIB - 1}, "free_disk_limit"),
        ({"artifact_bytes": 2 * resource.GIB + 1}, "artifact_byte_limit"),
        ({"free_memory_fraction": 0.249}, "host_free_memory_limit"),
        ({"memory_pressure": True}, "host_memory_pressure"),
    ],
)
def test_resource_admission_fails_closed(changes, reason):
    guard = resource.ResourceGuard(probe=lambda: safe_snapshot(**changes))
    with pytest.raises(resource.ResourceStop, match=reason):
        guard.admit()


def test_memory_admission_and_running_floors_are_distinct():
    snapshot = safe_snapshot(free_memory_fraction=0.25)
    guard = resource.ResourceGuard(probe=lambda: snapshot)
    guard.admit()
    snapshot = safe_snapshot(free_memory_fraction=0.20)
    guard.check()
    snapshot = safe_snapshot(free_memory_fraction=0.199)
    with pytest.raises(resource.ResourceStop, match="host_free_memory_limit"):
        guard.check()
    snapshot = safe_snapshot()
    with pytest.raises(resource.ResourceStop, match="host_free_memory_limit"):
        guard.check()


def test_probe_failure_and_missing_admission_close_the_gate():
    def broken():
        raise OSError("fictional unavailable probe")

    with pytest.raises(resource.ResourceStop, match="resource_probe_unavailable"):
        resource.ResourceGuard(probe=broken).admit()
    guard = resource.ResourceGuard(probe=lambda: safe_snapshot())
    with pytest.raises(resource.ResourceStop, match="resource_session_not_admitted"):
        guard.check()
    guard.admit()
    with pytest.raises(
        resource.ResourceStop, match="resource_session_already_admitted"
    ):
        guard.admit()


def test_unknown_probe_failure_is_permanent_and_hides_exception_text():
    calls = []

    def broken():
        calls.append(True)
        raise OSError("fictional-sensitive-probe-output")

    guard = resource.ResourceGuard(probe=broken)
    for _ in range(2):
        with pytest.raises(resource.ResourceStop) as failure:
            guard.admit()
        assert failure.value.code == "resource_probe_unavailable"
        assert "fictional-sensitive-probe-output" not in "".join(
            traceback.format_exception(failure.value)
        )
    assert len(calls) == 1
    assert not guard.admitted


def test_unknown_probe_state_blocks_admission_permanently():
    guard = resource.ResourceGuard(probe=lambda: None)
    for _ in range(2):
        with pytest.raises(resource.ResourceStop, match="resource_probe_invalid"):
            guard.admit()
    assert not guard.admitted


def test_artifact_and_normalized_reservations_do_not_refund_failed_writes():
    guard = resource.ResourceGuard(
        probe=lambda: safe_snapshot(),
        limits=resource.ResourceLimits(max_normalized_bytes=100),
    )
    guard.admit()
    guard.reserve_artifact(60, normalized=True)
    with pytest.raises(resource.ResourceStop, match="normalized_byte_limit"):
        guard.reserve_artifact(41, normalized=True)
    assert guard.normalized_bytes == 60
    assert guard.reserved_artifact_bytes == 60
    guard = resource.ResourceGuard(
        probe=lambda: safe_snapshot(),
        limits=resource.ResourceLimits(max_artifact_bytes=100),
    )
    guard.admit()
    guard.reserve_artifact(100)
    with pytest.raises(resource.ResourceStop, match="artifact_byte_limit"):
        guard.reserve_artifact(1)


def test_retained_normalized_selection_and_new_copy_share_the_same_cap():
    guard = resource.ResourceGuard(
        probe=lambda: safe_snapshot(artifact_bytes=60),
        limits=resource.ResourceLimits(max_normalized_bytes=100),
        initial_normalized_bytes=60,
    )
    guard.admit()
    guard.reserve_artifact(40, normalized=True)
    assert guard.normalized_bytes == 100
    assert guard.reserved_artifact_bytes == 100
    with pytest.raises(resource.ResourceStop, match="normalized_byte_limit"):
        guard.reserve_artifact(1, normalized=True)
    assert guard.normalized_bytes == 100


@pytest.mark.parametrize("initial", [-1, True, 1.5])
def test_invalid_initial_normalized_reservation_is_rejected(initial):
    with pytest.raises(resource.ResourceStop, match="invalid_initial_normalized_bytes"):
        resource.ResourceGuard(
            probe=lambda: safe_snapshot(), initial_normalized_bytes=initial
        )


def test_retained_normalized_selection_above_cap_is_rejected_before_probe():
    def must_not_probe():
        pytest.fail("over-cap reservation must fail before measurement")

    with pytest.raises(resource.ResourceStop, match="normalized_byte_limit"):
        resource.ResourceGuard(
            probe=must_not_probe, initial_normalized_bytes=100_000_001
        )


def test_guard_deadline_and_invalid_clock_are_not_restartable():
    clock = ManualClock()
    guard = resource.ResourceGuard(
        probe=lambda: safe_snapshot(),
        clock=clock,
        limits=resource.ResourceLimits(session_seconds=1),
    )
    guard.admit()
    clock.advance(1)
    with pytest.raises(resource.ResourceStop, match="session_deadline"):
        guard.check()
    clock = ManualClock()
    guard = resource.ResourceGuard(probe=lambda: safe_snapshot(), clock=clock)
    guard.admit()
    clock.advance(-1)
    with pytest.raises(resource.ResourceStop, match="clock_moved_backwards"):
        guard.check()


def test_probe_runtime_consumes_the_absolute_resource_deadline():
    clock = ManualClock()

    def slow_probe():
        clock.advance(5)
        return safe_snapshot()

    guard = resource.ResourceGuard(
        probe=slow_probe, clock=clock, limits=resource.ResourceLimits(session_seconds=5)
    )
    with pytest.raises(resource.ResourceStop, match="session_deadline"):
        guard.admit()


@pytest.mark.parametrize(
    "changes",
    [
        {"rss_hard_bytes": 2 * resource.GIB + 1},
        {"min_free_disk_bytes": 1},
        {"admission_free_memory_fraction": 0.2},
        {"stop_free_memory_fraction": 0.19},
    ],
)
def test_resource_configuration_cannot_weaken_approval(changes):
    with pytest.raises(resource.ResourceStop):
        resource.ResourceLimits(**changes)


def test_aggregate_process_probe_includes_worker_children_without_other_groups(
    monkeypatch,
):
    table = "100 1 100 50\n200 100 200 100\n201 200 200 150\n202 201 202 200\n900 1 900 9999\n"
    monkeypatch.setattr(resource, "_run_probe", lambda command, **kwargs: table)
    assert resource.aggregate_process_rss(200, 100) == 500 * 1024
    assert resource.aggregate_process_rss(None, 100) == 50 * 1024


@pytest.mark.parametrize(
    "failed_command, code",
    [
        ("ps", "rss_probe_unavailable"),
        ("memory_pressure", "host_free_memory_probe_unavailable"),
        ("sysctl", "host_pressure_probe_unavailable"),
    ],
)
def test_command_probe_diagnostics_identify_subprobe_without_output(
    monkeypatch, failed_command, code
):
    monkeypatch.setattr(resource.sys, "platform", "darwin")

    def run(command, **kwargs):
        if command[0] == failed_command:
            raise subprocess.CalledProcessError(
                1, command, output="fictional-sensitive-probe-output"
            )
        return SimpleNamespace(stdout="System-wide memory free percentage: 50%")

    monkeypatch.setattr(resource.subprocess, "run", run)
    with pytest.raises(resource.ResourceStop) as failure:
        if failed_command == "ps":
            resource.aggregate_process_rss(None, 100)
        else:
            resource._host_memory()
    assert failure.value.code == code
    assert "fictional-sensitive-probe-output" not in "".join(
        traceback.format_exception(failure.value)
    )


@pytest.mark.parametrize(
    "memory, pressure, code",
    [
        ("unknown", "1", "invalid_host_free_memory_probe"),
        (
            "System-wide memory free percentage: 101%",
            "1",
            "invalid_host_free_memory_probe",
        ),
        (
            "System-wide memory free percentage: 50%",
            "unknown",
            "invalid_host_pressure_probe",
        ),
    ],
)
def test_unknown_darwin_memory_state_stops(monkeypatch, memory, pressure, code):
    monkeypatch.setattr(resource.sys, "platform", "darwin")
    monkeypatch.setattr(
        resource,
        "_run_probe",
        lambda command, **kwargs: memory
        if command[0] == "memory_pressure"
        else pressure,
    )
    with pytest.raises(resource.ResourceStop, match=code):
        resource._host_memory()


@pytest.mark.parametrize(
    "failed_path, code",
    [
        ("/proc/meminfo", "host_free_memory_probe_unavailable"),
        ("/proc/pressure/memory", "host_pressure_probe_unavailable"),
    ],
)
def test_linux_probe_file_failures_are_specific_and_safe(
    monkeypatch, failed_path, code
):
    monkeypatch.setattr(resource.sys, "platform", "linux")

    def read_text(path, **kwargs):
        if str(path) == failed_path:
            raise PermissionError("fictional-sensitive-probe-output")
        return "MemTotal: 100 kB\nMemAvailable: 50 kB\n"

    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(resource.ResourceStop) as failure:
        resource._host_memory()
    assert failure.value.code == code
    assert "fictional-sensitive-probe-output" not in "".join(
        traceback.format_exception(failure.value)
    )


@pytest.mark.parametrize(
    "memory, pressure, code",
    [
        ("MemTotal: unknown kB\n", "", "invalid_host_free_memory_probe"),
        (
            "MemTotal: 100 kB\nMemAvailable: 101 kB\n",
            "",
            "invalid_host_free_memory_probe",
        ),
        (
            "MemTotal: 100 kB\nMemAvailable: 50 kB\n",
            "some avg10=unknown avg60=0.00\nfull avg10=0.00 avg60=0.00\n",
            "invalid_host_pressure_probe",
        ),
    ],
)
def test_unknown_linux_memory_state_stops(monkeypatch, memory, pressure, code):
    monkeypatch.setattr(resource.sys, "platform", "linux")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, **kwargs: memory if str(path) == "/proc/meminfo" else pressure,
    )
    with pytest.raises(resource.ResourceStop, match=code):
        resource._host_memory()


def test_system_snapshot_counts_files_and_rejects_symlinks(tmp_path, monkeypatch):
    monkeypatch.setattr(resource, "_host_memory", lambda: (0.5, False))
    monkeypatch.setattr(resource, "aggregate_process_rss", lambda *args: 12345)
    monkeypatch.setattr(
        resource.shutil,
        "disk_usage",
        lambda root: SimpleNamespace(free=20 * resource.GIB),
    )
    (tmp_path / "one").write_bytes(b"abc")
    (tmp_path / "child").mkdir()
    (tmp_path / "child" / "two").write_bytes(b"defg")
    assert resource.system_snapshot(tmp_path).artifact_bytes == 7
    (tmp_path / "link").symlink_to(tmp_path / "one")
    with pytest.raises(resource.ResourceStop, match="artifact_path_not_regular"):
        resource.system_snapshot(tmp_path)


def test_original_and_new_artifact_roots_share_one_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(resource, "_host_memory", lambda: (0.5, False))
    monkeypatch.setattr(resource, "aggregate_process_rss", lambda *args: 12345)
    monkeypatch.setattr(
        resource.shutil,
        "disk_usage",
        lambda root: SimpleNamespace(free=20 * resource.GIB),
    )
    original = tmp_path / "original"
    retry = tmp_path / "retry"
    original.mkdir()
    retry.mkdir()
    (original / "fictional-selection.json").write_bytes(b"a" * 60)
    (retry / "fictional-copy.json").write_bytes(b"b" * 40)
    # A sibling is outside the two explicitly approved roots.
    (tmp_path / "unrelated.bin").write_bytes(b"x" * 101)

    def probe():
        return resource.system_snapshot(retry, additional_artifact_roots=(original,))

    guard = resource.ResourceGuard(
        probe=probe, limits=resource.ResourceLimits(max_artifact_bytes=100)
    )
    assert guard.admit().artifact_bytes == 100
    with pytest.raises(resource.ResourceStop, match="artifact_byte_limit"):
        guard.reserve_artifact(1)


def test_missing_retained_artifact_root_cannot_reduce_measurement(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(resource, "_host_memory", lambda: (0.5, False))
    monkeypatch.setattr(resource, "aggregate_process_rss", lambda *args: 12345)
    monkeypatch.setattr(
        resource.shutil,
        "disk_usage",
        lambda root: SimpleNamespace(free=20 * resource.GIB),
    )
    with pytest.raises(resource.ResourceStop, match="artifact_root_missing"):
        resource.system_snapshot(
            tmp_path / "new", additional_artifact_roots=(tmp_path / "missing-old",)
        )


@pytest.mark.parametrize(
    "target, code",
    [
        ("memory", "host_memory_probe_unavailable"),
        ("rss", "rss_probe_unavailable"),
        ("disk", "disk_probe_unavailable"),
    ],
)
def test_snapshot_subprobe_failures_have_safe_specific_codes(
    tmp_path, monkeypatch, target, code
):
    def unavailable(*args):
        raise RuntimeError("fictional-sensitive-probe-output")

    monkeypatch.setattr(
        resource,
        "_host_memory",
        unavailable if target == "memory" else lambda: (0.5, False),
    )
    monkeypatch.setattr(
        resource,
        "aggregate_process_rss",
        unavailable if target == "rss" else lambda *args: 1,
    )
    if target == "disk":
        monkeypatch.setattr(resource.shutil, "disk_usage", unavailable)
    with pytest.raises(resource.ResourceStop) as failure:
        resource.system_snapshot(tmp_path)
    assert failure.value.code == code
    assert "fictional-sensitive-probe-output" not in "".join(
        traceback.format_exception(failure.value)
    )


def test_resource_artifact_root_cannot_be_a_regular_file(tmp_path, monkeypatch):
    monkeypatch.setattr(resource, "_host_memory", lambda: (0.5, False))
    monkeypatch.setattr(resource, "aggregate_process_rss", lambda *args: 12345)
    monkeypatch.setattr(
        resource.shutil,
        "disk_usage",
        lambda root: SimpleNamespace(free=20 * resource.GIB),
    )
    artifact = tmp_path / "one"
    artifact.write_bytes(b"fictional artifact")
    with pytest.raises(resource.ResourceStop, match="artifact_root_not_directory"):
        resource.system_snapshot(artifact)


def test_atomic_publication_unlink_does_not_invalidate_artifact_measurement(
    tmp_path, monkeypatch
):
    # _PrivateRun publishes a hard link, then removes its .pending name. Model
    # a directory listing taken just before that legitimate unlink.
    (tmp_path / "published.json").write_bytes(b"seven77")
    calls = []

    def changing_walk(root, **kwargs):
        calls.append(root)
        files = ["published.json"]
        if len(calls) == 1:
            files.append(".pending-removed")
        yield str(root), [], files

    monkeypatch.setattr(resource.os, "walk", changing_walk)
    assert resource._artifact_size(tmp_path) == 7
    assert len(calls) == 2


def test_actual_concurrent_publication_unlink_is_remeasured_completely(
    tmp_path, monkeypatch, record_testsuite_property
):
    # Exercise the real publisher and filesystem. Events only arrange the
    # timing: enumeration sees the temporary link, then publication unlinks it
    # before measurement stats that stale name. No file entry is fabricated.
    from watchlist.ingest.acquire import _PrivateRun

    run = _PrivateRun(tmp_path / "fictional-run")
    run.publish("stable.json", b"stable")
    payload = b"fictional publication"
    ready = threading.Event()
    listed = threading.Event()
    removed = threading.Event()
    errors = []
    scans = []
    actual_walk = os.walk
    actual_unlink = os.unlink

    def coordinated_unlink(path, *args, **kwargs):
        if (
            isinstance(path, str)
            and path.startswith(".pending-")
            and kwargs.get("dir_fd") == run.fd
        ):
            ready.set()
            if not listed.wait(2):
                raise TimeoutError("fictional publication race coordination expired")
            result = actual_unlink(path, *args, **kwargs)
            removed.set()
            return result
        return actual_unlink(path, *args, **kwargs)

    def coordinated_walk(root, **kwargs):
        scans.append(root)
        for base, directories, files in actual_walk(root, **kwargs):
            if len(scans) == 1 and any(name.startswith(".pending-") for name in files):
                listed.set()
                assert removed.wait(2)
            yield base, directories, files

    def publish():
        try:
            run.publish("published.json", payload)
        except Exception as exc:
            errors.append(type(exc).__name__)

    monkeypatch.setattr(resource.os, "walk", coordinated_walk)
    monkeypatch.setattr(resource.os, "unlink", coordinated_unlink)
    publisher = threading.Thread(target=publish, daemon=True)
    publisher.start()
    try:
        assert ready.wait(2)
        measured = resource._artifact_size(run.path)
    finally:
        listed.set()
        publisher.join(timeout=3)
        if not publisher.is_alive():
            run.close()
    assert not publisher.is_alive()
    assert errors == []
    assert removed.is_set()
    assert len(scans) == 2
    assert measured == len(b"stable") + len(payload)
    assert (run.path / "published.json").read_bytes() == payload
    assert sorted(path.name for path in run.path.iterdir()) == [
        "published.json",
        "stable.json",
    ]
    record_testsuite_property("actual_publication_race_scan_attempts", len(scans))
    record_testsuite_property("actual_publication_race_measured_bytes", measured)
    record_testsuite_property("actual_publication_race_expected_bytes", 27)


def test_artifact_walk_permission_error_stops_without_retry_or_exception_text(
    tmp_path, monkeypatch
):
    scans = []

    def denied_walk(root, **kwargs):
        scans.append(root)
        kwargs["onerror"](PermissionError("fictional-sensitive-artifact-path"))
        yield str(root), [], []

    monkeypatch.setattr(resource.os, "walk", denied_walk)
    with pytest.raises(resource.ResourceStop) as failure:
        resource._artifact_size(tmp_path)
    assert failure.value.code == "artifact_probe_unavailable"
    assert "fictional-sensitive-artifact-path" not in "".join(
        traceback.format_exception(failure.value)
    )
    assert len(scans) == 1


def test_persistently_unstable_artifact_measurement_stops_after_bounded_scans(
    tmp_path, monkeypatch
):
    calls = []

    def unstable_walk(root, **kwargs):
        calls.append(root)
        yield str(root), [], [".pending-removed"]

    monkeypatch.setattr(resource.os, "walk", unstable_walk)
    with pytest.raises(resource.ResourceStop, match="artifact_snapshot_unstable"):
        resource._artifact_size(tmp_path)
    assert len(calls) == 3


def test_guard_preserves_specific_resource_failure_without_relaxing_stop():
    def unavailable():
        raise resource.ResourceStop("artifact_snapshot_unstable")

    guard = resource.ResourceGuard(probe=unavailable)
    with pytest.raises(resource.ResourceStop, match="artifact_snapshot_unstable"):
        guard.admit()
    assert guard.admitted is False


def test_real_worker_is_terminated_by_injected_hard_rss_probe(tmp_path):
    observed = []

    def probe(pid):
        if pid is not None:
            observed.append(pid)
            os.kill(pid, 0)  # Confirm this is an actual live worker, not a mock.
            return safe_snapshot(aggregate_rss_bytes=2 * resource.GIB)
        return safe_snapshot()

    result = resource.supervise_command(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
        artifact_root=tmp_path,
        probe=probe,
        poll_interval=0.01,
    )
    assert result.status == "terminated"
    assert result.stop_reason == "rss_hard_limit"
    assert result.returncode < 0
    assert result.peak_rss_bytes == 2 * resource.GIB
    assert len(observed) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(observed[0], 0)


def test_supervisor_deadline_stops_actual_worker(tmp_path):
    result = resource.supervise_command(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
        artifact_root=tmp_path,
        probe=lambda pid: safe_snapshot(),
        timeout_seconds=0.05,
        poll_interval=0.01,
    )
    assert result.status == "terminated"
    assert result.stop_reason == "worker_deadline"
    assert result.elapsed_seconds < 3


def test_supervisor_success_and_probe_failure_are_reported(tmp_path):
    result = resource.supervise_command(
        [sys.executable, "-I", "-B", "-c", "pass"],
        artifact_root=tmp_path,
        probe=lambda pid: safe_snapshot(),
        poll_interval=0.01,
    )
    assert result.status == "exited" and result.returncode == 0

    def probe(pid):
        if pid is not None:
            raise OSError("fictional unavailable probe")
        return safe_snapshot()

    result = resource.supervise_command(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
        artifact_root=tmp_path,
        probe=probe,
    )
    assert result.stop_reason == "resource_probe_unavailable"
    assert result.returncode < 0


def test_process_group_termination_reaches_child_and_does_not_touch_neighbor(tmp_path):
    child_file = tmp_path / "child.pid"
    worker_file = tmp_path / "worker.py"
    worker_file.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(30)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    neighbor = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )

    def probe(pid):
        if pid is not None and child_file.exists():
            return safe_snapshot(memory_pressure=True)
        return safe_snapshot()

    try:
        result = resource.supervise_command(
            [sys.executable, "-I", "-B", str(worker_file), str(child_file)],
            artifact_root=tmp_path,
            probe=probe,
            timeout_seconds=5,
            poll_interval=0.01,
        )
        assert result.stop_reason == "host_memory_pressure"
        child_pid = int(child_file.read_text())
        # A terminated orphan can briefly remain as a zombie until OS reaping.
        state_deadline = time.monotonic() + 1
        while True:
            child_state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(child_pid)],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if (
                not child_state
                or child_state.startswith("Z")
                or time.monotonic() >= state_deadline
            ):
                break
            time.sleep(0.01)
        assert not child_state or child_state.startswith("Z")
        assert neighbor.poll() is None
    finally:
        os.killpg(neighbor.pid, signal.SIGKILL)
        neighbor.wait(timeout=3)


def test_real_numeric_process_probe_observes_own_process():
    assert resource.aggregate_process_rss(None, os.getpid()) > 0


def test_worker_admission_rejection_creates_no_process(tmp_path, monkeypatch):
    def must_not_start(*args, **kwargs):
        pytest.fail("worker must not launch after failed admission")

    monkeypatch.setattr(resource.subprocess, "Popen", must_not_start)
    with pytest.raises(resource.ResourceStop, match="free_disk_limit"):
        resource.supervise_command(
            [sys.executable, "-c", "pass"],
            artifact_root=tmp_path,
            probe=lambda pid: safe_snapshot(free_disk_bytes=0),
        )
