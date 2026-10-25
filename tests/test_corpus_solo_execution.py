"""Fictional-only tests of genuine-mode gates; no real response is fabricated."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import socket

import pytest

from watchlist import corpus_solo_execution as execution
from watchlist import corpus_solo_review as solo
from watchlist.ingest.resource_guard import (
    ResourceGuard,
    ResourceSnapshot,
    ResourceStop,
    GIB,
)
from test_corpus_adjudication import FictionalAdjudication, replace_private
from test_corpus_solo_review import FictionalSoloIntake, multilingual_observations
from test_readiness_review import safe_guard, saved_tree


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("fictional offline tests only")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


class Fixture:
    def __init__(self, tmp_path, monkeypatch):
        self.old = FictionalSoloIntake(
            FictionalAdjudication(
                tmp_path / "fictional-source", mutate=multilingual_observations
            )
        )
        self.root = self.old.root
        self.out = self.root / "execution"
        self.out.mkdir(mode=0o700)
        (self.out / "incoming").mkdir(mode=0o700)
        self.policy_path = self.out / "policy.json"
        self.now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        monkeypatch.setattr(execution, "_now", lambda: self.now)
        self.policy = {
            "schema_version": 1,
            "scope": execution.SCOPE,
            "mode": "fictional_fixture",
            "packet": {
                "path": str(
                    (self.old.packet_path / "manifest.json").relative_to(self.root)
                ),
                "sha256": self.old.packet_sha256,
            },
            "source_config": None,
            "closure": None,
            "artifact_roots": [
                str(self.old.artifacts.relative_to(self.root)),
                str(self.old.h1.artifacts.relative_to(self.root)),
                "execution",
            ],
            "output_root": "execution",
            "owner": {
                "actor_id": "fictional-solo-owner",
                "uid": os.getuid(),
                "account_owner_attested": True,
                "record_review": True,
                "languages": {
                    "en": "fluent",
                    "ur": "fluent",
                    "ar": "none",
                    "ru": "none",
                    "zh": "none",
                    "ja": "none",
                },
                "domain": "self-learning-ML-no-professional-sanctions-expertise",
                "attestation_ref": "fictional-owner-attestation",
            },
            "retention": execution.RETENTION,
            "approval_ref": "fictional-test-only",
            "created_at": self.now.isoformat(),
            "limits": dict(execution.LIMITS),
            "permissions": dict(execution.PERMISSIONS),
            "code_pins": [
                {
                    "path": str(
                        (self.old.packet_path / "manifest.json").relative_to(self.root)
                    ),
                    "sha256": self.old.packet_sha256,
                }
            ],
        }
        self.save_policy()
        self.head = None

    def save_policy(self):
        raw = solo._canonical(self.policy)
        if self.policy_path.exists():
            replace_private(self.policy_path, raw)
        else:
            self.policy_path.write_bytes(raw)
            self.policy_path.chmod(0o600)
        self.pin = solo._sha(raw)

    def kwargs(self, **overrides):
        return {
            "policy_sha256": self.pin,
            "project_root": self.root,
            "guard": safe_guard(),
            **overrides,
        }

    def activate(self, **overrides):
        self.head = execution.activate(self.policy_path, **self.kwargs(**overrides))
        return self.head

    def op(self, action="status", **overrides):
        result = execution.operate(
            self.policy_path,
            action=action,
            **self.kwargs(expected_head=self.head, **overrides),
        )
        self.head = result["head_sha256"]
        return result

    def start(self, session_id="session-first", seconds=1200):
        return self.op("start-session", session_id=session_id, seconds=seconds)

    def draft(self, case=None, **overrides):
        case = case or self.old.packet["cases"][0]
        self.now += timedelta(seconds=45)
        response = self.old.payload(
            case,
            outcome="insufficient_evidence",
            target_scope="unresolved",
            uncertain=True,
            created_at=self.now.isoformat(),
            **overrides,
        )
        path = self.out / "incoming" / (response["submission_id"] + ".json")
        path.write_bytes(solo._canonical(response))
        path.chmod(0o600)
        return path

    def submit(self, path, session_id="session-first"):
        return self.op("submit", session_id=session_id, submission_path=path)


@pytest.fixture
def f(tmp_path, monkeypatch):
    return Fixture(tmp_path, monkeypatch)


def test_activation_submission_checkpoint_replay_and_correction(f):
    before = saved_tree(f.old.artifacts)
    f.activate()
    assert f.op()["submission_count"] == 0
    f.start()
    draft = f.draft()
    first = json.loads(draft.read_bytes())
    result = f.submit(draft)
    assert result["inspected_case_count"] == result["submission_count"] == 1
    assert result["actual_submissions"] == result["accepted_labels"] == 0
    assert f.op() == result
    assert f.op("confirm-first")["first_case_verified"] is True
    correction = f.draft(
        supersedes=first["submission_id"],
        correction_reason="Fictional clarification only",
    )
    changed = f.submit(correction)
    assert changed["correction_count"] == 1
    assert changed["inspected_case_count"] == 1
    assert changed["submission_count"] == 2
    assert f.op() == changed
    assert saved_tree(f.old.artifacts) == before


def test_only_new_session_after_checkpoint_can_review_next_case(f):
    f.activate()
    f.start()
    second = f.draft(f.old.packet["cases"][1])
    with pytest.raises(execution.ExecutionError, match="first_case"):
        f.submit(second)
    f.submit(f.draft())
    f.op("confirm-first")
    second = f.draft(f.old.packet["cases"][1])
    with pytest.raises(execution.ExecutionError, match="first_case"):
        f.submit(second)
    f.start("session-next", 1800)
    response = f.draft(f.old.packet["cases"][1])
    assert f.submit(response, "session-next")["inspected_case_count"] == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p["owner"].update(uid=os.getuid() + 1),
        lambda p: p["owner"].update(account_owner_attested=False),
        lambda p: p["owner"].update(record_review=False),
        lambda p: p["owner"]["languages"].update(ar="fluent"),
        lambda p: p["limits"].update(review_seconds=14401),
        lambda p: p["permissions"].update(training_allowed=True),
        lambda p: p.update(retention="public"),
        lambda p: p.update(approval_ref="real-approval"),
        lambda p: p.update(output_root="../escape"),
        lambda p: p.update(code_pins=[]),
        lambda p: p["artifact_roots"].remove("execution"),
        lambda p: p["artifact_roots"].append("execution/child"),
    ],
)
def test_invalid_declarations_policies_and_paths_fail_before_activation(f, change):
    change(f.policy)
    f.save_policy()
    with pytest.raises(ValueError):
        f.activate()
    assert not (f.out / "ledger").exists()


def test_policy_hash_cannot_be_replaced(f):
    pin = f.pin
    f.policy["created_at"] = (f.now + timedelta(seconds=1)).isoformat()
    f.save_policy()
    with pytest.raises(execution.ExecutionError, match="pin_mismatch"):
        f.activate(policy_sha256=pin)


def test_repeat_activation_preserves_ledger(f):
    f.activate()
    before = saved_tree(f.out / "ledger")
    with pytest.raises(FileExistsError):
        f.activate()
    assert saved_tree(f.out / "ledger") == before


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(actor_id="fictional-another"),
        lambda r: r.update(origin="human"),
        lambda r: r.update(evidence_origin="publisher_assertion"),
        lambda r: r.update(review_label="independent human validation"),
        lambda r: r.update(packet_sha256="0" * 64),
        lambda r: r.update(case_sha256="0" * 64),
        lambda r: r.update(evidence_refs=[]),
        lambda r: r.update(evidence_versions={}),
        lambda r: r.update(case_id="fictional-unknown"),
        lambda r: r.update(supersedes="fictional-solo-missing"),
        lambda r: r.update(correction_reason="without ID"),
        lambda r: r.update(duration_seconds=True),
        lambda r: r.update(duration_seconds=1801),
        lambda r: r.update(uncertain="yes"),
        lambda r: r.update(created_at="2026-10-25T10:00:00Z"),
        lambda r: r.update(outcome="supported_same", target_scope="publisher_record"),
    ],
)
def test_invalid_response_is_not_published(f, change):
    f.activate()
    f.start()
    draft = f.draft()
    raw = json.loads(draft.read_bytes())
    change(raw)
    replace_private(draft, solo._canonical(raw))
    before = saved_tree(f.out / "ledger")
    with pytest.raises(ValueError):
        f.submit(draft)
    assert saved_tree(f.out / "ledger") == before


def test_duplicate_and_conflicting_response_need_correction(f):
    f.activate()
    f.start()
    draft = f.draft()
    f.submit(draft)
    with pytest.raises(ValueError, match="duplicate"):
        f.submit(draft)
    with pytest.raises(ValueError, match="supersede"):
        f.submit(f.draft())


def test_session_required_expiry_and_future_time(f):
    f.activate()
    with pytest.raises(execution.ExecutionError, match="session_required"):
        f.submit(f.draft())
    f.start(seconds=30)
    with pytest.raises(execution.ExecutionError, match="outside_review_session"):
        f.submit(f.draft())


def test_session_allocation_exhaustion_and_duplicates(f):
    f.activate()
    f.start()
    with pytest.raises(execution.ExecutionError, match="duplicate_review_session"):
        f.start()
    with pytest.raises(execution.ExecutionError, match="allowance"):
        f.start("session-too-long", 1201)
    for i in range(11):
        f.start(f"session-{i}")
    assert f.op()["remaining_unreserved_review_seconds"] == 0
    with pytest.raises(execution.ExecutionError, match="allowance"):
        f.start("session-excess", 1)


def test_stale_head_corruption_and_truncation(f):
    genesis = f.activate()
    f.start()
    head = f.head
    with pytest.raises(execution.ExecutionError, match="truncation"):
        execution.operate(f.policy_path, **f.kwargs(expected_head=genesis))
    event = f.out / "ledger/events/000000000001.json"
    original = event.read_bytes()
    replace_private(event, b'{"bad":true}\n')
    with pytest.raises(ValueError):
        f.op()
    replace_private(event, original)
    event.unlink()
    with pytest.raises(execution.ExecutionError, match="truncation"):
        execution.operate(f.policy_path, **f.kwargs(expected_head=head))


def test_unsafe_or_public_incoming_paths(f):
    f.activate()
    f.start()
    draft = f.draft()
    external = f.root / "outside.json"
    external.write_bytes(draft.read_bytes())
    with pytest.raises(execution.ExecutionError, match="incoming"):
        f.submit(external)
    draft.chmod(0o644)
    with pytest.raises(ValueError):
        f.submit(draft)
    draft.chmod(0o600)
    linked = f.out / "incoming/link.json"
    linked.symlink_to(draft)
    with pytest.raises(ValueError):
        f.submit(linked)


def test_resource_pressure_prevents_activation(f):
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, 20 * GIB, 0, 0.5, True)
    )
    with pytest.raises(ResourceStop, match="host_memory_pressure"):
        f.activate(guard=guard)
    assert not (f.out / "ledger").exists()


def test_interrupted_activation_does_not_create_accepted_ledger(f, monkeypatch):
    def interrupt(*args):
        raise OSError("fictional interrupted write")

    monkeypatch.setattr(solo, "_write_payload", interrupt)
    with pytest.raises(OSError):
        f.activate()
    assert not (f.out / "ledger/header.json").exists()
    with pytest.raises(ValueError):
        execution.operate(f.policy_path, **f.kwargs(expected_head="0" * 64))


def test_interrupted_append_preserves_previous_head(f, monkeypatch):
    f.activate()
    f.start()
    before = saved_tree(f.out / "ledger")

    def interrupt(*args):
        raise OSError("fictional interrupted append")

    monkeypatch.setattr(solo, "_write_payload", interrupt)
    with pytest.raises(OSError):
        f.submit(f.draft())
    assert saved_tree(f.out / "ledger") == before
    assert f.op()["submission_count"] == 0


def test_urdu_does_not_grant_arabic_or_unknown_language_competence(f):
    owner = f.policy["owner"]
    case = {
        "required_competencies": ["record_review", "script:ARABIC"],
        "observations": [
            {
                "aliases": [
                    {"evidence_id": "a", "value": "نام", "language": "ur"},
                    {"evidence_id": "b", "value": "دوسرا", "language": "ur"},
                ]
            }
        ],
    }
    value = {
        "relationship_annotation": "unresolved",
        "direction": {
            "adequacy": "unresolved",
            "query_evidence_id": None,
            "reference_evidence_id": None,
        },
    }
    assert execution._qualified(case, value, owner)
    for language in ("ar", None, "fa"):
        changed = deepcopy(case)
        changed["observations"][0]["aliases"][0]["language"] = language
        assert not execution._qualified(changed, value, owner)


def test_linguistic_claim_requires_actual_known_languages(f):
    case = {
        "required_competencies": ["record_review", "script:LATIN"],
        "observations": [
            {
                "aliases": [
                    {"evidence_id": "a", "value": "Fictional A", "language": "en"},
                    {"evidence_id": "b", "value": "Fictional B", "language": None},
                ]
            }
        ],
    }
    value = {
        "relationship_annotation": "translation",
        "direction": {
            "adequacy": "adequate",
            "query_evidence_id": "a",
            "reference_evidence_id": "b",
        },
    }
    assert not execution._qualified(case, value, f.policy["owner"])


def test_policy_mutation_during_guard_callback_is_rejected(f):
    f.activate()
    f.start()
    path = f.draft()
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        if calls == 3:
            f.policy["owner"]["attestation_ref"] = "fictional-changed"
            f.save_policy()
        return ResourceSnapshot(20_000_000, 20 * GIB, 0, 0.5, False)

    old_pin = f.pin
    with pytest.raises(ValueError):
        execution.operate(
            f.policy_path,
            **f.kwargs(
                policy_sha256=old_pin,
                expected_head=f.head,
                action="submit",
                session_id="session-first",
                submission_path=path,
                guard=ResourceGuard(probe=probe),
            ),
        )
    assert len(list((f.out / "ledger/events").iterdir())) == 1


def test_real_mode_activation_and_human_provenance_on_isolated_authored_data(
    tmp_path, monkeypatch
):
    """Real-mode code contract exercised only on named fictional fixture records."""
    from test_corpus_solo_review import FictionalConfiguredSolo, human_preparation

    configured = FictionalConfiguredSolo(
        human_preparation.__wrapped__(tmp_path, monkeypatch)
    )
    configured.prepare()
    root = configured.root
    packet_pin = solo._sha((configured.output / "manifest.json").read_bytes())
    packet, _ = solo._load_packet(configured.output, packet_pin)
    out = root / "execution"
    out.mkdir(mode=0o700)
    (out / "incoming").mkdir(mode=0o700)
    closure = out / "fictional-closure.json"
    closure.write_bytes(
        solo._canonical({"solo_i_acceptance_complete": True, "step08_complete": False})
    )
    closure.chmod(0o600)
    timestamp = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(execution, "_now", lambda: timestamp)
    policy = {
        "schema_version": 1,
        "scope": execution.SCOPE,
        "mode": "development_blank",
        "packet": {
            "path": str((configured.output / "manifest.json").relative_to(root)),
            "sha256": packet_pin,
        },
        "source_config": {
            "path": str(configured.config_path.relative_to(root)),
            "sha256": solo._sha(configured.config_path.read_bytes()),
        },
        "closure": {
            "path": str(closure.relative_to(root)),
            "sha256": solo._sha(closure.read_bytes()),
        },
        "artifact_roots": [*configured.config["artifact_roots"], "execution"],
        "output_root": "execution",
        "owner": {
            "actor_id": "solo-owner-01",
            "uid": os.getuid(),
            "account_owner_attested": True,
            "record_review": True,
            "languages": {
                "en": "fluent",
                "ur": "fluent",
                "ar": "none",
                "ru": "none",
                "zh": "none",
                "ja": "none",
            },
            "domain": "self-learning-ML-no-professional-sanctions-expertise",
            "attestation_ref": "fictional-test-of-real-mode-ONLY",
        },
        "retention": execution.RETENTION,
        "approval_ref": "user-approved-SOLO-E-and-declarations-2026-10-25",
        "created_at": timestamp.isoformat(),
        "limits": dict(execution.LIMITS),
        "permissions": dict(execution.PERMISSIONS),
        "code_pins": [
            {
                "path": str(configured.config_path.relative_to(root)),
                "sha256": solo._sha(configured.config_path.read_bytes()),
            }
        ],
    }
    policy_path = out / "policy.json"
    policy_path.write_bytes(solo._canonical(policy))
    policy_path.chmod(0o600)
    pin = solo._sha(policy_path.read_bytes())
    kwargs = dict(policy_sha256=pin, project_root=root)
    old = saved_tree(configured.artifacts)
    head = execution.activate(policy_path, **kwargs, guard=safe_guard())
    result = execution.operate(
        policy_path,
        **kwargs,
        expected_head=head,
        action="start-session",
        session_id="session-test",
        seconds=1200,
        guard=safe_guard(),
    )
    timestamp += timedelta(seconds=60)
    case = packet["cases"][0]
    response = solo._template(packet, case, packet_pin)
    refs = case["evidence_refs"][:1]
    response.update(
        submission_id="solo-fictional-real-mode-test",
        actor_id="solo-owner-01",
        outcome="insufficient_evidence",
        target_scope="unresolved",
        rationale="ISOLATED FICTIONAL TEST; not an owner review.",
        evidence_refs=refs,
        evidence_versions={k: case["evidence_versions"][k] for k in refs},
        created_at=timestamp.isoformat(),
        uncertain=True,
        conflict_declared=False,
        duration_seconds=30,
        relationship_annotation="unresolved",
    )
    draft = out / "incoming/fictional.json"
    draft.write_bytes(solo._canonical(response))
    draft.chmod(0o600)
    result = execution.operate(
        policy_path,
        **kwargs,
        expected_head=result["head_sha256"],
        action="submit",
        session_id="session-test",
        submission_path=draft,
        guard=safe_guard(),
    )
    assert result["actual_submissions"] == 1
    assert result["accepted_labels"] == 0
    assert saved_tree(configured.artifacts) == old
    with pytest.raises(solo.SoloReviewError, match="real_review_execution_disabled"):
        solo._declaration({"owner": {"actor_id": "solo-owner-01"}}, packet)


def test_cross_record_support_requires_documentary_identity_witnesses(f):
    case = deepcopy(
        next(c for c in f.old.packet["cases"] if len(c["observations"]) == 2)
    )
    # Use only Latin authored names so this tests identity evidence, not language rejection.
    for observation in case["observations"]:
        observation["aliases"] = [
            a
            for a in observation["aliases"]
            if execution.script_set(a["value"]) <= {"LATIN"}
        ]
    case["required_competencies"] = ["record_review", "script:LATIN"]
    case["identity_evidence_refs"] = {}
    case["restrictions"] = []
    packet = deepcopy(f.old.packet)
    packet["cases"] = [case]
    value = f.old.payload(f.old.packet["cases"][0])
    value.update(
        case_id=case["case_id"],
        case_sha256=case["case_sha256"],
        evidence_origin=case["evidence_origin"],
        evidence_refs=case["evidence_refs"],
        evidence_versions=case["evidence_versions"],
        created_at=f.now.isoformat(),
        outcome="supported_distinct",
        target_scope="cross_record_identity",
    )
    with pytest.raises(
        execution.ExecutionError, match="positive_documentary_identity_evidence"
    ):
        execution._validate_response(value, packet, f.policy)


def test_corrupt_source_evidence_stops_before_ledger_mutation(f):
    f.activate()
    f.start()
    draft = f.draft()
    manifest = f.old.packet_path / "manifest.json"
    replace_private(manifest, b"{}\n")
    with pytest.raises(ValueError):
        f.submit(draft)
    assert len(list((f.out / "ledger/events").iterdir())) == 1


def test_future_response_and_unverified_checkpoint_fail_closed(f):
    f.activate()
    with pytest.raises(execution.ExecutionError, match="checkpoint"):
        f.op("confirm-first")
    f.start()
    draft = f.draft()
    value = json.loads(draft.read_bytes())
    value["created_at"] = (f.now + timedelta(seconds=10)).isoformat()
    replace_private(draft, solo._canonical(value))
    with pytest.raises(execution.ExecutionError, match="outside_review_session"):
        f.submit(draft)


def test_download_staging_is_private_idempotent_and_does_not_import(f):
    f.activate()
    f.start()
    draft = f.draft()
    download = f.root / "owner-download.json"
    original = draft.read_bytes()
    download.write_bytes(original)
    download.chmod(0o644)
    first = execution.stage_download(download, f.policy_path, **f.kwargs())
    second = execution.stage_download(download, f.policy_path, **f.kwargs())
    assert first == second
    target = f.out / "incoming" / ("draft-" + solo._sha(original) + ".json")
    assert target.read_bytes() == download.read_bytes() == original
    solo._private(target)
    assert f.op()["submission_count"] == 0
    assert f.submit(target)["submission_count"] == 1


def test_staging_rejects_fictional_to_human_origin_change(f):
    f.activate()
    draft = f.draft(origin="human")
    before = saved_tree(f.out / "incoming")
    with pytest.raises(execution.ExecutionError, match="provenance"):
        execution.stage_download(draft, f.policy_path, **f.kwargs())
    assert saved_tree(f.out / "incoming") == before


def test_source_language_tag_case_preserved_but_competence_comparison_is_caseless(f):
    case = {
        "required_competencies": ["record_review", "script:LATIN", "script:ARABIC"],
        "observations": [
            {
                "aliases": [
                    {"evidence_id": "a", "value": "Fictional", "language": "EN"},
                    {"evidence_id": "b", "value": "خیالی", "language": "UR"},
                ]
            }
        ],
    }
    value = {
        "relationship_annotation": "translation",
        "direction": {
            "adequacy": "adequate",
            "query_evidence_id": "a",
            "reference_evidence_id": "b",
        },
    }
    original = deepcopy(case)
    assert execution._qualified(case, value, f.policy["owner"])
    assert case == original
    case["observations"][0]["aliases"][1]["language"] = "AR"
    assert not execution._qualified(case, value, f.policy["owner"])


def test_versioned_reactivation_preserves_original_empty_ledger(f):
    original_head = f.activate()
    original = saved_tree(f.out / "ledger")
    f.policy["ledger_name"] = "ledger-v2"
    f.save_policy()
    new_head = f.activate()
    assert new_head != original_head
    assert f.op()["submission_count"] == 0
    f.start()
    assert f.op()["event_count"] == 1
    assert saved_tree(f.out / "ledger") == original
    assert len(list((f.out / "ledger-v2/events").iterdir())) == 1


def test_unapproved_ledger_path_is_rejected(f):
    f.policy["ledger_name"] = "../ledger"
    f.save_policy()
    with pytest.raises(execution.ExecutionError, match="ledger_name"):
        f.activate()
