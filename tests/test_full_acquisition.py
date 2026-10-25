"""Full-profile preparation uses invented entities and in-memory transports."""

from dataclasses import replace
import hashlib
import http.client
import io
import json
from pathlib import Path
import socket
import ssl
import stat
from urllib.parse import urlencode
import zipfile

import pytest

from watchlist.ingest import full_acquire as full
from watchlist.ingest.acquire import HTTPTransport
from watchlist.ingest.parse_ofac import NAMESPACE as OFAC_NAMESPACE
from watchlist.ingest.resource_guard import (
    BudgetLedger,
    GIB,
    ResourceGuard,
    ResourceLimits,
    ResourceSnapshot,
    STEP08_LIMITS,
)
from watchlist.ingest.source_registry import ParseContext, SourceValidationError


URLS = {
    "opensanctions_un": "https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000000-fictional/entities.ftm.json",
    "ofac_sdn": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP",
    "eu_consolidated": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content",
}


@pytest.fixture(autouse=True)
def deny_real_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Full acquisition tests must never use the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def ftm_record(number, *, schema="Organization", aliases=None):
    return {
        "id": f"fictional-{number:06d}",
        "schema": schema,
        "properties": {
            "name": [f"Fictional Orbital Workshop {number}"],
            "alias": [f"कल्पित कार्यशाला {number}"] if aliases is None else aliases,
            "topics": ["sanction"],
        },
    }


def ftm_payload(count, *, additional=()):
    return (
        "\n".join(
            json.dumps(record, ensure_ascii=False)
            for record in [
                *(ftm_record(number) for number in range(count)),
                *additional,
            ]
        )
        + "\n"
    ).encode()


def zipped_xml(payload):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("SDN.XML", payload)
    return stream.getvalue()


def ofac_payload(count, *, extra="", declared=None, namespace=OFAC_NAMESPACE):
    entries = "".join(
        f"<sdnEntry><uid>{number}</uid><sdnType>Entity</sdnType><lastName>Fictional Moon Harbor {number}</lastName></sdnEntry>"
        for number in range(1, count + 1)
    )
    xml = (
        f'<sdnList xmlns="{namespace}" xml:lang="fr"><publshInformation>'
        f"<Publish_Date>Fictional 2093-01-01</Publish_Date><Record_Count>{count if declared is None else declared}</Record_Count>"
        f"</publshInformation>{entries}{extra}</sdnList>"
    ).encode()
    return zipped_xml(xml), xml


def eu_payload(count):
    entries = "".join(
        f'<sanctionEntity logicalId="fictional-{number}"><subjectType code="enterprise" classificationCode="E"/>'
        f'<nameAlias logicalId="name-{number}" wholeName="Fictional Solar Workshop {number}" strong="true" nameLanguage="fr" regulationLanguage="en">'
        "<regulationSummary/></nameAlias></sanctionEntity>"
        for number in range(count)
    )
    return (
        '<export xmlns="http://eu.europa.ec/fpi/fsd/export" generationDate="2093-01-01" globalFileId="fictional-export" xml:lang="fr">'
        f"{entries}</export>"
    ).encode()


def policy(source="opensanctions_un", **changes):
    return full.FullSourcePolicy(source, URLS[source], **changes)


def guard(**limit_changes):
    return ResourceGuard(
        probe=lambda: ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False),
        limits=ResourceLimits(**limit_changes),
    )


def acquire(
    tmp_path,
    payload,
    *,
    source="opensanctions_un",
    reply=None,
    source_policy=None,
    ledger=None,
    resource_guard=None,
):
    selected_policy = source_policy or policy(source)
    transport = full.FictionalTransport(
        {selected_policy.url: (reply or full.FictionalReply(payload),)}
    )
    receipt = full.acquire_fictional(
        full.prepare_full_profile((selected_policy,)),
        tmp_path / "run",
        transport=transport,
        ledger=ledger or BudgetLedger(),
        guard=resource_guard or guard(),
    )
    return receipt, transport


def test_full_preparation_is_separate_from_frozen_feasibility_profile():
    profile = full.prepare_full_profile(tuple(policy(source) for source in URLS))
    assert [source.max_groups for source in profile.sources] == [300, 12_000, 2_000]
    assert profile.live_authorized is False
    assert len(profile.policy_sha256) == 64
    assert profile == full.prepare_full_profile(
        tuple(policy(source) for source in URLS)
    )
    with pytest.raises(SourceValidationError):
        ParseContext("ofac_sdn", max_groups=201)
    with pytest.raises(full.FullAcquisitionError, match="retention_cap"):
        policy("ofac_sdn", max_groups=12_001)
    with pytest.raises(full.FullAcquisitionError, match="source_not_in_full"):
        full.FullSourcePolicy(
            "un_consolidated",
            "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000000-fictional/entities.ftm.json",
        "https://data.opensanctions.org/unreviewed/entities.ftm.json",
        "https://example.invalid/entities.ftm.json",
        URLS["opensanctions_un"] + "?extra=1",
    ],
)
def test_full_preparation_rejects_non_exact_destinations(url):
    with pytest.raises(SourceValidationError):
        full.FullSourcePolicy("opensanctions_un", url)


def test_ftm_full_parser_exceeds_200_and_reports_selection_exclusions():
    payload = ftm_payload(305, additional=(ftm_record(999999, schema="Person"),))
    result = full.parse_full_payload(payload, policy())
    assert len(result.records) == 300
    assert result.input_records == 306
    assert result.excluded_person_records == 1
    assert result.excluded_by_limit == 5
    assert result.records[-1].provider_id == "fictional-000299"
    assert len(result.records[0].aliases) == 2
    assert result.input_sha256 == hashlib.sha256(payload).hexdigest()


def test_ftm_bom_is_allowed_only_at_start_of_whole_input():
    payload = ftm_payload(1)
    assert (
        len(full.parse_full_payload(b"\xef\xbb\xbf\n" + payload, policy()).records) == 1
    )
    with pytest.raises(SourceValidationError, match="Malformed"):
        full.parse_full_payload(payload + b"\xef\xbb\xbf" + payload, policy())


def test_ofac_full_cap_and_original_container_metadata():
    payload, xml = ofac_payload(12_001)
    result = full.parse_full_payload(payload, policy("ofac_sdn"))
    assert len(result.records) == 12_000
    assert result.excluded_by_limit == 1
    assert result.input_records == 12_001
    assert result.input_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.decoded_bytes == len(xml)
    assert result.decoded_sha256 == hashlib.sha256(xml).hexdigest()
    assert result.source_version == "Fictional 2093-01-01"
    assert result.source_version_field == "sdnList.publshInformation.Publish_Date"
    assert all(record.aliases[0].language == "fr" for record in result.records)
    assert result.records[0].classification_basis is None


def test_eu_full_cap_and_source_attribute_evidence():
    result = full.parse_full_payload(eu_payload(2001), policy("eu_consolidated"))
    assert len(result.records) == 2000 and result.excluded_by_limit == 1
    assert json.loads(result.source_version) == {
        "generationDate": "2093-01-01",
        "globalFileId": "fictional-export",
    }
    evidence = result.records[0].aliases[0]
    assert evidence.language == "fr"
    assert dict(evidence.attributes)["regulationLanguage"] == "en"
    assert dict(evidence.attributes)["strong"] == "true"


@pytest.mark.parametrize("source", ["opensanctions_un", "ofac_sdn", "eu_consolidated"])
def test_duplicate_provider_ids_are_rejected_even_in_excluded_people(source):
    if source == "opensanctions_un":
        payload = ftm_payload(1, additional=(ftm_record(0, schema="Person"),))
    elif source == "ofac_sdn":
        extra = "<sdnEntry><uid>1</uid><sdnType>Individual</sdnType><lastName>Fictional Person</lastName></sdnEntry>"
        payload, _ = ofac_payload(1, extra=extra, declared=2)
    else:
        payload = eu_payload(1).replace(
            b"</export>",
            b'<sanctionEntity logicalId="fictional-0"><subjectType code="person" classificationCode="P"/></sanctionEntity></export>',
        )
    with pytest.raises(SourceValidationError, match="Duplicate"):
        full.parse_full_payload(payload, policy(source))


def test_whole_xml_count_namespace_and_unknown_children_are_validated():
    payload, _ = ofac_payload(1, declared=2)
    with pytest.raises(SourceValidationError, match="record count"):
        full.parse_full_payload(payload, policy("ofac_sdn"))
    payload, _ = ofac_payload(1, namespace="https://fictional.invalid/namespace")
    with pytest.raises(SourceValidationError, match="namespace"):
        full.parse_full_payload(payload, policy("ofac_sdn"))
    payload, _ = ofac_payload(1, extra="<unknown/>")
    with pytest.raises(SourceValidationError, match="top-level"):
        full.parse_full_payload(payload, policy("ofac_sdn"))


def test_late_invalid_aliases_are_not_silently_truncated_or_published(tmp_path):
    oversized = ftm_record(
        999999, aliases=[f"Fictional Alias {number}" for number in range(129)]
    )
    payload = ftm_payload(300, additional=(oversized,))
    receipt, transport = acquire(tmp_path, payload)
    assert receipt["status"] == "failed"
    assert receipt["stop_reason"] == "source_validation_failed"
    assert receipt["ledger"]["total_received_bytes"] == len(payload)
    assert not list((tmp_path / "run").glob("*.jsonl"))
    assert transport.responses[0].closed
    saved = (tmp_path / "run" / "receipt.json").read_text()
    assert "Fictional Alias" not in saved and "Orbital" not in saved


def test_offline_success_publishes_private_no_raw_body_artifacts(tmp_path):
    payload = ftm_payload(250)
    receipt, transport = acquire(tmp_path, payload)
    assert receipt["status"] == "passed"
    assert receipt["sources"][0]["retained_groups"] == 250
    assert receipt["sources"][0]["input_bytes"] == len(payload)
    assert receipt["sources"][0]["container_format"] is None
    assert receipt["sources"][0]["container_member"] is None
    assert receipt["live_authorized"] is False
    assert receipt["independent_custody_verified"] is False
    assert receipt["selection_use"] == "fictional-development-only"
    rows = (tmp_path / "run" / "opensanctions_un.jsonl").read_text().splitlines()
    assert len(rows) == 250
    assert json.loads(rows[0])["qualified_id"].startswith("opensanctions_un:fictional-")
    assert transport.calls == [URLS["opensanctions_un"]]
    assert stat.S_IMODE((tmp_path / "run").stat().st_mode) == 0o700
    for item in (tmp_path / "run").iterdir():
        assert stat.S_IMODE(item.stat().st_mode) == 0o600
        assert item.read_bytes() != payload


def test_live_transport_and_fabricated_live_authorization_are_rejected(tmp_path):
    profile = full.prepare_full_profile((policy(),))
    with pytest.raises(
        full.FullAcquisitionError, match="live_transport_not_authorized"
    ):
        full.acquire_fictional(
            profile,
            tmp_path / "live",
            transport=HTTPTransport(),
            ledger=BudgetLedger(),
            guard=guard(),
        )
    with pytest.raises(full.FullAcquisitionError, match="invalid_or_live"):
        full.acquire_fictional(
            replace(profile, live_authorized=True),
            tmp_path / "live",
            transport=full.FictionalTransport({}),
            ledger=BudgetLedger(),
            guard=guard(),
        )
    assert not (tmp_path / "live").exists()


def test_declared_oversize_fails_before_read_and_preserves_attempt(tmp_path):
    payload = ftm_payload(1)
    receipt, transport = acquire(
        tmp_path,
        payload,
        reply=full.FictionalReply(payload, headers=(("Content-Length", "5000001"),)),
    )
    assert receipt["stop_reason"] == "declared_length_exceeds_remaining"
    assert receipt["ledger"]["total_received_bytes"] == 0
    assert receipt["ledger"]["transactions"]["opensanctions_un"] == 1
    assert transport.responses[0]._position == 0


def test_underreported_length_cannot_hide_a_late_duplicate_record(tmp_path):
    prefix = ftm_payload(1)
    payload = prefix + prefix
    receipt, _ = acquire(
        tmp_path,
        payload,
        reply=full.FictionalReply(
            payload, headers=(("Content-Length", str(len(prefix))),)
        ),
    )
    assert receipt["status"] == "failed"
    assert receipt["stop_reason"] == "declared_length_hides_trailing_body"
    assert receipt["ledger"]["total_received_bytes"] == len(prefix)
    assert not list((tmp_path / "run").glob("*.jsonl"))


@pytest.mark.parametrize("status", [429, 500, 503])
def test_error_response_bodies_are_charged_without_retry(tmp_path, status):
    body = b"Fictional provider error body"
    receipt, transport = acquire(
        tmp_path, body, reply=full.FictionalReply(body, status=status)
    )
    assert receipt["stop_reason"] == "http_status_rejected"
    assert receipt["ledger"]["total_received_bytes"] == len(body)
    assert len(transport.calls) == 1


def test_interrupted_response_keeps_bytes_and_no_retry(tmp_path):
    payload = ftm_payload(2)
    receipt, transport = acquire(
        tmp_path,
        payload,
        reply=full.FictionalReply(payload, chunk_bytes=10, fail_after_bytes=20),
    )
    assert receipt["status"] == "failed"
    assert receipt["ledger"]["total_received_bytes"] == 20
    assert len(transport.calls) == 1
    assert not list((tmp_path / "run").glob("*.jsonl"))


def test_exact_redirect_bodies_and_final_body_share_one_bucket(tmp_path):
    destination = URLS["opensanctions_un"].replace("-fictional/", "-fictionalredirect/")
    source_policy = policy(allowed_redirects=(destination,))
    payload = ftm_payload(1)
    transport = full.FictionalTransport(
        {
            source_policy.url: (
                full.FictionalReply(
                    b"fictional redirect", 302, (("Location", destination),)
                ),
            ),
            destination: (full.FictionalReply(payload),),
        }
    )
    receipt = full.acquire_fictional(
        full.prepare_full_profile((source_policy,)),
        tmp_path / "run",
        transport=transport,
        ledger=BudgetLedger(),
        guard=guard(),
    )
    assert receipt["status"] == "passed"
    assert receipt["ledger"]["total_received_bytes"] == len(payload) + len(
        b"fictional redirect"
    )
    assert receipt["ledger"]["transactions"]["opensanctions_un"] == 2
    assert all(response.closed for response in transport.responses)


def test_unreviewed_redirect_is_not_opened_but_its_body_is_charged(tmp_path):
    body = b"fictional redirect body"
    receipt, transport = acquire(
        tmp_path,
        body,
        reply=full.FictionalReply(
            body, 302, (("Location", "https://example.invalid/unreviewed"),)
        ),
    )
    assert receipt["stop_reason"] == "unreviewed_redirect_destination"
    assert receipt["ledger"]["total_received_bytes"] == len(body)
    assert len(transport.calls) == 1


def test_failed_output_cannot_be_reopened_or_redirected_through_symlink(tmp_path):
    acquire(tmp_path, b"invalid fictional JSON")
    before = {item.name: item.read_bytes() for item in (tmp_path / "run").iterdir()}
    with pytest.raises(FileExistsError):
        acquire(tmp_path, ftm_payload(1))
    assert {
        item.name: item.read_bytes() for item in (tmp_path / "run").iterdir()
    } == before
    (tmp_path / "link").symlink_to(tmp_path / "run", target_is_directory=True)
    with pytest.raises(SourceValidationError):
        full.acquire_fictional(
            full.prepare_full_profile((policy(),)),
            tmp_path / "link" / "new",
            transport=full.FictionalTransport({}),
            ledger=BudgetLedger(),
            guard=guard(),
        )


def test_publisher_digest_and_size_mismatch_fail_before_publication(tmp_path):
    payload = ftm_payload(1)
    receipt, _ = acquire(
        tmp_path, payload, source_policy=policy(expected_sha256="0" * 64)
    )
    assert receipt["status"] == "failed"
    assert not list((tmp_path / "run").glob("*.jsonl"))
    with pytest.raises(SourceValidationError, match="size mismatch"):
        full.parse_full_payload(payload, policy(expected_bytes=len(payload) + 1))


def test_normalized_limit_is_enforced_before_selection_publication(tmp_path):
    receipt, _ = acquire(
        tmp_path, ftm_payload(1), resource_guard=guard(max_normalized_bytes=100)
    )
    assert receipt["stop_reason"] == "normalized_byte_limit"
    assert not list((tmp_path / "run").glob("*.jsonl"))


def test_response_budget_includes_failed_reads_and_declared_cap_after_redirect(
    tmp_path,
):
    destination = URLS["opensanctions_un"].replace("-fictional/", "-second/")
    source_policy = policy(allowed_redirects=(destination,))
    limits = dict(STEP08_LIMITS)
    limits["opensanctions_un"] = replace(
        limits["opensanctions_un"], received_bytes=30, response_bytes=30
    )
    transport = full.FictionalTransport(
        {
            source_policy.url: (
                full.FictionalReply(b"1234567890", 302, (("Location", destination),)),
            ),
            destination: (
                full.FictionalReply(b"not read", headers=(("Content-Length", "21"),)),
            ),
        }
    )
    receipt = full.acquire_fictional(
        full.prepare_full_profile((source_policy,)),
        tmp_path / "run",
        transport=transport,
        ledger=BudgetLedger(limits=limits),
        guard=guard(),
    )
    assert receipt["stop_reason"] == "declared_length_exceeds_remaining"
    assert receipt["ledger"]["total_received_bytes"] == 10
    assert transport.responses[-1]._position == 0
    journals = sorted((tmp_path / "run").glob("ledger-*.json"))
    assert any(
        json.loads(path.read_bytes())["active_response_reservation"] == 20
        for path in journals
    )


def test_shared_session_does_not_reset_bytes_deadline_or_attempts_between_calls(
    tmp_path,
):
    ledger = BudgetLedger()
    resources = guard()
    first = ftm_payload(1)
    second, _ = ofac_payload(1)
    first_profile = full.prepare_full_profile((policy(),))
    first_transport = full.FictionalTransport(
        {URLS["opensanctions_un"]: (full.FictionalReply(first),)}
    )
    first_receipt = full.acquire_fictional(
        first_profile,
        tmp_path / "first",
        transport=first_transport,
        ledger=ledger,
        guard=resources,
    )
    assert first_receipt["status"] == "passed"
    deadline = resources.deadline
    initial_normalized = resources.normalized_bytes
    second_profile = full.prepare_full_profile((policy("ofac_sdn"),))
    second_transport = full.FictionalTransport(
        {URLS["ofac_sdn"]: (full.FictionalReply(second),)}
    )
    second_receipt = full.acquire_fictional(
        second_profile,
        tmp_path / "second",
        transport=second_transport,
        ledger=ledger,
        guard=resources,
    )
    assert second_receipt["status"] == "passed"
    assert second_receipt["sources"][0]["input_bytes"] == len(second)
    assert second_receipt["sources"][0]["container_format"] == "zip"
    assert second_receipt["sources"][0]["container_member"] == "SDN.XML"
    assert second_receipt["ledger"]["total_received_bytes"] == len(first) + len(second)
    assert resources.deadline == deadline
    assert resources.normalized_bytes > initial_normalized
    repeated = full.acquire_fictional(
        first_profile,
        tmp_path / "repeated",
        transport=full.FictionalTransport({}),
        ledger=ledger,
        guard=resources,
    )
    assert repeated["status"] == "failed"
    assert repeated["stop_reason"] == "source_attempt_already_used"
    assert repeated["ledger"]["total_received_bytes"] == len(first) + len(second)


def test_known_fictional_completion_at_exact_byte_cap_needs_no_extra_read(tmp_path):
    payload = ftm_payload(1)
    limits = dict(STEP08_LIMITS)
    limits["opensanctions_un"] = replace(
        limits["opensanctions_un"],
        received_bytes=len(payload),
        response_bytes=len(payload),
    )
    receipt, transport = acquire(tmp_path, payload, ledger=BudgetLedger(limits=limits))
    assert receipt["status"] == "passed"
    assert receipt["ledger"]["total_received_bytes"] == len(payload)
    assert transport.responses[0].body_complete


class LiveResponse:
    """Native-transport-shaped response; all contents remain invented."""

    def __init__(self, body, *, status=200, headers=None, error=None, on_read=None):
        self.body = body
        self.status = status
        self.headers = (
            {"content-length": str(len(body))} if headers is None else headers
        )
        self.error = error
        self.on_read = on_read
        self.url = None
        self.position = 0
        self.reads = []
        self.closed = False

    def read(self, size, *, timeout):
        self.reads.append((size, timeout))
        if self.on_read is not None:
            self.on_read()
        if self.error is not None:
            raise self.error
        block = self.body[self.position : self.position + size]
        self.position += len(block)
        return block

    def close(self):
        self.closed = True


class LiveTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def open(self, url, *, timeout):
        self.calls.append((url, timeout))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        response.url = url
        return response


def live_fixture(tmp_path, *, ftm_count=1):
    """Fictional grants simulate this schema without asserting real permission."""
    root = Path(__file__).resolve().parents[1]
    policy_data = json.loads(
        (root / "config/data-sources-step08-full.json").read_bytes()
    )
    approval = {"path": "approval.json", "sha256": ""}
    approval_bytes = b'{"approval":"fictional test-only execution; no real network"}\n'
    (tmp_path / approval["path"]).write_bytes(approval_bytes)
    approval["sha256"] = hashlib.sha256(approval_bytes).hexdigest()
    policy_data["approval"] = approval
    policy_data["session_claim_path"] = "session.claim.json"
    payloads = {
        "opensanctions_un": ftm_payload(ftm_count),
        "ofac_sdn": ofac_payload(1)[0],
        "eu_consolidated": eu_payload(1),
    }
    for source in policy_data["sources"]:
        source_id = source["source_id"]
        grant = json.loads((root / source["permission_path"]).read_bytes())
        grant["approval"] = approval
        grant["evidence"] = [approval]
        grant["reviewer"] = "Fictional test reviewer; no real permission assertion"
        source["permission_path"] = source_id + ".grant.json"
        grant_bytes = json.dumps(grant, ensure_ascii=False).encode()
        (tmp_path / source["permission_path"]).write_bytes(grant_bytes)
        source["permission_sha256"] = hashlib.sha256(grant_bytes).hexdigest()
        source["expected_bytes"] = (
            len(payloads[source_id]) if source_id != "eu_consolidated" else None
        )
        source["expected_sha1"] = (
            hashlib.sha1(payloads[source_id]).hexdigest()
            if source_id == "opensanctions_un"
            else None
        )
        if source_id == "ofac_sdn":
            with zipfile.ZipFile(io.BytesIO(payloads[source_id])) as archive:
                source["expected_decoded_sha256"] = hashlib.sha256(
                    archive.read("SDN.XML")
                ).hexdigest()
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")
    responses = {
        full.LIVE_URLS[source]: LiveResponse(payload)
        for source, payload in payloads.items()
    }
    return policy_file, policy_data, LiveTransport(responses), payloads


def save_live_policy(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_live_fixture(tmp_path, policy_file, data, transport, **kwargs):
    return full.acquire_live(
        policy_file,
        tmp_path / "live-run",
        project_root=tmp_path,
        expected_policy_sha256=save_live_policy(policy_file, data),
        transport=transport,
        guard=kwargs.pop("guard", guard()),
        **kwargs,
    )


def test_live_success_binds_receipt_purpose_and_complete_three_source_bytes(tmp_path):
    policy_file, data, transport, payloads = live_fixture(tmp_path)
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    output = tmp_path / "live-run"
    assert receipt["status"] == "passed"
    assert receipt["scope"] == full.LIVE_SCOPE
    assert receipt["selection_use"] == "shared-development-candidates-only"
    assert receipt["independent_custody_verified"] is False
    assert receipt["ledger"]["total_received_bytes"] == sum(map(len, payloads.values()))
    assert receipt["ledger"]["tranche_bytes"] == 39_000_000
    assert receipt["ledger"]["bulk_transaction_limit"] == 3
    assert len(transport.calls) == 3
    assert set(receipt["ledger"]["allowed_buckets"]) == set(full.LIVE_URLS)
    assert (output / "execution-policy.json").read_bytes() == policy_file.read_bytes()
    receipt_hash = hashlib.sha256((output / "receipt.json").read_bytes()).hexdigest()
    for row in receipt["sources"]:
        assert (
            row["requested_url"] == row["final_url"] == full.LIVE_URLS[row["source_id"]]
        )
        assert row["transaction_count"] == 1 and row["complete"]
        assert row["input_sha256"] == row["body_sha256"]
        assert row["input_bytes"] == row["bytes_received"]
        purpose = json.loads(
            (output / (row["source_id"] + ".purpose.json")).read_bytes()
        )
        assert purpose["receipt_sha256"] == receipt_hash
        assert purpose["selection_sha256"] == row["selection_sha256"]
        assert (
            purpose["reviewer"]
            == "Fictional test reviewer; no real permission assertion"
        )
        assert row["publisher_checksum"]["verified"] == (
            row["source_id"] != "eu_consolidated"
        )
        assert row["publisher_checksum"]["hash_verified"] == (
            row["source_id"] != "eu_consolidated"
        )
        assert (output / row["selection_path"]).read_bytes() != payloads[
            row["source_id"]
        ]
    assert all(response.closed for response in transport.responses.values())


@pytest.mark.parametrize(
    "fault",
    [
        "blocked_grant",
        "changed_evidence",
        "wrong_fields",
        "redirect_permission",
        "new_endpoint",
        "missing_source",
        "wider_budget",
    ],
)
def test_all_live_grants_validate_before_transport_or_claim(
    tmp_path, monkeypatch, fault
):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    if fault in {"blocked_grant", "wrong_fields"}:
        source = data["sources"][-1]
        path = tmp_path / source["permission_path"]
        grant = json.loads(path.read_bytes())
        if fault == "blocked_grant":
            grant["status"] = "blocked"
        else:
            grant["alias_fields"].remove("language")
        path.write_text(json.dumps(grant), encoding="utf-8")
        source["permission_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault == "changed_evidence":
        (tmp_path / "approval.json").write_bytes(b"changed evidence")
    elif fault == "redirect_permission":
        data["sources"][0]["allowed_redirects"] = ["https://example.invalid/redirect"]
    elif fault == "new_endpoint":
        data["sources"][1]["url"] = "https://example.invalid/substitute.zip"
    elif fault == "missing_source":
        data["sources"].pop()
    else:
        data["limits"]["total_bytes"] += 1
    monkeypatch.setattr(
        full,
        "HTTPTransport",
        lambda: pytest.fail("transport constructed before all grants validated"),
    )
    with pytest.raises((full.FullAcquisitionError, SourceValidationError)):
        full.acquire_live(
            policy_file,
            tmp_path / "live-run",
            project_root=tmp_path,
            expected_policy_sha256=save_live_policy(policy_file, data),
            guard=guard(),
        )
    assert transport.calls == []
    assert not (tmp_path / "session.claim.json").exists()
    assert not (tmp_path / "live-run").exists()


def test_live_grant_bytes_are_verified_even_if_changed_between_reads(
    tmp_path, monkeypatch
):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    target = data["sources"][-1]["permission_path"]
    original_read = full._local_bytes
    reads = 0

    def changed_read(root, relative):
        nonlocal reads
        payload = original_read(root, relative)
        if relative == target:
            reads += 1
            if reads == 2:
                grant = json.loads(payload)
                grant["reviewer"] = "Unpinned replacement reviewer"
                return json.dumps(grant).encode()
        return payload

    monkeypatch.setattr(full, "_local_bytes", changed_read)
    with pytest.raises(
        full.FullAcquisitionError, match="permission_evidence_digest_mismatch"
    ):
        run_live_fixture(tmp_path, policy_file, data, transport)
    assert reads == 2
    assert transport.calls == []
    assert not (tmp_path / "session.claim.json").exists()


def test_live_response_close_failure_prevents_successful_selection(
    tmp_path, monkeypatch
):
    policy_file, data, transport, payloads = live_fixture(tmp_path)
    first = transport.responses[full.LIVE_URLS["opensanctions_un"]]

    def failed_close():
        raise OSError("fictional close failure")

    monkeypatch.setattr(first, "close", failed_close)
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    row = receipt["sources"][0]
    assert receipt["status"] == "partial"
    assert row["status"] == "failed"
    assert row["stop_reason"] == "response_close_failed"
    assert row["bytes_received"] == len(payloads["opensanctions_un"])
    assert receipt["ledger"]["active_response_reservation"] == 0
    assert "close_failed" not in row
    assert not (tmp_path / "live-run" / "opensanctions_un.jsonl").exists()
    assert not list((tmp_path / "live-run").glob("*.purpose.json"))


@pytest.mark.parametrize("status", [302, 429, 500])
def test_live_failure_body_counts_without_redirect_or_retry(tmp_path, status):
    policy_file, data, transport, payloads = live_fixture(tmp_path)
    body = b"fictional unavailable source"
    transport.responses[full.LIVE_URLS["ofac_sdn"]] = LiveResponse(
        body,
        status=status,
        headers={
            "content-length": str(len(body)),
            "location": "https://example.invalid/never-follow",
        },
    )
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    assert receipt["status"] == "partial"
    failed = receipt["sources"][1]
    assert failed["stop_reason"] == (
        "redirect_not_followed" if status == 302 else "http_non_200"
    )
    assert failed["bytes_received"] == len(body)
    assert failed["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert receipt["ledger"]["total_received_bytes"] == len(
        payloads["opensanctions_un"]
    ) + len(body) + len(payloads["eu_consolidated"])
    assert [url for url, _ in transport.calls] == list(full.LIVE_URLS.values())
    assert not list((tmp_path / "live-run").glob("*.purpose.json"))
    assert not (tmp_path / "live-run" / "ofac_sdn.jsonl").exists()


def test_live_incomplete_read_partial_bytes_remain_charged(tmp_path):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    partial = b"fictional partial payload"
    transport.responses[full.LIVE_URLS["opensanctions_un"]] = LiveResponse(
        b"", headers={}, error=http.client.IncompleteRead(partial, 50)
    )
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    first = receipt["sources"][0]
    assert first["stop_reason"] == "incomplete_response"
    assert first["bytes_received"] == len(partial)
    assert first["body_sha256"] == hashlib.sha256(partial).hexdigest()
    assert receipt["ledger"]["received_bytes"]["opensanctions_un"] == len(partial)
    assert not first["complete"]


@pytest.mark.parametrize(
    "headers, reason",
    [
        ({"content-length": "1, 1"}, "invalid_content_length"),
        (
            {"content-length": "1", "transfer-encoding": "chunked"},
            "ambiguous_transfer_framing",
        ),
        ({"content-encoding": "gzip"}, "unexpected_content_encoding"),
        ({"content-length": "5000001"}, "declared_length_exceeds_remaining"),
    ],
)
def test_live_framing_and_declared_cap_fail_before_body_read(tmp_path, headers, reason):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    first = LiveResponse(b"fictional", headers=headers)
    transport.responses[full.LIVE_URLS["opensanctions_un"]] = first
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    assert receipt["sources"][0]["stop_reason"] == reason
    assert first.reads == []
    assert receipt["ledger"]["received_bytes"]["opensanctions_un"] == 0


def test_live_timeout_stops_run_after_one_attempt(tmp_path):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    transport.responses[full.LIVE_URLS["opensanctions_un"]] = TimeoutError(
        "fictional timeout"
    )
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    assert receipt["status"] == "failed"
    assert receipt["stop_reason"] == "request_timeout"
    assert len(transport.calls) == 1
    assert receipt["ledger"]["transactions"]["opensanctions_un"] == 1


@pytest.mark.parametrize("field", ["expected_sha1", "expected_decoded_sha256"])
def test_live_publisher_digest_mismatch_prevents_source_selection(tmp_path, field):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    index = 0 if field == "expected_sha1" else 1
    data["sources"][index][field] = "0" * (40 if field == "expected_sha1" else 64)
    receipt = run_live_fixture(tmp_path, policy_file, data, transport)
    assert receipt["status"] == "partial"
    assert receipt["sources"][index]["status"] == "failed"
    assert not (
        tmp_path / "live-run" / (data["sources"][index]["source_id"] + ".jsonl")
    ).exists()


def test_live_claim_prevents_new_output_reset_and_never_overwrites(tmp_path):
    policy_file, data, transport, _ = live_fixture(tmp_path)
    run_live_fixture(tmp_path, policy_file, data, transport)
    before = (tmp_path / "session.claim.json").read_bytes()
    with pytest.raises(FileExistsError):
        full.acquire_live(
            policy_file,
            tmp_path / "different-output",
            project_root=tmp_path,
            expected_policy_sha256=save_live_policy(policy_file, data),
            transport=transport,
            guard=guard(),
        )
    assert len(transport.calls) == 3
    assert (tmp_path / "session.claim.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        run_live_fixture(tmp_path, policy_file, data, transport)


def test_live_parsing_keeps_per_record_deadlines_without_per_record_os_probes(tmp_path):
    policy_file, data, transport, _ = live_fixture(tmp_path, ftm_count=3000)
    probes = []

    def probe():
        probes.append(True)
        return ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False)

    receipt = run_live_fixture(
        tmp_path,
        policy_file,
        data,
        transport,
        guard=ResourceGuard(probe=probe),
        clock=lambda: 100.0,
    )
    assert receipt["status"] == "passed"
    assert receipt["sources"][0]["input_records"] == 3000
    assert len(probes) < 150


def test_live_unknown_length_cap_does_not_request_an_extra_byte(tmp_path):
    policy_file, data, _, _ = live_fixture(tmp_path)
    source = data["sources"][0]
    response = LiveResponse(b"12345678901", headers={})
    transport = LiveTransport({source["url"]: response})
    limits = dict(STEP08_LIMITS)
    limits["opensanctions_un"] = replace(
        limits["opensanctions_un"], received_bytes=10, response_bytes=10, transactions=1
    )
    ledger = BudgetLedger(
        limits=limits,
        total_received_limit=39_000_000,
        bulk_transaction_limit=3,
        allowed_buckets=frozenset(full.LIVE_URLS),
    )
    ledger.begin_source("opensanctions_un")
    row = {"bytes_received": 0}
    snapshots = []
    with pytest.raises(full.FullAcquisitionError, match="response_cap_before_eof"):
        full._transfer_live(
            source,
            transport,
            ledger,
            lambda: None,
            lambda: snapshots.append(ledger.receipt()),
            row,
        )
    assert response.position == 10
    assert [size for size, _ in response.reads] == [10]
    assert ledger.receipt()["total_received_bytes"] == 10
    assert any(item["active_response_reservation"] == 10 for item in snapshots)


class RecoveryResponse(LiveResponse):
    @property
    def body_complete(self):
        return self.position == len(self.body)


def recovery_fixture(tmp_path, *, signed_redirect=True):
    """Build fictional interrupted evidence and a distinct two-source approval."""
    original_policy, original_data, original_transport, payloads = live_fixture(
        tmp_path
    )
    original_transport.responses[full.LIVE_URLS["ofac_sdn"]] = LiveResponse(
        b"", status=302
    )
    eu_reads = 0

    def interrupt_eu_read():
        nonlocal eu_reads
        eu_reads += 1
        if eu_reads > 1:
            raise TimeoutError("fictional interruption")

    original_transport.responses[full.LIVE_URLS["eu_consolidated"]] = LiveResponse(
        payloads["eu_consolidated"][:10],
        headers={"content-length": str(len(payloads["eu_consolidated"]))},
        on_read=interrupt_eu_read,
    )
    run_live_fixture(tmp_path, original_policy, original_data, original_transport)
    original_run = tmp_path / "live-run"
    # This fixture models the durable journal state of a killed test worker.
    # Production code never removes or fabricates an original receipt.
    (original_run / "receipt.json").unlink()

    def ref(path):
        return {
            "path": path.relative_to(tmp_path).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def save(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")
        return ref(path)

    journal_files = sorted(original_run.glob("live-ledger-*.json"))
    snapshots = [(path, json.loads(path.read_bytes())) for path in journal_files]
    completed_path, completed_journal = next(
        (path, item)
        for path, item in snapshots
        if len(item["sources"]) == 1
        and item["sources"][0]["status"] == "passed"
        and item["ledger"]["active_source"] is None
        and item["ledger"]["active_request"] is None
    )
    journal_path, journal = next(
        (path, item)
        for path, item in reversed(snapshots)
        if item["ledger"]["active_request"] is not None
        and item["ledger"]["active_source"] == "eu_consolidated"
        and item["sources"][-1]["http_status"] == 200
        and item["sources"][-1]["bytes_received"] > 0
    )
    # Model termination at this actual pre-timeout durable snapshot. Only these
    # invented fixture outputs are trimmed; real acquisition history is immutable.
    for path, _ in snapshots:
        if path.name > journal_path.name:
            path.unlink()
    assert completed_journal["sources"][0] == journal["sources"][0]
    old_refs = {
        "policy": ref(original_run / "execution-policy.json"),
        "claim": ref(tmp_path / "session.claim.json"),
        "completed_journal": ref(completed_path),
        "selection": ref(original_run / "opensanctions_un.jsonl"),
        "permission": ref(tmp_path / original_data["sources"][0]["permission_path"]),
    }
    received = journal["ledger"]["total_received_bytes"]
    reserved = journal["ledger"]["active_response_reservation"]
    assessment = {
        "schema_version": 1,
        "scope": "08B-2-offline-interruption-assessment-v1",
        "artifact_kind": "interruption_assessment_not_acquisition_receipt",
        "assessment_status": "persisted_evidence_consistent",
        "claim": {
            "evidence": old_refs["claim"],
            "persisted_value": json.loads(
                (tmp_path / "session.claim.json").read_bytes()
            ),
            "session_consumed": True,
        },
        "policy": {"execution_policy_copy": old_refs["policy"]},
        "sources": [
            {"source_id": row["source_id"], "persisted_row": row}
            for row in journal["sources"]
        ],
        "artifact_state": {
            "final_acquisition_receipt_exists": False,
            "full_candidate_corpus_accepted": False,
        },
        "journals": {
            "last": ref(journal_path),
            "last_ledger": journal["ledger"],
        },
        "accounting": {
            "persisted_received_body_bytes_lower_bound": received,
            "conservative_active_response_reservation_bytes": reserved,
            "received_plus_reservation_bytes": received + reserved,
            "remaining_authorized_transactions": 0,
        },
    }
    old_refs["interruption_assessment"] = save(
        tmp_path / "interruption.json", assessment
    )
    approval = save(
        tmp_path / "recovery-approval.json",
        {"fictional": "test-only recovery approval; no real networking"},
    )
    policy = {
        "schema_version": 1,
        "scope": full.RECOVERY_POLICY_SCOPE,
        "approval": approval,
        "limits": dict(full.RECOVERY_LIMITS),
        "session_claim_path": "recovery.claim.json",
        "sources": [],
    }
    for original_source in original_data["sources"][1:]:
        source = dict(original_source)
        source_id = source["source_id"]
        source.update(
            transactions=2 if source_id == "ofac_sdn" else 1,
            content_length_required=True,
            expected_decoded_bytes=None,
        )
        source["allowed_redirects"] = (
            [full.RECOVERY_OFAC_REDIRECT] if source_id == "ofac_sdn" else []
        )
        if source_id == "ofac_sdn":
            with zipfile.ZipFile(io.BytesIO(payloads[source_id])) as archive:
                source["expected_decoded_bytes"] = len(archive.read("SDN.XML"))
        grant = json.loads((tmp_path / source["permission_path"]).read_bytes())
        grant["approval"] = approval
        grant["evidence"] = [approval]
        del grant["prospective_binding"]["require_complete_direct_200"]
        grant["prospective_binding"]["require_complete_approved_200"] = True
        grant_ref = save(tmp_path / ("recovery-" + source_id + ".grant.json"), grant)
        source["permission_path"], source["permission_sha256"] = (
            grant_ref["path"],
            grant_ref["sha256"],
        )
        policy["sources"].append(source)
    os_grant = json.loads((tmp_path / old_refs["permission"]["path"]).read_bytes())
    os_grant["approval"] = approval
    os_grant["evidence"] = [approval, *old_refs.values()]
    os_grant["recovery_binding"] = {
        "original_policy": old_refs["policy"],
        "original_claim": old_refs["claim"],
        "interruption_assessment": old_refs["interruption_assessment"],
        "completed_journal": old_refs["completed_journal"],
        "selection": old_refs["selection"],
        "original_permission": old_refs["permission"],
        "original_final_receipt_absent": True,
        "original_session_remains_interrupted": True,
        "cross_session_manifest_required": True,
    }
    recovery_grant = save(tmp_path / "opensanctions.recovery-grant.json", os_grant)
    policy["reuse_completed_source"] = {
        "source_id": "opensanctions_un",
        **old_refs,
        "recovery_permission": recovery_grant,
    }
    policy_path = tmp_path / "recovery-policy.json"
    save(policy_path, policy)
    redirect = full.RECOVERY_OFAC_REDIRECT
    if signed_redirect:
        redirect += "?" + urlencode(
            {
                "X-Amz-Expires": "300",
                "X-Amz-Security-Token": "fictional-security-token-never-persist",
                "response-content-disposition": "attachment; filename=SDN_XML.ZIP",
                "response-content-type": "application/zip",
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Credential": "ABCDEFGHIJKLMNOP/20261025/us-gov-west-1/s3/aws4_request",
                "X-Amz-Date": "20261025T010000Z",
                "X-Amz-SignedHeaders": "host",
                "X-Amz-Signature": "a" * 64,
            }
        )
    body = b"fictional redirect response"
    responses = {
        full.LIVE_URLS["ofac_sdn"]: RecoveryResponse(
            body,
            status=302,
            headers={"content-length": str(len(body)), "location": redirect},
        ),
        redirect: RecoveryResponse(payloads["ofac_sdn"]),
        full.LIVE_URLS["eu_consolidated"]: RecoveryResponse(
            payloads["eu_consolidated"]
        ),
    }
    return policy_path, policy, LiveTransport(responses), payloads


def run_recovery_fixture(tmp_path, policy_path, data, transport, **kwargs):
    resources = kwargs.pop("guard", None) or ResourceGuard(
        probe=lambda: ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False),
        initial_normalized_bytes=len(
            (
                tmp_path / data["reuse_completed_source"]["selection"]["path"]
            ).read_bytes()
        ),
    )
    return full.acquire_recovery(
        policy_path,
        tmp_path / "recovery-run",
        project_root=tmp_path,
        expected_policy_sha256=save_live_policy(policy_path, data),
        transport=transport,
        guard=resources,
        **kwargs,
    )


def test_recovery_reuses_completed_source_and_redacts_signed_redirect(tmp_path):
    policy_path, data, transport, payloads = recovery_fixture(tmp_path)
    original_paths = sorted((tmp_path / "live-run").iterdir())
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in original_paths
    }
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["scope"] == full.RECOVERY_SCOPE and receipt["status"] == "passed"
    assert len(transport.calls) == 3
    assert receipt["ledger"]["transactions"]["opensanctions_un"] == 0
    reused, ofac, eu = receipt["sources"]
    assert reused["acquisition_origin"] == "reused_completed_source"
    assert reused["transactions"] == [] and reused["transaction_count"] == 1
    assert ofac["transaction_count"] == 2 and eu["transaction_count"] == 1
    assert [tx["outcome"] for tx in ofac["transactions"]] == [
        "approved_redirect",
        "complete_200",
    ]
    assert ofac["transactions"][1]["signing_query_present"]
    assert ofac["final_url"] == full.RECOVERY_OFAC_REDIRECT
    assert ofac["bytes_received"] == len(payloads["ofac_sdn"]) + len(
        b"fictional redirect response"
    )
    assert ofac["input_bytes"] == len(payloads["ofac_sdn"])
    assert ofac["input_sha256"] == ofac["body_sha256"]
    assert receipt["recovery_accounting"]["unresolved_response_reservation_bytes"] == 0
    assert (
        receipt["recovery_accounting"]["received_body_bytes"]
        == ofac["bytes_received"] + eu["bytes_received"]
    )
    output = tmp_path / "recovery-run"
    for path in output.iterdir():
        assert b"fictional-security-token-never-persist" not in path.read_bytes()
        assert b"X-Amz-Signature" not in path.read_bytes()
    assert (output / "opensanctions_un.jsonl").read_bytes() == (
        tmp_path / data["reuse_completed_source"]["selection"]["path"]
    ).read_bytes()
    digest = hashlib.sha256((output / "receipt.json").read_bytes()).hexdigest()
    for source in full.LIVE_URLS:
        assert (
            json.loads((output / (source + ".purpose.json")).read_bytes())[
                "receipt_sha256"
            ]
            == digest
        )
    assert before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in original_paths
    }
    assert not (tmp_path / "live-run" / "receipt.json").exists()


@pytest.mark.parametrize(
    "fault", ["missing", "zero", "mismatch", "oversize", "duplicate", "ambiguous"]
)
def test_recovery_length_gate_stops_before_dataset_read_and_before_eu(tmp_path, fault):
    policy_path, data, transport, payloads = recovery_fixture(tmp_path)
    body = payloads["ofac_sdn"]
    headers = {
        "missing": {},
        "zero": {"content-length": "0"},
        "mismatch": {"content-length": str(len(body) + 1)},
        "oversize": {"content-length": "4000001"},
        "duplicate": {"content-length": "1, 1"},
        "ambiguous": {"content-length": str(len(body)), "transfer-encoding": "chunked"},
    }[fault]
    response = RecoveryResponse(body, headers=headers)
    transport.responses[full.LIVE_URLS["ofac_sdn"]] = response
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["status"] == "partial"
    assert response.reads == [] and response.closed
    assert len(transport.calls) == 1
    assert receipt["ledger"]["total_received_bytes"] == 0
    assert (
        receipt["recovery_accounting"]["unresolved_response_reservation_bytes"]
        == 4_000_000
    )
    assert not list((tmp_path / "recovery-run").glob("*.purpose.json"))


@pytest.mark.parametrize(
    "location",
    [
        "https://example.invalid/unapproved",
        full.RECOVERY_OFAC_REDIRECT.replace("2026-10-20", "2026-10-21"),
        full.RECOVERY_OFAC_REDIRECT + "?unsupported=secret",
    ],
)
def test_recovery_unapproved_redirect_body_is_charged_and_package_stops(
    tmp_path, location
):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    response = transport.responses[full.LIVE_URLS["ofac_sdn"]]
    response.headers["location"] = location
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["stop_reason"] == "unapproved_recovery_redirect"
    assert len(transport.calls) == 1
    assert receipt["ledger"]["total_received_bytes"] == len(response.body)
    assert receipt["recovery_accounting"]["unresolved_response_reservation_bytes"] == 0
    expected_target = location if location.endswith("/SDN_XML.ZIP") else None
    assert (
        receipt["sources"][1]["transactions"][0]["redirect_target"] == expected_target
    )


def test_recovery_records_changed_official_object_without_following_or_query_leak(
    tmp_path,
):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    response = transport.responses[full.LIVE_URLS["ofac_sdn"]]
    response.headers["location"] = response.headers["location"].replace(
        "2026-10-20", "2026-10-21"
    )
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    tx = receipt["sources"][1]["transactions"][0]
    assert receipt["status"] == "partial"
    assert tx["outcome"] == "rejected"
    assert tx["stop_reason"] == "unapproved_recovery_redirect"
    assert tx["redirect_target"] == full.RECOVERY_OFAC_REDIRECT.replace(
        "2026-10-20", "2026-10-21"
    )
    assert len(transport.calls) == 1
    assert receipt["ledger"]["transactions"]["eu_consolidated"] == 0
    assert receipt["ledger"]["total_received_bytes"] == len(response.body)
    for path in (tmp_path / "recovery-run").iterdir():
        payload = path.read_bytes()
        assert b"fictional-security-token-never-persist" not in payload
        assert b"X-Amz-Signature" not in payload
    assert not list((tmp_path / "recovery-run").glob("*.purpose.json"))


def test_recovery_incomplete_read_preserves_partial_bytes_and_reservation(tmp_path):
    policy_path, data, transport, payloads = recovery_fixture(tmp_path)
    partial = b"fictional partial response"
    response = RecoveryResponse(
        payloads["ofac_sdn"], error=http.client.IncompleteRead(partial, 10)
    )
    transport.responses[full.LIVE_URLS["ofac_sdn"]] = response
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["stop_reason"] == "incomplete_response"
    assert len(transport.calls) == 1
    tx = receipt["sources"][1]["transactions"][0]
    assert tx["bytes_received"] == len(partial)
    assert tx["body_sha256"] == hashlib.sha256(partial).hexdigest()
    assert tx["unresolved_response_reservation_bytes"] == 4_000_000 - len(partial)
    assert (
        receipt["recovery_accounting"]["received_plus_reservation_bytes"] == 4_000_000
    )


def test_recovery_declared_length_underreports_fictional_complete_body(tmp_path):
    policy_path, data, transport, payloads = recovery_fixture(tmp_path)
    response = RecoveryResponse(
        payloads["ofac_sdn"] + b"unframed",
        headers={"content-length": str(len(payloads["ofac_sdn"]))},
    )
    transport.responses[full.LIVE_URLS["ofac_sdn"]] = response
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["stop_reason"] == "declared_length_before_transport_eof"
    assert response.position == len(payloads["ofac_sdn"])
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "fault",
    ["changed_selection", "blocked_eu_grant", "old_final_receipt", "claim_reuse"],
)
def test_recovery_all_permissions_and_old_evidence_gate_before_claim(tmp_path, fault):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    if fault == "changed_selection":
        (tmp_path / data["reuse_completed_source"]["selection"]["path"]).write_bytes(
            b"changed"
        )
    elif fault == "blocked_eu_grant":
        source = data["sources"][1]
        path = tmp_path / source["permission_path"]
        grant = json.loads(path.read_bytes())
        grant["status"] = "blocked"
        source["permission_sha256"] = save_live_policy(path, grant)
    elif fault == "old_final_receipt":
        (tmp_path / "live-run" / "receipt.json").write_bytes(
            b"fictional existing final receipt"
        )
    else:
        data["session_claim_path"] = "session.claim.json"
    with pytest.raises(full.FullAcquisitionError):
        run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert transport.calls == []
    assert not (tmp_path / "recovery.claim.json").exists()


def test_recovery_claim_cannot_reset_with_new_output(tmp_path):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    run_recovery_fixture(tmp_path, policy_path, data, transport)
    before = (tmp_path / "recovery.claim.json").read_bytes()
    with pytest.raises(FileExistsError):
        full.acquire_recovery(
            policy_path,
            tmp_path / "another-recovery-output",
            project_root=tmp_path,
            expected_policy_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            transport=transport,
            guard=ResourceGuard(
                probe=lambda: ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False),
                initial_normalized_bytes=100_000,
            ),
        )
    assert len(transport.calls) == 3
    assert (tmp_path / "recovery.claim.json").read_bytes() == before


def test_recovery_decoded_size_pin_failure_stops_before_eu(tmp_path):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    data["sources"][0]["expected_decoded_bytes"] += 1
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    assert receipt["stop_reason"] == "publisher_decoded_size_mismatch"
    assert len(transport.calls) == 2
    assert not (tmp_path / "recovery-run" / "ofac_sdn.jsonl").exists()


@pytest.mark.parametrize("api", ["live", "recovery"])
@pytest.mark.parametrize("explicit_native", [False, True])
def test_native_tls_empty_trust_blocks_before_claim_or_request(
    tmp_path, monkeypatch, api, explicit_native
):
    if api == "recovery":
        policy_path, data, _, _ = recovery_fixture(tmp_path)
        resources = ResourceGuard(
            probe=lambda: ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False),
            initial_normalized_bytes=100_000,
        )
        acquire = full.acquire_recovery
    else:
        policy_path, data, _, _ = live_fixture(tmp_path)
        resources = guard()
        acquire = full.acquire_live
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert context.get_ca_certs(binary_form=True) == []
    monkeypatch.setattr(full.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(
        HTTPTransport,
        "open",
        lambda *args, **kwargs: pytest.fail("native open before valid TLS trust"),
    )
    with pytest.raises(full.FullAcquisitionError, match="tls_trust_store_empty"):
        acquire(
            policy_path,
            tmp_path / "blocked-tls-output",
            project_root=tmp_path,
            expected_policy_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            transport=HTTPTransport() if explicit_native else None,
            guard=resources,
        )
    assert not (tmp_path / data["session_claim_path"]).exists()
    assert not (tmp_path / "blocked-tls-output").exists()


@pytest.mark.parametrize("api", ["live", "recovery"])
def test_native_tls_trusted_configuration_passes_with_mocked_transport(
    tmp_path, monkeypatch, api
):
    fixture = recovery_fixture if api == "recovery" else live_fixture
    policy_path, data, fictional, _ = fixture(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Mock a loaded CA inventory and native open; no certificate installation
    # or TLS handshake is performed by this deterministic boundary test.
    monkeypatch.setattr(
        ssl.SSLContext,
        "get_ca_certs",
        lambda self, binary_form=False: [b"fictional loaded CA"],
    )
    monkeypatch.setattr(full.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(
        HTTPTransport,
        "open",
        lambda self, url, *, timeout: fictional.open(url, timeout=timeout),
    )
    if api == "recovery":
        receipt = run_recovery_fixture(tmp_path, policy_path, data, HTTPTransport())
    else:
        receipt = run_live_fixture(tmp_path, policy_path, data, HTTPTransport())
    assert receipt["status"] == "passed"
    assert len(fictional.calls) == 3


@pytest.mark.parametrize("disable_verification", [False, True])
def test_native_tls_insecure_configuration_is_rejected(
    monkeypatch, disable_verification
):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    if disable_verification:
        context.verify_mode = ssl.CERT_NONE
    monkeypatch.setattr(full.ssl, "create_default_context", lambda: context)
    with pytest.raises(full.FullAcquisitionError, match="tls_verification_required"):
        full._native_tls_preflight(HTTPTransport())


@pytest.mark.parametrize(
    "error,code",
    [
        (
            ssl.SSLCertVerificationError(1, "fictional-private-signing-value"),
            "tls_certificate_verification_failed",
        ),
        (
            ssl.SSLError(1, "fictional-private-signing-value"),
            "tls_handshake_or_io_failed",
        ),
        (
            socket.gaierror(-2, "fictional-private-signing-value"),
            "dns_resolution_failed",
        ),
        (
            ConnectionRefusedError("fictional-private-signing-value"),
            "connection_failed",
        ),
        (ConnectionResetError("fictional-private-signing-value"), "connection_failed"),
        (
            http.client.HTTPException("fictional-private-signing-value"),
            "http_framing_error",
        ),
        (full._FetchFailure("invalid_transfer_framing"), "http_framing_error"),
        (OSError("fictional-private-signing-value"), "transport_io_failed"),
    ],
)
def test_recovery_safe_transport_failure_codes_do_not_persist_exception_text(
    tmp_path, error, code
):
    policy_path, data, transport, _ = recovery_fixture(tmp_path)
    redirected_url = transport.responses[full.LIVE_URLS["ofac_sdn"]].headers["location"]
    transport.responses[redirected_url] = error
    receipt = run_recovery_fixture(tmp_path, policy_path, data, transport)
    tx = receipt["sources"][1]["transactions"][-1]
    assert receipt["status"] == "partial" and receipt["stop_reason"] == code
    assert tx["outcome"] == "rejected" and tx["stop_reason"] == code
    assert tx["http_status"] is None and tx["bytes_received"] == 0
    assert receipt["ledger"]["transactions"]["eu_consolidated"] == 0
    assert (
        receipt["recovery_accounting"]["received_plus_reservation_bytes"] == 4_000_000
    )
    assert len(transport.calls) == 2
    for path in (tmp_path / "recovery-run").iterdir():
        payload = path.read_bytes()
        assert b"fictional-private-signing-value" not in payload
        assert b"fictional-security-token-never-persist" not in payload
        assert b"X-Amz-Signature" not in payload


def continuation_fixture(tmp_path):
    """Preserve an actual fictional failed recovery, then authorize one new run."""
    prior_path, prior, transport, payloads = recovery_fixture(tmp_path)
    successful_responses = dict(transport.responses)
    transport.responses[full.LIVE_URLS["ofac_sdn"]] = OSError("fictional failure")
    run_recovery_fixture(tmp_path, prior_path, prior, transport)

    def ref(path):
        return {
            "path": path.relative_to(tmp_path).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def save(path, value):
        path.write_text(json.dumps(value))
        return ref(path)

    data = json.loads(json.dumps(prior))
    data["scope"] = full.CONTINUATION_POLICY_SCOPE
    data["limits"] = dict(full.CONTINUATION_LIMITS)
    data["session_claim_path"] = "continuation.claim.json"
    data["approval"] = save(
        tmp_path / "continuation-approval.json", {"fictional": True}
    )
    bundle = tmp_path / "fictional-ca.pem"
    bundle.write_text("fixture only; never used by native transport")
    data["continuation"] = {
        "policy": ref(prior_path),
        "receipt": ref(tmp_path / "recovery-run/receipt.json"),
        "claim": ref(tmp_path / prior["session_claim_path"]),
        "carried_reservation_bytes": 4_000_000,
        "prior_charged_transactions": 1,
        "cumulative_transaction_limit": 4,
        "recovery_ceiling_bytes": 34_000_000,
        "tls_ca_bundle": ref(bundle),
        "release_authorized": False,
    }
    for source in [
        *data["sources"],
        {
            "source_id": "opensanctions_un",
            "permission_path": data["reuse_completed_source"]["recovery_permission"][
                "path"
            ],
        },
    ]:
        grant = json.loads((tmp_path / source["permission_path"]).read_bytes())
        grant["approval"] = data["approval"]
        grant["evidence"].append(data["approval"])
        saved = save(
            tmp_path / ("continuation-" + source["source_id"] + ".json"), grant
        )
        if source["source_id"] == "opensanctions_un":
            data["reuse_completed_source"]["recovery_permission"] = saved
        else:
            source["permission_path"] = saved["path"]
            source["permission_sha256"] = saved["sha256"]
    path = tmp_path / "continuation-policy.json"
    save(path, data)
    return path, data, LiveTransport(successful_responses), payloads


def run_continuation_fixture(tmp_path, path, data, transport):
    return full.acquire_recovery(
        path,
        tmp_path / "continuation-run",
        project_root=tmp_path,
        expected_policy_sha256=save_live_policy(path, data),
        transport=transport,
        guard=ResourceGuard(
            probe=lambda: ResourceSnapshot(30_000_000, 20 * GIB, 0, 0.5, False),
            initial_normalized_bytes=2
            * len(
                (
                    tmp_path / data["reuse_completed_source"]["selection"]["path"]
                ).read_bytes()
            ),
        ),
    )


def test_continuation_preserves_reservation_history_and_forbids_release(tmp_path):
    path, data, transport, _ = continuation_fixture(tmp_path)
    old = {p: p.read_bytes() for p in (tmp_path / "recovery-run").iterdir()}
    receipt = run_continuation_fixture(tmp_path, path, data, transport)
    assert receipt["status"] == "passed"
    assert receipt["scope"] == full.CONTINUATION_SCOPE
    assert len(transport.calls) == 3
    assert receipt["ledger"]["tranche_bytes"] == 30_000_000
    accounting = receipt["recovery_accounting"]
    assert accounting["carried_prior_recovery_reservation_bytes"] == 4_000_000
    assert accounting["cumulative_recovery_transactions"] == 4
    assert (
        accounting["cumulative_recovery_accounted_bytes"]
        == 4_000_000 + receipt["ledger"]["total_received_bytes"]
    )
    assert not list((tmp_path / "continuation-run").glob("*.purpose.json"))
    assert all(p.read_bytes() == contents for p, contents in old.items())
    with pytest.raises(FileExistsError):
        run_continuation_fixture(tmp_path, path, data, transport)
    assert len(transport.calls) == 3


@pytest.mark.parametrize(
    "change",
    [
        "reservation",
        "ceiling",
        "transactions",
        "release",
        "history",
        "redirect",
        "bundle",
    ],
)
def test_continuation_rejects_invalid_binding_before_request(tmp_path, change):
    path, data, transport, _ = continuation_fixture(tmp_path)
    if change == "reservation":
        data["continuation"]["carried_reservation_bytes"] = 0
    elif change == "ceiling":
        data["limits"]["total_bytes"] = 34_000_000
    elif change == "transactions":
        data["limits"]["transactions"] = 4
    elif change == "release":
        data["continuation"]["release_authorized"] = True
    elif change == "history":
        (tmp_path / data["continuation"]["receipt"]["path"]).write_text("{}")
    elif change == "redirect":
        data["sources"][0]["allowed_redirects"] = []
    else:
        (tmp_path / data["continuation"]["tls_ca_bundle"]["path"]).write_text("changed")
    with pytest.raises(full.FullAcquisitionError):
        run_continuation_fixture(tmp_path, path, data, transport)
    assert not transport.calls
    assert not (tmp_path / "continuation.claim.json").exists()


def test_continuation_combined_cap_rejects_eu_before_body(tmp_path):
    path, data, transport, _ = continuation_fixture(tmp_path)
    response = transport.responses[full.LIVE_URLS["eu_consolidated"]]
    response.headers["content-length"] = "30000000"
    receipt = run_continuation_fixture(tmp_path, path, data, transport)
    assert receipt["status"] == "partial"
    assert response.position == 0
    assert len(transport.calls) == 3
    assert (
        receipt["recovery_accounting"]["cumulative_recovery_accounted_bytes"]
        <= 34_000_000
    )


def test_continuation_native_unselected_bundle_fails_before_claim(
    tmp_path, monkeypatch
):
    path, data, _, _ = continuation_fixture(tmp_path)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    with pytest.raises(full.FullAcquisitionError, match="tls_bundle_not_selected"):
        run_continuation_fixture(tmp_path, path, data, None)
    assert not (tmp_path / "continuation.claim.json").exists()
