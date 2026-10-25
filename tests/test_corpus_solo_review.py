"""Fictional solo feedback preserves provenance without granting real review rights."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading

import pytest

from watchlist import corpus_human_review as human_review
from watchlist import corpus_solo_review as solo
from watchlist.ingest.resource_guard import (
    GIB,
    ResourceGuard,
    ResourceSnapshot,
    ResourceStop,
)

from test_corpus_adjudication import FictionalAdjudication, replace_private
from test_corpus_human_review import (
    FictionalIntake,
    PilotHTML,
    many_observations,
    preparation as _human_preparation,
)
from test_readiness_review import digest, encoded, safe_guard, saved_tree


def multilingual_observations(observations):
    """Keep five authored records, with compact multilingual names and no weak aliases."""
    for record in observations:
        record["referents"] = []
        record["aliases"] = [
            alias
            for alias in record["aliases"]
            if alias["evidence_id"] != "fictional-name-b2"
        ]
        for alias in record["aliases"]:
            alias["attributes"] = []
            if "weak" in alias["field"].lower():
                alias["field"] = "properties.alias"
        if record["observation_id"] == "fictional-observation-a":
            record["aliases"].extend(
                {
                    "evidence_id": "fictional-name-" + suffix,
                    "value": text,
                    "field": "properties.alias",
                    "language": language,
                    "attributes": [],
                }
                for suffix, text, language in (
                    ("a4", "بستان خيالي", "ar"),
                    ("a5", "Вымышленный сад", "ru"),
                )
            )


class FictionalSoloIntake:
    """Build isolated H1 evidence, a separate solo packet and one fictional owner."""

    def __init__(self, source, *, declaration_mutator=None, create=True):
        self.source = source
        self.root = source.root
        self.h1 = FictionalIntake(source, create=False)
        self.artifacts = self.root / "solo-review-artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.packet_path = self.artifacts / "packet"
        self.packet_sha256 = solo.write_fictional_packet(
            self.h1.pilot_path,
            self.packet_path,
            expected_h1_sha256=self.h1.pilot_sha256,
            project_root=self.root,
            guard=safe_guard(),
        )
        self.packet, _ = solo._load_packet(self.packet_path, self.packet_sha256)
        self.ledger_path = self.artifacts / "ledger"
        self.declaration = {
            "owner": {
                "actor_id": "fictional-solo-owner",
                "principal_id": "fictional-solo-principal",
                "display_name": "Fictional solo researcher",
                "attestation_ref": "fictional-owner-attestation",
                "competencies": sorted(
                    {
                        item
                        for case in self.packet["cases"]
                        for item in case["required_competencies"]
                    }
                ),
                "declared_at": "2026-10-25T11:00:00+00:00",
            },
            "protocol_version": "solo-review-protocol-v1",
            "scope": "development_pilot",
            "retention_ref": "fictional-retention-policy",
            "real_execution_approval_ref": None,
            "identity_verification_status": "fictional_owner_attestation",
        }
        if declaration_mutator is not None:
            declaration_mutator(self.declaration)
        self.head = None
        self.serial = 0
        if create:
            self.create()

    def create(self, **overrides):
        self.head = solo.create_ledger(
            self.packet_path,
            self.ledger_path,
            **{
                "expected_packet_sha256": self.packet_sha256,
                "declaration": self.declaration,
                "project_root": self.root,
                "guard": safe_guard(),
                **overrides,
            },
        )
        return self.head

    def context(self, **overrides):
        return {
            "packet_path": self.packet_path,
            "expected_packet_sha256": self.packet_sha256,
            "expected_head": self.head,
            "declaration": self.declaration,
            "project_root": self.root,
            "guard": safe_guard(),
            **overrides,
        }

    def replay(self, **overrides):
        return solo.replay_ledger(self.ledger_path, **self.context(**overrides))

    def case(self, kind="proposed_positive"):
        h1_ids = {
            item["case_id"]
            for item in self.h1.pilot["cases"]
            if self.source.cases[item["c2_case_id"]]["kind"] == kind
        }
        return next(case for case in self.packet["cases"] if case["case_id"] in h1_ids)

    def payload(self, case=None, **overrides):
        case = case or self.case()
        self.serial += 1
        template = solo.export_template(
            self.packet_path,
            case_id=case["case_id"],
            expected_packet_sha256=self.packet_sha256,
            project_root=self.root,
            guard=safe_guard(),
        )
        return {
            **template,
            "submission_id": f"fictional-solo-submission-{self.serial}",
            "actor_id": self.declaration["owner"]["actor_id"],
            "outcome": "supported_same",
            "target_scope": "publisher_record"
            if len(case["observations"]) == 1
            else "cross_record_identity",
            "rationale": "Fictional evidence inspected by the single fixture owner.",
            "evidence_refs": list(case["evidence_refs"]),
            "evidence_versions": {
                ref: case["evidence_versions"][ref] for ref in case["evidence_refs"]
            },
            "evidence_origin": "synthetic_derivation",
            "review_origin": "single_human",
            "review_label": "single-reviewer development feedback",
            "created_at": (
                datetime(2026, 10, 25, 11, 1, tzinfo=timezone.utc)
                + timedelta(seconds=self.serial)
            ).isoformat(),
            "origin": "fictional_human",
            "uncertain": False,
            "conflict_declared": False,
            "duration_seconds": 30,
            "relationship_annotation": "unresolved",
            "direction": {
                "query_evidence_id": None,
                "reference_evidence_id": None,
                "adequacy": "unresolved",
            },
            "supersedes": None,
            "correction_reason": None,
            **overrides,
        }

    def submit(self, payload, **overrides):
        self.head = solo.append_submission(
            self.ledger_path, payload, **self.context(**overrides)
        )
        return self.head


class FictionalConfiguredSolo:
    """Use authored inputs to exercise the real-mode blank preparation gate."""

    def __init__(self, h1):
        self.h1 = h1
        self.root = h1.root
        h1.prepare()
        self.artifacts = self.root / "solo-review-artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.output = self.artifacts / "packet"
        self.ledger_path = self.artifacts / "ledger"
        self.config_path = self.root / "config" / "corpus-solo-review-v1.json"
        self.config = {
            "schema_version": 1,
            "scope": "08-SOLO-I-offline-solo-intake",
            "h1": {
                "configuration": {
                    "path": h1.config_path.relative_to(self.root).as_posix(),
                    "sha256": digest(h1.config_path.read_bytes()),
                },
                "manifest": {
                    "path": (h1.output / "manifest.json")
                    .relative_to(self.root)
                    .as_posix(),
                    "sha256": digest((h1.output / "manifest.json").read_bytes()),
                },
            },
            "output_path": self.output.relative_to(self.root).as_posix(),
            "ledger_path": self.ledger_path.relative_to(self.root).as_posix(),
            "artifact_roots": [*h1.config["artifact_roots"], "solo-review-artifacts"],
            "limits": dict(human_review.LIMITS),
            "permissions": deepcopy(h1.config["permissions"]),
            "versions": {
                "packet": "solo-review-packet-v1",
                "ledger": "solo-review-ledger-v1",
                "protocol": "solo-review-protocol-v1",
            },
            "metadata": {
                "created_at": "2026-10-25T11:00:00+00:00",
                "creator": "codex-offline-preparation",
                "approval_ref": "user-approved-SOLO-I",
            },
            "declaration": deepcopy(solo.BLANK_DECLARATION),
            "expected_counts": {
                "pilot_cases": 40,
                "actual_submissions": 0,
                "accepted_labels": 0,
            },
        }
        self.save_config()

    def save_config(self):
        self.config_path.write_bytes(encoded(self.config))

    def prepare(self, **overrides):
        return solo.prepare_solo_review(
            self.config_path,
            self.output,
            **{"project_root": self.root, "guard": safe_guard(), **overrides},
        )

    def validate(self, **overrides):
        return solo.validate_solo_review(
            self.output,
            **{
                "config_path": self.config_path,
                "project_root": self.root,
                "guard": safe_guard(),
                **overrides,
            },
        )


def make_browser_fixture(root):
    """Create a disposable multilingual blank form using only authored evidence.

    A caller may import this helper with ``PYTHONPATH=src:tests`` and pass an
    empty temporary path. No actual corpus or network access is involved.
    The returned fixture exposes its packet, ledger and pin for draft validation.
    """
    source = FictionalAdjudication(Path(root), mutate=multilingual_observations)
    return FictionalSoloIntake(source)


@pytest.fixture(autouse=True)
def no_fixture_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("solo review tests may not access the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def source(tmp_path):
    return FictionalAdjudication(
        tmp_path / "fictional-solo-source", mutate=multilingual_observations
    )


@pytest.fixture
def intake(source):
    return FictionalSoloIntake(source)


@pytest.fixture
def human_preparation(tmp_path, monkeypatch):
    return _human_preparation.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def preparation(human_preparation):
    return FictionalConfiguredSolo(human_preparation)


def test_exact_forty_case_selection_and_prior_histories_are_preserved(tmp_path):
    source = FictionalAdjudication(
        tmp_path / "fictional-forty-case-solo", mutate=many_observations
    )
    before = saved_tree(source.artifacts)
    intake = FictionalSoloIntake(source)
    h1_cases = {case["case_id"]: case for case in intake.h1.pilot["cases"]}
    assert len(intake.packet["cases"]) == len(h1_cases) == 40
    for case in intake.packet["cases"]:
        old = h1_cases[case["case_id"]]
        assert case["case_sha256"] == old["case_sha256"]
        assert [item["observation_id"] for item in case["observations"]] == old[
            "observation_ids"
        ]
        assert case["evidence_refs"] == old["evidence_refs"]
    assert saved_tree(source.artifacts) == before
    assert intake.replay()["event_count"] == 0
    assert intake.h1.pilot_sha256 in json.dumps(intake.packet["source"])


def test_initial_ledger_and_blank_template_cannot_claim_independent_review(intake):
    before = saved_tree(intake.h1.pilot_path)
    result = intake.replay()
    assert result["event_count"] == result["inspected_case_count"] == 0
    assert result["accepted_labels"] == result["identity_merges"] == 0
    assert result["independent_human_reviews"] == 0
    assert result["accepted_corpus_release"] is False
    assert result["actual_partitions"] == []
    template = solo.export_template(
        intake.packet_path,
        case_id=intake.case()["case_id"],
        expected_packet_sha256=intake.packet_sha256,
        project_root=intake.root,
        guard=safe_guard(),
    )
    assert template["outcome"] is None
    assert template["review_origin"] == "single_human"
    assert template["evidence_origin"] == "synthetic_derivation"
    assert template["review_label"] == "single-reviewer development feedback"
    assert (
        not {"adjudication_id", "independent_first_pass", "accepted_label"}
        & template.keys()
    )
    assert saved_tree(intake.h1.pilot_path) == before


def test_source_evidence_and_single_human_origin_remain_separate(intake):
    payload = intake.payload()
    intake.submit(payload)
    result = intake.replay()
    assert result == intake.replay()
    state = result["case_states"][payload["case_id"]]
    assert state["active_submission_id"] == payload["submission_id"]
    assert state["outcome"] == "supported_same"
    assert state["release_blocked"] is True
    event = json.loads(
        (intake.ledger_path / "events" / "000000000001.json").read_bytes()
    )
    assert event["payload"]["evidence_origin"] == "synthetic_derivation"
    assert event["payload"]["review_origin"] == "single_human"
    assert result["accepted_labels"] == result["independent_human_reviews"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("review_origin", "independently_reviewed_humans"),
        ("review_origin", "none"),
        ("review_label", "independent adjudication"),
        ("evidence_origin", "publisher_assertion"),
        ("evidence_origin", "independent_documentary_evidence"),
        ("origin", "human"),
        ("independent_first_pass", True),
        ("adjudication_id", "fictional-self-adjudication"),
        ("accepted_label", True),
    ],
)
def test_provenance_misclassification_and_extra_authority_are_rejected(
    intake, field, value
):
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.submit(intake.payload(**{field: value}))
    assert saved_tree(intake.ledger_path) == before


@pytest.mark.parametrize(
    "change",
    [
        "second_owner",
        "missing_attestation",
        "real_actor",
        "naive_time",
        "future_approval",
        "fake_verification",
    ],
)
def test_owner_declaration_is_explicit_single_and_has_no_real_execution_rights(
    source, change
):
    def mutate(declaration):
        if change == "second_owner":
            declaration["owners"] = [deepcopy(declaration["owner"])]
        elif change == "missing_attestation":
            declaration["owner"]["attestation_ref"] = None
        elif change == "real_actor":
            declaration["owner"]["actor_id"] = "real-owner"
        elif change == "naive_time":
            declaration["owner"]["declared_at"] = "2026-10-25T11:00:00"
        elif change == "future_approval":
            declaration["real_execution_approval_ref"] = "fictional-solo-e-approval"
        else:
            declaration["identity_verification_status"] = "independently_verified"

    intake = FictionalSoloIntake(source, declaration_mutator=mutate, create=False)
    with pytest.raises(ValueError):
        intake.create()
    assert not (intake.ledger_path / "header.json").exists()


def test_distinction_requires_documentary_evidence_for_both_records(intake):
    case = intake.case("negative_candidate")
    payload = intake.payload(case, outcome="supported_distinct")
    intake.submit(payload)
    assert (
        intake.replay()["case_states"][case["case_id"]]["outcome"]
        == "supported_distinct"
    )
    assert intake.replay()["accepted_labels"] == 0


@pytest.mark.parametrize(
    "claim", ["different IDs", "name mismatch", "low similarity score", "not found"]
)
def test_name_or_identifier_difference_cannot_replace_negative_identity_evidence(
    intake, claim
):
    case = intake.case("negative_candidate")
    identity = {ref for refs in case["identity_evidence_refs"].values() for ref in refs}
    payload = intake.payload(case, outcome="supported_distinct", rationale=claim)
    payload["evidence_refs"] = [
        ref for ref in payload["evidence_refs"] if ref not in identity
    ]
    payload["evidence_versions"] = {
        ref: payload["evidence_versions"][ref] for ref in payload["evidence_refs"]
    }
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.submit(payload)
    assert saved_tree(intake.ledger_path) == before


def test_one_endpoints_identity_evidence_is_not_a_negative_witness(intake):
    case = intake.case("negative_candidate")
    omitted = set(next(iter(case["identity_evidence_refs"].values())))
    payload = intake.payload(case, outcome="supported_distinct")
    payload["evidence_refs"] = [
        ref for ref in payload["evidence_refs"] if ref not in omitted
    ]
    payload["evidence_versions"] = {
        ref: payload["evidence_versions"][ref] for ref in payload["evidence_refs"]
    }
    with pytest.raises(ValueError):
        intake.submit(payload)
    assert intake.replay()["event_count"] == 0


def test_missing_linguistic_competence_allows_only_an_unresolved_review(source):
    def without_languages(declaration):
        declaration["owner"]["competencies"] = ["record_review"]

    intake = FictionalSoloIntake(source, declaration_mutator=without_languages)
    case = next(
        case
        for case in intake.packet["cases"]
        if "script:ARABIC" in case["required_competencies"]
    )
    with pytest.raises(ValueError):
        intake.submit(intake.payload(case))
    payload = intake.payload(
        case, outcome="insufficient_evidence", target_scope="unresolved", uncertain=True
    )
    intake.submit(payload)
    assert (
        intake.replay()["case_states"][case["case_id"]]["outcome"]
        == "insufficient_evidence"
    )
    correction = intake.payload(
        case,
        outcome="insufficient_evidence",
        target_scope="unresolved",
        uncertain=True,
        relationship_annotation="translation",
        supersedes=payload["submission_id"],
        correction_reason="Fictional attempted language judgment without competence.",
    )
    with pytest.raises(ValueError):
        intake.submit(correction)
    assert intake.replay()["event_count"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "actor",
        "packet_pin",
        "case_pin",
        "evidence",
        "evidence_version",
        "missing_version",
        "wrong_scope",
        "uncertain",
        "conflict",
        "duration_zero",
        "duration_bool",
        "naive_time",
        "time_before_declaration",
    ],
)
def test_invalid_bindings_and_inconsistent_claims_never_append(intake, change):
    payload = intake.payload()
    if change == "actor":
        payload["actor_id"] = "fictional-other-owner"
    elif change == "packet_pin":
        payload["packet_sha256"] = "0" * 64
    elif change == "case_pin":
        payload["case_sha256"] = "0" * 64
    elif change == "evidence":
        payload["evidence_refs"] = ["fictional-unrelated-evidence"]
    elif change == "evidence_version":
        payload["evidence_versions"][payload["evidence_refs"][0]] = "0" * 64
    elif change == "missing_version":
        payload["evidence_versions"].pop(payload["evidence_refs"][0])
    elif change == "wrong_scope":
        payload["target_scope"] = "cross_record_identity"
    elif change in {"uncertain", "conflict"}:
        payload["uncertain" if change == "uncertain" else "conflict_declared"] = True
    elif change.startswith("duration_"):
        payload["duration_seconds"] = 0 if change == "duration_zero" else True
    elif change == "naive_time":
        payload["created_at"] = "2026-10-25T11:01:00"
    else:
        payload["created_at"] = "2026-10-25T10:59:00+00:00"
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.submit(payload)
    assert saved_tree(intake.ledger_path) == before


def test_corrections_append_and_preserve_the_first_judgment(intake):
    first = intake.payload()
    intake.submit(first)
    original = saved_tree(intake.ledger_path / "events")
    corrected = intake.payload(
        outcome="insufficient_evidence",
        target_scope="unresolved",
        uncertain=True,
        supersedes=first["submission_id"],
        correction_reason="Fictional evidence was insufficient after reinspection.",
    )
    intake.submit(corrected)
    result = intake.replay()
    assert result["event_count"] == result["submission_count"] == 2
    assert result["correction_count"] == result["inspected_case_count"] == 1
    assert (
        result["case_states"][first["case_id"]]["active_submission_id"]
        == corrected["submission_id"]
    )
    for name, raw in original.items():
        assert (intake.ledger_path / "events" / name).read_bytes() == raw
    assert result["independent_human_reviews"] == result["accepted_labels"] == 0


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_case",
        "duplicate_id",
        "unknown_prior",
        "missing_reason",
        "reason_without_prior",
        "other_case",
    ],
)
def test_duplicate_or_invalid_supersession_cannot_replace_history(intake, change):
    first = intake.payload()
    intake.submit(first)
    payload = intake.payload(
        supersedes=first["submission_id"], correction_reason="Fictional correction."
    )
    if change == "duplicate_case":
        payload["supersedes"] = payload["correction_reason"] = None
    elif change == "duplicate_id":
        payload["submission_id"] = first["submission_id"]
    elif change == "unknown_prior":
        payload["supersedes"] = "fictional-unknown-submission"
    elif change == "missing_reason":
        payload["correction_reason"] = None
    elif change == "reason_without_prior":
        payload["supersedes"] = None
    else:
        payload = intake.payload(
            intake.case("negative_candidate"),
            supersedes=first["submission_id"],
            correction_reason="Fictional cross-case correction.",
        )
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.submit(payload)
    assert saved_tree(intake.ledger_path) == before


def test_stale_head_and_changed_owner_declaration_cannot_authorize_new_events(intake):
    stale = intake.head
    intake.submit(intake.payload())
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.replay(expected_head=stale)
    with pytest.raises(ValueError):
        intake.submit(
            intake.payload(intake.case("negative_candidate")), expected_head=stale
        )
    changed = deepcopy(intake.declaration)
    changed["owner"]["principal_id"] = "fictional-new-owner"
    with pytest.raises(ValueError):
        intake.replay(declaration=changed)
    assert saved_tree(intake.ledger_path) == before


@pytest.mark.parametrize(
    "change", ["content", "rehash", "truncate", "partial", "nonprivate"]
)
def test_corruption_and_history_truncation_are_detected_against_external_head(
    intake, change
):
    intake.submit(intake.payload())
    path = intake.ledger_path / "events" / "000000000001.json"
    if change == "truncate":
        path.unlink()
    elif change == "partial":
        (path.parent / "000000000002.json").write_bytes(b'{"schema_version":')
    elif change == "nonprivate":
        path.chmod(0o644)
    elif change == "content":
        replace_private(path, path.read_bytes() + b"\n")
    else:
        event = json.loads(path.read_bytes())
        event["payload"]["rationale"] = "Fictional rewritten history."
        event["event_sha256"] = digest(
            encoded(
                {key: value for key, value in event.items() if key != "event_sha256"}
            )
        )
        replace_private(path, encoded(event))
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.replay()
    assert saved_tree(intake.ledger_path) == before


@pytest.mark.parametrize("after_publication", [False, True])
def test_interrupted_append_keeps_the_external_head_acknowledgment_boundary(
    intake, monkeypatch, after_publication
):
    original = solo._write_payload
    previous_head = intake.head

    def interrupted(directory_fd, name, payload):
        if name == "000000000001.json":
            if after_publication:
                original(directory_fd, name, payload)
            raise OSError("fictional interrupted solo append")
        original(directory_fd, name, payload)

    monkeypatch.setattr(solo, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional interrupted solo append"):
        intake.submit(intake.payload())
    assert intake.head == previous_head
    if after_publication:
        with pytest.raises(ValueError):
            intake.replay()
        event = json.loads(
            (intake.ledger_path / "events" / "000000000001.json").read_bytes()
        )
        assert intake.replay(expected_head=event["event_sha256"])["event_count"] == 1
    else:
        assert intake.replay()["event_count"] == 0


def test_competing_writers_using_one_head_publish_one_event(intake):
    payloads = [intake.payload(), intake.payload(intake.case("negative_candidate"))]
    context = intake.context()
    barrier = threading.Barrier(2)

    def append(payload):
        barrier.wait(timeout=5)
        try:
            return solo.append_submission(
                intake.ledger_path, payload, **{**context, "guard": safe_guard()}
            )
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, payloads))
    winners = [result for result in outcomes if isinstance(result, str)]
    assert len(winners) == 1
    assert sum(isinstance(result, ValueError) for result in outcomes) == 1
    assert intake.replay(expected_head=winners[0])["event_count"] == 1


@pytest.mark.parametrize("target", ["packet", "ledger", "event"])
def test_symlink_inputs_are_rejected_without_changing_targets(intake, target):
    intake.submit(intake.payload())
    path, overrides = intake.ledger_path, {}
    if target in {"packet", "ledger"}:
        original = intake.packet_path if target == "packet" else intake.ledger_path
        link = intake.root / ("fictional-linked-" + target)
        link.symlink_to(original, target_is_directory=True)
        if target == "packet":
            overrides["packet_path"] = link
        else:
            path = link
    else:
        saved = intake.ledger_path / "events" / "000000000001.json"
        outside = intake.root / "fictional-external-event.json"
        outside.write_bytes(saved.read_bytes())
        saved.unlink()
        saved.symlink_to(outside)
    before = saved_tree(intake.root)
    with pytest.raises((ValueError, OSError)):
        solo.replay_ledger(path, **intake.context(**overrides))
    assert saved_tree(intake.root) == before


def test_private_artifacts_cannot_be_overwritten(intake):
    assert stat.S_IMODE(intake.ledger_path.stat().st_mode) == 0o700
    for path in intake.ledger_path.rglob("*"):
        if path.is_file() and path.name != ".lock":
            assert stat.S_IMODE(path.stat().st_mode) & 0o277 == 0
    before = saved_tree(intake.ledger_path)
    with pytest.raises(FileExistsError):
        intake.create()
    assert saved_tree(intake.ledger_path) == before


def test_resource_stop_occurs_before_a_submission_is_written(intake):
    before = saved_tree(intake.ledger_path)
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, GIB, 0, 0.5, False)
    )
    with pytest.raises(ResourceStop):
        intake.submit(intake.payload(), guard=guard)
    assert saved_tree(intake.ledger_path) == before


@pytest.mark.parametrize("target", ["packet", "h1"])
def test_changed_evidence_invalidates_replay_and_append(intake, target):
    path = (
        intake.packet_path if target == "packet" else intake.h1.pilot_path
    ) / "manifest.json"
    replace_private(path, path.read_bytes() + b"\n")
    before = saved_tree(intake.ledger_path)
    with pytest.raises(ValueError):
        intake.replay()
    with pytest.raises(ValueError):
        solo.append_submission(intake.ledger_path, {}, **intake.context())
    assert saved_tree(intake.ledger_path) == before


def test_final_resource_callback_cannot_replace_evidence_before_header_commit(
    source, monkeypatch
):
    intake = FictionalSoloIntake(source, create=False)
    guard = safe_guard()
    original = guard.check
    changed = []

    def change_when_staged(*args, **kwargs):
        result = original(*args, **kwargs)
        if not changed and intake.ledger_path.exists():
            path = intake.h1.pilot_path / "manifest.json"
            replace_private(path, path.read_bytes() + b"\n")
            changed.append(True)
        return result

    monkeypatch.setattr(guard, "check", change_when_staged)
    with pytest.raises(ValueError):
        intake.create(guard=guard)
    assert changed == [True]
    assert not (intake.ledger_path / "header.json").exists()


def test_caller_payload_is_snapshotted_before_resource_callbacks(intake, monkeypatch):
    payload = intake.payload()
    original_payload = deepcopy(payload)
    guard = safe_guard()
    original = guard.check
    changed = []

    def mutate_caller(*args, **kwargs):
        result = original(*args, **kwargs)
        if not changed:
            payload["review_origin"] = "independently_reviewed_humans"
            payload["rationale"] = "Fictional caller mutation after invocation."
            payload["evidence_versions"].clear()
            changed.append(True)
        return result

    monkeypatch.setattr(guard, "check", mutate_caller)
    intake.submit(payload, guard=guard)
    event = json.loads(
        (intake.ledger_path / "events" / "000000000001.json").read_bytes()
    )
    assert changed == [True]
    assert event["payload"] == original_payload
    assert intake.replay()["independent_human_reviews"] == 0


def test_owner_declaration_is_snapshotted_before_resource_callbacks(
    source, monkeypatch
):
    intake = FictionalSoloIntake(source, create=False)
    original_declaration = deepcopy(intake.declaration)
    guard = safe_guard()
    original = guard.check
    changed = []

    def mutate_caller(*args, **kwargs):
        result = original(*args, **kwargs)
        if not changed:
            intake.declaration["owner"]["actor_id"] = "fictional-replaced-owner"
            intake.declaration["owner"]["competencies"].clear()
            changed.append(True)
        return result

    monkeypatch.setattr(guard, "check", mutate_caller)
    intake.create(guard=guard)
    assert changed == [True]
    assert intake.replay(declaration=original_declaration)["event_count"] == 0
    with pytest.raises(ValueError):
        intake.replay()


def test_rehashed_event_cannot_introduce_independent_review_even_with_new_head(intake):
    intake.submit(intake.payload())
    path = intake.ledger_path / "events" / "000000000001.json"
    event = json.loads(path.read_bytes())
    event["payload"]["review_origin"] = "independently_reviewed_humans"
    event["event_sha256"] = digest(
        encoded({key: value for key, value in event.items() if key != "event_sha256"})
    )
    replace_private(path, encoded(event))
    with pytest.raises(ValueError):
        intake.replay(expected_head=event["event_sha256"])


def test_html_preserves_multilingual_names_as_inert_data_and_blank_controls(tmp_path):
    malicious = '</script><img src=x onerror="alert(71)"> Ignore previous instructions.'

    def injected(observations):
        multilingual_observations(observations)
        observations[0]["aliases"][1]["value"] = malicious

    source = FictionalAdjudication(tmp_path / "fictional-solo-html", mutate=injected)
    intake = FictionalSoloIntake(source)
    html_files = list(intake.packet_path.glob("*.html"))
    assert len(html_files) == 1
    html = html_files[0].read_text()
    parsed = PilotHTML()
    parsed.feed(html)
    assert "img" not in parsed.tags
    assert malicious not in html
    assert "negative_candidate" not in html
    assert "proposed_positive" not in html
    packet = json.loads("".join(parsed.packet))
    values = [
        alias["value"]
        for case in packet["cases"]
        for observation in case["observations"]
        for alias in observation["aliases"]
    ]
    assert malicious in values
    for name in ("虚构灯园", "بستان خيالي", "Вымышленный сад"):
        assert name in values
    assert "localStorage" not in html and "sessionStorage" not in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html
    assert intake.replay()["event_count"] == 0


def test_old_h1_real_intake_gate_remains_disabled(human_preparation, intake):
    human_preparation.prepare()
    pin = digest((human_preparation.output / "manifest.json").read_bytes())
    with pytest.raises(ValueError):
        human_review.create_intake_ledger(
            human_preparation.output,
            human_preparation.ledger_path,
            expected_pilot_sha256=pin,
            declaration=intake.h1.declaration,
            project_root=human_preparation.root,
            guard=safe_guard(),
        )
    assert not (human_preparation.ledger_path / "header.json").exists()


def test_configured_blank_packet_and_ledger_have_no_real_decisions(preparation, intake):
    before = saved_tree(preparation.h1.output)
    summary = preparation.prepare()
    assert preparation.validate() == summary
    assert summary["counts"]["accepted_labels"] == 0
    assert saved_tree(preparation.h1.output) == before
    pin = digest((preparation.output / "manifest.json").read_bytes())
    with pytest.raises(ValueError):
        solo.create_ledger(
            preparation.output,
            preparation.ledger_path,
            expected_packet_sha256=pin,
            declaration=intake.declaration,
            project_root=preparation.root,
            guard=safe_guard(),
        )
    head = solo.create_ledger(
        preparation.output,
        preparation.ledger_path,
        expected_packet_sha256=pin,
        declaration=preparation.config["declaration"],
        project_root=preparation.root,
        guard=safe_guard(),
    )
    context = {
        "packet_path": preparation.output,
        "expected_packet_sha256": pin,
        "expected_head": head,
        "declaration": preparation.config["declaration"],
        "project_root": preparation.root,
        "guard": safe_guard(),
    }
    result = solo.replay_ledger(preparation.ledger_path, **context)
    assert result["event_count"] == result["accepted_labels"] == 0
    saved = saved_tree(preparation.ledger_path)
    with pytest.raises(ValueError):
        solo.append_submission(preparation.ledger_path, intake.payload(), **context)
    assert saved_tree(preparation.ledger_path) == saved
    with pytest.raises(ValueError):
        solo.write_fictional_packet(
            preparation.h1.output,
            preparation.artifacts / "fictional-laundering-attempt",
            expected_h1_sha256=digest(
                (preparation.h1.output / "manifest.json").read_bytes()
            ),
            project_root=preparation.root,
            guard=safe_guard(),
        )


@pytest.mark.parametrize(
    "change",
    [
        "execution_approval",
        "permission",
        "event_bytes",
        "artifact_bytes",
        "deadline",
        "overlapping_root",
    ],
)
def test_configuration_cannot_expand_approved_scope_or_limits(preparation, change):
    if change == "execution_approval":
        preparation.config["declaration"]["real_execution_approval_ref"] = (
            "user-approved-SOLO-E"
        )
    elif change == "permission":
        preparation.config["permissions"][
            next(iter(preparation.config["permissions"]))
        ] = True
    elif change == "event_bytes":
        preparation.config["limits"]["max_event_bytes"] += 1
    elif change == "artifact_bytes":
        preparation.config["limits"]["max_new_artifact_bytes"] += 1
    elif change == "deadline":
        preparation.config["limits"]["session_seconds"] += 1
    else:
        preparation.config["artifact_roots"][-1] = preparation.h1.config[
            "artifact_roots"
        ][-1]
    preparation.save_config()
    before = saved_tree(preparation.artifacts)
    with pytest.raises(ValueError):
        preparation.prepare()
    assert saved_tree(preparation.artifacts) == before


def test_interrupted_packet_write_has_no_manifest_and_preserves_partial_work(
    preparation, monkeypatch
):
    original = solo._write_payload
    written = []

    def interrupted(directory_fd, name, payload):
        original(directory_fd, name, payload)
        written.append(name)
        if name != "manifest.json":
            raise OSError("fictional interrupted solo packet")

    monkeypatch.setattr(solo, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional interrupted solo packet"):
        preparation.prepare()
    assert written
    assert not (preparation.output / "manifest.json").exists()
    saved = saved_tree(preparation.output)
    monkeypatch.setattr(solo, "_write_payload", original)
    with pytest.raises(FileExistsError):
        preparation.prepare()
    assert saved_tree(preparation.output) == saved


@pytest.mark.parametrize("kind", ["outside", "symlink", "traversal"])
def test_packet_output_paths_cannot_escape_or_follow_links(source, kind):
    h1 = FictionalIntake(source, create=False)
    external = source.root.parent / "fictional-external"
    external.mkdir(mode=0o700)
    sentinel = external / "sentinel.txt"
    sentinel.write_text("Fictional untouched sentinel")
    if kind == "outside":
        output = external / "packet"
    elif kind == "symlink":
        linked = source.root / "fictional-linked-parent"
        linked.symlink_to(external, target_is_directory=True)
        output = linked / "packet"
    else:
        output = source.root / "fictional-unused" / ".." / "packet"
    before = saved_tree(external)
    with pytest.raises((ValueError, OSError)):
        solo.write_fictional_packet(
            h1.pilot_path,
            output,
            expected_h1_sha256=h1.pilot_sha256,
            project_root=source.root,
            guard=safe_guard(),
        )
    assert saved_tree(external) == before


def export_arguments(intake, output):
    return [
        "--project-root",
        str(intake.root),
        "export-template",
        "--packet",
        str(intake.packet_path),
        "--packet-sha256",
        intake.packet_sha256,
        "--case-id",
        intake.case()["case_id"],
        "--output",
        str(output),
    ]


CLI_SAFE_RESOURCES = """
import sys
from watchlist import corpus_solo_review as solo
from watchlist.ingest.resource_guard import GIB, ResourceSnapshot

solo.review.system_snapshot = lambda *args, **kwargs: ResourceSnapshot(
    20_000_000, 20 * GIB, 0, 0.5, False
)
raise SystemExit(solo.main(sys.argv[1:]))
"""


def assert_cli_failure(completed):
    """A failed command must expose only one aggregate JSON status, on either stream."""
    assert completed.returncode != 0
    output = completed.stdout + completed.stderr
    assert json.loads(output)["status"] == "failed_closed"
    assert "fictional" not in output


def test_cli_export_is_private_and_cannot_overwrite_a_response(intake):
    output = intake.artifacts / "fictional-draft.json"
    arguments = export_arguments(intake, output)
    expected = solo.export_template(
        intake.packet_path,
        case_id=intake.case()["case_id"],
        expected_packet_sha256=intake.packet_sha256,
        project_root=intake.root,
        guard=safe_guard(),
    )
    before = saved_tree(intake.ledger_path)
    command = [sys.executable, "-B", "-c", CLI_SAFE_RESOURCES, *arguments]
    first = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=20
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert first.stderr == ""
    assert json.loads(first.stdout)["real_execution_enabled"] is False
    saved = output.read_bytes()
    assert json.loads(saved) == expected
    assert stat.S_IMODE(output.stat().st_mode) == 0o400
    second = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=20
    )
    assert_cli_failure(second)
    assert output.read_bytes() == saved
    assert saved_tree(intake.ledger_path) == before


@pytest.mark.parametrize("destination", ["h1", "packet", "ledger", "outside"])
def test_cli_draft_cannot_write_into_evidence_or_outside_solo_root(intake, destination):
    outside = intake.root / "fictional-unrelated-private"
    outside.mkdir(mode=0o700)
    parent = {
        "h1": intake.h1.pilot_path,
        "packet": intake.packet_path,
        "ledger": intake.ledger_path,
        "outside": outside,
    }[destination]
    output = parent / "fictional-draft.json"
    before = saved_tree(intake.root)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            CLI_SAFE_RESOURCES,
            *export_arguments(intake, output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert_cli_failure(completed)
    assert saved_tree(intake.root) == before


def test_cli_final_resource_callback_cannot_change_evidence_before_draft_write(intake):
    output = intake.artifacts / "fictional-draft.json"
    source_manifest = intake.h1.pilot_path / "manifest.json"
    original_source = source_manifest.read_bytes()
    code = """
from pathlib import Path
import sys
from watchlist import corpus_solo_review as solo
from watchlist.ingest.resource_guard import GIB, ResourceGuard, ResourceSnapshot

solo.review.system_snapshot = lambda *args, **kwargs: ResourceSnapshot(
    20_000_000, 20 * GIB, 0, 0.5, False
)
target = Path(sys.argv[1])
export = solo.export_template
check = ResourceGuard.check
changed = []

def late_callback(guard):
    result = check(guard)
    if not changed:
        raw = target.read_bytes()
        target.chmod(0o600)
        target.write_bytes(raw + b'\\n')
        target.chmod(0o400)
        changed.append(True)
    return result

def arm_after_export(*args, **kwargs):
    result = export(*args, **kwargs)
    ResourceGuard.check = late_callback
    return result

solo.export_template = arm_after_export
raise SystemExit(solo.main(sys.argv[2:]))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            code,
            str(source_manifest),
            *export_arguments(intake, output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert source_manifest.read_bytes() != original_source
    assert_cli_failure(completed)
    assert not output.exists()


def test_cli_network_denial_reports_only_aggregate_failure():
    code = """
import socket
from watchlist import corpus_solo_review as solo

def attempted_network(*args, **kwargs):
    socket.socket()
    raise RuntimeError('Fictional private source names must never reach console')

solo.prepare_solo_review = attempted_network
raise SystemExit(solo.main(['prepare', '--config', 'fictional-private.json', '--output', 'fictional-output']))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert_cli_failure(completed)


def test_cli_export_accounts_for_existing_solo_artifact_bytes(intake):
    template = solo.export_template(
        intake.packet_path,
        case_id=intake.case()["case_id"],
        expected_packet_sha256=intake.packet_sha256,
        project_root=intake.root,
        guard=safe_guard(),
    )
    used = sum(
        path.stat().st_size for path in intake.artifacts.rglob("*") if path.is_file()
    )
    filler = intake.artifacts / "fictional-retained-artifact.bin"
    with filler.open("wb") as handle:
        handle.truncate(16_000_000 - used - len(encoded(template)))
    filler.chmod(0o400)
    output = intake.artifacts / "fictional-draft.json"
    before = saved_tree(intake.ledger_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            CLI_SAFE_RESOURCES,
            *export_arguments(intake, output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert_cli_failure(completed)
    assert not output.exists()
    assert saved_tree(intake.ledger_path) == before
