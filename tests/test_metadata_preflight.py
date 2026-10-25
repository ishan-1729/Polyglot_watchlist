"""Offline fictional transport tests of the approved metadata-only budget."""

from copy import deepcopy
import hashlib
import http.client
import json
import socket

import pytest

from watchlist.ingest import metadata_preflight as metadata


URL = "https://www.wikidata.org/wiki/Wikidata:Data_access"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("fictional test attempted networking")

    routes = set(metadata.REVIEWED_ROUTES)
    routes.update(
        ("wikidata_orgs", URL + (f"?fictional={i}" if i else ""), "GET", "json")
        for i in range(16)
    )
    monkeypatch.setattr(metadata, "REVIEWED_ROUTES", routes)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Response:
    def __init__(
        self,
        body=b'{"fictional":true}',
        *,
        status=200,
        headers=None,
        url=URL,
        error=None,
        clock=None,
    ):
        self.body, self.status, self.url = body, status, url
        self.headers = (
            {"content-type": "application/json"} if headers is None else headers
        )
        self.error, self.clock, self.closed = error, clock, False
        self.position = 0
        self.requests = []

    def read(self, size, *, timeout):
        self.requests.append(size)
        if self.error:
            raise self.error
        if self.clock:
            self.clock.now += 31
        chunk = self.body[self.position : self.position + size]
        self.position += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, url, *, timeout):
        self.calls.append((url, timeout))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def policy(tmp_path, count=1):
    basis = tmp_path / "basis.md"
    basis.write_text("Fictional metadata test approval; no source data. " + URL)
    data = {
        "schema_version": 1,
        "scope": "08B-1-metadata-only",
        "approval": "fictional test only",
        "limits": deepcopy(metadata.LIMITS),
        "endpoints": [
            {
                "id": f"fictional-{i}",
                "source_id": "wikidata_orgs",
                "url": URL + (f"?fictional={i}" if i else ""),
                "method": "GET",
                "kind": "json",
                "purpose": "fictional metadata",
                "basis": "basis.md",
                "basis_sha256": hashlib.sha256(basis.read_bytes()).hexdigest(),
            }
            for i in range(count)
        ],
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(data))
    return path, data


def run(tmp_path, response, **kwargs):
    path, _ = policy(tmp_path)
    transport = Transport([response])
    result = metadata.run_session(
        path, tmp_path / "new", project_root=tmp_path, transport=transport, **kwargs
    )
    return result, transport


def test_success_is_not_permission_or_contract_verification(tmp_path):
    response = Response()
    result, transport = run(tmp_path, response)
    assert result["transactions"] == 1
    assert result["bytes_received"] == len(response.body)
    assert result["reserved_bytes"] == 0
    assert result["results"][0]["outcome"] == "complete_metadata_pending_review"
    assert not result["results"][0]["contract_verified"]
    assert not result["dataset_acquisition_authorized"]
    assert len(transport.calls) == 1 and response.closed
    assert (tmp_path / "new/fictional-0.body").read_bytes() == response.body


@pytest.mark.parametrize("status", [202, 301, 302, 307, 400, 403, 429, 500, 504])
def test_unsuccessful_responses_are_counted_not_retried(tmp_path, status):
    response = Response(
        status=status,
        headers={"location": "https://example.invalid/private?secret=value"},
    )
    result, transport = run(tmp_path, response)
    assert result["transactions"] == len(transport.calls) == 1
    assert result["bytes_received"] == len(response.body)
    assert result["results"][0]["outcome"] == "failed"
    assert not (tmp_path / "new/fictional-0.body").exists()
    assert "secret=value" not in (tmp_path / "new/session.json").read_text()


@pytest.mark.parametrize(
    "headers,error",
    [
        ({"content-length": "512001"}, "declared_body_exceeds_cap"),
        ({"content-length": "3, 3"}, "invalid_content_length"),
        ({"content-length": "999"}, "incomplete_response"),
        ({"content-encoding": "gzip"}, "unexpected_content_encoding"),
        (
            {"transfer-encoding": "chunked", "content-length": "4"},
            "invalid_transfer_framing",
        ),
    ],
)
def test_bad_framing_never_becomes_saved_evidence(tmp_path, headers, error):
    result, _ = run(tmp_path, Response(headers=headers))
    assert result["results"][0]["error"] == error
    assert not (tmp_path / "new/fictional-0.body").exists()


def test_unknown_length_cap_does_not_probe_one_extra_byte(tmp_path):
    response = Response(body=b"x" * 512001)
    result, _ = run(tmp_path, response)
    assert result["bytes_received"] == response.position == 512000
    assert result["results"][0]["error"] == "response_cap_before_eof"


def test_exact_declared_cap_accepted_without_extra_read(tmp_path):
    response = Response(
        body=b'"' + b"x" * 511998 + b'"', headers={"content-length": "512000"}
    )
    # Scalar JSON is not a metadata contract; transfer can be complete but rejected.
    result, _ = run(tmp_path, response)
    assert result["bytes_received"] == 512000
    assert result["results"][0]["complete"]
    assert result["results"][0]["error"] == "unexpected_metadata_format"


def test_timeout_charges_returned_chunk_and_closes(tmp_path):
    clock = Clock()
    response = Response(clock=clock)
    result, _ = run(tmp_path, response, clock=clock)
    assert result["results"][0]["error"] == "request_timeout"
    assert result["bytes_received"] == len(response.body)
    assert response.closed


def test_open_failure_is_transaction_without_retry(tmp_path):
    result, transport = run(tmp_path, OSError("fictional"))
    assert result["transactions"] == len(transport.calls) == 1
    assert result["bytes_received"] == 0
    assert result["results"][0]["error"] == "transport_failure"


def test_unchecked_transport_redirect_rejected(tmp_path):
    result, _ = run(tmp_path, Response(url="https://example.invalid"))
    assert result["results"][0]["error"] == "unreviewed_transport_redirect"


def test_interrupt_persists_receipt_and_preserves_old_artifact(tmp_path):
    old = tmp_path / "old.json"
    old.write_bytes(b"old evidence")
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, Response(error=KeyboardInterrupt()))
    state = json.loads((tmp_path / "new/session.json").read_text())
    assert state["status"] == "aborted_no_automatic_resume"
    assert state["transactions"] == 1
    assert old.read_bytes() == b"old evidence"


def test_existing_output_refused_before_network(tmp_path):
    path, _ = policy(tmp_path)
    destination = tmp_path / "new"
    destination.mkdir()
    transport = Transport([])
    with pytest.raises(metadata.MetadataError, match="already exists"):
        metadata.run_session(
            path, destination, project_root=tmp_path, transport=transport
        )
    assert not transport.calls


@pytest.mark.parametrize(
    "mutation",
    ["limits", "dataset", "un", "api-data", "basis", "duplicate", "post", "seventeen"],
)
def test_policy_failures_before_network_or_output(tmp_path, mutation):
    path, data = policy(tmp_path)
    if mutation == "limits":
        data["limits"]["total_bytes"] += 1
    if mutation == "dataset":
        data["endpoints"][0]["url"] = "https://data.opensanctions.org/entities.ftm.json"
    if mutation == "un":
        data["endpoints"][0]["source_id"] = "un_consolidated"
    if mutation == "api-data":
        data["endpoints"][0]["url"] = (
            "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1"
        )
    if mutation == "basis":
        data["endpoints"][0]["basis_sha256"] = "0" * 64
    if mutation == "duplicate":
        data["endpoints"] *= 2
    if mutation == "post":
        data["endpoints"][0]["method"] = "POST"
    if mutation == "seventeen":
        data["endpoints"] *= 17
    path.write_text(json.dumps(data))
    transport = Transport([])
    with pytest.raises((metadata.MetadataError, ValueError)):
        metadata.run_session(
            path, tmp_path / "new", project_root=tmp_path, transport=transport
        )
    assert not transport.calls and not (tmp_path / "new").exists()


def test_global_bytes_stop_before_sixteenth_transaction(tmp_path):
    path, data = policy(tmp_path, 16)
    responses = [Response(b"x" * 512000, url=item["url"]) for item in data["endpoints"]]
    transport = Transport(responses)
    result = metadata.run_session(
        path, tmp_path / "new", project_root=tmp_path, transport=transport
    )
    assert result["transactions"] == 10
    assert result["bytes_received"] == 5000000
    assert len(transport.calls) == 10


def test_session_deadline_skips_remaining_requests(tmp_path):
    path, data = policy(tmp_path, 2)
    clock = Clock()

    class SlowTransport(Transport):
        def open(self, url, *, timeout):
            value = super().open(url, timeout=timeout)
            clock.now = 3601
            return value

    transport = SlowTransport([Response(url=data["endpoints"][0]["url"])])
    result = metadata.run_session(
        path, tmp_path / "new", project_root=tmp_path, transport=transport, clock=clock
    )
    assert result["transactions"] == 1
    assert result["stop_reason"] == "session_limit"


def test_offline_cli_does_not_construct_transport(tmp_path, monkeypatch, capsys):
    path, _ = policy(tmp_path)
    monkeypatch.setattr(
        metadata, "MetadataTransport", lambda _: pytest.fail("unexpected transport")
    )
    assert (
        metadata.main(
            [
                "--policy",
                str(path),
                "--output",
                str(tmp_path / "new"),
                "--project-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "no request" in capsys.readouterr().out
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize(
    "location",
    [
        "https://user:password@example.invalid/a?private=secret",  # pragma: allowlist secret -- fictional redaction regression
        "https://[malformed",
    ],
)
def test_redirect_location_does_not_leak_userinfo_or_crash(tmp_path, location):
    result, _ = run(tmp_path, Response(status=302, headers={"location": location}))
    assert result["results"][0]["error"] == "redirect_not_followed"
    assert "password" not in (tmp_path / "new/session.json").read_text()
    assert "redirect_location_without_query" not in result["results"][0]


def test_partial_exception_bytes_are_charged(tmp_path):
    result, _ = run(
        tmp_path, Response(error=http.client.IncompleteRead(b"fictional", 100))
    )
    assert result["bytes_received"] == 9
    assert result["results"][0]["error"] == "incomplete_response"


@pytest.mark.parametrize(
    "url,source",
    [
        (
            "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
            "ofac_sdn",
        ),
        (
            "https://www.wikidata.org/w/%61pi.php?action=wbgetentities&ids=Q1",
            "wikidata_orgs",
        ),
        (URL, "ofac_sdn"),
    ],
)
def test_official_host_does_not_authorize_arbitrary_routes(tmp_path, url, source):
    path, data = policy(tmp_path)
    data["endpoints"][0].update(url=url, source_id=source)
    path.write_text(json.dumps(data))
    with pytest.raises(metadata.MetadataError, match="exact reviewed"):
        metadata.load_policy(path, tmp_path)


def test_explicit_second_batch_carries_counters_and_refuses_retry(tmp_path):
    result, _ = run(tmp_path, Response())
    prior = tmp_path / "new/session.json"
    path, data = policy(tmp_path)
    with pytest.raises(metadata.MetadataError, match="already attempted"):
        metadata.run_session(
            path,
            tmp_path / "retry",
            project_root=tmp_path,
            transport=Transport([]),
            previous=prior,
        )
    data["endpoints"][0].update(id="next-document", url=URL + "?fictional=1")
    path.write_text(json.dumps(data))
    response = Response(url=data["endpoints"][0]["url"])
    continued = metadata.run_session(
        path,
        tmp_path / "continued",
        project_root=tmp_path,
        transport=Transport([response]),
        previous=prior,
    )
    assert continued["transactions"] == 2
    assert continued["bytes_received"] == result["bytes_received"] + len(response.body)
    assert continued["started_at_utc"] == result["started_at_utc"]
    assert json.loads(prior.read_text()) == result


def test_unfinished_prior_batch_cannot_reset_budget(tmp_path):
    run(tmp_path, Response())
    prior = tmp_path / "new/session.json"
    data = json.loads(prior.read_text())
    data["status"] = "running"
    prior.write_text(json.dumps(data))
    path, _ = policy(tmp_path)
    with pytest.raises(metadata.MetadataError, match="unfinished"):
        metadata.run_session(
            path,
            tmp_path / "continued",
            project_root=tmp_path,
            transport=Transport([]),
            previous=prior,
        )


@pytest.mark.parametrize("tamper", ["negative", "boolean", "receipt", "body", "policy"])
def test_prior_receipts_and_body_integrity_required(tmp_path, tamper):
    run(tmp_path, Response())
    prior = tmp_path / "new/session.json"
    state = json.loads(prior.read_text())
    if tamper in {"negative", "boolean"}:
        state["results"][0]["bytes_received"] = -1 if tamper == "negative" else True
        state["bytes_received"] = state["results"][0]["bytes_received"]
        prior.write_text(json.dumps(state))
    elif tamper == "receipt":
        (tmp_path / "new/fictional-0.receipt.json").write_text("{}")
    elif tamper == "body":
        (tmp_path / "new/fictional-0.body").write_bytes(b"changed")
    else:
        (tmp_path / "new/policy.json").write_text("{}")
    path, data = policy(tmp_path)
    data["endpoints"][0].update(id="next-document", url=URL + "?fictional=1")
    path.write_text(json.dumps(data))
    transport = Transport([])
    with pytest.raises(metadata.MetadataError):
        metadata.run_session(
            path,
            tmp_path / "continued",
            project_root=tmp_path,
            transport=transport,
            previous=prior,
        )
    assert not transport.calls
