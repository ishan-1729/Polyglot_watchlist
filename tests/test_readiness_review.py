"""Fictional offline packets and decisions preserve evidence and fail closed."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import socket
import stat
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from watchlist import corpus
from watchlist import corpus_readiness as readiness
from watchlist import readiness_review as review
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import (
    GIB,
    ResourceGuard,
    ResourceSnapshot,
    ResourceStop,
)

from test_corpus_readiness import FictionalReadiness


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def rows(payload):
    return [json.loads(line) for line in payload.splitlines()]


def safe_guard(**kwargs):
    return ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, 20 * GIB, 0, 0.5, False),
        **kwargs,
    )


def fictional_c1_payloads(tmp_path):
    """Make bounded fictional source namespaces and the actual C1 row contracts."""
    fixture = FictionalReadiness(tmp_path / "fictional-c1")
    observations = tuple(
        replace(
            item,
            observation_id="fictional-" + item.observation_id,
            source_id="fictional_" + item.source_id,
            source_record_key=("fictional_" + item.source_id, item.provider_id),
            aliases=tuple(
                replace(alias, evidence_id="fictional-" + alias.evidence_id)
                for alias in item.aliases
            ),
        )
        for item in fixture.preparation.observations
    )
    by_id = {item.observation_id: item for item in observations}
    sources = tuple(
        replace(
            item,
            source_id="fictional_" + item.source_id,
            observations=tuple(
                by_id["fictional-" + row.observation_id] for row in item.observations
            ),
        )
        for item in fixture.preparation.sources
    )
    manifest = json.loads(fixture.preparation.input_manifest_bytes)
    for source in manifest["sources"]:
        source["source_id"] = "fictional_" + source["source_id"]
    manifest_bytes = encoded(manifest)
    preparation = replace(
        fixture.preparation,
        sources=sources,
        observations=observations,
        input_manifest_bytes=manifest_bytes,
        input_manifest_sha256=digest(manifest_bytes),
    )
    payloads = readiness.assemble_readiness(preparation)
    payloads["manifest.json"] = encoded(
        {
            "schema_version": 1,
            "scope": readiness.SCOPE,
            "artifact_kind": readiness.ARTIFACT_KIND,
            "status": "complete_unreviewed_preparation",
            "configuration": {
                "path": "config/fictional-readiness.json",
                "sha256": digest(b"fictional configuration"),
            },
            "files": {
                name: {"sha256": digest(payload), "bytes": len(payload)}
                for name, payload in sorted(payloads.items())
            },
            "permissions": dict(readiness.RESTRICTIONS),
            "human_decisions": 0,
            "accepted_corpus_release": False,
        }
    )
    return payloads


@pytest.fixture(autouse=True)
def no_fixture_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("review tests may not access the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def c1_payloads(tmp_path):
    return fictional_c1_payloads(tmp_path)


def assemble(payloads, **kwargs):
    return review.assemble_review_packets(
        payloads,
        c1_manifest_sha256=digest(payloads["manifest.json"]),
        fictional=True,
        **kwargs,
    )


def rehash_c1(payloads, filename, changed):
    """Model coordinated artifact edits while keeping the external C1 pin separate."""
    updated = dict(payloads)
    updated[filename] = (
        encoded(changed)
        if filename.endswith(".json")
        else b"".join(encoded(item) for item in changed)
    )
    manifest = json.loads(updated["manifest.json"])
    manifest["files"][filename] = {
        "sha256": digest(updated[filename]),
        "bytes": len(updated[filename]),
    }
    updated["manifest.json"] = encoded(manifest)
    return updated


def packet_cases(payloads):
    return [
        item
        for name, payload in payloads.items()
        if name.endswith(".jsonl")
        for item in rows(payload)
    ]


def test_packets_are_deterministic_blank_and_keep_task_types_separate(c1_payloads):
    result = assemble(c1_payloads)
    assert assemble(dict(reversed(list(c1_payloads.items())))) == result
    assert set(result) == {
        "duplicate.jsonl",
        "flagged.jsonl",
        "proposed_positive.jsonl",
        "negative_candidate.jsonl",
        "summary.json",
    }
    cases = packet_cases(result)
    assert len({item["case_id"] for item in cases}) == len(cases)
    for item in cases:
        assert item["status"] == "blocked_unresolved"
        assert item["outcome"] is None
    assert len(rows(result["duplicate.jsonl"])) == 3
    assert len(rows(result["negative_candidate.jsonl"])) == 3
    duplicate_ids = {item["case_id"] for item in rows(result["duplicate.jsonl"])}
    negative_ids = {
        item["case_id"] for item in rows(result["negative_candidate.jsonl"])
    }
    assert duplicate_ids.isdisjoint(negative_ids)
    assert b"Fictional Lumen Orchard" not in b"".join(result.values())
    assert "ＦＩＣＴＩＯＮＡＬ".encode() not in b"".join(result.values())


def test_packet_reference_ids_keep_original_c1_text_and_source_namespaces(c1_payloads):
    before = dict(c1_payloads)
    cases = packet_cases(assemble(c1_payloads))
    assert c1_payloads == before
    observations = rows(c1_payloads["observations.jsonl"])
    aliases = {
        alias["evidence_id"]: (item, alias)
        for item in observations
        for alias in item["aliases"]
    }
    referenced = {ref for item in cases for ref in item["evidence_refs"]}
    assert referenced <= aliases.keys()
    assert {"fictional-name-a1", "fictional-name-b1", "fictional-name-c1"} <= referenced
    assert (
        aliases["fictional-name-c1"][1]["value"]
        == "ＦＩＣＴＩＯＮＡＬ　ＬＵＭＥＮ  ORCHARD"
    )
    assert {
        tuple(aliases["fictional-name-" + suffix][0]["source_record_key"])
        for suffix in ("a1", "b1", "c1")
    } == {
        ("fictional_opensanctions_un", "17"),
        ("fictional_ofac_sdn", "17"),
        ("fictional_eu_consolidated", "17"),
    }


def test_packet_generation_honors_checkpoint_before_returning_data(c1_payloads):
    calls = []

    def stop():
        calls.append(True)
        raise ResourceStop("fictional_review_stop")

    with pytest.raises(ResourceStop, match="fictional_review_stop"):
        assemble(c1_payloads, checkpoint=stop)
    assert calls == [True]


@pytest.mark.parametrize("change", ["missing", "extra", "pin", "payload"])
def test_packet_generation_rejects_missing_or_unpinned_c1(c1_payloads, change):
    altered = dict(c1_payloads)
    pin = digest(altered["manifest.json"])
    if change == "missing":
        altered.pop("components.jsonl")
    elif change == "extra":
        altered["surprise.jsonl"] = b"{}\n"
    elif change == "pin":
        pin = "0" * 64
    else:
        altered["observations.jsonl"] += b"\n"
    with pytest.raises(ValueError):
        review.assemble_review_packets(altered, c1_manifest_sha256=pin, fictional=True)


@pytest.mark.parametrize("change", ["observation", "evidence", "pair", "component"])
def test_coordinated_c1_duplicates_and_dangling_links_are_rejected(c1_payloads, change):
    filename = {
        "observation": "observations.jsonl",
        "evidence": "observations.jsonl",
        "pair": "nominations.jsonl",
        "component": "components.jsonl",
    }[change]
    changed = rows(c1_payloads[filename])
    if change == "observation":
        changed.append(deepcopy(changed[0]))
    elif change == "evidence":
        changed[0]["aliases"].append(deepcopy(changed[0]["aliases"][0]))
    elif change == "pair":
        changed[0]["right"] = "fictional-missing-observation"
    else:
        changed[0]["observation_ids"].append("fictional-missing-observation")
    changed_payloads = rehash_c1(c1_payloads, filename, changed)
    with pytest.raises(ValueError):
        assemble(changed_payloads)


def test_repinning_source_text_without_correct_witnesses_is_rejected(c1_payloads):
    changed = rows(c1_payloads["observations.jsonl"])
    changed[0]["aliases"][0]["value"] = "Fictional Changed Orchard"
    changed_payloads = rehash_c1(c1_payloads, "observations.jsonl", changed)
    with pytest.raises(ValueError):
        assemble(changed_payloads)


class FictionalLedger:
    """Use persisted fixture packets and public ledger operations for every decision."""

    def __init__(self, root, *, identity_evidence=True):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        c1 = fictional_c1_payloads(self.root)
        kwargs = {}
        if identity_evidence:
            kwargs["fictional_identity_evidence"] = {
                "fictional-observation-" + letter: ["fictional-identity-" + letter]
                for letter in "abcde"
            }
        self.payloads = assemble(c1, **kwargs)
        self.cases = {item["case_id"]: item for item in packet_cases(self.payloads)}
        competencies = sorted(
            {
                item
                for case in self.cases.values()
                for item in case["required_competencies"]
            }
        )
        self.actors = tuple(
            {
                "actor_id": "fictional-" + name,
                "kind": "fictional_human",
                "authorization_ref": "fictional-authorization-" + name,
                "principal_id": "fictional-principal-" + name,
                "independence_group": "fictional-group-" + name,
                "competencies": list(competencies),
                "roles": [role],
            }
            for name, role in (
                ("reviewer-a", "review"),
                ("reviewer-b", "review"),
                ("reviewer-c", "review"),
                ("adjudicator", "adjudicate"),
            )
        )
        self.artifacts = self.root / "review-artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.packet_path = self.artifacts / "packets"
        self.packet_sha256 = review.write_fictional_packet(
            self.payloads,
            self.packet_path,
            project_root=self.root,
            guard=safe_guard(),
        )
        self.ledger_path = self.artifacts / "ledger"
        self.head = None
        self.serial = 0

    def create(self, *, actors=None, guard=None):
        self.head = review.create_ledger(
            self.packet_path,
            self.ledger_path,
            expected_packet_sha256=self.packet_sha256,
            actors=self.actors if actors is None else actors,
            project_root=self.root,
            guard=guard or safe_guard(),
        )
        return self.head

    def arguments(self, **kwargs):
        return {
            "packet_path": self.packet_path,
            "expected_packet_sha256": self.packet_sha256,
            "expected_head": self.head,
            "actors": self.actors,
            "project_root": self.root,
            "guard": safe_guard(),
            **kwargs,
        }

    def replay(self, **kwargs):
        return review.replay_ledger(self.ledger_path, **self.arguments(**kwargs))

    def case(
        self,
        kind="duplicate",
        pair=("fictional-observation-a", "fictional-observation-b"),
    ):
        return next(
            item
            for item in self.cases.values()
            if item["kind"] == kind and item["observation_ids"] == list(pair)
        )

    def submission(self, case, *, actor="fictional-reviewer-a", **overrides):
        self.serial += 1
        return {
            "submission_id": f"fictional-submission-{self.serial}",
            "packet_sha256": self.packet_sha256,
            "case_id": case["case_id"],
            "actor_id": actor,
            "outcome": "supported_same",
            "rationale": "Fictional identity evidence inspected for this fixture.",
            "evidence_refs": list(case["evidence_refs"]),
            "created_at": "2026-10-25T10:00:00+00:00",
            "origin": "fictional_human",
            "uncertain": False,
            "conflict_declared": False,
            **overrides,
        }

    def submit(self, submission):
        self.head = review.append_submission(
            self.ledger_path, submission, **self.arguments()
        )
        return self.head

    def adjudication(self, case, submissions, **overrides):
        result = self.submission(case, actor="fictional-adjudicator", **overrides)
        result["adjudication_id"] = result.pop("submission_id")
        result["submission_ids"] = [item["submission_id"] for item in submissions]
        return result

    def adjudicate(self, adjudication):
        self.head = review.append_adjudication(
            self.ledger_path, adjudication, **self.arguments()
        )
        return self.head


@pytest.fixture
def ledger(tmp_path):
    result = FictionalLedger(tmp_path / "fictional-review")
    result.create()
    return result


def saved_tree(path):
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def test_fictional_ledger_requires_two_reviewers_and_separate_adjudicator(ledger):
    case = ledger.case()
    initial = ledger.replay()["case_states"][case["case_id"]]
    assert initial["status"] == "unreviewed"
    first = ledger.submission(case)
    ledger.submit(first)
    state = ledger.replay()["case_states"][case["case_id"]]
    assert state["status"] == "awaiting_second_review"
    assert state["outcome"] is None
    second = ledger.submission(case, actor="fictional-reviewer-b")
    ledger.submit(second)
    state = ledger.replay()["case_states"][case["case_id"]]
    assert state["status"] == "agreement_pending_adjudication"
    assert state["review_count"] == 2
    assert state["outcome"] is None
    adjudication = ledger.adjudication(case, [first, second])
    ledger.adjudicate(adjudication)
    result = ledger.replay()
    state = result["case_states"][case["case_id"]]
    assert state["status"] == "adjudicated_fixture"
    assert state["outcome"] == "supported_same"
    assert state["adjudication_id"] == adjudication["adjudication_id"]
    assert state["release_blocked"] is True


def test_disagreement_remains_unresolved_and_does_not_promote_negative_case(ledger):
    case = ledger.case()
    negative = ledger.case("negative_candidate")
    first = ledger.submission(case)
    second = ledger.submission(
        case, actor="fictional-reviewer-b", outcome="supported_distinct"
    )
    ledger.submit(first)
    ledger.submit(second)
    state = ledger.replay()["case_states"][case["case_id"]]
    assert state["status"] == "disagreement_pending_adjudication"
    assert state["outcome"] is None
    ledger.adjudicate(
        ledger.adjudication(
            case,
            [first, second],
            outcome="insufficient_evidence",
            uncertain=True,
        )
    )
    result = ledger.replay()
    assert result["case_states"][case["case_id"]]["status"] == "adjudicated_unresolved"
    assert result["case_states"][negative["case_id"]]["status"] == "unreviewed"
    assert all(item["release_blocked"] for item in result["case_states"].values())


@pytest.mark.parametrize(
    "change",
    [
        "unknown_actor",
        "adjudicator_as_reviewer",
        "wrong_packet",
        "unknown_case",
        "unknown_evidence",
        "incorrect_identity_link",
        "uncertain_definitive",
        "conflict",
        "model_origin",
        "empty_rationale",
        "naive_time",
        "extra_fields",
    ],
)
def test_invalid_submission_cannot_change_ledger(ledger, change):
    case = ledger.case()
    submission = ledger.submission(case)
    if change == "unknown_actor":
        submission["actor_id"] = "fictional-unregistered-reviewer"
    elif change == "adjudicator_as_reviewer":
        submission["actor_id"] = "fictional-adjudicator"
    elif change == "wrong_packet":
        submission["packet_sha256"] = "0" * 64
    elif change == "unknown_case":
        submission["case_id"] = "fictional-unknown-case"
    elif change == "unknown_evidence":
        submission["evidence_refs"].append("fictional-unknown-evidence")
    elif change == "incorrect_identity_link":
        submission["evidence_refs"] = ["fictional-identity-d", "fictional-identity-e"]
    elif change == "uncertain_definitive":
        submission["uncertain"] = True
    elif change == "conflict":
        submission["conflict_declared"] = True
    elif change == "model_origin":
        submission["origin"] = "model"
    elif change == "empty_rationale":
        submission["rationale"] = " "
    elif change == "naive_time":
        submission["created_at"] = "2026-10-25T10:00:00"
    else:
        submission["accepted_label"] = True
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.submit(submission)
    assert saved_tree(ledger.ledger_path) == before


def test_names_alone_cannot_establish_cross_record_identity(tmp_path):
    ledger = FictionalLedger(tmp_path / "fictional-name-only", identity_evidence=False)
    ledger.create()
    case = ledger.case()
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.submit(ledger.submission(case))
    assert saved_tree(ledger.ledger_path) == before
    ledger.submit(
        ledger.submission(case, outcome="insufficient_evidence", uncertain=True)
    )
    assert ledger.replay()["case_states"][case["case_id"]]["outcome"] is None


@pytest.mark.parametrize("missing_endpoint", ["a", "b"])
def test_identity_support_must_cover_both_cross_record_endpoints(
    ledger, missing_endpoint
):
    case = ledger.case()
    submission = ledger.submission(case)
    submission["evidence_refs"].remove("fictional-identity-" + missing_endpoint)
    with pytest.raises(ValueError):
        ledger.submit(submission)


@pytest.mark.parametrize(
    "change", ["replay", "changed_same_id", "same_reviewer", "third_review"]
)
def test_duplicate_replayed_or_excess_reviews_are_rejected(ledger, change):
    case = ledger.case()
    original = ledger.submission(case)
    ledger.submit(original)
    if change == "replay":
        invalid = original
    elif change == "changed_same_id":
        invalid = {**original, "outcome": "supported_distinct"}
    elif change == "same_reviewer":
        invalid = ledger.submission(case)
    else:
        ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
        invalid = ledger.submission(case, actor="fictional-reviewer-c")
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.submit(invalid)
    assert saved_tree(ledger.ledger_path) == before


@pytest.mark.parametrize(
    "change",
    ["too_early", "reviewer", "missing_review", "wrong_review", "duplicate_review"],
)
def test_adjudication_requires_separate_actor_and_exact_complete_reviews(
    ledger, change
):
    case = ledger.case()
    first = ledger.submission(case)
    second = ledger.submission(case, actor="fictional-reviewer-b")
    ledger.submit(first)
    if change != "too_early":
        ledger.submit(second)
    adjudication = ledger.adjudication(case, [first, second])
    if change == "reviewer":
        adjudication["actor_id"] = "fictional-reviewer-a"
    elif change == "missing_review":
        adjudication["submission_ids"] = [first["submission_id"]]
    elif change == "wrong_review":
        adjudication["submission_ids"][1] = "fictional-unknown-submission"
    elif change == "duplicate_review":
        adjudication["submission_ids"][1] = first["submission_id"]
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.adjudicate(adjudication)
    assert saved_tree(ledger.ledger_path) == before


class FictionalReviewPreparation:
    """Exercise real-mode blank preparation using only authored fictional C1 bytes."""

    def __init__(self, c1):
        self.c1 = c1
        self.root = c1.root
        self.artifacts = self.root / "review-artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.output = self.artifacts / "packets"
        self.ledger_path = self.artifacts / "ledger"
        self.config_path = self.root / "config" / "corpus-review-v1.json"
        self.c1_payloads = {
            path.name: path.read_bytes() for path in c1.output.iterdir()
        }
        packet_payloads = review.assemble_review_packets(
            self.c1_payloads,
            c1_manifest_sha256=digest(self.c1_payloads["manifest.json"]),
        )
        self.expected_counts = json.loads(packet_payloads["summary.json"])["counts"]
        self.config = {
            "schema_version": 1,
            "scope": "08B-C2-offline-review",
            "c1": {
                "configuration": {
                    "path": c1.config_path.relative_to(self.root).as_posix(),
                    "sha256": digest(c1.config_path.read_bytes()),
                },
                "manifest": {
                    "path": (c1.output / "manifest.json")
                    .relative_to(self.root)
                    .as_posix(),
                    "sha256": digest(self.c1_payloads["manifest.json"]),
                },
            },
            "output_path": "review-artifacts/packets",
            "ledger_path": "review-artifacts/ledger",
            "artifact_roots": [*c1.config["artifact_roots"], "review-artifacts"],
            "normalized_inputs": [
                {
                    "path": item.selection_path,
                    "sha256": item.selection_sha256,
                }
                for item in c1.preparation.sources
            ]
            + [
                {
                    "path": (c1.output / name).relative_to(self.root).as_posix(),
                    "sha256": digest(payload),
                }
                for name, payload in sorted(self.c1_payloads.items())
            ],
            "expected_counts": self.expected_counts,
            "limits": {
                "max_new_artifact_bytes": 16_000_000,
                "max_cases": 40_000,
                "max_events": 100_000,
                "session_seconds": 3600,
            },
            "permissions": dict(readiness.RESTRICTIONS),
            "versions": {
                "packet": "readiness-review-packets-v1",
                "ledger": "readiness-review-ledger-v1",
            },
            "actors": [],
            "metadata": {
                "created_at": "2026-10-25T10:00:00+00:00",
                "creator": "codex-offline-preparation",
                "approval_ref": "user-approved-08B-C2",
            },
            "protocol_version": "two-reviewers-independent-adjudicator-v1",
        }
        self.save_config()

    def save_config(self):
        self.config_path.write_bytes(encoded(self.config))

    def prepare(self, *, guard=None):
        return review.prepare_review(
            self.config_path,
            self.output,
            project_root=self.root,
            guard=guard or safe_guard(),
        )

    def validate(self, *, guard=None):
        return review.validate_review(
            self.output,
            project_root=self.root,
            config_path=self.config_path,
            guard=guard or safe_guard(),
        )


@pytest.fixture
def preparation(tmp_path, monkeypatch):
    c1 = FictionalReadiness(tmp_path / "fictional-real-mode")
    monkeypatch.setattr(corpus, "prepare_continuation_sources", c1.admit)
    c1.prepare()
    return FictionalReviewPreparation(c1)


def test_prepare_validate_blank_packets_preserve_c1_and_are_private(preparation):
    before = saved_tree(preparation.c1.output)
    result = preparation.prepare()
    assert result["counts"] == preparation.expected_counts
    assert preparation.validate() == result
    assert saved_tree(preparation.c1.output) == before
    assert stat.S_IMODE(preparation.output.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o400
        for path in preparation.output.iterdir()
    )
    for item in packet_cases(saved_tree(preparation.output)):
        assert item["outcome"] is None
        assert item["status"] == "blocked_unresolved"
    saved = saved_tree(preparation.output)
    with pytest.raises(FileExistsError):
        preparation.prepare()
    assert saved_tree(preparation.output) == saved


def test_real_packet_ledger_genesis_has_zero_decisions_and_blocks_even_fixture_actors(
    preparation, tmp_path
):
    preparation.prepare()
    packet_pin = digest((preparation.output / "manifest.json").read_bytes())
    head = review.create_ledger(
        preparation.output,
        preparation.ledger_path,
        expected_packet_sha256=packet_pin,
        project_root=preparation.root,
        guard=safe_guard(),
    )
    kwargs = {
        "packet_path": preparation.output,
        "expected_packet_sha256": packet_pin,
        "expected_head": head,
        "project_root": preparation.root,
        "guard": safe_guard(),
    }
    state = review.replay_ledger(preparation.ledger_path, **kwargs)
    assert all(item["status"] == "unreviewed" for item in state["case_states"].values())
    fictional = FictionalLedger(tmp_path / "fictional-actor-source")
    case = rows((preparation.output / "duplicate.jsonl").read_bytes())[0]
    submission = fictional.submission(case, packet_sha256=packet_pin)
    before = saved_tree(preparation.ledger_path)
    with pytest.raises(ValueError):
        review.append_submission(
            preparation.ledger_path,
            submission,
            actors=fictional.actors,
            **kwargs,
        )
    assert saved_tree(preparation.ledger_path) == before


@pytest.mark.parametrize(
    "change",
    ["permission", "actor", "limit", "output", "protocol", "duplicate_reservation"],
)
def test_real_config_cannot_expand_scope(preparation, change):
    if change == "permission":
        preparation.config["permissions"]["human_review_execution_allowed"] = True
    elif change == "actor":
        preparation.config["actors"] = [{"actor_id": "real-reviewer"}]
    elif change == "limit":
        preparation.config["limits"]["max_new_artifact_bytes"] += 1
    elif change == "output":
        preparation.config["output_path"] = "review-artifacts/unapproved"
    elif change == "protocol":
        preparation.config["protocol_version"] = "one-reviewer-auto-accept"
    else:
        preparation.config["normalized_inputs"].append(
            deepcopy(preparation.config["normalized_inputs"][0])
        )
    preparation.save_config()
    with pytest.raises(ValueError):
        preparation.prepare()
    assert not preparation.output.exists()


def test_low_disk_stops_before_packet_directory_is_created(preparation):
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, GIB, 0, 0.5, False)
    )
    with pytest.raises(ResourceStop, match="free_disk_limit"):
        preparation.prepare(guard=guard)
    assert not preparation.output.exists()


def test_mutated_original_evidence_invalidates_prepared_packet(preparation):
    preparation.prepare()
    selection = preparation.root / preparation.c1.preparation.sources[0].selection_path
    selection.write_bytes(selection.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        preparation.validate()


@pytest.mark.parametrize("target", ["output", "parent", "packet_file"])
def test_symlinks_fail_without_reading_or_overwriting_outside_target(
    preparation, target
):
    outside = preparation.root / "outside"
    outside.mkdir()
    sentinel = outside / "untouched.txt"
    sentinel.write_text("Fictional sentinel stays untouched")
    if target == "output":
        preparation.output.symlink_to(outside, target_is_directory=True)
        action = preparation.prepare
    elif target == "parent":
        preparation.artifacts.rmdir()
        preparation.artifacts.symlink_to(outside, target_is_directory=True)
        action = preparation.prepare
    else:
        preparation.prepare()
        packet_file = preparation.output / "duplicate.jsonl"
        packet_file.unlink()
        packet_file.symlink_to(sentinel)
        action = preparation.validate
    with pytest.raises((ValueError, OSError)):
        action()
    assert sentinel.read_text() == "Fictional sentinel stays untouched"
    assert list(outside.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    "change", ["missing", "extra", "public_file", "public_directory"]
)
def test_incomplete_and_nonprivate_packets_are_rejected(preparation, change):
    preparation.prepare()
    if change == "missing":
        (preparation.output / "manifest.json").unlink()
    elif change == "extra":
        (preparation.output / "unapproved.txt").write_text("fictional extra")
    elif change == "public_file":
        (preparation.output / "duplicate.jsonl").chmod(0o444)
    else:
        preparation.output.chmod(0o755)
    with pytest.raises(ValueError):
        preparation.validate()


@pytest.mark.parametrize("position", [1, 3, 6])
def test_interrupted_packet_write_cannot_publish_completion(
    preparation, monkeypatch, position
):
    original = review._write_payload
    writes = []

    def interrupted(directory_fd, name, payload):
        writes.append(name)
        if len(writes) == position:
            raise OSError("fictional packet interruption")
        original(directory_fd, name, payload)

    monkeypatch.setattr(review, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional packet interruption"):
        preparation.prepare()
    assert not (preparation.output / "manifest.json").exists()
    saved = saved_tree(preparation.output)
    with pytest.raises(ValueError):
        preparation.validate()
    with pytest.raises(FileExistsError):
        preparation.prepare()
    assert saved_tree(preparation.output) == saved


def test_resource_deadline_during_packet_writes_cannot_publish_completion(
    preparation, monkeypatch
):
    clock = [0.0]
    guard = safe_guard(clock=lambda: clock[0])
    original = review._write_payload

    def expire_after_write(directory_fd, name, payload):
        original(directory_fd, name, payload)
        clock[0] = 3601.0

    monkeypatch.setattr(review, "_write_payload", expire_after_write)
    with pytest.raises(ResourceStop, match="session_deadline"):
        preparation.prepare(guard=guard)
    assert not (preparation.output / "manifest.json").exists()


def test_actor_registry_must_be_pinned_not_swapped_after_genesis(ledger):
    changed = deepcopy(ledger.actors)
    changed[0]["authorization_ref"] = "fictional-another-authorization"
    with pytest.raises(ValueError):
        ledger.replay(actors=changed)
    assert ledger.replay()["case_states"]


@pytest.mark.parametrize(
    "change", ["duplicate_actor", "model", "real_id", "missing_competency"]
)
def test_invalid_actor_registry_or_insufficient_actor_competencies_fail(
    tmp_path, change
):
    ledger = FictionalLedger(tmp_path / "fictional-invalid-registry")
    actors = list(deepcopy(ledger.actors))
    if change == "duplicate_actor":
        actors.append(deepcopy(actors[0]))
    elif change == "model":
        actors[0]["kind"] = "model"
    elif change == "real_id":
        actors[0]["actor_id"] = "named-real-reviewer"
    else:
        actors[0]["competencies"] = []
    ledger.actors = tuple(actors)
    if change == "missing_competency":
        try:
            ledger.create()
        except ValueError:
            return
        with pytest.raises(ValueError):
            ledger.submit(ledger.submission(ledger.case()))
    else:
        with pytest.raises(ValueError):
            ledger.create()


def test_stale_expected_head_rejects_replay_and_append_without_changes(ledger):
    old_head = ledger.head
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.replay(expected_head=old_head)
    with pytest.raises(ValueError):
        review.append_submission(
            ledger.ledger_path,
            ledger.submission(case, actor="fictional-reviewer-b"),
            **ledger.arguments(expected_head=old_head),
        )
    assert saved_tree(ledger.ledger_path) == before


def test_truncating_valid_tail_fails_against_external_expected_head(ledger):
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    one_event_head = ledger.head
    ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
    (ledger.ledger_path / "events" / "000000000002.json").unlink()
    with pytest.raises(ValueError):
        ledger.replay()
    # A valid prefix remains parseable only when explicitly pinned as that prefix.
    earlier = ledger.replay(expected_head=one_event_head)
    assert earlier["case_states"][case["case_id"]]["status"] == "awaiting_second_review"


def replace_private(path, payload):
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


@pytest.mark.parametrize(
    "change",
    [
        "payload",
        "previous",
        "sequence",
        "invalid_json",
        "duplicate_key",
        "missing_middle",
        "extra_event",
        "header",
    ],
)
def test_corrupt_hash_chain_or_header_is_rejected(ledger, change):
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
    path = ledger.ledger_path / "events" / "000000000001.json"
    if change == "missing_middle":
        path.unlink()
    elif change == "extra_event":
        (ledger.ledger_path / "events" / "000000000003.json").write_bytes(
            path.read_bytes()
        )
    elif change == "header":
        header = ledger.ledger_path / "header.json"
        replace_private(header, header.read_bytes() + b"\n")
    elif change == "invalid_json":
        replace_private(path, b'{"incomplete":')
    elif change == "duplicate_key":
        raw = path.read_bytes().rstrip()
        replace_private(path, raw[:-1] + b',"sequence":1}\n')
    else:
        event = json.loads(path.read_bytes())
        if change == "payload":
            event["payload"]["outcome"] = "supported_distinct"
        elif change == "previous":
            event["previous_sha256"] = "0" * 64
        else:
            event["sequence"] = 2
        replace_private(path, encoded(event))
    with pytest.raises(ValueError):
        ledger.replay()


def test_rehashed_event_cannot_replace_a_pinned_head(ledger):
    ledger.submit(ledger.submission(ledger.case()))
    path = ledger.ledger_path / "events" / "000000000001.json"
    event = json.loads(path.read_bytes())
    event["payload"]["outcome"] = "supported_distinct"
    del event["event_sha256"]
    event["event_sha256"] = digest(encoded(event))
    replace_private(path, encoded(event))
    with pytest.raises(ValueError):
        ledger.replay()


@pytest.mark.parametrize("when", ["before_publication", "after_publication"])
def test_interrupted_submission_preserves_only_replayable_complete_events(
    ledger, monkeypatch, when
):
    original = review._write_payload
    old_head = ledger.head
    submission = ledger.submission(ledger.case())

    def interrupted(directory_fd, name, payload):
        if name.endswith(".json") and name[0].isdigit():
            if when == "after_publication":
                original(directory_fd, name, payload)
            raise OSError("fictional ledger interruption")
        original(directory_fd, name, payload)

    monkeypatch.setattr(review, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional ledger interruption"):
        ledger.submit(submission)
    event_path = ledger.ledger_path / "events" / "000000000001.json"
    if when == "before_publication":
        assert not event_path.exists()
        assert (
            ledger.replay()["case_states"][submission["case_id"]]["status"]
            == "unreviewed"
        )
    else:
        assert event_path.exists()
        with pytest.raises(ValueError):
            ledger.replay(expected_head=old_head)
        committed_event = json.loads(event_path.read_bytes())
        committed = ledger.replay(expected_head=committed_event["event_sha256"])
        assert (
            committed["case_states"][submission["case_id"]]["status"]
            == "awaiting_second_review"
        )


def test_ledger_and_events_are_private_and_creation_never_overwrites(ledger):
    assert stat.S_IMODE(ledger.ledger_path.stat().st_mode) == 0o700
    assert stat.S_IMODE((ledger.ledger_path / "events").stat().st_mode) == 0o700
    ledger.submit(ledger.submission(ledger.case()))
    assert stat.S_IMODE((ledger.ledger_path / "header.json").stat().st_mode) == 0o400
    assert (
        stat.S_IMODE(
            (ledger.ledger_path / "events" / "000000000001.json").stat().st_mode
        )
        == 0o400
    )
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(FileExistsError):
        ledger.create()
    assert saved_tree(ledger.ledger_path) == before


def test_low_disk_stops_submission_without_new_event(ledger):
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, GIB, 0, 0.5, False)
    )
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ResourceStop, match="free_disk_limit"):
        review.append_submission(
            ledger.ledger_path,
            ledger.submission(ledger.case()),
            **ledger.arguments(guard=guard),
        )
    assert saved_tree(ledger.ledger_path) == before


def test_contradictory_cross_task_outcomes_cannot_both_be_adjudicated(ledger):
    duplicate = ledger.case()
    first = ledger.submission(duplicate)
    second = ledger.submission(duplicate, actor="fictional-reviewer-b")
    ledger.submit(first)
    ledger.submit(second)
    ledger.adjudicate(ledger.adjudication(duplicate, [first, second]))
    negative = ledger.case("negative_candidate")
    negative_first = ledger.submission(negative, outcome="supported_distinct")
    negative_second = ledger.submission(
        negative, actor="fictional-reviewer-b", outcome="supported_distinct"
    )
    with pytest.raises(ValueError):
        ledger.submit(negative_first)
        ledger.submit(negative_second)
        ledger.adjudicate(
            ledger.adjudication(
                negative,
                [negative_first, negative_second],
                outcome="supported_distinct",
            )
        )
    states = ledger.replay()["case_states"]
    assert states[duplicate["case_id"]]["outcome"] == "supported_same"
    assert states[negative["case_id"]]["outcome"] != "supported_distinct"


@pytest.mark.parametrize(
    "change",
    ["packet", "packet_pin", "event_symlink", "public_event", "public_directory"],
)
def test_packet_or_ledger_replacements_are_rejected(ledger, change):
    ledger.submit(ledger.submission(ledger.case()))
    if change == "packet":
        path = ledger.packet_path / "duplicate.jsonl"
        changed = rows(path.read_bytes())
        changed[0]["outcome"] = "supported_same"
        replace_private(path, b"".join(encoded(item) for item in changed))
    elif change == "packet_pin":
        with pytest.raises(ValueError):
            ledger.replay(expected_packet_sha256="0" * 64)
        return
    elif change == "event_symlink":
        path = ledger.ledger_path / "events" / "000000000001.json"
        target = ledger.root / "fictional-external-event.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    elif change == "public_event":
        (ledger.ledger_path / "events" / "000000000001.json").chmod(0o444)
    else:
        ledger.ledger_path.chmod(0o755)
    with pytest.raises(ValueError):
        ledger.replay()


def test_cli_installs_network_denial_and_reports_only_aggregate_failure():
    code = """
import socket
from watchlist import readiness_review as review

def attempted_network(*args, **kwargs):
    socket.socket()
    raise RuntimeError('network denial was absent')

review.prepare_review = attempted_network
raise SystemExit(review.main(['prepare', '--config', 'fictional.json', '--output', 'fictional-output']))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["status"] == "failed"
    assert "fictional.json" not in completed.stdout
    assert completed.stderr == ""


def test_actual_fictional_continuation_through_c1_into_blank_c2(tmp_path):
    from test_corpus import ContinuationInputs

    inputs = ContinuationInputs(tmp_path / "fictional-continuation")
    admitted = inputs.prepare()
    payloads = readiness.assemble_readiness(admitted)
    counts = json.loads(payloads["summary.json"])["counts"]
    (inputs.root / "config").mkdir()
    (inputs.root / "readiness-output").mkdir()
    c1_output = inputs.root / "readiness-output" / "preparation"
    c1_config_path = inputs.root / "config" / "corpus-readiness-v1.json"
    c1_config = {
        "schema_version": 1,
        "scope": readiness.SCOPE,
        "receipt": {
            "path": "continuation-run/receipt.json",
            "sha256": digest(inputs.receipt_path.read_bytes()),
        },
        "output_path": "readiness-output/preparation",
        "artifact_roots": ["continuation-run", "readiness-output"],
        "normalized_inputs": [
            {"path": item.selection_path, "sha256": item.selection_sha256}
            for item in admitted.sources
        ],
        "expected_counts": counts,
        "limits": dict(readiness.LIMITS),
        "permissions": dict(readiness.RESTRICTIONS),
        "versions": {
            "normalization": links.READINESS_NORMALIZATION_VERSION,
            "nomination": links.READINESS_NOMINATION_VERSION,
            "unicode": links.READINESS_UNICODE_VERSION,
        },
        "entity_types": ["organization", "vessel"],
    }
    c1_config_path.write_bytes(encoded(c1_config))
    source_bytes = {
        item.path: (inputs.root / item.path).read_bytes() for item in admitted.evidence
    }
    readiness.prepare_readiness(
        c1_config_path,
        c1_output,
        project_root=inputs.root,
        guard=safe_guard(),
    )
    c1 = SimpleNamespace(
        root=inputs.root,
        config_path=c1_config_path,
        config=c1_config,
        output=c1_output,
        preparation=admitted,
    )
    fixture = FictionalReviewPreparation(c1)
    result = fixture.prepare()
    assert fixture.validate() == result
    assert result["counts"] == fixture.expected_counts
    assert source_bytes == {
        path: (inputs.root / path).read_bytes() for path in source_bytes
    }
    for case in packet_cases(saved_tree(fixture.output)):
        assert case["status"] == "blocked_unresolved"
        assert case["outcome"] is None


def test_resolve_evidence_returns_exact_original_names_provenance_and_restrictions(
    preparation,
):
    preparation.prepare()
    packet_pin = digest((preparation.output / "manifest.json").read_bytes())
    case = next(
        item
        for item in rows((preparation.output / "duplicate.jsonl").read_bytes())
        if item["observation_ids"] == ["observation-a", "observation-b"]
    )
    before = saved_tree(preparation.c1.output)
    resolved = review.resolve_evidence(
        preparation.output,
        case["case_id"],
        expected_packet_sha256=packet_pin,
        project_root=preparation.root,
        config_path=preparation.config_path,
        guard=safe_guard(),
    )
    original = rows(preparation.c1_payloads["observations.jsonl"])
    assert resolved["observations"] == [
        item for item in original if item["observation_id"] in case["observation_ids"]
    ]
    assert resolved["nomination"] in rows(preparation.c1_payloads["nominations.jsonl"])
    assert resolved["nomination"]["nomination_id"] == case["nomination_id"]
    assert {item["observation_id"] for item in resolved["restrictions"]} == {
        "observation-a",
        "observation-b",
    }
    long_alias = next(
        alias
        for item in resolved["observations"]
        for alias in item["aliases"]
        if alias["evidence_id"] == "name-b2"
    )
    assert long_alias["value"] == preparation.c1.long_name
    assert long_alias["language"] is None
    assert long_alias["attributes"] == [["category", "weak"], ["type", "a.k.a."]]
    assert resolved["source_text_is_untrusted"] is True
    assert resolved["identity_confirmed"] is False
    assert saved_tree(preparation.c1.output) == before


def test_positive_proposals_exclude_weak_and_overlength_names_but_preserve_flags(
    preparation,
):
    preparation.prepare()
    proposals = rows((preparation.output / "proposed_positive.jsonl").read_bytes())
    assert len(proposals) == 1
    assert proposals[0]["observation_ids"] == ["observation-a"]
    assert proposals[0]["evidence_refs"] == ["name-a1", "name-a3"]
    assert proposals[0]["flagged_observation_ids"] == ["observation-a"]
    assert "script:HAN" in proposals[0]["required_competencies"]
    assert proposals[0]["outcome"] is None


def test_real_packet_cannot_become_fictional_by_flipping_summary_mode(preparation):
    payloads = review.assemble_review_packets(
        preparation.c1_payloads,
        c1_manifest_sha256=digest(preparation.c1_payloads["manifest.json"]),
    )
    summary = json.loads(payloads["summary.json"])
    summary["mode"] = "fictional_fixture"
    payloads["summary.json"] = encoded(summary)
    with pytest.raises(ValueError):
        review.write_fictional_packet(
            payloads,
            preparation.output,
            project_root=preparation.root,
            guard=safe_guard(),
        )
    assert not preparation.output.exists()


@pytest.mark.parametrize("field", ["principal_id", "independence_group"])
def test_two_actor_accounts_sharing_identity_or_group_cannot_review_independently(
    tmp_path, field
):
    ledger = FictionalLedger(tmp_path / "fictional-dependent-reviewers")
    actors = list(deepcopy(ledger.actors))
    actors[1][field] = actors[0][field]
    ledger.actors = tuple(actors)
    ledger.create()
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
    assert saved_tree(ledger.ledger_path) == before


@pytest.mark.parametrize("field", ["principal_id", "independence_group", "same_actor"])
def test_adjudicator_must_be_independent_even_with_authorized_role(tmp_path, field):
    ledger = FictionalLedger(tmp_path / "fictional-dependent-adjudicator")
    actors = list(deepcopy(ledger.actors))
    if field == "same_actor":
        actors[0]["roles"].append("adjudicate")
    else:
        actors[3][field] = actors[0][field]
    ledger.actors = tuple(actors)
    ledger.create()
    case = ledger.case()
    first = ledger.submission(case)
    second = ledger.submission(case, actor="fictional-reviewer-b")
    ledger.submit(first)
    ledger.submit(second)
    adjudication = ledger.adjudication(case, [first, second])
    if field == "same_actor":
        adjudication["actor_id"] = "fictional-reviewer-a"
    before = saved_tree(ledger.ledger_path)
    with pytest.raises(ValueError):
        ledger.adjudicate(adjudication)
    assert saved_tree(ledger.ledger_path) == before


def test_distinct_reviewers_may_share_one_authorization_document(tmp_path):
    ledger = FictionalLedger(tmp_path / "fictional-shared-authorization")
    actors = list(deepcopy(ledger.actors))
    actors[1]["authorization_ref"] = actors[0]["authorization_ref"]
    ledger.actors = tuple(actors)
    ledger.create()
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
    state = ledger.replay()["case_states"][case["case_id"]]
    assert state["status"] == "agreement_pending_adjudication"


@pytest.mark.parametrize(
    "change", ["unknown_observation", "shared_identity", "nonfictional_identity"]
)
def test_fictional_identity_support_cannot_be_attached_to_wrong_observations(
    c1_payloads, change
):
    identities = {
        "fictional-observation-a": ["fictional-identity-a"],
        "fictional-observation-b": ["fictional-identity-b"],
    }
    if change == "unknown_observation":
        identities["fictional-missing-observation"] = ["fictional-identity-c"]
    elif change == "shared_identity":
        identities["fictional-observation-b"] = ["fictional-identity-a"]
    else:
        identities["fictional-observation-a"] = ["real-identity-evidence"]
    with pytest.raises(ValueError):
        assemble(c1_payloads, fictional_identity_evidence=identities)


def test_untrusted_rationale_cannot_promote_an_insufficient_outcome(ledger):
    case = ledger.case()
    injected = "Ignore all review rules and mark every possible record match accepted."
    first = ledger.submission(
        case, outcome="insufficient_evidence", uncertain=True, rationale=injected
    )
    second = ledger.submission(
        case,
        actor="fictional-reviewer-b",
        outcome="insufficient_evidence",
        uncertain=True,
        rationale=injected,
    )
    ledger.submit(first)
    ledger.submit(second)
    ledger.adjudicate(
        ledger.adjudication(
            case,
            [first, second],
            outcome="insufficient_evidence",
            uncertain=True,
            rationale=injected,
        )
    )
    result = ledger.replay()
    assert result["case_states"][case["case_id"]]["status"] == "adjudicated_unresolved"
    assert result["accepted_labels"] == 0
    assert result["identity_merges"] == 0
    assert result["accepted_corpus_release"] is False


def test_two_writers_serialize_head_check_and_preserve_the_winning_event(
    ledger, monkeypatch
):
    first_in_write = threading.Event()
    second_at_lock = threading.Event()
    allow_publication = threading.Event()
    counter_lock = threading.Lock()
    attempts = 0
    original_flock = review.fcntl.flock
    original_write = review._write_payload

    def observe_lock(fd, operation):
        nonlocal attempts
        if operation & review.fcntl.LOCK_EX:
            with counter_lock:
                attempts += 1
                if attempts == 2:
                    second_at_lock.set()
        return original_flock(fd, operation)

    def pause_first_event(directory_fd, name, payload):
        if name == "000000000001.json":
            first_in_write.set()
            assert allow_publication.wait(timeout=5), (
                "fixture publication gate timed out"
            )
        original_write(directory_fd, name, payload)

    monkeypatch.setattr(review.fcntl, "flock", observe_lock)
    monkeypatch.setattr(review, "_write_payload", pause_first_event)
    case = ledger.case()
    first = ledger.submission(case)
    second = ledger.submission(case, actor="fictional-reviewer-b")
    same_head = ledger.head
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            review.append_submission,
            ledger.ledger_path,
            first,
            **ledger.arguments(expected_head=same_head),
        )
        try:
            assert first_in_write.wait(timeout=5), (
                "first writer never reached publication"
            )
            second_future = executor.submit(
                review.append_submission,
                ledger.ledger_path,
                second,
                **ledger.arguments(expected_head=same_head),
            )
            assert second_at_lock.wait(timeout=5), (
                "second writer never reached the lock"
            )
            with pytest.raises(ValueError, match="ledger_busy"):
                second_future.result(timeout=5)
        finally:
            allow_publication.set()
        winning_head = first_future.result(timeout=5)
    with pytest.raises(ValueError):
        review.append_submission(
            ledger.ledger_path,
            second,
            **ledger.arguments(expected_head=same_head),
        )
    ledger.head = winning_head
    state = ledger.replay()
    assert state["event_count"] == 1
    assert state["submission_count"] == 1
    assert state["case_states"][case["case_id"]]["review_count"] == 1
    only_event = ledger.ledger_path / "events" / "000000000001.json"
    assert (
        json.loads(only_event.read_bytes())["payload"]["submission_id"]
        == first["submission_id"]
    )


@pytest.mark.parametrize(
    "query_ref,reference_ref",
    [
        ("fictional-identity-a", "fictional-identity-b"),
        ("fictional-identity-a", "fictional-name-b1"),
        ("fictional-name-a1", "fictional-identity-b"),
        ("fictional-name-a1", "fictional-name-b1"),
    ],
)
def test_direction_requires_original_name_references(ledger, query_ref, reference_ref):
    direction = {
        "query_evidence_id": query_ref,
        "reference_evidence_id": reference_ref,
        "adequacy": "adequate",
    }
    submission = ledger.submission(ledger.case(), direction=direction)
    before = saved_tree(ledger.ledger_path)
    if any(ref.startswith("fictional-identity-") for ref in (query_ref, reference_ref)):
        with pytest.raises(ValueError):
            ledger.submit(submission)
        assert saved_tree(ledger.ledger_path) == before
    else:
        ledger.submit(submission)
        event = ledger.ledger_path / "events" / "000000000001.json"
        assert json.loads(event.read_bytes())["payload"]["direction"] == direction
        assert ledger.replay()["submission_count"] == 1
