"""Offline-tested Step 08 bounds and supervision for a trusted local worker.

The byte ledger is one session object: failures consume their transactions and
all returned bytes. It has no reset or resume API. Its receipt is evidence, not
permission to start another session. RSS enforcement is sampled supervision,
not an operating-system allocation limit: a worker can overshoot between polls.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from types import MappingProxyType
from typing import Callable, Mapping, Sequence


GIB = 1024**3


class ResourceStop(ValueError):
    """An aggregate limit or an unavailable measurement closes the gate."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class BucketLimits:
    received_bytes: int
    transactions: int
    response_bytes: int
    request_seconds: int
    source_seconds: int


STEP08_LIMITS: Mapping[str, BucketLimits] = MappingProxyType(
    {
        "metadata": BucketLimits(5_000_000, 16, 512_000, 30, 3600),
        "opensanctions_un": BucketLimits(5_000_000, 3, 5_000_000, 30, 120),
        "ofac_sdn": BucketLimits(4_000_000, 3, 4_000_000, 30, 120),
        "eu_consolidated": BucketLimits(30_000_000, 3, 30_000_000, 180, 240),
        "wikidata_orgs": BucketLimits(15_000_000, 250, 2_000_000, 30, 1800),
    }
)
BULK_SOURCES = frozenset({"opensanctions_un", "ofac_sdn", "eu_consolidated"})
TRANCHE_BYTES = 59_000_000


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ResourceStop(f"invalid_{label}")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResourceStop(f"invalid_{label}")
    if not math.isfinite(value):
        raise ResourceStop(f"invalid_{label}")
    return float(value)


@dataclass(frozen=True, slots=True)
class RequestTicket:
    """Opaque session-local handle; callers cannot reset its charged counters."""

    sequence: int
    bucket: str
    deadline: float


class BudgetLedger:
    """Count serial requests and returned bodies against intersecting caps.

    Call ``begin_source``, ``begin_request``, ``charge_received`` and the matching
    finish methods. Check ``remaining_seconds`` before and after blocking work.
    A source may begin only once, including after a failure. Separate metadata
    and API implementations may share this same object with the three sources.
    No wall-clock restart or receipt import is supported in this offline phase.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        session_seconds: float = 3600,
        limits: Mapping[str, BucketLimits] = STEP08_LIMITS,
        on_change: Callable[[dict], None] | None = None,
        total_received_limit: int = TRANCHE_BYTES,
        bulk_transaction_limit: int = 9,
        allowed_buckets: frozenset[str] | None = None,
    ) -> None:
        self._clock = clock
        self._last_time = _finite(clock(), "clock")
        duration = _finite(session_seconds, "session_seconds")
        if not 0 < duration <= 3600 or set(limits) != set(STEP08_LIMITS):
            raise ResourceStop("invalid_session_limits")
        for name, value in limits.items():
            if not isinstance(value, BucketLimits):
                raise ResourceStop("invalid_bucket_limits")
            for key, ceiling in asdict(STEP08_LIMITS[name]).items():
                if not 1 <= _integer(getattr(value, key), key) <= ceiling:
                    raise ResourceStop("bucket_limit_exceeds_approval")
        if (
            not 1
            <= _integer(total_received_limit, "total_received_limit")
            <= TRANCHE_BYTES
        ):
            raise ResourceStop("aggregate_limit_exceeds_approval")
        if not 1 <= _integer(bulk_transaction_limit, "bulk_transaction_limit") <= 9:
            raise ResourceStop("aggregate_limit_exceeds_approval")
        selected = frozenset(limits) if allowed_buckets is None else allowed_buckets
        if (
            not isinstance(selected, frozenset)
            or not selected
            or not selected <= set(limits)
        ):
            raise ResourceStop("invalid_allowed_buckets")
        self.total_received_limit = total_received_limit
        self.bulk_transaction_limit = bulk_transaction_limit
        self.allowed_buckets = selected
        self.limits = MappingProxyType(dict(limits))
        self.deadline = self._last_time + duration
        self._on_change = on_change
        self._used: set[str] = set()
        self._active_source: str | None = None
        self._source_deadline: float | None = None
        self._request: RequestTicket | None = None
        self._request_received = 0
        self._response_limit = 0
        self._sequence = 0
        self._received = {name: 0 for name in self.limits}
        self._transactions = {name: 0 for name in self.limits}
        self._stop_reason: str | None = None

    def _fail(self, code: str) -> None:
        self._stop_reason = self._stop_reason or code
        self._changed()
        raise ResourceStop(self._stop_reason)

    def _now(self) -> float:
        value = _finite(self._clock(), "clock")
        if value < self._last_time:
            self._fail("clock_moved_backwards")
        self._last_time = value
        return value

    def _check(self) -> float:
        if self._stop_reason:
            raise ResourceStop(self._stop_reason)
        now = self._now()
        if now >= self.deadline:
            self._fail("session_deadline")
        if self._source_deadline is not None and now >= self._source_deadline:
            self._fail("source_deadline")
        if self._request is not None and now >= self._request.deadline:
            self._fail("request_deadline")
        return now

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change(self.receipt())

    def begin_source(self, bucket: str) -> None:
        """Consume the sole source attempt before transport work starts."""
        now = self._check()
        if bucket not in self.limits:
            self._fail("unknown_bucket")
        if bucket not in self.allowed_buckets:
            self._fail("bucket_not_authorized")
        if self._active_source is not None:
            self._fail("concurrent_source_forbidden")
        if bucket in self._used:
            self._fail("source_attempt_already_used")
        self._used.add(bucket)
        self._active_source = bucket
        self._source_deadline = min(
            self.deadline, now + self.limits[bucket].source_seconds
        )
        self._changed()

    def begin_request(self, bucket: str) -> RequestTicket:
        """Charge an HTTP transaction even if opening the response later fails."""
        now = self._check()
        if bucket != self._active_source or self._request is not None:
            self._fail("request_outside_serial_source")
        limit = self.limits[bucket]
        if self._transactions[bucket] >= limit.transactions:
            self._fail("transaction_limit")
        if (
            bucket in BULK_SOURCES
            and sum(self._transactions[source] for source in BULK_SOURCES)
            >= self.bulk_transaction_limit
        ):
            self._fail("bulk_transaction_limit")
        available = min(
            limit.received_bytes - self._received[bucket],
            self.total_received_limit - sum(self._received.values()),
        )
        if available <= 0:
            self._fail("received_byte_limit")
        self._transactions[bucket] += 1
        self._sequence += 1
        self._request = RequestTicket(
            self._sequence,
            bucket,
            min(self._source_deadline, now + limit.request_seconds),
        )
        self._request_received = 0
        self._response_limit = min(limit.response_bytes, available)
        self._changed()
        return self._request

    def _ticket(self, ticket: RequestTicket) -> None:
        if ticket is not self._request:
            self._fail("inactive_request_ticket")

    def remaining_seconds(self, ticket: RequestTicket | None = None) -> float:
        now = self._check()
        if ticket is not None:
            self._ticket(ticket)
            return ticket.deadline - now
        return min(self.deadline, self._source_deadline or self.deadline) - now

    def remaining_bytes(self, ticket: RequestTicket) -> int:
        self._ticket(ticket)
        self._check()
        return min(
            self._response_limit - self._request_received,
            self.limits[ticket.bucket].received_bytes - self._received[ticket.bucket],
            self.total_received_limit - sum(self._received.values()),
        )

    def declare_length(self, ticket: RequestTicket, byte_count: int) -> None:
        if _integer(byte_count, "declared_length") > self.remaining_bytes(ticket):
            self._fail("declared_length_exceeds_remaining")

    def charge_received(self, ticket: RequestTicket, byte_count: int) -> None:
        """Charge before checking limits, even after a late/oversized read."""
        self._ticket(ticket)
        amount = _integer(byte_count, "received_bytes")
        self._received[ticket.bucket] += amount
        self._request_received += amount
        self._changed()
        if (
            self._request_received > self._response_limit
            or self._received[ticket.bucket] > self.limits[ticket.bucket].received_bytes
            or sum(self._received.values()) > self.total_received_limit
        ):
            self._fail("received_byte_limit")
        self._check()

    def finish_request(self, ticket: RequestTicket) -> None:
        """Release the active slot without refunding bytes or transactions."""
        self._ticket(ticket)
        self._request = None
        self._changed()

    def finish_source(self, bucket: str) -> None:
        self._check()
        if bucket != self._active_source or self._request is not None:
            self._fail("source_still_has_active_request")
        self._active_source = None
        self._source_deadline = None
        self._changed()

    def receipt(self) -> dict:
        """Aggregate evidence only; never serialize source names or raw bodies."""
        return {
            "schema_version": 1,
            "scope": "step08-single-session-no-resume",
            "limits": {name: asdict(value) for name, value in self.limits.items()},
            "tranche_bytes": self.total_received_limit,
            "bulk_transaction_limit": self.bulk_transaction_limit,
            "allowed_buckets": sorted(self.allowed_buckets),
            "total_received_bytes": sum(self._received.values()),
            "received_bytes": dict(self._received),
            "transactions": dict(self._transactions),
            "attempted_sources": sorted(self._used),
            "active_source": self._active_source,
            "active_request": asdict(self._request) if self._request else None,
            "active_response_reservation": (
                max(0, self._response_limit - self._request_received)
                if self._request
                else 0
            ),
            "session_deadline_monotonic": self.deadline,
            "stop_reason": self._stop_reason,
            "resume_supported": False,
        }


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    rss_soft_bytes: int = 3 * GIB // 2
    rss_hard_bytes: int = 2 * GIB
    min_free_disk_bytes: int = 10 * GIB
    max_artifact_bytes: int = 2 * GIB
    max_normalized_bytes: int = 100_000_000
    admission_free_memory_fraction: float = 0.25
    stop_free_memory_fraction: float = 0.20
    session_seconds: float = 3600

    def __post_init__(self) -> None:
        for name, ceiling in (
            ("rss_soft_bytes", 3 * GIB // 2),
            ("rss_hard_bytes", 2 * GIB),
            ("max_artifact_bytes", 2 * GIB),
            ("max_normalized_bytes", 100_000_000),
        ):
            if not 1 <= _integer(getattr(self, name), name) <= ceiling:
                raise ResourceStop("resource_limit_exceeds_approval")
        if self.rss_soft_bytes > self.rss_hard_bytes:
            raise ResourceStop("invalid_rss_thresholds")
        if _integer(self.min_free_disk_bytes, "free_disk_limit") < 10 * GIB:
            raise ResourceStop("free_disk_floor_below_approval")
        admission = _finite(self.admission_free_memory_fraction, "admission_fraction")
        stop = _finite(self.stop_free_memory_fraction, "stop_fraction")
        if not 0.25 <= admission <= 1 or not 0.20 <= stop <= admission:
            raise ResourceStop("free_memory_floor_below_approval")
        if not 0 < _finite(self.session_seconds, "session_seconds") <= 3600:
            raise ResourceStop("invalid_session_seconds")


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    aggregate_rss_bytes: int
    free_disk_bytes: int
    artifact_bytes: int
    free_memory_fraction: float
    memory_pressure: bool

    def __post_init__(self) -> None:
        for name in ("aggregate_rss_bytes", "free_disk_bytes", "artifact_bytes"):
            _integer(getattr(self, name), name)
        if not 0 <= _finite(self.free_memory_fraction, "free_memory_fraction") <= 1:
            raise ResourceStop("invalid_memory_measurement")
        if type(self.memory_pressure) is not bool:
            raise ResourceStop("invalid_pressure_measurement")


class ResourceGuard:
    """Check aggregate resources before admission and at safe checkpoints.

    Inline checks cannot interrupt a blocked parser or network call. Use
    ``supervise_command`` around a trusted worker for enforced stop behavior.
    """

    def __init__(
        self,
        *,
        probe: Callable[[], ResourceSnapshot],
        limits: ResourceLimits = ResourceLimits(),
        clock: Callable[[], float] = time.monotonic,
        initial_normalized_bytes: int = 0,
    ) -> None:
        self.limits = limits
        self._probe = probe
        self._clock = clock
        self._last_time = _finite(clock(), "clock")
        self.deadline = self._last_time + limits.session_seconds
        self._admitted = False
        self._stopped: str | None = None
        self.peak_rss_bytes = 0
        self.reserved_artifact_bytes = 0
        # Recovery may retain earlier selections. Their bytes remain charged
        # even when the next run only copies an already validated selection.
        self.normalized_bytes = _integer(
            initial_normalized_bytes, "initial_normalized_bytes"
        )
        if self.normalized_bytes > limits.max_normalized_bytes:
            self._stop("normalized_byte_limit")

    @property
    def admitted(self) -> bool:
        """Whether this same session began; checking again never restarts it."""
        return self._admitted

    def _stop(self, code: str) -> None:
        self._stopped = self._stopped or code
        raise ResourceStop(self._stopped) from None

    def _check(self, *, admission: bool) -> ResourceSnapshot:
        if self._stopped:
            raise ResourceStop(self._stopped)
        now = _finite(self._clock(), "clock")
        if now < self._last_time:
            self._stop("clock_moved_backwards")
        self._last_time = now
        if now >= self.deadline:
            self._stop("session_deadline")
        try:
            snapshot = self._probe()
        except ResourceStop as exc:
            self._stop(exc.code)
        except Exception:
            self._stop("resource_probe_unavailable")
        if not isinstance(snapshot, ResourceSnapshot):
            self._stop("resource_probe_invalid")
        # Probing itself consumes the session window. A slow OS query must
        # not let a worker continue on a measurement taken after its deadline.
        measured_at = _finite(self._clock(), "clock")
        if measured_at < self._last_time:
            self._stop("clock_moved_backwards")
        self._last_time = measured_at
        if measured_at >= self.deadline:
            self._stop("session_deadline")
        self.peak_rss_bytes = max(self.peak_rss_bytes, snapshot.aggregate_rss_bytes)
        if snapshot.aggregate_rss_bytes >= self.limits.rss_hard_bytes:
            self._stop("rss_hard_limit")
        if snapshot.aggregate_rss_bytes >= self.limits.rss_soft_bytes:
            self._stop("rss_soft_limit")
        if snapshot.memory_pressure:
            self._stop("host_memory_pressure")
        floor = (
            self.limits.admission_free_memory_fraction
            if admission
            else self.limits.stop_free_memory_fraction
        )
        if snapshot.free_memory_fraction < floor:
            self._stop("host_free_memory_limit")
        if snapshot.free_disk_bytes < self.limits.min_free_disk_bytes:
            self._stop("free_disk_limit")
        if (
            max(snapshot.artifact_bytes, self.reserved_artifact_bytes)
            > self.limits.max_artifact_bytes
        ):
            self._stop("artifact_byte_limit")
        return snapshot

    def admit(self) -> ResourceSnapshot:
        if self._admitted:
            self._stop("resource_session_already_admitted")
        snapshot = self._check(admission=True)
        self._admitted = True
        return snapshot

    def check(self) -> ResourceSnapshot:
        if not self._admitted:
            raise ResourceStop("resource_session_not_admitted")
        return self._check(admission=False)

    def reserve_artifact(self, byte_count: int, *, normalized: bool = False) -> None:
        """Reserve before writing; failed writes are conservatively not refunded."""
        amount = _integer(byte_count, "artifact_bytes")
        snapshot = self.check()
        total = max(snapshot.artifact_bytes, self.reserved_artifact_bytes) + amount
        if total > self.limits.max_artifact_bytes:
            self._stop("artifact_byte_limit")
        if (
            normalized
            and self.normalized_bytes + amount > self.limits.max_normalized_bytes
        ):
            self._stop("normalized_byte_limit")
        self.reserved_artifact_bytes = total
        if normalized:
            self.normalized_bytes += amount


def _run_probe(command: Sequence[str], *, failure_code: str) -> str:
    """Report the failed OS subprobe without command output or exception text."""
    try:
        return subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise ResourceStop(failure_code) from None


def aggregate_process_rss(process_group_id: int | None, supervisor_pid: int) -> int:
    """Sum the supervisor, owned process group and currently visible descendants.

    Only numeric process fields are inspected. Trusted workers must not detach
    into new sessions; this is not a sandbox for a hostile executable.
    """
    _integer(supervisor_pid, "supervisor_pid", minimum=1)
    if process_group_id is not None:
        _integer(process_group_id, "process_group_id", minimum=1)
    rows: dict[int, tuple[int, int, int]] = {}
    for line in _run_probe(
        ("ps", "-axo", "pid=,ppid=,pgid=,rss="),
        failure_code="rss_probe_unavailable",
    ).splitlines():
        fields = line.split()
        if len(fields) != 4 or any(not value.isdecimal() for value in fields):
            raise ResourceStop("invalid_process_probe")
        pid, parent, group, rss_kib = map(int, fields)
        rows[pid] = (parent, group, rss_kib * 1024)
    if supervisor_pid not in rows:
        raise ResourceStop("supervisor_missing_from_probe")
    owned = {supervisor_pid}
    if process_group_id is not None:
        owned.update(
            pid for pid, (_, group, _) in rows.items() if group == process_group_id
        )
        pending = set(owned) - {supervisor_pid}
        while pending:
            children = {
                pid for pid, (parent, _, _) in rows.items() if parent in pending
            } - owned
            owned.update(children)
            pending = children
    return sum(rows[pid][2] for pid in owned)


def _artifact_size(root: Path, *, required: bool = False) -> int:
    """Measure one explicit root, with at most three complete scan attempts."""
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        if required:
            raise ResourceStop("artifact_root_missing") from None
        return 0
    except OSError:
        raise ResourceStop("artifact_probe_unavailable") from None
    if stat.S_ISLNK(root_info.st_mode):
        raise ResourceStop("artifact_path_symlink")
    if not stat.S_ISDIR(root_info.st_mode):
        raise ResourceStop("artifact_root_not_directory")

    def raise_walk_error(error: OSError) -> None:
        raise error

    # Atomic publishers unlink temporary names after linking the final file.
    # Restart the whole measurement if such a name disappears after listing;
    # never accept a partial sum or retry an HTTP request. Persistent churn,
    # permission errors and unsafe file types still stop the worker.
    for _ in range(3):
        total = 0
        try:
            for base, directories, files in os.walk(
                root, followlinks=False, onerror=raise_walk_error
            ):
                for name in directories + files:
                    info = (Path(base) / name).lstat()
                    if stat.S_ISLNK(info.st_mode) or not (
                        stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
                    ):
                        raise ResourceStop("artifact_path_not_regular")
                    if stat.S_ISREG(info.st_mode):
                        total += info.st_size
            return total
        except FileNotFoundError:
            continue
        except OSError:
            raise ResourceStop("artifact_probe_unavailable") from None
    raise ResourceStop("artifact_snapshot_unstable")


def _host_memory() -> tuple[float, bool]:
    if sys.platform == "darwin":
        output = _run_probe(
            ("memory_pressure", "-Q"),
            failure_code="host_free_memory_probe_unavailable",
        )
        match = re.search(r"System-wide memory free percentage:\s*(\d+)%", output)
        if match is None or not 0 <= int(match[1]) <= 100:
            raise ResourceStop("invalid_host_free_memory_probe")
        pressure = _run_probe(
            ("sysctl", "-n", "kern.memorystatus_vm_pressure_level"),
            failure_code="host_pressure_probe_unavailable",
        ).strip()
        if pressure not in {"1", "2", "4"}:
            raise ResourceStop("invalid_host_pressure_probe")
        return int(match[1]) / 100, pressure != "1"
    if sys.platform.startswith("linux"):
        try:
            memory = Path("/proc/meminfo").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            raise ResourceStop("host_free_memory_probe_unavailable") from None
        values: dict[str, int] = {}
        for line in memory.splitlines():
            fields = line.split()
            if fields and fields[0] in {"MemTotal:", "MemAvailable:"}:
                if (
                    len(fields) != 3
                    or not fields[1].isdecimal()
                    or fields[2] != "kB"
                    or fields[0] in values
                ):
                    raise ResourceStop("invalid_host_free_memory_probe")
                values[fields[0]] = int(fields[1])
        if (
            set(values) != {"MemTotal:", "MemAvailable:"}
            or values["MemTotal:"] <= 0
            or values["MemAvailable:"] > values["MemTotal:"]
        ):
            raise ResourceStop("invalid_host_free_memory_probe")
        try:
            pressure = Path("/proc/pressure/memory").read_text(encoding="ascii")
        except (OSError, UnicodeError):
            raise ResourceStop("host_pressure_probe_unavailable") from None
        levels = re.findall(
            r"^(some|full) avg10=([0-9]+(?:\.[0-9]+)?) ", pressure, re.MULTILINE
        )
        if len(levels) != 2 or {name for name, _ in levels} != {"some", "full"}:
            raise ResourceStop("invalid_host_pressure_probe")
        return values["MemAvailable:"] / values["MemTotal:"], any(
            float(value) > 0 for _, value in levels
        )
    raise ResourceStop("unsupported_resource_platform")


def system_snapshot(
    artifact_root: Path,
    *,
    process_group_id: int | None = None,
    supervisor_pid: int | None = None,
    additional_artifact_roots: Sequence[Path] = (),
) -> ResourceSnapshot:
    """Measure explicit artifact roots together, without scanning their parent.

    The primary root may not exist before admission. Additional retained roots
    must exist; losing access to earlier artifacts cannot reduce the total.
    Overlapping roots count conservatively, including duplicated hard links.
    """
    roots = tuple(
        Path(path).absolute() for path in (artifact_root, *additional_artifact_roots)
    )
    disk_roots = []
    try:
        for root in roots:
            if ".." in root.parts:
                raise ResourceStop("artifact_path_parent_traversal")
            if any(part.is_symlink() for part in (root, *root.parents)):
                raise ResourceStop("artifact_path_symlink")
            disk_roots.append(root if root.exists() else root.parent)
    except OSError:
        raise ResourceStop("artifact_probe_unavailable") from None
    try:
        fraction, pressure = _host_memory()
    except ResourceStop:
        raise
    except Exception:
        raise ResourceStop("host_memory_probe_unavailable") from None
    try:
        rss = aggregate_process_rss(process_group_id, supervisor_pid or os.getpid())
    except ResourceStop:
        raise
    except Exception:
        raise ResourceStop("rss_probe_unavailable") from None
    try:
        free_disk = min(shutil.disk_usage(root).free for root in disk_roots)
    except Exception:
        raise ResourceStop("disk_probe_unavailable") from None
    artifact_bytes = sum(
        _artifact_size(root, required=index > 0) for index, root in enumerate(roots)
    )
    return ResourceSnapshot(
        rss,
        free_disk,
        artifact_bytes,
        fraction,
        pressure,
    )


@dataclass(frozen=True, slots=True)
class SupervisionResult:
    """Sampled peak; interval is the sleep between probes, not a hard latency."""

    returncode: int
    status: str
    stop_reason: str | None
    peak_rss_bytes: int
    elapsed_seconds: float
    sampling_interval_seconds: float
    enforcement: str = "owned-process-group-termination-after-sampled-breach"


def _terminate_group(process: subprocess.Popen) -> None:
    """Terminate only the newly created worker group, including its children."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)


def supervise_command(
    argv: Sequence[str],
    *,
    artifact_root: Path,
    limits: ResourceLimits = ResourceLimits(),
    probe: Callable[[int | None], ResourceSnapshot] | None = None,
    timeout_seconds: float = 3600,
    poll_interval: float = 0.1,
    cwd: Path | None = None,
) -> SupervisionResult:
    """Run a trusted worker privately and stop its process group on any breach.

    The worker gets no stdin and its stdout/stderr are discarded to avoid raw
    source data in developer logs. Do not use this to run daemonizing workers.
    Probe errors, disk/host-memory pressure, soft/hard RSS and elapsed deadlines
    all terminate the group. Short allocations between samples may be missed.
    """
    if os.name != "posix":
        raise ResourceStop("unsupported_supervision_platform")
    if (
        isinstance(argv, (str, bytes))
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise ResourceStop("invalid_worker_command")
    duration = _finite(timeout_seconds, "worker_timeout")
    interval = _finite(poll_interval, "poll_interval")
    if not 0 < duration <= limits.session_seconds or not 0 < interval <= 1:
        raise ResourceStop("invalid_supervision_deadline")
    process: subprocess.Popen | None = None
    chosen_probe = probe or (
        lambda pid: system_snapshot(artifact_root, process_group_id=pid)
    )
    guard = ResourceGuard(
        probe=lambda: chosen_probe(process.pid if process else None), limits=limits
    )
    guard.admit()
    started = time.monotonic()
    deadline = min(guard.deadline, started + duration)
    reason = None
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        while True:
            guard.check()
            if time.monotonic() >= deadline:
                raise ResourceStop("worker_deadline")
            if process.poll() is not None:
                break
            time.sleep(min(interval, max(0, deadline - time.monotonic())))
    except ResourceStop as exc:
        reason = exc.code
    finally:
        if process is not None:
            _terminate_group(process)
    if process is None:
        raise ResourceStop("worker_not_started")
    return SupervisionResult(
        process.returncode,
        "terminated" if reason else "exited",
        reason,
        guard.peak_rss_bytes,
        time.monotonic() - started,
        interval,
    )
