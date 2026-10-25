"""Deterministic acquisition boundary tests; no real HTTP or source data."""

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
from urllib.parse import urlencode, urlsplit, urlunsplit
import zipfile

import pytest

from watchlist.ingest import acquire
from watchlist.ingest.source_registry import (
    ParseResult,
    load_registry,
    registry_from_dict,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "opensanctions_un"
SECOND_SOURCE = "un_consolidated"


@pytest.fixture(autouse=True)
def deny_real_network(monkeypatch):
    """An accidental real DNS lookup or connection is a test failure."""

    def denied(*args, **kwargs):
        raise AssertionError("Acquisition tests must use an injected transport.")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def configuration(*approved: str, **limits: object) -> dict:
    data = json.loads((ROOT / "config/data-sources.json").read_text(encoding="utf-8"))
    for source in data["sources"]:
        source["permission"]["status"] = (
            "approved" if source["source_id"] in approved else "blocked"
        )
        source["permission"]["rationale"] = (
            "Fictional test-only permission decision; transport is injected and offline."
        )
        source["permission"]["terms_urls"] = ["https://example.invalid/fictional-terms"]
        source["permission"]["evidence_paths"] = [
            "tests/fixtures/opensanctions_synthetic.metadata.json"
        ]
    data["limits"].update(limits)
    return data


def source_config(data: dict, source_id: str = SOURCE) -> dict:
    return next(item for item in data["sources"] if item["source_id"] == source_id)


def fictional_publisher_index(config: dict, payload: bytes) -> dict:
    url = source_config(config)["url"]
    return {
        "name": "un_sc_sanctions",
        "version": urlsplit(url).path.split("/")[-2],
        "resources": [
            {
                "name": "entities.ftm.json",
                "url": url,
                "size": len(payload),
                "checksum": hashlib.sha1(payload).hexdigest(),
            }
        ],
    }


def registry_with_evidence(tmp_path, config, filename, payload, source_id=SOURCE):
    source_config(config, source_id)["permission"]["evidence_paths"] = [filename]
    (tmp_path / filename).write_bytes(payload)
    return registry_from_dict(config, project_root=tmp_path)


class ManualClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeResponse:
    """A finite HTTP body with observable reads and deliberately injectable faults."""

    def __init__(
        self,
        body: bytes,
        url: str,
        *,
        headers=None,
        status=200,
        chunk_size=None,
        fail_after=None,
        on_read=None,
        violate_read_bound=False,
        read_error=None,
    ):
        self.body = body
        self.url = url
        self.status = status
        self.headers = {} if headers is None else dict(headers)
        self.chunk_size = chunk_size
        self.fail_after = fail_after
        self.on_read = on_read
        self.violate_read_bound = violate_read_bound
        self.read_error = read_error
        self.position = 0
        self.reads = []
        self.closed = False

    def read(self, size, *, timeout):
        assert type(size) is int and size > 0
        assert timeout > 0
        self.reads.append((size, timeout))
        if self.on_read is not None:
            self.on_read()
        if self.fail_after is not None and self.position >= self.fail_after:
            raise self.read_error or OSError("Fictional interrupted response.")
        amount = len(self.body) if self.violate_read_bound else size
        if self.chunk_size is not None:
            amount = min(amount, self.chunk_size)
        result = self.body[self.position : self.position + amount]
        self.position += len(result)
        return result

    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self, *outcomes, on_open=None):
        self.outcomes = list(outcomes)
        self.calls = []
        self.on_open = on_open

    def open(self, url, *, timeout):
        assert timeout > 0
        self.calls.append((url, timeout))
        if self.on_open is not None:
            self.on_open()
        if not self.outcomes:
            raise AssertionError("Unexpected additional HTTP request.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RecordingParser:
    def __init__(self, *, failure=False):
        self.calls = []
        self.failure = failure

    def __call__(self, payload, *, context):
        self.calls.append((payload, context))
        if self.failure:
            raise ValueError("Fictional malformed source payload.")
        return ParseResult(
            records=(),
            input_records=0,
            excluded_person_records=0,
            excluded_other_records=0,
            excluded_by_limit=0,
            parser_version="fictional-transport-test-v1",
            input_sha256=hashlib.sha256(payload).hexdigest(),
            source_version=None,
            source_version_field=None,
        )


def run_fake(tmp_path, body=b"fictional payload", *, headers=None, **limits):
    limits.setdefault("max_attempts", 1)
    config = configuration(SOURCE, **limits)
    registry = registry_from_dict(config)
    response = FakeResponse(body, source_config(config)["url"], headers=headers)
    transport, parser = FakeTransport(response), RecordingParser()
    output = tmp_path / "new-acquisition"
    result = acquire.fetch_profile(
        registry,
        output,
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    return result, output, response, transport, parser


def receipt_for(result: dict, source_id: str = SOURCE) -> dict:
    return next(item for item in result["sources"] if item["source_id"] == source_id)


def test_preflight_is_offline_and_does_not_create_outputs(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = acquire.preflight(registry_from_dict(configuration(SOURCE)))
    assert isinstance(result, dict)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "source_ids", [["unknown-source"], [SOURCE, SOURCE], [SECOND_SOURCE]]
)
def test_unauthorized_unknown_or_duplicate_requests_fail_before_effects(
    tmp_path, source_ids
) -> None:
    transport = FakeTransport()
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry_from_dict(configuration(SOURCE)),
            output,
            source_ids=source_ids,
            transport=transport,
        )
    assert transport.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("status", ["blocked", "pending"])
def test_permission_status_cannot_be_overridden_by_request(tmp_path, status) -> None:
    config = configuration()
    source_config(config)["permission"]["status"] = status
    transport = FakeTransport()
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry_from_dict(config),
            tmp_path / "forbidden",
            source_ids=[SOURCE],
            transport=transport,
        )
    assert transport.calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://data.opensanctions.org/datasets/latest/un_sc_sanctions/entities.ftm.json",
        "https://unapproved.example.invalid/export.json",
        "https://data.opensanctions.org.attacker.invalid/export.json",
        "https://127.0.0.1/export.json",
        "https://[::1]/export.json",
        "file:///tmp/fictional-export.json",
        "data:application/json,[]",
        "https://data.opensanctions.org:8443/export.json",
    ],
)
def test_registry_rejects_unapproved_network_destinations(url: str) -> None:
    config = configuration(SOURCE)
    source_config(config)["url"] = url
    with pytest.raises(ValueError):
        registry_from_dict(config)


@pytest.mark.parametrize("location", ["url", "allowed_redirects"])
def test_registry_rejects_url_userinfo_and_fragments(location) -> None:
    config = configuration(SOURCE)
    original = urlsplit(source_config(config)["url"])
    for unsafe in (
        urlunsplit(original._replace(netloc="fictional:invalid@" + original.netloc)),
        urlunsplit(original._replace(fragment="fictional-fragment")),
    ):
        candidate = deepcopy(config)
        source_config(candidate)[location] = unsafe if location == "url" else [unsafe]
        with pytest.raises(ValueError):
            registry_from_dict(candidate)


@pytest.mark.parametrize(
    "change", ["duplicate-source", "missing-source", "wrong-parser", "wrong-role"]
)
def test_registry_does_not_guess_unknown_or_inconsistent_contracts(change) -> None:
    config = configuration(SOURCE)
    if change == "duplicate-source":
        config["sources"].append(deepcopy(config["sources"][0]))
    elif change == "missing-source":
        config["sources"].pop()
    elif change == "wrong-parser":
        source_config(config)["parser"] = "un"
    else:
        source_config(config)["role"] = "supplemental_unlabelled"
    with pytest.raises(ValueError):
        registry_from_dict(config)


@pytest.mark.parametrize(
    "suffix",
    [
        ',"schema_version":1}',
        ',"extra":{"x":1,"x":2}}',
        ',"extra":NaN}',
        ',"extra":Infinity}',
        ',"extra":-Infinity}',
        ',"extra":1e999}',
    ],
)
def test_registry_loader_rejects_duplicate_json_and_nonfinite_values(
    tmp_path, suffix
) -> None:
    payload = json.dumps(configuration(SOURCE))[:-1] + suffix
    path = tmp_path / "fictional-registry.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        load_registry(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_source_bytes", 10_000_001),
        ("max_eu_source_bytes", 32_000_001),
        ("max_eu_source_bytes", True),
        ("max_eu_source_bytes", 0),
        ("max_total_bytes", 50_000_001),
        ("max_groups", 201),
        ("max_attempts", 3),
        ("max_redirects", 4),
        ("request_timeout_seconds", 31),
        ("source_deadline_seconds", 121),
        ("eu_request_timeout_seconds", 181),
        ("eu_source_deadline_seconds", 241),
        ("eu_request_timeout_seconds", True),
        ("eu_source_deadline_seconds", True),
        ("eu_request_timeout_seconds", 0),
        ("eu_source_deadline_seconds", 0),
        ("eu_request_timeout_seconds", 1.5),
        ("eu_source_deadline_seconds", float("inf")),
        ("wikidata_request_timeout_seconds", 91),
        ("wikidata_request_timeout_seconds", True),
        ("wikidata_request_timeout_seconds", 0),
        ("wikidata_request_timeout_seconds", 1.5),
        ("max_source_bytes", True),
        ("max_source_bytes", 0),
        ("max_total_bytes", -1),
        ("max_groups", 1.5),
        ("max_attempts", 0),
        ("request_timeout_seconds", float("inf")),
        ("source_deadline_seconds", float("nan")),
    ],
)
def test_registry_cannot_expand_approved_resource_limits(field, value) -> None:
    with pytest.raises(ValueError):
        registry_from_dict(configuration(SOURCE, **{field: value}))


def test_source_specific_retry_limits_preserve_unamended_limits_in_the_offline_plan():
    config = configuration(
        "eu_consolidated",
        max_eu_source_bytes=32_000_000,
        eu_request_timeout_seconds=180,
        eu_source_deadline_seconds=240,
        wikidata_request_timeout_seconds=90,
    )
    plan = acquire.preflight(registry_from_dict(config))
    assert plan["limits"]["max_total_bytes"] == 50_000_000
    assert plan["limits"]["max_groups"] == 200
    for candidate in plan["candidate_sources"]:
        eu = candidate["source_id"] == "eu_consolidated"
        assert candidate["max_response_body_bytes"] == (
            32_000_000 if eu else 10_000_000
        )
        request_timeout = {"eu_consolidated": 180, "wikidata_orgs": 90}.get(
            candidate["source_id"], 30
        )
        assert candidate["request_timeout_seconds"] == request_timeout
        assert candidate["source_deadline_seconds"] == (240 if eu else 120)


def test_omitted_wikidata_request_override_preserves_the_original_limit_in_preflight():
    config = configuration("wikidata_orgs")
    config["limits"].pop("wikidata_request_timeout_seconds", None)
    plan = acquire.preflight(registry_from_dict(config))
    wikidata = next(
        item
        for item in plan["candidate_sources"]
        if item["source_id"] == "wikidata_orgs"
    )
    assert wikidata["request_timeout_seconds"] == 30
    assert wikidata["source_deadline_seconds"] == 120
    assert wikidata["max_response_body_bytes"] == 10_000_000


@pytest.mark.parametrize(
    "kind",
    ["existing-file", "existing-directory", "symlink", "parent-symlink", "traversal"],
)
def test_unsafe_or_existing_destinations_fail_before_http(tmp_path, kind) -> None:
    output = tmp_path / "output"
    sentinel = tmp_path / "preserved"
    sentinel.write_bytes(b"fictional original bytes")
    if kind == "existing-file":
        output.write_bytes(b"fictional original output")
    elif kind == "existing-directory":
        output.mkdir()
    elif kind == "symlink":
        output.symlink_to(sentinel)
    elif kind == "parent-symlink":
        link = tmp_path / "linked"
        link.symlink_to(tmp_path, target_is_directory=True)
        output = link / "output"
    else:
        parent = tmp_path / "parent"
        parent.mkdir()
        output = parent / ".." / "output"
    before = {
        p.name: (p.is_symlink(), p.read_bytes() if p.is_file() else None)
        for p in tmp_path.iterdir()
    }
    transport = FakeTransport()
    with pytest.raises((ValueError, OSError)):
        acquire.fetch_profile(
            registry_from_dict(configuration(SOURCE)),
            output,
            source_ids=[SOURCE],
            transport=transport,
            parsers={SOURCE: RecordingParser()},
        )
    after = {
        p.name: (p.is_symlink(), p.read_bytes() if p.is_file() else None)
        for p in tmp_path.iterdir()
    }
    assert before == after
    assert transport.calls == []


def test_success_passes_exact_bytes_to_parser_and_records_an_immutable_receipt(
    tmp_path,
) -> None:
    body = b"fictional complete body"
    result, output, response, transport, parser = run_fake(
        tmp_path, body, headers={"Content-Length": str(len(body))}
    )
    assert result["status"] == "complete"
    assert parser.calls[0][0] == body
    assert parser.calls[0][1].source_id == SOURCE
    assert response.closed
    assert len(transport.calls) == 1
    assert (output / "manifest.json").is_file()
    assert (output / f"{SOURCE}.receipt.json").is_file()
    assert (output / f"{SOURCE}.jsonl").is_file()
    receipt = receipt_for(result)
    assert receipt["bytes_received"] == result["total_bytes_received"] == len(body)
    assert receipt["complete_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert (
        receipt["normalized_selection_sha256"]
        == hashlib.sha256((output / f"{SOURCE}.jsonl").read_bytes()).hexdigest()
    )
    assert receipt["raw_retained"] is result["raw_retained"] is False
    assert json.loads((output / f"{SOURCE}.receipt.json").read_text()) == json.loads(
        json.dumps(receipt)
    )
    assert json.loads((output / "manifest.json").read_text()) == json.loads(
        json.dumps(result)
    )
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises((ValueError, OSError)):
        acquire.fetch_profile(
            registry_from_dict(configuration(SOURCE)),
            output,
            source_ids=[SOURCE],
            transport=FakeTransport(),
            parsers={SOURCE: RecordingParser()},
        )
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before


@pytest.mark.parametrize("headers", [None, {"Content-Length": "4"}])
def test_exact_byte_cap_never_silently_certifies_unknown_length(
    tmp_path, headers
) -> None:
    result, output, response, _, parser = run_fake(
        tmp_path,
        b"abcd",
        headers=headers,
        max_source_bytes=4,
        max_total_bytes=4,
    )
    if headers is None:
        assert result["status"] == "failed"
        assert parser.calls == []
        assert not (output / f"{SOURCE}.jsonl").exists()
    else:
        assert result["status"] == "complete"
    assert response.position == 4
    assert response.closed


@pytest.mark.parametrize(
    "source_id", [SOURCE, SECOND_SOURCE, "ofac_sdn", "wikidata_orgs", "eu_consolidated"]
)
@pytest.mark.parametrize("body_size", [4, 8, 9])
def test_eu_allowance_does_not_expand_another_sources_transfer_or_parser_limit(
    tmp_path, source_id, body_size
) -> None:
    config = configuration(
        source_id,
        max_source_bytes=4,
        max_eu_source_bytes=8,
        max_total_bytes=12,
        max_attempts=1,
    )
    body = b"x" * body_size
    response = FakeResponse(
        body,
        source_config(config, source_id)["url"],
        headers={"Content-Length": str(body_size)},
    )
    parser = RecordingParser()
    output = tmp_path / "source-specific-bound"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[source_id],
        transport=FakeTransport(response),
        parsers={source_id: parser},
        clock=ManualClock(),
    )
    expected_limit = 8 if source_id == "eu_consolidated" else 4
    if body_size <= expected_limit:
        assert result["status"] == "complete"
        assert parser.calls[0][0] == body
        assert parser.calls[0][1].max_input_bytes == expected_limit
    else:
        assert result["status"] == "failed"
        assert parser.calls == [] and response.position == 0
        assert not (output / f"{source_id}.jsonl").exists()
    assert response.closed


def test_eu_allowance_still_obeys_the_shared_profile_budget(tmp_path) -> None:
    source_id = "eu_consolidated"
    config = configuration(
        source_id, max_eu_source_bytes=8, max_total_bytes=6, max_attempts=1
    )
    response = FakeResponse(b"abcdefgh", source_config(config, source_id)["url"])
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "shared-budget",
        source_ids=[source_id],
        transport=FakeTransport(response),
        parsers={source_id: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert result["total_bytes_received"] == response.position == 6
    assert parser.calls == [] and response.closed


@pytest.mark.parametrize(
    "length",
    ["100", "-1", "invalid", "2", "8", pytest.param("9" * 5000, id="overlong-decimal")],
)
def test_lying_or_malformed_content_length_never_publishes_partial_data(
    tmp_path, length
) -> None:
    result, output, response, _, parser = run_fake(
        tmp_path,
        b"abcd",
        headers={"Content-Length": length},
        max_source_bytes=16,
        max_total_bytes=16,
    )
    assert result["status"] == "failed"
    assert parser.calls == []
    assert not (output / f"{SOURCE}.jsonl").exists()
    assert response.closed


def test_unknown_length_stream_larger_than_budget_is_bounded_and_incomplete(
    tmp_path,
) -> None:
    result, output, response, _, parser = run_fake(
        tmp_path,
        b"a" * 32,
        max_source_bytes=8,
        max_total_bytes=8,
    )
    assert result["status"] == "failed"
    assert response.position <= 8
    assert parser.calls == []
    assert not (output / f"{SOURCE}.jsonl").exists()
    receipt = receipt_for(result)
    assert (
        receipt["bytes_received"] == result["total_bytes_received"] == response.position
    )
    assert receipt["complete_body_sha256"] is None
    assert receipt["normalized_selection_sha256"] is None
    assert receipt["records_path"] is None


def test_unapproved_redirect_is_rejected_before_following_or_reading(tmp_path) -> None:
    config = configuration(SOURCE)
    response = FakeResponse(
        b"never read redirected payload",
        source_config(config)["url"],
        status=302,
        headers={"Location": "https://unapproved.example.invalid/fictional"},
    )
    transport, parser = FakeTransport(response), RecordingParser()
    output = tmp_path / "redirect-attempt"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert len(transport.calls) == 1
    assert response.position == 0 and response.closed
    assert parser.calls == []
    assert not (output / f"{SOURCE}.jsonl").exists()


def test_transport_cannot_silently_follow_a_redirect(tmp_path) -> None:
    config = configuration(SOURCE)
    response = FakeResponse(
        b"fictional", "https://unapproved.example.invalid/fictional"
    )
    transport, parser = FakeTransport(response), RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "followed-redirect",
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert response.position == 0 and response.closed
    assert parser.calls == []


@pytest.mark.parametrize("total_cap,expected_status", [(12, "complete"), (8, "failed")])
def test_failed_attempt_bytes_stay_charged_against_retry_budget(
    tmp_path, total_cap, expected_status
) -> None:
    body = b"abcdefgh"
    config = configuration(
        SOURCE,
        max_source_bytes=12,
        max_total_bytes=total_cap,
        max_attempts=2,
    )
    url = source_config(config)["url"]
    first = FakeResponse(
        body, url, headers={"Content-Length": "8"}, chunk_size=4, fail_after=4
    )
    second = FakeResponse(body, url, headers={"Content-Length": "8"})
    transport, parser = FakeTransport(first, second), RecordingParser()
    output = tmp_path / "retry"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    receipt = receipt_for(result)
    assert result["status"] == expected_status
    assert len(transport.calls) == 2
    assert (
        receipt["bytes_received"]
        == result["total_bytes_received"]
        == first.position + second.position
    )
    assert receipt["bytes_received"] <= total_cap
    assert len(receipt["attempts"]) == 2
    assert receipt["attempts"][0]["bytes_received"] == 4
    assert (
        receipt["attempts"][0]["partial_body_sha256"]
        == hashlib.sha256(body[:4]).hexdigest()
    )
    assert first.closed and second.closed
    if expected_status == "complete":
        assert receipt["bytes_received"] == 12
        assert parser.calls[0][0] == body
        assert receipt["complete_body_sha256"] == hashlib.sha256(body).hexdigest()
    else:
        assert parser.calls == []
        assert receipt["complete_body_sha256"] is None
        assert not (output / f"{SOURCE}.jsonl").exists()


@pytest.mark.parametrize("source_id", [SOURCE, "eu_consolidated"])
def test_source_cap_is_cumulative_even_when_profile_budget_is_larger(
    tmp_path, source_id
) -> None:
    config = configuration(
        source_id,
        max_source_bytes=8,
        max_eu_source_bytes=8,
        max_total_bytes=32,
        max_attempts=2,
    )
    url = source_config(config, source_id)["url"]
    first = FakeResponse(
        b"abcdefgh", url, headers={"Content-Length": "8"}, chunk_size=4, fail_after=4
    )
    second = FakeResponse(b"abcdefgh", url, headers={"Content-Length": "8"})
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "source-cap",
        source_ids=[source_id],
        transport=FakeTransport(first, second),
        parsers={source_id: RecordingParser()},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert result["total_bytes_received"] == first.position + second.position <= 8


def test_profile_budget_covers_all_sources_and_keeps_previous_success(tmp_path) -> None:
    config = configuration(
        SOURCE, SECOND_SOURCE, max_source_bytes=8, max_total_bytes=7, max_attempts=1
    )
    first = FakeResponse(
        b"abcd", source_config(config)["url"], headers={"Content-Length": "4"}
    )
    second = FakeResponse(
        b"efgh",
        source_config(config, SECOND_SOURCE)["url"],
        headers={"Content-Length": "4"},
    )
    output = tmp_path / "partial-profile"
    parsers = {SOURCE: RecordingParser(), SECOND_SOURCE: RecordingParser()}
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE, SECOND_SOURCE],
        transport=FakeTransport(first, second),
        parsers=parsers,
        clock=ManualClock(),
    )
    assert result["status"] == "partial"
    assert receipt_for(result)["status"] == "success"
    assert receipt_for(result, SECOND_SOURCE)["status"] == "failed"
    assert result["total_bytes_received"] == first.position + second.position <= 7
    assert (output / f"{SOURCE}.jsonl").exists()
    assert not (output / f"{SECOND_SOURCE}.jsonl").exists()
    assert parsers[SECOND_SOURCE].calls == []


@pytest.mark.parametrize("point", ["open", "read", "parse"])
def test_source_deadline_prevents_success_after_slow_operation(tmp_path, point) -> None:
    config = configuration(
        SOURCE,
        request_timeout_seconds=1,
        source_deadline_seconds=2,
        max_attempts=1,
    )
    clock = ManualClock()

    def advance():
        clock.advance(3)

    response = FakeResponse(
        b"abcd",
        source_config(config)["url"],
        headers={"Content-Length": "4"},
        on_read=advance if point == "read" else None,
    )
    transport = FakeTransport(response, on_open=advance if point == "open" else None)
    parser = RecordingParser()

    def timed_parser(payload, *, context):
        result = parser(payload, context=context)
        if point == "parse":
            advance()
        return result

    output = tmp_path / "deadline"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: timed_parser},
        clock=clock,
    )
    assert result["status"] == "failed"
    assert response.closed
    assert all(timeout <= 1 for _, timeout in transport.calls + response.reads)
    assert not (output / f"{SOURCE}.jsonl").exists()
    assert receipt_for(result)["records_path"] is None
    if point == "open":
        assert response.position == 0
    if point != "parse":
        assert parser.calls == []


@pytest.mark.parametrize(
    "source_id", [SOURCE, SECOND_SOURCE, "ofac_sdn", "wikidata_orgs", "eu_consolidated"]
)
@pytest.mark.parametrize("elapsed", [119, 120, 239, 240])
def test_source_specific_request_and_source_deadlines_remain_hard_bounds(
    tmp_path, source_id, elapsed
):
    config = configuration(
        source_id,
        max_eu_source_bytes=32_000_000,
        eu_request_timeout_seconds=180,
        eu_source_deadline_seconds=240,
        wikidata_request_timeout_seconds=90,
        max_attempts=1,
    )
    clock = ManualClock()
    response = FakeResponse(
        b"abcd",
        source_config(config, source_id)["url"],
        headers={"Content-Length": "4"},
    )
    transport, parser = FakeTransport(response), RecordingParser()

    def timed_parser(payload, *, context):
        parsed = parser(payload, context=context)
        clock.advance(elapsed)
        return parsed

    output = tmp_path / "source-specific-timeouts"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: timed_parser},
        clock=clock,
    )
    eu = source_id == "eu_consolidated"
    request_timeout = {"eu_consolidated": 180, "wikidata_orgs": 90}.get(source_id, 30)
    source_deadline = 240 if eu else 120
    receipt = receipt_for(result, source_id)
    assert receipt["request_timeout_seconds"] == request_timeout
    assert receipt["source_deadline_seconds"] == source_deadline
    assert receipt["max_response_body_bytes"] == (32_000_000 if eu else 10_000_000)
    assert transport.calls[0][1] == request_timeout
    assert all(timeout <= request_timeout for _, timeout in response.reads)
    assert parser.calls[0][1].max_groups == 200
    assert (
        response.closed
        and receipt["complete_body_sha256"] == hashlib.sha256(b"abcd").hexdigest()
    )
    if elapsed < source_deadline:
        assert result["status"] == "complete"
        assert (output / f"{source_id}.jsonl").is_file()
    else:
        assert result["status"] == "failed"
        assert receipt["error_code"] == "deadline_exceeded"
        assert receipt["records_path"] is receipt["normalized_selection_sha256"] is None
        assert not (output / f"{source_id}.jsonl").exists()


@pytest.mark.parametrize("elapsed", [10, 11])
def test_eu_time_allowances_can_still_be_reduced_for_a_bounded_run(tmp_path, elapsed):
    source_id = "eu_consolidated"
    config = configuration(
        source_id,
        request_timeout_seconds=3,
        source_deadline_seconds=5,
        eu_request_timeout_seconds=7,
        eu_source_deadline_seconds=11,
        max_attempts=1,
    )
    clock = ManualClock()
    response = FakeResponse(
        b"abcd",
        source_config(config, source_id)["url"],
        headers={"Content-Length": "4"},
    )
    transport, parser = FakeTransport(response), RecordingParser()

    def timed_parser(payload, *, context):
        parsed = parser(payload, context=context)
        clock.advance(elapsed)
        return parsed

    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "reduced-eu-time",
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: timed_parser},
        clock=clock,
    )
    assert transport.calls[0][1] == 7
    assert result["status"] == ("complete" if elapsed < 11 else "failed")
    assert receipt_for(result, source_id)["source_deadline_seconds"] == 11


@pytest.mark.parametrize("second_elapsed", [60, 70])
def test_eu_retries_share_one_source_deadline_and_shrink_the_next_request_timeout(
    tmp_path, second_elapsed
):
    source_id = "eu_consolidated"
    config = configuration(
        source_id,
        eu_request_timeout_seconds=180,
        eu_source_deadline_seconds=240,
        max_attempts=2,
    )
    clock = ManualClock()
    response = FakeResponse(
        b"abcd",
        source_config(config, source_id)["url"],
        headers={"Content-Length": "4"},
    )

    def advance_on_open():
        clock.advance(170 if len(transport.calls) == 1 else second_elapsed)

    transport = FakeTransport(
        TimeoutError("Fictional first request timed out."),
        response,
        on_open=advance_on_open,
    )
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "cumulative-eu-deadline",
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: parser},
        clock=clock,
    )
    assert [timeout for _, timeout in transport.calls] == [180, 70]
    receipt = receipt_for(result, source_id)
    assert receipt["attempts"][0]["error_code"] == "transport_timeout"
    assert response.closed
    if second_elapsed == 60:
        assert result["status"] == "complete"
        assert parser.calls[0][0] == b"abcd"
        assert clock.value == 230
    else:
        assert result["status"] == "failed"
        assert receipt["error_code"] == "deadline_exceeded"
        assert parser.calls == [] and response.position == 0
        assert clock.value == 240


@pytest.mark.parametrize("second_elapsed", [39, 40])
def test_wikidata_longer_request_does_not_extend_its_cumulative_source_deadline(
    tmp_path, second_elapsed
):
    source_id = "wikidata_orgs"
    config = configuration(
        source_id, wikidata_request_timeout_seconds=90, max_attempts=2
    )
    clock = ManualClock()
    response = FakeResponse(
        b"abcd",
        source_config(config, source_id)["url"],
        headers={"Content-Length": "4"},
    )

    def advance_on_open():
        clock.advance(80 if len(transport.calls) == 1 else second_elapsed)

    transport = FakeTransport(
        TimeoutError("Fictional first request timed out."),
        response,
        on_open=advance_on_open,
    )
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "cumulative-wikidata-deadline",
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: parser},
        clock=clock,
    )
    assert [timeout for _, timeout in transport.calls] == [90, 40]
    receipt = receipt_for(result, source_id)
    assert receipt["attempts"][0]["error_code"] == "transport_timeout"
    assert receipt["source_deadline_seconds"] == 120
    assert receipt["max_response_body_bytes"] == 10_000_000
    assert response.closed
    if second_elapsed == 39:
        assert result["status"] == "complete" and clock.value == 119
        assert parser.calls[0][0] == b"abcd"
    else:
        assert result["status"] == "failed" and clock.value == 120
        assert receipt["error_code"] == "deadline_exceeded"
        assert parser.calls == [] and response.position == 0


@pytest.mark.parametrize("point", ["open", "read"])
@pytest.mark.parametrize("timeout", [False, True])
def test_timeout_diagnostics_distinguish_timeout_from_other_transport_failures(
    tmp_path, point, timeout
):
    source_id = "eu_consolidated"
    config = configuration(
        source_id,
        eu_request_timeout_seconds=180,
        eu_source_deadline_seconds=240,
        max_attempts=1,
    )
    private_message = "fictional exception detail must not enter the receipt"
    fault = (TimeoutError if timeout else OSError)(private_message)
    response = FakeResponse(
        b"abcd",
        source_config(config, source_id)["url"],
        headers={"Content-Length": "4"},
        chunk_size=2,
        fail_after=2,
        read_error=fault,
    )
    transport = FakeTransport(fault if point == "open" else response)
    parser = RecordingParser()
    output = tmp_path / "diagnostic"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: parser},
        clock=ManualClock(),
    )
    receipt = receipt_for(result, source_id)
    expected = "transport_timeout" if timeout else "transport_failure"
    assert result["status"] == "failed" and receipt["error_code"] == expected
    assert receipt["attempts"][0]["error_code"] == expected
    assert receipt["bytes_received"] == (0 if point == "open" else 2)
    assert (
        receipt["attempts"][0]["partial_body_sha256"]
        == hashlib.sha256(b"" if point == "open" else b"ab").hexdigest()
    )
    assert receipt["request_timeout_seconds"] == 180
    assert receipt["source_deadline_seconds"] == 240
    if point == "open":
        assert "http_status" not in receipt["attempts"][0]
    else:
        assert receipt["attempts"][0]["http_status"] == 200
    assert parser.calls == [] and receipt["complete_body_sha256"] is None
    assert private_message not in (output / f"{source_id}.receipt.json").read_text()


def test_parser_failure_keeps_transfer_evidence_but_no_publishable_selection(
    tmp_path,
) -> None:
    body = b"fictional malformed parser input"
    config = configuration(SOURCE)
    response = FakeResponse(
        body, source_config(config)["url"], headers={"Content-Length": str(len(body))}
    )
    output = tmp_path / "parser-failure"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE],
        transport=FakeTransport(response),
        parsers={SOURCE: RecordingParser(failure=True)},
        clock=ManualClock(),
    )
    receipt = receipt_for(result)
    assert result["status"] == "failed"
    assert receipt["bytes_received"] == len(body)
    assert receipt["complete_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert receipt["normalized_selection_sha256"] is receipt["records_path"] is None
    assert not (output / f"{SOURCE}.jsonl").exists()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_http_error_bodies_are_not_parsed_or_retained(tmp_path, status) -> None:
    config = configuration(SOURCE, max_attempts=1)
    response = FakeResponse(
        b"fictional server error", source_config(config)["url"], status=status
    )
    parser = RecordingParser()
    output = tmp_path / "http-error"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[SOURCE],
        transport=FakeTransport(response),
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert receipt_for(result)["attempts"][0]["http_status"] == status
    assert response.position == 0 and response.closed
    assert parser.calls == []
    assert not (output / f"{SOURCE}.jsonl").exists()


@pytest.mark.parametrize(
    "status,next_status,requests,expected_status",
    [
        (429, 200, 1, "failed"),
        (500, 200, 1, "failed"),
        (503, 200, 2, "complete"),
        (503, 503, 2, "failed"),
    ],
)
def test_http_status_receipts_preserve_the_existing_bounded_retry_policy(
    tmp_path, status, next_status, requests, expected_status
):
    source_id = "wikidata_orgs"
    config = configuration(source_id, max_attempts=2)
    url = source_config(config, source_id)["url"]
    unretained = "fictional HTTP error metadata must stay unretained"
    first = FakeResponse(
        unretained.encode(),
        url,
        status=status,
        headers={"X-Fictional-Diagnostic": unretained, "Retry-After": "999"},
    )
    second = FakeResponse(
        b"abcd", url, status=next_status, headers={"Content-Length": "4"}
    )
    transport, parser = FakeTransport(first, second), RecordingParser()
    output = tmp_path / "safe-http-status"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[source_id],
        transport=transport,
        parsers={source_id: parser},
        clock=ManualClock(),
    )
    assert result["status"] == expected_status
    assert len(transport.calls) == requests
    attempts = receipt_for(result, source_id)["attempts"]
    assert [attempt["http_status"] for attempt in attempts] == (
        [status, next_status] if requests == 2 else [status]
    )
    assert first.closed and first.position == 0
    if expected_status == "complete":
        assert parser.calls[0][0] == b"abcd"
        assert result["total_bytes_received"] == 4
    else:
        assert parser.calls == [] and result["total_bytes_received"] == 0
        assert not (output / f"{source_id}.jsonl").exists()
    if requests == 2:
        assert second.closed
    saved = (output / f"{source_id}.receipt.json").read_text()
    assert unretained not in saved and "X-Fictional-Diagnostic" not in saved
    assert "Retry-After" not in saved


@pytest.mark.parametrize("status", [None, True, "200", 200.0, 99, 600])
def test_invalid_transport_status_is_rejected_without_invented_http_evidence(
    tmp_path, status
):
    config = configuration(SOURCE, max_attempts=1)
    response = FakeResponse(
        b"unread fictional bytes", source_config(config)["url"], status=status
    )
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "invalid-http-status",
        source_ids=[SOURCE],
        transport=FakeTransport(response),
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    receipt = receipt_for(result)
    assert result["status"] == "failed"
    assert receipt["error_code"] == "invalid_http_status"
    assert "http_status" not in receipt["attempts"][0]
    assert response.position == 0 and response.closed and parser.calls == []


def test_unrequested_compression_is_rejected_before_body_read(tmp_path) -> None:
    result, _, response, _, parser = run_fake(
        tmp_path,
        b"fictional compressed bytes",
        headers={"Content-Encoding": "gzip"},
    )
    assert result["status"] == "failed"
    assert response.position == 0 and response.closed
    assert parser.calls == []


@pytest.mark.parametrize("allowance", [0, 1])
def test_exact_reviewed_redirect_obeys_count_and_url_policy(
    tmp_path, allowance
) -> None:
    config = configuration(SOURCE, max_redirects=allowance, max_attempts=1)
    url = source_config(config)["url"]
    parts = urlsplit(url)
    segments = parts.path.split("/")
    segments[-2] = "20261025000000-fictional"
    redirected_url = urlunsplit(parts._replace(path="/".join(segments)))
    source_config(config)["allowed_redirects"] = [redirected_url]
    redirect = FakeResponse(
        b"ignored redirect body", url, status=302, headers={"Location": redirected_url}
    )
    final = FakeResponse(b"abcd", redirected_url, headers={"Content-Length": "4"})
    transport, parser = FakeTransport(redirect, final), RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "reviewed-redirect",
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert redirect.position == 0 and redirect.closed
    if allowance:
        assert result["status"] == "complete"
        assert receipt_for(result)["attempts"][0]["http_status"] == 200
        assert [call[0] for call in transport.calls] == [url, redirected_url]
        assert parser.calls[0][0] == b"abcd"
    else:
        assert result["status"] == "failed"
        assert receipt_for(result)["attempts"][0]["http_status"] == 302
        assert len(transport.calls) == 1
        assert parser.calls == []


def fictional_ofac_signed_redirect():
    config = configuration("ofac_sdn", max_attempts=1)
    canonical = (
        "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/"
        "Published/00000000-0000-0000-0000-000000000000/2026-01-01/"
        "11111111-1111-1111-1111-111111111111/SDN_XML.ZIP"
    )
    source_config(config, "ofac_sdn")["allowed_redirects"] = [canonical]
    query = {
        "X-Amz-Expires": "3600",
        "X-Amz-Security-Token": "fictional-public-download-token",
        "response-content-disposition": 'attachment; filename="SDN_XML.ZIP"',
        "response-content-type": "application/zip",
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": "FICTIONALKEY000000/20260101/us-gov-west-1/s3/aws4_request",
        "X-Amz-Date": "20260101T000000Z",
        "X-Amz-SignedHeaders": "host",
        "X-Amz-Signature": "a" * 64,
    }
    return config, canonical, query


def test_ofac_reviewed_signed_redirect_follows_exact_object_and_redacts_saved_query(
    tmp_path,
) -> None:
    config, canonical, query = fictional_ofac_signed_redirect()
    url = source_config(config, "ofac_sdn")["url"]
    signed = canonical + "?" + urlencode(query)
    redirect = FakeResponse(
        b"unread redirect body", url, status=302, headers={"Location": signed}
    )
    final = FakeResponse(b"abcd", signed, headers={"Content-Length": "4"})
    transport, parser = FakeTransport(redirect, final), RecordingParser()
    output = tmp_path / "signed-object"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=["ofac_sdn"],
        transport=transport,
        parsers={"ofac_sdn": parser},
        clock=ManualClock(),
    )
    assert result["status"] == "complete"
    assert [call[0] for call in transport.calls] == [url, signed]
    assert redirect.position == 0 and redirect.closed and final.closed
    receipt = receipt_for(result, "ofac_sdn")
    expected = {
        "url_sha256": hashlib.sha256(signed.encode()).hexdigest(),
        "query_present": True,
        "signing_query_redacted": True,
    }
    assert receipt["redirects"] == [{"url": canonical, **expected}]
    assert receipt["final_url"] == canonical
    assert receipt["final_url_evidence"] == expected
    saved = b"".join(path.read_bytes() for path in output.iterdir())
    for value in (
        query["X-Amz-Security-Token"],
        query["X-Amz-Credential"],
        query["X-Amz-Signature"],
    ):
        assert value.encode() not in saved
        assert value not in json.dumps(result)
    assert b"X-Amz-" not in saved


@pytest.mark.parametrize(
    "change",
    [
        "missing-key",
        "extra-key",
        "duplicate-key",
        "blank-token",
        "long-token",
        "algorithm",
        "signed-headers",
        "expiry-zero",
        "expiry-too-long",
        "expiry-nonascii",
        "signature",
        "invalid-date",
        "credential-date",
        "credential-region",
        "unreviewed-object",
    ],
)
def test_ofac_unreviewed_or_malformed_signed_redirect_fails_before_follow_or_body_read(
    tmp_path, change
) -> None:
    config, canonical, query = fictional_ofac_signed_redirect()
    if change == "missing-key":
        query.pop("X-Amz-Signature")
    elif change == "extra-key":
        query["unreviewed"] = "fictional"
    elif change == "blank-token":
        query["X-Amz-Security-Token"] = ""
    elif change == "long-token":
        query["X-Amz-Security-Token"] = "x" * 8193
    elif change == "algorithm":
        query["X-Amz-Algorithm"] = "fictional-algorithm"
    elif change == "signed-headers":
        query["X-Amz-SignedHeaders"] = "host;authorization"
    elif change.startswith("expiry-"):
        query["X-Amz-Expires"] = {
            "expiry-zero": "0",
            "expiry-too-long": "3601",
            "expiry-nonascii": "١",
        }[change]
    elif change == "signature":
        query["X-Amz-Signature"] = "g" * 64
    elif change == "invalid-date":
        query["X-Amz-Date"] = "20260230T000000Z"
        query["X-Amz-Credential"] = query["X-Amz-Credential"].replace(
            "20260101", "20260230"
        )
    elif change == "credential-date":
        query["X-Amz-Credential"] = query["X-Amz-Credential"].replace(
            "20260101", "20260102"
        )
    elif change == "credential-region":
        query["X-Amz-Credential"] = query["X-Amz-Credential"].replace(
            "us-gov-west-1", "us-east-1"
        )
    elif change == "unreviewed-object":
        canonical = canonical.replace(
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        )
    signed = canonical + "?" + urlencode(query)
    if change == "duplicate-key":
        signed += "&X-Amz-Expires=3600"
    url = source_config(config, "ofac_sdn")["url"]
    response = FakeResponse(
        b"unread redirect body", url, status=302, headers={"Location": signed}
    )
    transport, parser = FakeTransport(response), RecordingParser()
    output = tmp_path / "forbidden-redirect"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=["ofac_sdn"],
        transport=transport,
        parsers={"ofac_sdn": parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert [call[0] for call in transport.calls] == [url]
    assert response.position == 0 and response.closed and parser.calls == []
    assert not (output / "ofac_sdn.jsonl").exists()
    if query.get("X-Amz-Security-Token"):
        assert (
            query["X-Amz-Security-Token"].encode()
            not in (output / "ofac_sdn.receipt.json").read_bytes()
        )


def test_acquisition_outputs_never_change_the_legacy_snapshot_path(tmp_path) -> None:
    legacy = tmp_path / "raw/un_sc_sanctions"
    legacy.mkdir(parents=True)
    originals = {
        legacy / "entities.ftm.json": b"fictional preserved twenty-record input",
        legacy / "index.json": b"fictional preserved metadata",
        tmp_path / "legacy.sqlite": b"fictional preserved database",
    }
    for path, content in originals.items():
        path.write_bytes(content)
    result, output, *_ = run_fake(tmp_path)
    assert result["status"] == "complete"
    assert output != legacy
    assert {path: path.read_bytes() for path in originals} == originals


class FakeWireSocket:
    """Feed a real HTTP parser from bytes while recording the native transport boundary."""

    def __init__(self, wire: bytes, *, on_receive=None, chunk_size=None):
        self.wire = wire
        self.position = 0
        self.timeouts = []
        self.connections = []
        self.sent = []
        self.closed = False
        self.on_receive = on_receive
        self.chunk_size = chunk_size

    def settimeout(self, value):
        assert value > 0
        self.timeouts.append(value)

    def connect(self, address):
        self.connections.append(address)

    def sendall(self, data):
        if self.closed:
            raise OSError("Fictional TLS socket is closed.")
        self.sent.append(data)

    def recv_into(self, buffer):
        if self.closed:
            raise OSError("Fictional TLS socket is closed.")
        amount = len(buffer)
        if self.chunk_size is not None:
            amount = min(amount, self.chunk_size)
        block = self.wire[self.position : self.position + amount]
        buffer[: len(block)] = block
        self.position += len(block)
        if self.on_receive is not None:
            self.on_receive(self.position)
        return len(block)

    def close(self):
        self.closed = True


def wire_transport(
    monkeypatch,
    wire: bytes,
    *,
    addresses=("93.184.216.34",),
    clock=None,
    on_receive=None,
    chunk_size=None,
):
    """Patch DNS/TLS/socket seams, leaving the production HTTP transport intact."""
    raw = FakeWireSocket(wire, on_receive=on_receive, chunk_size=chunk_size)
    observed = {"dns": [], "sockets": [], "sni": [], "contexts": 0}

    def resolve(host, port, *, type):
        observed["dns"].append((host, port, type))
        return [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
            for address in addresses
        ]

    def make_socket(*args):
        observed["sockets"].append(args)
        return raw

    class VerifiedContext:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def wrap_socket(self, sock, *, server_hostname):
            assert self.check_hostname is True
            assert self.verify_mode == ssl.CERT_REQUIRED
            assert sock is raw
            observed["sni"].append(server_hostname)
            return raw

    def default_context():
        observed["contexts"] += 1
        return VerifiedContext()

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", make_socket)
    monkeypatch.setattr(ssl, "create_default_context", default_context)
    if clock is not None:
        monkeypatch.setattr(acquire.time, "monotonic", clock)
    return raw, observed


def run_native_fake(tmp_path, *, source_id=SOURCE, clock=None, **limits):
    limits.setdefault("max_attempts", 1)
    config = configuration(source_id, **limits)
    parser = RecordingParser()
    output = tmp_path / "native-transport"
    result = acquire.fetch_profile(
        registry_from_dict(config),
        output,
        source_ids=[source_id],
        transport=acquire.HTTPTransport(),
        parsers={source_id: parser},
        **({"clock": clock} if clock is not None else {}),
    )
    return result, output, parser


def test_native_transport_pins_public_ip_and_preserves_hostname_tls_and_host_header(
    tmp_path, monkeypatch
) -> None:
    wire = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nabcd"
    raw, observed = wire_transport(monkeypatch, wire)
    monkeypatch.setenv("HTTPS_PROXY", "http://fictional-proxy.invalid:8080")
    monkeypatch.setenv("HTTP_PROXY", "http://fictional-proxy.invalid:8080")
    result, _, parser = run_native_fake(tmp_path)
    assert result["status"] == "complete"
    assert raw.connections == [("93.184.216.34", 443)]
    assert observed["dns"] == [("data.opensanctions.org", 443, socket.SOCK_STREAM)]
    assert observed["sni"] == ["data.opensanctions.org"]
    assert observed["contexts"] == 1
    request = b"".join(raw.sent)
    assert b"Host: data.opensanctions.org\r\n" in request
    assert b"Accept-Encoding: identity\r\n" in request
    assert parser.calls[0][0] == b"abcd"
    assert raw.closed


def test_native_connection_close_header_keeps_body_reader_alive_until_finished(
    tmp_path, monkeypatch
) -> None:
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\n"
    raw, _ = wire_transport(monkeypatch, header + b"abcdefgh")
    result, _, parser = run_native_fake(tmp_path)
    assert result["status"] == "complete"
    assert parser.calls[0][0] == b"abcdefgh"
    assert result["total_bytes_received"] == 8
    assert raw.closed


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.169.254",),
        ("0.0.0.0",),
        ("100.64.0.1",),
        ("192.0.2.1",),
        ("::1",),
        ("fc00::1",),
        ("fe80::1",),
        ("93.184.216.34", "10.0.0.1"),
        (),
    ],
)
def test_native_transport_rejects_any_nonpublic_dns_answer_before_connect(
    tmp_path, monkeypatch, addresses
) -> None:
    raw, observed = wire_transport(monkeypatch, b"", addresses=addresses)
    result, output, parser = run_native_fake(tmp_path)
    assert result["status"] == "failed"
    assert observed["sockets"] == []
    assert raw.connections == [] and observed["sni"] == []
    assert parser.calls == []
    assert not (output / f"{SOURCE}.jsonl").exists()


def test_native_transport_rejects_redirect_before_body_read_or_second_dns(
    tmp_path, monkeypatch
) -> None:
    header = (
        b"HTTP/1.1 302 Found\r\n"
        b"Location: https://unapproved.example.invalid/fictional\r\n"
        b"Content-Length: 8\r\n\r\n"
    )
    raw, observed = wire_transport(monkeypatch, header + b"fiction!")
    result, _, parser = run_native_fake(tmp_path)
    assert result["status"] == "failed"
    assert raw.position == len(header)
    assert len(observed["dns"]) == 1
    assert parser.calls == [] and raw.closed


def test_native_transport_does_not_prefetch_body_bytes_past_the_budget(
    tmp_path, monkeypatch
) -> None:
    header = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n"
    raw, _ = wire_transport(monkeypatch, header + b"a" * 32)
    result, _, parser = run_native_fake(tmp_path, max_source_bytes=8, max_total_bytes=8)
    assert result["status"] == "failed"
    assert raw.position == len(header) + 8
    assert result["total_bytes_received"] == 8
    assert parser.calls == [] and raw.closed


def test_native_transport_rejects_conflicting_length_headers_without_body_read(
    tmp_path, monkeypatch
) -> None:
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nContent-Length: 8\r\n\r\n"
    raw, _ = wire_transport(monkeypatch, header + b"abcdefgh")
    result, _, parser = run_native_fake(tmp_path)
    assert result["status"] == "failed"
    assert raw.position == len(header)
    assert parser.calls == [] and raw.closed


def test_native_transport_incomplete_body_is_never_complete_evidence(
    tmp_path, monkeypatch
) -> None:
    raw, _ = wire_transport(
        monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\nabcd"
    )
    result, output, parser = run_native_fake(tmp_path)
    assert result["status"] == "failed"
    assert result["total_bytes_received"] == 4
    assert receipt_for(result)["complete_body_sha256"] is None
    assert parser.calls == [] and raw.closed
    assert not (output / f"{SOURCE}.jsonl").exists()


@pytest.mark.parametrize("slow_phase", ["headers", "body"])
def test_native_transport_deadline_expires_while_bytes_keep_arriving(
    tmp_path, monkeypatch, slow_phase
) -> None:
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n"
    clock = ManualClock()

    def arrive(position):
        if slow_phase == "headers" or position > len(header):
            clock.advance(0.75)

    raw, _ = wire_transport(
        monkeypatch,
        header + b"abcdefgh",
        clock=clock,
        on_receive=arrive,
        chunk_size=1,
    )
    result, output, parser = run_native_fake(
        tmp_path,
        clock=clock,
        request_timeout_seconds=2,
        source_deadline_seconds=10,
    )
    assert result["status"] == "failed"
    assert all(0 < timeout <= 2 for timeout in raw.timeouts)
    assert raw.position < len(header) + 8
    assert parser.calls == [] and raw.closed
    assert not (output / f"{SOURCE}.jsonl").exists()
    assert receipt_for(result)["complete_body_sha256"] is None


@pytest.mark.parametrize(
    "source_id,seconds_per_byte,success,expected_elapsed",
    [
        (SOURCE, 40, False, 40),
        (SOURCE, 60, False, 60),
        ("eu_consolidated", 40, True, 160),
        ("eu_consolidated", 60, False, 180),
        ("wikidata_orgs", 20, True, 80),
        ("wikidata_orgs", 30, False, 90),
    ],
)
def test_native_source_request_deadlines_are_isolated_and_never_reset_per_read(
    tmp_path, monkeypatch, source_id, seconds_per_byte, success, expected_elapsed
):
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n"
    clock = ManualClock()

    def arrive(position):
        if position > len(header):
            clock.advance(seconds_per_byte)

    raw, _ = wire_transport(
        monkeypatch, header + b"abcd", clock=clock, on_receive=arrive, chunk_size=1
    )
    result, output, parser = run_native_fake(
        tmp_path,
        source_id=source_id,
        clock=clock,
        eu_request_timeout_seconds=180,
        eu_source_deadline_seconds=240,
        wikidata_request_timeout_seconds=90,
    )
    request_timeout = {"eu_consolidated": 180, "wikidata_orgs": 90}.get(source_id, 30)
    assert raw.timeouts[0] == request_timeout
    assert all(0 < timeout <= request_timeout for timeout in raw.timeouts)
    assert raw.closed
    receipt = receipt_for(result, source_id)
    assert clock.value == expected_elapsed
    if success:
        assert result["status"] == "complete"
        assert parser.calls[0][0] == b"abcd"
    else:
        assert result["status"] == "failed"
        assert receipt["error_code"] == "transport_timeout"
        assert receipt["complete_body_sha256"] is None
        assert parser.calls == [] and not (output / f"{source_id}.jsonl").exists()


@pytest.mark.parametrize("point", ["body", "parse"])
def test_keyboard_interrupt_preserves_honest_failure_evidence_and_stops_requests(
    tmp_path, point
) -> None:
    config = configuration(SOURCE, SECOND_SOURCE)
    response = FakeResponse(
        b"abcdefgh",
        source_config(config)["url"],
        headers={"Content-Length": "8"},
        chunk_size=4,
        fail_after=4 if point == "body" else None,
        read_error=KeyboardInterrupt(),
    )
    transport = FakeTransport(response)

    def parser(payload, *, context):
        raise KeyboardInterrupt()

    output = tmp_path / "interrupted-run"
    with pytest.raises(KeyboardInterrupt):
        acquire.fetch_profile(
            registry_from_dict(config),
            output,
            source_ids=[SOURCE, SECOND_SOURCE],
            transport=transport,
            parsers={SOURCE: parser, SECOND_SOURCE: RecordingParser()},
            clock=ManualClock(),
        )
    assert len(transport.calls) == 1 and response.closed
    manifest = json.loads((output / "manifest.json").read_text())
    receipt = json.loads((output / f"{SOURCE}.receipt.json").read_text())
    assert manifest["status"] == receipt["status"] == "failed"
    assert (
        receipt["bytes_received"]
        == manifest["total_bytes_received"]
        == (4 if point == "body" else 8)
    )
    assert receipt["records_path"] is receipt["normalized_selection_sha256"] is None
    assert not (output / f"{SOURCE}.jsonl").exists()
    assert not (output / f"{SECOND_SOURCE}.jsonl").exists()
    if point == "body":
        assert receipt["complete_body_sha256"] is None
        assert (
            receipt["attempts"][0]["partial_body_sha256"]
            == hashlib.sha256(b"abcd").hexdigest()
        )
    else:
        assert (
            receipt["complete_body_sha256"] == hashlib.sha256(b"abcdefgh").hexdigest()
        )


@pytest.mark.parametrize(
    "race",
    ["destination-replaced", "selection-file-created", "selection-symlink-created"],
)
def test_concurrent_output_changes_never_overwrite_another_file(tmp_path, race) -> None:
    config = configuration(SOURCE, max_attempts=1)
    output = tmp_path / "race-output"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / f"{SOURCE}.jsonl"
    sentinel.write_bytes(b"fictional separately owned output")

    def mutate_destination():
        if race == "destination-replaced":
            output.rename(tmp_path / "moved-output")
            output.symlink_to(outside, target_is_directory=True)
        elif race == "selection-file-created":
            (output / f"{SOURCE}.jsonl").write_bytes(b"fictional concurrent selection")
        else:
            (output / f"{SOURCE}.jsonl").symlink_to(sentinel)

    response = FakeResponse(
        b"abcd", source_config(config)["url"], headers={"Content-Length": "4"}
    )
    with pytest.raises((ValueError, OSError)):
        acquire.fetch_profile(
            registry_from_dict(config),
            output,
            source_ids=[SOURCE],
            transport=FakeTransport(response, on_open=mutate_destination),
            parsers={SOURCE: RecordingParser()},
            clock=ManualClock(),
        )
    assert sentinel.read_bytes() == b"fictional separately owned output"
    if race == "selection-file-created":
        assert (
            output / f"{SOURCE}.jsonl"
        ).read_bytes() == b"fictional concurrent selection"
    assert not (output / "manifest.json").exists()
    assert response.closed


def test_permission_evidence_must_exist_before_output_or_http(tmp_path) -> None:
    config = configuration(SOURCE)
    source_config(config)["permission"]["evidence_paths"] = [
        "missing-fictional-permission.txt"
    ]
    transport = FakeTransport()
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry_from_dict(config, project_root=tmp_path),
            tmp_path / "forbidden",
            source_ids=[SOURCE],
            transport=transport,
        )
    assert transport.calls == []
    assert list(tmp_path.iterdir()) == []


def test_publisher_index_binds_complete_bytes_and_keeps_both_checksum_algorithms(
    tmp_path,
) -> None:
    payload = b"fictional publisher-versioned payload"
    config = configuration(SOURCE, max_attempts=1)
    index = fictional_publisher_index(config, payload)
    evidence_bytes = json.dumps(index).encode()
    registry = registry_with_evidence(
        tmp_path, config, "opensanctions-un-index.json", evidence_bytes
    )
    response = FakeResponse(
        payload,
        source_config(config)["url"],
        headers={"Content-Length": str(len(payload))},
    )
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry,
        tmp_path / "publisher-bound",
        source_ids=[SOURCE],
        transport=FakeTransport(response),
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "complete"
    receipt = receipt_for(result)
    snapshot = receipt["publisher_snapshot"]
    assert snapshot["version"] == index["version"]
    assert snapshot["resource_url"] == source_config(config)["url"]
    assert snapshot["resource_bytes"] == len(payload)
    assert snapshot["published_checksum"] == hashlib.sha1(payload).hexdigest()
    assert snapshot["checksum_comparison"] == "sha1"
    assert receipt["publisher_checksum_verified"] is True
    assert receipt["complete_body_sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["source_version"] == index["version"]
    assert receipt["source_version_field"] == "index.json.version"
    assert (
        receipt["permission_evidence"][0]["sha256"]
        == hashlib.sha256(evidence_bytes).hexdigest()
    )
    assert parser.calls[0][0] == payload and response.closed


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "version",
        "url",
        "zero-size",
        "boolean-size",
        "checksum",
        "missing-resource",
        "duplicate-resource",
        "resources-type",
    ],
)
def test_malformed_publisher_binding_fails_before_output_or_http(tmp_path, change):
    config = configuration(SOURCE, max_attempts=1)
    index = fictional_publisher_index(config, b"fictional bytes")
    resource = index["resources"][0]
    if change == "source":
        index["name"] = "fictional-other-source"
    elif change == "version":
        index["version"] = "20260101000000-fictional"
    elif change == "url":
        resource["url"] += "?unreviewed=1"
    elif change == "zero-size":
        resource["size"] = 0
    elif change == "boolean-size":
        resource["size"] = True
    elif change == "checksum":
        resource["checksum"] = "not-a-sha1-checksum"
    elif change == "missing-resource":
        index["resources"] = []
    elif change == "duplicate-resource":
        index["resources"].append(deepcopy(resource))
    else:
        index["resources"] = "not-a-resource-list"
    registry = registry_with_evidence(
        tmp_path, config, "opensanctions-un-index.json", json.dumps(index).encode()
    )
    output = tmp_path / "forbidden"
    transport = FakeTransport()
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry, output, source_ids=[SOURCE], transport=transport
        )
    assert transport.calls == [] and not output.exists()


@pytest.mark.parametrize(
    "change",
    ["duplicate-version", "duplicate-resource-size", "nan", "overflow", "nested"],
)
def test_publisher_index_rejects_ambiguous_or_excessive_json_before_effects(
    tmp_path, change
) -> None:
    config = configuration(SOURCE)
    payload = json.dumps(fictional_publisher_index(config, b"fictional bytes"))
    if change == "duplicate-version":
        payload = payload[:-1] + ',"version":"conflicting-fictional-version"}'
    elif change == "duplicate-resource-size":
        payload = payload.replace('"size": 15', '"size": 15, "size": 16')
    elif change == "nested":
        payload = payload[:-1] + ',"extra":' + "[" * 2000 + "0" + "]" * 2000 + "}"
    else:
        payload = (
            payload[:-1] + ',"extra":' + ("NaN" if change == "nan" else "1e999") + "}"
        )
    registry = registry_with_evidence(
        tmp_path, config, "opensanctions-un-index.json", payload.encode()
    )
    transport = FakeTransport()
    output = tmp_path / "forbidden"
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry, output, source_ids=[SOURCE], transport=transport
        )
    assert transport.calls == [] and not output.exists()


@pytest.mark.parametrize("change", ["size", "checksum"])
def test_download_must_match_the_publisher_snapshot_before_parsing(tmp_path, change):
    body = b"fictional downloaded bytes"
    config = configuration(SOURCE, max_attempts=1)
    index = fictional_publisher_index(config, body)
    if change == "size":
        index["resources"][0]["size"] += 1
    else:
        index["resources"][0]["checksum"] = hashlib.sha1(b"different bytes").hexdigest()
    registry = registry_with_evidence(
        tmp_path, config, "opensanctions-un-index.json", json.dumps(index).encode()
    )
    response = FakeResponse(
        body, source_config(config)["url"], headers={"Content-Length": str(len(body))}
    )
    transport, parser = FakeTransport(response), RecordingParser()
    output = tmp_path / "mismatched-snapshot"
    result = acquire.fetch_profile(
        registry,
        output,
        source_ids=[SOURCE],
        transport=transport,
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    receipt = receipt_for(result)
    assert result["status"] == receipt["status"] == "failed"
    assert receipt["error_code"] == "publisher_snapshot_mismatch"
    assert receipt["complete_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["total_bytes_received"] == len(body)
    assert parser.calls == [] and response.closed and len(transport.calls) == 1
    assert not (output / f"{SOURCE}.jsonl").exists()
    assert receipt["records_path"] is receipt["normalized_selection_sha256"] is None


@pytest.mark.parametrize(
    "outcome",
    ["success", "parser-rejected", "publisher-mismatch", "deadline", "interrupt"],
)
def test_completed_mixed_payload_is_released_before_receipt_or_next_source(
    tmp_path, monkeypatch, outcome
):
    config = configuration(
        SOURCE, SECOND_SOURCE, max_attempts=1, source_deadline_seconds=2
    )
    body = b"fictional first-source mixed payload"
    index = fictional_publisher_index(config, body)
    if outcome == "publisher-mismatch":
        index["resources"][0]["checksum"] = hashlib.sha1(b"other bytes").hexdigest()
    source_config(config, SECOND_SOURCE)["permission"]["evidence_paths"] = [
        "fictional-permission.txt"
    ]
    (tmp_path / "fictional-permission.txt").write_bytes(b"Fictional permission only.")
    registry = registry_with_evidence(
        tmp_path, config, "opensanctions-un-index.json", json.dumps(index).encode()
    )
    released = []

    class TrackedPayload(bytes):
        """Observe lifetime without retaining the transferred bytes in a test log."""

        def __new__(cls, value, source_id):
            instance = super().__new__(cls, value)
            instance.source_id = source_id
            return instance

        def __del__(self):
            released.append(self.source_id)

    original_transfer = acquire._transfer

    def tracked_transfer(*args, **kwargs):
        return TrackedPayload(original_transfer(*args, **kwargs), args[0].source_id)

    original_publish = acquire._PrivateRun.publish
    checked = []

    def checked_publish(run, filename, content):
        if filename in {f"{SOURCE}.receipt.json", "manifest.json"}:
            assert SOURCE in released, "Completed mixed payload is still retained."
            checked.append(filename)
        return original_publish(run, filename, content)

    clock = ManualClock()

    def first_parser(payload, *, context):
        if outcome == "parser-rejected":
            raise ValueError("Fictional parser failure after complete transfer.")
        if outcome == "interrupt":
            raise KeyboardInterrupt
        if outcome == "deadline":
            clock.advance(3)
        return ParseResult(
            records=(),
            input_records=0,
            excluded_person_records=0,
            excluded_other_records=0,
            excluded_by_limit=0,
            parser_version="fictional-lifetime-test-v1",
            input_sha256=hashlib.sha256(payload).hexdigest(),
        )

    first = FakeResponse(
        body, source_config(config)["url"], headers={"Content-Length": str(len(body))}
    )
    second = FakeResponse(
        b"abcd",
        source_config(config, SECOND_SOURCE)["url"],
        headers={"Content-Length": "4"},
    )

    def check_before_next_source():
        if len(transport.calls) > 1:
            assert SOURCE in released, (
                "Previous mixed payload survived into the next request."
            )

    transport = FakeTransport(first, second, on_open=check_before_next_source)
    monkeypatch.setattr(acquire, "_transfer", tracked_transfer)
    monkeypatch.setattr(acquire._PrivateRun, "publish", checked_publish)
    output = tmp_path / "observed-payload-lifetime"
    arguments = {
        "source_ids": [SOURCE, SECOND_SOURCE],
        "transport": transport,
        "parsers": {SOURCE: first_parser, SECOND_SOURCE: RecordingParser()},
        "clock": clock,
    }
    if outcome == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            acquire.fetch_profile(registry, output, **arguments)
        result = json.loads((output / "manifest.json").read_text())
        assert len(transport.calls) == 1
        assert result["status"] == "failed"
    else:
        result = acquire.fetch_profile(registry, output, **arguments)
        assert result["status"] == ("complete" if outcome == "success" else "partial")
        assert len(transport.calls) == 2
    assert checked == [f"{SOURCE}.receipt.json", "manifest.json"]
    assert SOURCE in released and first.closed
    expected_errors = {
        "parser-rejected": "parser_rejected",
        "publisher-mismatch": "publisher_snapshot_mismatch",
        "deadline": "deadline_exceeded",
        "interrupt": "interrupted",
    }
    if outcome != "success":
        assert receipt_for(result)["error_code"] == expected_errors[outcome]


def fictional_ofac_publisher_evidence():
    config, canonical, _ = fictional_ofac_signed_redirect()
    decoded = (ROOT / "tests/fixtures/acquisition/ofac.xml").read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SDN.XML", decoded)
    body = buffer.getvalue()
    metadata = [
        {
            "fileName": "SDN_XML.ZIP",
            "size": len(body),
            "lastUpdated": "2026-01-01T00:00:00Z",
            "downloadLink": urlsplit(canonical).path.lstrip("/"),
        },
        {
            "fileName": "SDN.XML",
            "size": len(decoded),
            "lastUpdated": "2026-01-01T00:00:00Z",
            "hashCodes": json.dumps({"SHA-256": hashlib.sha256(decoded).hexdigest()}),
        },
    ]
    return config, body, decoded, metadata


@pytest.mark.parametrize(
    "change", [None, "archive-size", "decoded-size", "decoded-hash"]
)
def test_ofac_publisher_binding_distinguishes_archive_and_decoded_evidence(
    tmp_path, change
):
    config, body, decoded, metadata = fictional_ofac_publisher_evidence()
    if change == "archive-size":
        metadata[0]["size"] += 1
    elif change == "decoded-size":
        metadata[1]["size"] += 1
    elif change == "decoded-hash":
        metadata[1]["hashCodes"] = json.dumps(
            {"SHA-256": hashlib.sha256(b"other fictional XML").hexdigest()}
        )
    registry = registry_with_evidence(
        tmp_path,
        config,
        "ofac-sdn-metadata-post.json",
        json.dumps(metadata).encode(),
        source_id="ofac_sdn",
    )
    response = FakeResponse(
        body,
        source_config(config, "ofac_sdn")["url"],
        headers={"Content-Length": str(len(body))},
    )
    output = tmp_path / "ofac-publisher-bound"
    result = acquire.fetch_profile(
        registry,
        output,
        source_ids=["ofac_sdn"],
        transport=FakeTransport(response),
        clock=ManualClock(),
    )
    receipt = receipt_for(result, "ofac_sdn")
    assert receipt["complete_body_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["total_bytes_received"] == len(body) and response.closed
    if change is None:
        assert result["status"] == "complete"
        assert receipt["publisher_checksum_verified"] is None
        assert receipt["publisher_decoded_checksum_verified"] is True
        assert (
            receipt["publisher_snapshot"]["publisher_archive_checksum_available"]
            is False
        )
        assert receipt["decoded_sha256"] == hashlib.sha256(decoded).hexdigest()
        assert receipt["decoded_bytes"] == len(decoded)
        assert receipt["container_format"] == "zip"
        assert (output / "ofac_sdn.jsonl").is_file()
    else:
        assert result["status"] == "failed"
        assert receipt["error_code"] == (
            "publisher_snapshot_mismatch"
            if change == "archive-size"
            else "publisher_decoded_snapshot_mismatch"
        )
        assert receipt["records_path"] is receipt["normalized_selection_sha256"] is None
        assert not (output / "ofac_sdn.jsonl").exists()


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-field",
        "duplicate-inner-hash",
        "inner-nan",
        "nested",
        "unreviewed-object",
    ],
)
def test_ofac_publisher_evidence_rejects_ambiguous_json_or_unreviewed_objects_before_effects(
    tmp_path, change
):
    config, _, _, metadata = fictional_ofac_publisher_evidence()
    if change == "duplicate-inner-hash":
        metadata[1]["hashCodes"] = (
            '{"SHA-256":"' + "a" * 64 + '","SHA-256":"' + "b" * 64 + '"}'
        )
    elif change == "inner-nan":
        metadata[1]["hashCodes"] = metadata[1]["hashCodes"][:-1] + ',"extra":NaN}'
    elif change == "unreviewed-object":
        metadata[0]["downloadLink"] = metadata[0]["downloadLink"].replace(
            "11111111", "22222222"
        )
    payload = json.dumps(metadata)
    if change == "duplicate-field":
        payload = payload.replace(
            '"fileName": "SDN.XML"', '"fileName": "SDN.XML", "fileName": "SDN.XML"'
        )
    elif change == "nested":
        payload = payload[:-1] + ',{"extra":' + "[" * 2000 + "0" + "]" * 2000 + "}]"
    registry = registry_with_evidence(
        tmp_path,
        config,
        "ofac-sdn-metadata-post.json",
        payload.encode(),
        source_id="ofac_sdn",
    )
    transport = FakeTransport()
    output = tmp_path / "forbidden-ofac"
    with pytest.raises(ValueError):
        acquire.fetch_profile(
            registry, output, source_ids=["ofac_sdn"], transport=transport
        )
    assert transport.calls == [] and not output.exists()


def test_cli_preflight_uses_explicit_project_root_outside_the_checkout(
    tmp_path, monkeypatch, capsys
) -> None:
    config = configuration(SOURCE)
    source_config(config)["permission"]["evidence_paths"] = ["fictional-permission.txt"]
    evidence = tmp_path / "fictional-permission.txt"
    evidence.write_bytes(b"Fictional test-only permission evidence.")
    registry_path = tmp_path / "fictional-registry.json"
    registry_path.write_text(json.dumps(config))
    other = tmp_path / "other-working-directory"
    other.mkdir()
    monkeypatch.chdir(other)
    assert (
        acquire.main(
            [
                "preflight",
                "--registry",
                str(registry_path),
                "--project-root",
                str(tmp_path),
                "--source",
                SOURCE,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["network_performed"] is False
    assert (
        result["permission_evidence"][SOURCE][0]["sha256"]
        == hashlib.sha256(evidence.read_bytes()).hexdigest()
    )
    assert list(other.iterdir()) == []


def test_wikidata_endpoint_does_not_authorize_an_arbitrary_sparql_query() -> None:
    config = configuration(SOURCE)
    wikidata = source_config(config, "wikidata_orgs")
    parts = urlsplit(wikidata["url"])
    wikidata["url"] = urlunsplit(
        parts._replace(
            query=urlencode(
                {
                    "query": "SELECT * WHERE { ?item ?property ?value } LIMIT 200",
                    "format": "json",
                }
            )
        )
    )
    with pytest.raises(ValueError):
        registry_from_dict(config)


@pytest.mark.parametrize("kind", ["text", "none", "bytearray", "oversized"])
def test_broken_transport_chunks_fail_with_honest_byte_accounting(
    tmp_path, kind
) -> None:
    config = configuration(
        SOURCE, max_source_bytes=8, max_total_bytes=8, max_attempts=1
    )

    class BrokenResponse(FakeResponse):
        def read(self, size, *, timeout):
            if kind == "oversized":
                return b"a" * 12
            return {"text": "fictional", "none": None, "bytearray": bytearray(b"abcd")}[
                kind
            ]

    response = BrokenResponse(b"", source_config(config)["url"])
    parser = RecordingParser()
    result = acquire.fetch_profile(
        registry_from_dict(config),
        tmp_path / "bad-chunk",
        source_ids=[SOURCE],
        transport=FakeTransport(response),
        parsers={SOURCE: parser},
        clock=ManualClock(),
    )
    assert result["status"] == "failed"
    assert parser.calls == [] and response.closed
    assert result["total_bytes_received"] == (12 if kind == "oversized" else 0)
    assert receipt_for(result)["complete_body_sha256"] is None


@pytest.mark.parametrize(
    "chunked_body,expected_bytes,status",
    [
        (b"4\r\nabcd\r\n0\r\n\r\n", 4, "complete"),
        (b"4\r\nabcd\r\n0\r\n", 4, "failed"),
        (b"4\r\nabcdxx0\r\n\r\n", 4, "failed"),
        (b"4\r\nabcd\r\n4\r\nef", 6, "failed"),
        (b"4\r\nabcd\r\nnot-hex\r\n", 4, "failed"),
        (b"-1\r\n", 0, "failed"),
        (b"4\r\nabcd\r\n-1\r\n", 4, "failed"),
    ],
)
def test_native_chunked_framing_distinguishes_complete_and_interrupted_bodies(
    tmp_path, monkeypatch, chunked_body, expected_bytes, status
) -> None:
    header = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    raw, _ = wire_transport(monkeypatch, header + chunked_body)
    result, output, parser = run_native_fake(tmp_path)
    assert result["status"] == status
    assert result["total_bytes_received"] == expected_bytes
    assert raw.closed
    if status == "failed":
        assert parser.calls == []
        assert receipt_for(result)["complete_body_sha256"] is None
        assert not (output / f"{SOURCE}.jsonl").exists()
    else:
        assert parser.calls[0][0] == b"abcd"


def test_native_dns_returning_after_deadline_never_connects(
    tmp_path, monkeypatch
) -> None:
    clock = ManualClock()
    raw, observed = wire_transport(monkeypatch, b"", clock=clock)

    def delayed_resolution(host, port, *, type):
        clock.advance(3)
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(socket, "getaddrinfo", delayed_resolution)
    result, _, parser = run_native_fake(
        tmp_path,
        clock=clock,
        request_timeout_seconds=2,
        source_deadline_seconds=10,
    )
    assert result["status"] == "failed"
    assert raw.connections == [] and observed["sni"] == []
    assert parser.calls == []


def test_native_tls_certificate_failure_closes_socket_without_sending_http(
    tmp_path, monkeypatch
) -> None:
    raw, _ = wire_transport(monkeypatch, b"")

    class RejectCertificate:
        def wrap_socket(self, sock, *, server_hostname):
            raise ssl.SSLCertVerificationError("Fictional certificate rejection.")

    monkeypatch.setattr(ssl, "create_default_context", lambda: RejectCertificate())
    result, _, parser = run_native_fake(tmp_path)
    assert result["status"] == "failed"
    assert raw.closed and raw.sent == []
    assert parser.calls == []


def test_output_creation_race_cannot_adopt_or_chmod_a_preexisting_directory(
    tmp_path, monkeypatch
) -> None:
    output = tmp_path / "new-output"
    preexisting = tmp_path / "separately-owned"
    preexisting.mkdir(mode=0o755)
    preexisting.chmod(0o755)
    sentinel = preexisting / "fictional-sentinel.txt"
    sentinel.write_bytes(b"Fictional existing directory must stay unchanged.")
    original_mode = preexisting.stat().st_mode
    original_mkdir = os.mkdir
    substitutions = []

    def substitute_after_mkdir(path, mode=0o777, *, dir_fd=None):
        original_mkdir(path, mode=mode, dir_fd=dir_fd)
        if dir_fd is not None and not substitutions:
            os.rename(path, "original-new-output", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.rename(preexisting.name, path, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            substitutions.append(path)

    config = configuration(SOURCE)
    response = FakeResponse(
        b"abcd", source_config(config)["url"], headers={"Content-Length": "4"}
    )
    transport = FakeTransport(response)
    monkeypatch.setattr(os, "mkdir", substitute_after_mkdir)
    with pytest.raises((ValueError, OSError)):
        acquire.fetch_profile(
            registry_from_dict(config),
            output,
            source_ids=[SOURCE],
            transport=transport,
            parsers={SOURCE: RecordingParser()},
            clock=ManualClock(),
        )
    assert len(substitutions) == 1
    substituted = tmp_path / substitutions[0]
    assert substituted.stat().st_mode == original_mode
    assert (
        substituted / sentinel.name
    ).read_bytes() == b"Fictional existing directory must stay unchanged."
    assert sorted(path.name for path in substituted.iterdir()) == [sentinel.name]
    assert transport.calls == []
