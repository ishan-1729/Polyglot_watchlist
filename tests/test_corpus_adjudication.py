"""Fictional C2 decisions cannot bypass family, absence, or release boundaries."""

from copy import deepcopy
import json
import socket
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from watchlist import corpus
from watchlist import corpus_adjudication as adjudication
from watchlist import corpus_readiness as readiness
from watchlist import readiness_review as review
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import (
    GIB,
    ResourceGuard,
    ResourceSnapshot,
    ResourceStop,
)

from test_readiness_review import (
    FictionalLedger,
    FictionalReviewPreparation,
    digest,
    encoded,
    fictional_c1_payloads,
    packet_cases,
    rows,
    safe_guard,
    saved_tree,
)
from test_corpus_readiness import FictionalReadiness


def oid(letter):
    return "fictional-observation-" + letter


def eid(suffix):
    return "fictional-name-" + suffix


def rebuild_c1(payloads, observations):
    """Regenerate every C1 derivative from deliberately authored fictional rows."""
    typed = tuple(
        corpus.CandidateObservation(
            **{
                **row,
                "aliases": tuple(
                    corpus.CandidateNameEvidence(
                        **{
                            **alias,
                            "attributes": tuple(
                                tuple(pair) for pair in alias["attributes"]
                            ),
                        }
                    )
                    for alias in row["aliases"]
                ),
                "source_record_key": tuple(row["source_record_key"]),
                "referents": tuple(row["referents"]),
                "provider_datasets": tuple(row["provider_datasets"]),
                "provider_topics": tuple(row["provider_topics"]),
            }
        )
        for row in observations
    )
    result = readiness.assemble_readiness(
        corpus.ContinuationPreparation(
            receipt_sha256="",
            receipt_bytes=b"",
            input_manifest_bytes=payloads["input-manifest.json"],
            input_manifest_sha256=digest(payloads["input-manifest.json"]),
            evidence=(),
            sources=(),
            observations=typed,
        )
    )
    manifest = json.loads(payloads["manifest.json"])
    manifest["files"] = {
        name: {"sha256": digest(payload), "bytes": len(payload)}
        for name, payload in sorted(result.items())
    }
    result["manifest.json"] = encoded(manifest)
    return result


class FictionalAdjudication(FictionalLedger):
    """Retain C1 evidence while exercising the existing public C2 ledger API."""

    def __init__(self, root, *, mutate=None):
        self.root = root.resolve()
        self.root.mkdir(parents=True)
        self.c1_payloads = fictional_c1_payloads(self.root)
        observations = rows(self.c1_payloads["observations.jsonl"])
        if mutate is not None:
            mutate(observations)
            self.c1_payloads = rebuild_c1(self.c1_payloads, observations)
        identities = {
            item["observation_id"]: [
                "fictional-identity-"
                + item["observation_id"].removeprefix("fictional-")
            ]
            for item in observations
        }
        self.payloads = review.assemble_review_packets(
            self.c1_payloads,
            c1_manifest_sha256=digest(self.c1_payloads["manifest.json"]),
            fictional=True,
            fictional_identity_evidence=identities,
        )
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
                "competencies": competencies,
                "roles": [role],
            }
            for name, role in (
                ("reviewer-a", "review"),
                ("reviewer-b", "review"),
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
        self.create()

    def decide(
        self,
        pair=("a", "b"),
        *,
        kind="duplicate",
        outcome="supported_same",
        **annotations,
    ):
        case = self.case(kind, tuple(oid(letter) for letter in pair))
        uncertain = outcome == "insufficient_evidence"
        first = self.submission(
            case, outcome=outcome, uncertain=uncertain, **annotations
        )
        second = self.submission(
            case,
            actor="fictional-reviewer-b",
            outcome=outcome,
            uncertain=uncertain,
            **annotations,
        )
        self.submit(first)
        self.submit(second)
        decision = self.adjudication(
            case, [first, second], outcome=outcome, uncertain=uncertain, **annotations
        )
        self.adjudicate(decision)
        return decision

    def graph(self, **overrides):
        return adjudication.build_family_graph(
            self.c1_payloads,
            c1_manifest_sha256=digest(self.c1_payloads["manifest.json"]),
            **{**self.arguments(), "ledger_path": self.ledger_path, **overrides},
        )


@pytest.fixture(autouse=True)
def no_fixture_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("adjudication tests may not access the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def ledger(tmp_path):
    return FictionalAdjudication(tmp_path / "fictional-adjudication")


def reference_view(graph, letters=(), *, evidence_ids=None, **kwargs):
    return adjudication.build_reference_view(
        graph,
        view_id="fictional-reference-view",
        observation_ids=[oid(letter) for letter in letters],
        evidence_ids=evidence_ids,
        **kwargs,
    )


def absent_candidates(graph, view, letters):
    return adjudication.build_absent_candidates(
        graph, view, target_observation_ids=[oid(letter) for letter in letters]
    )


def replace_private(path, payload):
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def test_graph_rebuild_is_deterministic_and_never_changes_review_evidence(ledger):
    ledger.decide()
    original = saved_tree(ledger.root)
    result = ledger.graph()
    assert ledger.graph() == result
    ledger.c1_payloads = dict(reversed(list(ledger.c1_payloads.items())))
    assert ledger.graph() == result
    assert saved_tree(ledger.root) == original


def test_stale_external_ledger_head_blocks_adjudication_application(ledger):
    stale_head = ledger.head
    ledger.decide()
    before = saved_tree(ledger.root)
    with pytest.raises(ValueError):
        ledger.graph(expected_head=stale_head)
    assert saved_tree(ledger.root) == before


@pytest.mark.parametrize("change", ["missing", "extra", "content", "manifest"])
def test_graph_requires_complete_bound_c1_evidence(ledger, change):
    if change == "missing":
        ledger.c1_payloads.pop("components.jsonl")
    elif change == "extra":
        ledger.c1_payloads["unbound.jsonl"] = b"{}\n"
    elif change == "content":
        ledger.c1_payloads["observations.jsonl"] += b"\n"
    else:
        manifest = json.loads(ledger.c1_payloads["manifest.json"])
        manifest["configuration"]["sha256"] = "0" * 64
        ledger.c1_payloads["manifest.json"] = encoded(manifest)
    with pytest.raises(ValueError):
        ledger.graph()


def test_valid_revised_c1_cannot_reuse_superseded_packet_decisions(ledger):
    ledger.decide()
    changed = rows(ledger.c1_payloads["observations.jsonl"])
    changed[-1]["aliases"][0]["value"] = "Fictional Revised Garden"
    changed[-1]["primary_name"] = "Fictional Revised Garden"
    ledger.c1_payloads = rebuild_c1(ledger.c1_payloads, changed)
    with pytest.raises(ValueError):
        ledger.graph()


@pytest.mark.parametrize("change", ["packet_file", "packet_manifest", "packet_pin"])
def test_revised_packets_never_inherit_old_adjudications(ledger, change):
    ledger.decide()
    arguments = {}
    if change == "packet_pin":
        arguments["expected_packet_sha256"] = "0" * 64
    else:
        path = ledger.packet_path / (
            "manifest.json" if change == "packet_manifest" else "duplicate.jsonl"
        )
        replace_private(path, path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        ledger.graph(**arguments)


@pytest.mark.parametrize("change", ["content", "rehash", "truncate", "partial"])
def test_changed_or_incomplete_ledger_cannot_be_applied(ledger, change):
    ledger.decide()
    events = sorted((ledger.ledger_path / "events").iterdir())
    target = events[-1]
    if change == "truncate":
        target.unlink()
    elif change == "partial":
        (target.parent / "000000000004.json").write_bytes(b'{"schema_version":')
    elif change == "content":
        replace_private(target, target.read_bytes() + b"\n")
    else:
        value = json.loads(target.read_bytes())
        value["payload"]["rationale"] = "Fictional coordinated edit of saved history."
        value["event_sha256"] = digest(
            encoded(
                {key: value for key, value in value.items() if key != "event_sha256"}
            )
        )
        replace_private(target, encoded(value))
    before = saved_tree(ledger.root)
    with pytest.raises(ValueError):
        ledger.graph()
    assert saved_tree(ledger.root) == before


@pytest.mark.parametrize("target", ["ledger", "packet", "event"])
def test_graph_rejects_symlink_inputs_without_changing_targets(ledger, target):
    ledger.decide()
    arguments = {}
    if target in {"ledger", "packet"}:
        original = ledger.ledger_path if target == "ledger" else ledger.packet_path
        link = ledger.root / ("linked-" + target)
        link.symlink_to(original, target_is_directory=True)
        arguments[target + "_path"] = link
    else:
        original = ledger.ledger_path / "events" / "000000000003.json"
        outside = ledger.root / "outside-event.json"
        outside.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(outside)
    before = saved_tree(ledger.root)
    with pytest.raises(ValueError):
        ledger.graph(**arguments)
    assert saved_tree(ledger.root) == before


def test_resource_stop_prevents_graph_result_without_mutating_inputs(ledger):
    before = saved_tree(ledger.root)
    guard = ResourceGuard(
        probe=lambda: ResourceSnapshot(20_000_000, GIB, 0, 0.5, False)
    )
    with pytest.raises(ResourceStop):
        ledger.graph(guard=guard)
    assert saved_tree(ledger.root) == before


def group_sets(graph, field):
    names = [item["observation_id"] for item in graph["observations"]]
    return {frozenset(names[index] for index in group) for group in graph[field]}


def edge_pairs(graph, field):
    names = [item["observation_id"] for item in graph["observations"]]
    return {
        frozenset((names[edge["left"]], names[edge["right"]])) for edge in graph[field]
    }


def quarantined_observations(graph):
    names = [item["observation_id"] for item in graph["observations"]]
    return {names[index] for group in graph["quarantine"] for index in group["members"]}


def clean_names(observations):
    for item in observations:
        item["aliases"] = [
            alias for alias in item["aliases"] if alias["evidence_id"] != eid("b2")
        ]


@pytest.fixture
def resolved(tmp_path):
    fixture = FictionalAdjudication(tmp_path / "fictional-resolved", mutate=clean_names)
    for pair in (("a", "b"), ("a", "c"), ("b", "c")):
        fixture.decide(pair)
    fixture.decide(("a",), kind="proposed_positive")
    return fixture


def test_normalized_collisions_and_equal_provider_ids_do_not_assert_identity(ledger):
    graph = ledger.graph()
    assert group_sets(graph, "identity_groups") == {
        frozenset((oid(x),)) for x in "abcde"
    }
    assert edge_pairs(graph, "identity_edges") == set()
    assert edge_pairs(graph, "distinct_edges") == set()
    assert edge_pairs(graph, "uncertain_edges") == {
        frozenset((oid(a), oid(b))) for a, b in (("a", "b"), ("a", "c"), ("b", "c"))
    }
    records = {item["observation_id"]: item for item in graph["observations"]}
    assert (
        records[oid("a")]["source_record_key"][1]
        == records[oid("b")]["source_record_key"][1]
        == "17"
    )
    assert (
        records[oid("a")]["source_record_key"][0]
        != records[oid("b")]["source_record_key"][0]
    )
    assert {oid(x) for x in "abc"} <= quarantined_observations(graph)


def test_two_initial_reviews_alone_are_not_applied_as_identity(ledger):
    case = ledger.case()
    ledger.submit(ledger.submission(case))
    ledger.submit(ledger.submission(case, actor="fictional-reviewer-b"))
    graph = ledger.graph()
    assert edge_pairs(graph, "identity_edges") == set()
    assert frozenset((oid("a"), oid("b"))) not in group_sets(graph, "identity_groups")
    assert {oid("a"), oid("b")} <= quarantined_observations(graph)


def test_adjudicated_same_entity_unions_identity_without_asserting_same_record(ledger):
    decision = ledger.decide()
    graph = ledger.graph()
    assert frozenset((oid("a"), oid("b"))) in group_sets(graph, "identity_groups")
    assert group_sets(graph, "record_equivalence_groups") == {
        frozenset((oid(x),)) for x in "abcde"
    }
    assert decision["adjudication_id"] in graph["identity_edges"][0]["adjudication_ids"]
    assert {oid(x) for x in "abc"} <= quarantined_observations(graph)
    assert graph["custody"] == "development"
    assert graph["development_exposed"] is True
    assert graph["fresh_final_eligible"] is False
    assert graph["counts"]["independent_accepted_families"] == 0


def test_same_entity_is_transitive(ledger):
    ledger.decide(("a", "b"))
    ledger.decide(("b", "c"))
    assert frozenset(oid(x) for x in "abc") in group_sets(
        ledger.graph(), "identity_groups"
    )


def test_distinct_is_not_transitive_and_does_not_merge_families(ledger):
    ledger.decide(("a", "b"), outcome="supported_distinct")
    ledger.decide(("b", "c"), outcome="supported_distinct")
    graph = ledger.graph()
    assert group_sets(graph, "identity_groups") == {
        frozenset((oid(x),)) for x in "abcde"
    }
    assert edge_pairs(graph, "distinct_edges") == {
        frozenset((oid("a"), oid("b"))),
        frozenset((oid("b"), oid("c"))),
    }
    assert frozenset((oid("a"), oid("c"))) in edge_pairs(graph, "uncertain_edges")


def test_transitive_same_same_distinct_contradiction_is_rejected(ledger):
    ledger.decide(("a", "b"))
    ledger.decide(("b", "c"))
    ledger.decide(("a", "c"), outcome="supported_distinct")
    before = saved_tree(ledger.root)
    with pytest.raises(ValueError, match="contradiction"):
        ledger.graph()
    assert saved_tree(ledger.root) == before


@pytest.mark.parametrize("outcome", ["insufficient_evidence", "ineligible"])
def test_uncertain_or_ineligible_adjudication_never_unions_identity(ledger, outcome):
    ledger.decide(outcome=outcome)
    graph = ledger.graph()
    assert group_sets(graph, "identity_groups") == {
        frozenset((oid(x),)) for x in "abcde"
    }
    assert {oid("a"), oid("b")} <= quarantined_observations(graph)


def test_snapshot_continuity_is_dependence_without_identity(tmp_path):
    def add_copy(observations):
        original = next(
            item for item in observations if item["observation_id"] == oid("e")
        )
        copied = deepcopy(original)
        copied["observation_id"] = oid("f")
        copied["snapshot_id"] = "fictional-later-snapshot"
        copied["primary_name"] = "Fictional Renamed Garden"
        copied["aliases"] = [
            {
                **copied["aliases"][0],
                "evidence_id": eid("f1"),
                "value": copied["primary_name"],
            }
        ]
        observations.append(copied)

    fixture = FictionalAdjudication(tmp_path / "fictional-continuity", mutate=add_copy)
    graph = fixture.graph()
    assert frozenset((oid("e"), oid("f"))) in group_sets(graph, "dependence_groups")
    assert frozenset((oid("e"), oid("f"))) not in group_sets(graph, "identity_groups")
    assert frozenset((oid("e"), oid("f"))) not in group_sets(
        graph, "record_equivalence_groups"
    )
    assert graph["development_exposed"] is True
    assert graph["fresh_final_eligible"] is False


def test_original_unicode_aliases_and_qualifiers_survive_graph_application(ledger):
    ledger.decide()
    graph = ledger.graph()
    originals = rows(ledger.c1_payloads["observations.jsonl"])
    assert graph["c1_manifest_sha256"] == digest(ledger.c1_payloads["manifest.json"])
    for item in graph["observations"]:
        original = originals[item["c1_row"]]
        assert item["observation_id"] == original["observation_id"]
        assert item["source_record_key"] == original["source_record_key"]
    fullwidth = next(
        item for item in graph["observations"] if item["observation_id"] == oid("c")
    )
    assert (
        originals[fullwidth["c1_row"]]["aliases"][0]["value"]
        == "ＦＩＣＴＩＯＮＡＬ　ＬＵＭＥＮ  ORCHARD"
    )


def test_graph_exports_are_copies_and_plain_dicts_cannot_claim_validation(resolved):
    graph = resolved.graph()
    original = graph.to_dict()
    observations = graph["observations"]
    observations[0]["observation_id"] = "fictional-forged-observation"
    exported = graph.to_dict()
    exported["identity_groups"] = []
    assert graph.to_dict() == original
    for unsafe in (exported, original):
        with pytest.raises(ValueError):
            reference_view(unsafe)


def test_all_supported_source_copies_excluded_allow_only_dry_run_absence(resolved):
    graph = resolved.graph()
    view = reference_view(graph, "de")
    candidates = absent_candidates(graph, view, "a")
    assert candidates["candidates"][0]["status"] == "supported_absence_dry_run"
    assert set(candidates["candidates"][0]["excluded_family_observation_ids"]) == {
        oid(x) for x in "abc"
    }
    assert (
        adjudication.validate_absent_candidates(graph, view, candidates) == candidates
    )
    assert graph["counts"]["independent_accepted_families"] == 0
    assert graph["fresh_final_eligible"] is False


@pytest.mark.parametrize("retained", ["a", "b", "c"])
def test_any_equivalent_source_copy_in_view_disproves_absence(resolved, retained):
    graph = resolved.graph()
    view = reference_view(graph, "de" + retained)
    candidates = absent_candidates(graph, view, "a")
    assert candidates["candidates"][0]["status"] == "supported_presence"


@pytest.mark.parametrize("retained_alias", ["a1", "a2", "a3", "b1", "c1"])
def test_hidden_original_alias_membership_disproves_absence(resolved, retained_alias):
    graph = resolved.graph()
    view = reference_view(graph, "de", evidence_ids=[eid(retained_alias)])
    candidates = absent_candidates(graph, view, "a")
    assert candidates["candidates"][0]["status"] == "supported_presence"


@pytest.mark.parametrize(
    "kind", ["normalized_index", "display", "embedding_cache", "reviewer_memory"]
)
def test_derived_membership_keeps_original_alias_ancestry(resolved, kind):
    graph = resolved.graph()
    derived = {
        "representation_id": "fictional-derived-hidden-alias",
        "kind": kind,
        "parent_ids": [eid("a3")],
        "version": "fictional-transform-v1",
        "content_sha256": digest(b"fictional derived bytes"),
    }
    view = reference_view(
        graph, "de", evidence_ids=[], derived_representations=[derived]
    )
    candidates = absent_candidates(graph, view, "a")
    assert candidates["candidates"][0]["status"] == "supported_presence"


def test_nested_derived_cache_cannot_hide_an_excluded_original_alias(resolved):
    graph = resolved.graph()
    index = {
        "representation_id": "fictional-index-form",
        "kind": "normalized_index",
        "parent_ids": [eid("c1")],
        "version": "fictional-transform-v1",
        "content_sha256": digest(b"fictional normalized bytes"),
    }
    cache = {
        "representation_id": "fictional-cached-embedding",
        "kind": "embedding_cache",
        "parent_ids": [index["representation_id"]],
        "version": "fictional-cache-v1",
        "content_sha256": digest(b"fictional cache bytes"),
    }
    view = reference_view(
        graph,
        "de",
        evidence_ids=[],
        derived_representations=[cache, index],
        included_representation_ids=[cache["representation_id"]],
    )
    assert (
        absent_candidates(graph, view, "a")["candidates"][0]["status"]
        == "supported_presence"
    )
    excluded = reference_view(
        graph,
        "de",
        evidence_ids=[],
        derived_representations=[cache, index],
        included_representation_ids=[],
    )
    assert (
        absent_candidates(graph, excluded, "a")["candidates"][0]["status"]
        == "supported_absence_dry_run"
    )


def test_unresolved_possible_equivalent_blocks_absence_even_when_names_are_excluded(
    ledger,
):
    ledger.decide(("a", "b"))
    graph = ledger.graph()
    view = reference_view(graph, "de", evidence_ids=[])
    candidate = absent_candidates(graph, view, "a")["candidates"][0]
    assert candidate["status"] in {"unresolved_membership", "ineligible"}
    assert candidate["reasons"]


def test_unreviewed_singleton_is_not_an_accepted_absent_family(ledger):
    graph = ledger.graph()
    candidate = absent_candidates(graph, reference_view(graph, "d"), "e")["candidates"][
        0
    ]
    assert candidate["status"] in {"unresolved_membership", "ineligible"}
    assert candidate["reasons"]


def test_view_hash_binds_absence_to_the_exact_membership(resolved):
    graph = resolved.graph()
    excluded = reference_view(graph, "de")
    candidates = absent_candidates(graph, excluded, "a")
    retained = reference_view(graph, "ade")
    assert excluded != retained
    with pytest.raises(ValueError):
        adjudication.validate_absent_candidates(graph, retained, candidates)


@pytest.mark.parametrize(
    "change",
    ["status", "target", "excluded_family", "query_evidence", "graph_pin", "view_pin"],
)
def test_wrong_absence_labels_families_and_bindings_are_rejected(resolved, change):
    graph = resolved.graph()
    view = reference_view(graph, "de")
    result = deepcopy(absent_candidates(graph, view, "a"))
    candidate = result["candidates"][0]
    if change == "status":
        candidate["status"] = "supported_presence"
    elif change == "target":
        candidate["target_observation_ids"] = [oid("e")]
    elif change == "excluded_family":
        candidate["excluded_family_observation_ids"] = [oid("a")]
    elif change == "query_evidence":
        candidate["query_evidence_id"] = eid("e1")
    elif change == "graph_pin":
        result["graph_sha256"] = "0" * 64
    else:
        result["reference_view_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        adjudication.validate_absent_candidates(graph, view, result)


@pytest.mark.parametrize(
    "parameters",
    [
        {"view_kind": "per_query_deletion"},
        {"view_kind": "retrieval_top_k"},
        {"membership_complete": False},
    ],
)
def test_query_specific_or_incomplete_retrieval_views_cannot_prove_absence(
    resolved, parameters
):
    graph = resolved.graph()
    with pytest.raises(ValueError):
        reference_view(graph, "de", **parameters)


def test_rehashed_view_cannot_acquire_a_query_specific_scope(resolved):
    graph = resolved.graph()
    view = reference_view(graph, "de")
    view["query_scope"] = "fictional-query-specific-deletion"
    view["reference_view_sha256"] = digest(
        encoded(
            {
                key: value
                for key, value in view.items()
                if key != "reference_view_sha256"
            }
        )
    )
    with pytest.raises(ValueError):
        absent_candidates(graph, view, "a")


@pytest.mark.parametrize(
    "change",
    [
        "unknown_parent",
        "cycle",
        "duplicate_id",
        "invalid_kind",
        "name_id_collision",
        "unknown_included",
    ],
)
def test_invalid_derived_ancestry_is_rejected(resolved, change):
    graph = resolved.graph()
    item = {
        "representation_id": "fictional-derived",
        "kind": "display",
        "parent_ids": [eid("a3")],
        "version": "fictional-v1",
        "content_sha256": digest(b"fictional bytes"),
    }
    derived, extra = [item], {}
    if change == "unknown_parent":
        item["parent_ids"] = ["fictional-unknown-parent"]
    elif change == "cycle":
        item["parent_ids"] = [item["representation_id"]]
    elif change == "duplicate_id":
        derived.append(deepcopy(item))
    elif change == "invalid_kind":
        item["kind"] = "identity_assertion"
    elif change == "name_id_collision":
        item["representation_id"] = eid("a3")
    else:
        extra["included_representation_ids"] = ["fictional-unknown-derived"]
    with pytest.raises(ValueError):
        reference_view(graph, "de", derived_representations=derived, **extra)


def test_view_and_query_reordering_is_deterministic(resolved):
    graph = resolved.graph()
    first = reference_view(graph, "ed", evidence_ids=[eid("e1"), eid("d1")])
    second = reference_view(graph, "de", evidence_ids=[eid("d1"), eid("e1")])
    assert first == second
    assert absent_candidates(graph, first, "abc") == absent_candidates(
        graph, second, "cba"
    )


def test_graph_snapshot_becomes_stale_after_an_additional_valid_review(ledger):
    graph = ledger.graph()
    view = reference_view(graph, "de")
    ledger.decide()
    with pytest.raises(ValueError):
        absent_candidates(graph, view, "a")


@pytest.fixture
def homonyms(tmp_path):
    def add_other_names(observations):
        clean_names(observations)
        for item in observations:
            letter = item["observation_id"].removeprefix("fictional-observation-")
            if letter in "bc":
                item["aliases"].append(
                    {
                        "evidence_id": eid(letter + "2"),
                        "value": "Fictional Secondary " + letter.upper(),
                        "field": "properties.alias",
                        "language": "en",
                        "attributes": [],
                    }
                )

    fixture = FictionalAdjudication(
        tmp_path / "fictional-homonyms", mutate=add_other_names
    )
    for pair in (("a", "b"), ("a", "c"), ("b", "c")):
        fixture.decide(pair, outcome="supported_distinct")
    for letter in "abc":
        fixture.decide((letter,), kind="proposed_positive")
    return fixture


def test_same_name_distinct_entity_retained_in_view_blocks_unqualified_absence(
    homonyms,
):
    graph = homonyms.graph()
    result = absent_candidates(graph, reference_view(graph, "bde"), "a")
    assert result["candidates"][0]["status"] == "unresolved_membership"
    assert result["candidates"][0]["reasons"]


def test_normalized_homonym_derived_cache_also_blocks_unqualified_absence(homonyms):
    graph = homonyms.graph()
    derived = {
        "representation_id": "fictional-fullwidth-cache",
        "kind": "embedding_cache",
        "parent_ids": [eid("c1")],
        "version": "fictional-v1",
        "content_sha256": digest(b"fictional homonym cache"),
    }
    view = reference_view(
        graph, "de", evidence_ids=[], derived_representations=[derived]
    )
    assert (
        absent_candidates(graph, view, "a")["candidates"][0]["status"]
        == "unresolved_membership"
    )


def test_multiple_same_identity_targets_retain_all_copies_and_one_family(resolved):
    graph = resolved.graph()
    view = reference_view(graph, "de")
    queries = [
        {
            "query_id": "fictional-multi-target",
            "query_evidence_id": eid("a1"),
            "target_observation_ids": [oid(x) for x in "abc"],
        }
    ]
    result = adjudication.build_absent_candidates(graph, view, queries=queries)
    candidate = result["candidates"][0]
    assert candidate["status"] == "supported_absence_dry_run"
    assert candidate["target_observation_ids"] == [oid(x) for x in "abc"]
    assert result["counts"]["distinct_dry_run_families"] == 1
    assert result["counts"]["accepted_absent_families"] == 0


@pytest.mark.parametrize("retained", ["", "b"])
def test_distinct_multi_answer_targets_require_query_review_and_are_never_dropped(
    homonyms, retained
):
    graph = homonyms.graph()
    view = reference_view(graph, "de" + retained)
    queries = [
        {
            "query_id": "fictional-ambiguous-query",
            "query_evidence_id": eid("a1"),
            "target_observation_ids": [oid(x) for x in "abc"],
        }
    ]
    result = adjudication.build_absent_candidates(graph, view, queries=queries)
    candidate = result["candidates"][0]
    assert candidate["target_observation_ids"] == [oid(x) for x in "abc"]
    assert set(candidate["excluded_family_observation_ids"]) == {oid(x) for x in "abc"}
    assert candidate["status"] == (
        "supported_presence" if retained else "unresolved_membership"
    )
    assert result["counts"]["accepted_labels"] == 0


def test_held_alias_positive_is_separate_from_all_family_absence(tmp_path):
    fixture = FictionalAdjudication(
        tmp_path / "fictional-held-alias", mutate=clean_names
    )
    for pair in (("a", "b"), ("a", "c"), ("b", "c")):
        fixture.decide(pair)
    fixture.decide(
        ("a",),
        kind="proposed_positive",
        relationship_annotation="translation",
        direction={
            "query_evidence_id": eid("a3"),
            "reference_evidence_id": eid("a1"),
            "adequacy": "adequate",
        },
    )
    graph = fixture.graph()
    view = reference_view(graph, "abc", evidence_ids=[eid("a1"), eid("b1"), eid("c1")])
    result = adjudication.validate_held_alias_query(
        graph, view, query_evidence_id=eid("a3"), target_observation_ids=[oid("a")]
    )
    assert result["status"] == "supported_held_alias_dry_run"
    assert result["accepted_label"] is False
    assert (
        absent_candidates(graph, view, "a")["candidates"][0]["status"]
        == "supported_presence"
    )
    leaked = reference_view(graph, "abc")
    assert (
        adjudication.validate_held_alias_query(
            graph,
            leaked,
            query_evidence_id=eid("a3"),
            target_observation_ids=[oid("a")],
        )["status"]
        == "query_alias_leakage"
    )


@pytest.mark.parametrize("membership", ["historical_name", "derived_cache"])
def test_held_alias_history_copies_leak_across_dependence_without_identity(
    tmp_path, membership
):
    def add_historical_copy(observations):
        clean_names(observations)
        original = next(
            item for item in observations if item["observation_id"] == oid("a")
        )
        historical = deepcopy(original)
        historical["observation_id"] = oid("f")
        historical["snapshot_id"] = "fictional-earlier-reused-provider-key"
        alias = next(
            alias for alias in original["aliases"] if alias["evidence_id"] == eid("a3")
        )
        historical["aliases"] = [{**alias, "evidence_id": eid("f1")}]
        historical["primary_name"] = alias["value"]
        observations.append(historical)

    fixture = FictionalAdjudication(
        tmp_path / "fictional-held-alias-history", mutate=add_historical_copy
    )
    for pair in (("a", "b"), ("a", "c"), ("b", "c")):
        fixture.decide(pair)
    fixture.decide(("a", "f"), outcome="supported_distinct")
    fixture.decide(
        ("a",),
        kind="proposed_positive",
        relationship_annotation="translation",
        direction={
            "query_evidence_id": eid("a3"),
            "reference_evidence_id": eid("a1"),
            "adequacy": "adequate",
        },
    )
    graph = fixture.graph()
    assert frozenset(oid(letter) for letter in "abc") in group_sets(
        graph, "identity_groups"
    )
    assert frozenset(oid(letter) for letter in "abcf") in group_sets(
        graph, "dependence_groups"
    )
    assert not quarantined_observations(graph)
    excluded_history = reference_view(graph, "a", evidence_ids=[eid("a1")])
    arguments = {
        "query_evidence_id": eid("a3"),
        "target_observation_ids": [oid("a")],
    }
    assert (
        adjudication.validate_held_alias_query(graph, excluded_history, **arguments)[
            "status"
        ]
        == "supported_held_alias_dry_run"
    )
    extra = {}
    evidence_ids = [eid("a1")]
    if membership == "historical_name":
        evidence_ids.append(eid("f1"))
    else:
        extra["derived_representations"] = [
            {
                "representation_id": "fictional-historical-alias-cache",
                "kind": "embedding_cache",
                "parent_ids": [eid("f1")],
                "version": "fictional-cache-v1",
                "content_sha256": digest(b"fictional historical alias embedding"),
            }
        ]
    retained_history = reference_view(graph, "a", evidence_ids=evidence_ids, **extra)
    result = adjudication.validate_held_alias_query(
        graph, retained_history, **arguments
    )
    assert result["status"] == "query_alias_leakage"
    assert result["accepted_label"] is False


class FictionalConfiguredPreparation:
    """Exercise C3's real blank-ledger boundary using only local authored sources."""

    def __init__(self, c2):
        self.c2 = c2
        self.root = c2.root
        c2.prepare()
        packet_pin = digest((c2.output / "manifest.json").read_bytes())
        head = review.create_ledger(
            c2.output,
            c2.ledger_path,
            expected_packet_sha256=packet_pin,
            project_root=self.root,
            guard=safe_guard(),
        )
        self.artifacts = self.root / "adjudication-artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.output = self.artifacts / "preparation"
        self.config_path = self.root / "config" / "corpus-adjudication-v1.json"
        c1counts = json.loads((c2.c1.output / "summary.json").read_bytes())["counts"]
        self.config = {
            "schema_version": 1,
            "scope": "08B-C3-offline-adjudication",
            "c2": {
                "configuration": {
                    "path": c2.config_path.relative_to(self.root).as_posix(),
                    "sha256": digest(c2.config_path.read_bytes()),
                },
                "manifest": {
                    "path": (c2.output / "manifest.json")
                    .relative_to(self.root)
                    .as_posix(),
                    "sha256": packet_pin,
                },
                "ledger_path": c2.ledger_path.relative_to(self.root).as_posix(),
                "expected_head": head,
            },
            "output_path": self.output.relative_to(self.root).as_posix(),
            "artifact_roots": [*c2.config["artifact_roots"], "adjudication-artifacts"],
            "normalized_inputs": [
                *c2.config["normalized_inputs"],
                *[
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "sha256": digest(path.read_bytes()),
                    }
                    for path in sorted(c2.output.iterdir())
                ],
                {
                    "path": (c2.ledger_path / "header.json")
                    .relative_to(self.root)
                    .as_posix(),
                    "sha256": head,
                },
            ],
            "expected_counts": {
                "observations": c1counts["observations"],
                "name_entries": c1counts["name_entries"],
                "uncertain_pairs": c1counts["candidate_pairs"],
                "review_tasks": c2.expected_counts["total"],
                "ledger_events": 0,
                "adjudications": 0,
            },
            "limits": {
                "max_new_artifact_bytes": 16_000_000,
                "max_queries": 20_000,
                "max_representations": 100_000,
                "session_seconds": 3600,
            },
            "permissions": dict(readiness.RESTRICTIONS),
            "versions": {
                "graph": "corpus-family-graph-v1",
                "view": "corpus-reference-view-v1",
                "absence": "corpus-absence-candidates-v1",
            },
            "reference_view": {
                "view_id": "fictional-candidate-view",
                "universe_id": "fictional-candidate-universe",
                "selection": "all_observations",
                "view_kind": "corpus_level",
                "membership_complete": True,
            },
            "absent_target_observation_ids": [],
            "actors": [],
        }
        self.save_config()

    def save_config(self):
        self.config_path.write_bytes(encoded(self.config))

    def prepare(self, *, guard=None):
        return adjudication.prepare_adjudication(
            self.config_path,
            self.output,
            project_root=self.root,
            guard=guard or safe_guard(),
        )

    def validate(self, *, guard=None):
        return adjudication.validate_adjudication(
            self.output,
            project_root=self.root,
            config_path=self.config_path,
            guard=guard or safe_guard(),
        )


@pytest.fixture
def preparation(tmp_path, monkeypatch):
    c1 = FictionalReadiness(tmp_path / "fictional-configured")
    monkeypatch.setattr(corpus, "prepare_continuation_sources", c1.admit)
    c1.prepare()
    return FictionalConfiguredPreparation(FictionalReviewPreparation(c1))


def test_configured_blank_preparation_is_private_and_never_accepts_real_decisions(
    preparation,
):
    before = saved_tree(preparation.c2.artifacts)
    result = preparation.prepare()
    assert preparation.validate() == result
    assert result["status"] == "complete_provisional_dry_run"
    for field in (
        "human_decisions",
        "accepted_labels",
        "identity_merges",
        "accepted_reference_families",
        "accepted_absent_families",
    ):
        assert result[field] == 0
    assert result["actual_partitions"] == []
    assert result["accepted_corpus_release"] is False
    assert saved_tree(preparation.c2.artifacts) == before
    assert stat.S_IMODE(preparation.output.stat().st_mode) == 0o700
    for path in preparation.output.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) & 0o277 == 0
    saved = saved_tree(preparation.output)
    with pytest.raises(FileExistsError):
        preparation.prepare()
    assert saved_tree(preparation.output) == saved


@pytest.mark.parametrize(
    "change",
    [
        "network",
        "real_reviews",
        "identity",
        "release",
        "training",
        "step09",
        "limit",
        "actors",
        "targets",
        "counts",
        "normalized_coverage",
        "normalized_duplicates",
        "roots",
        "view",
    ],
)
def test_config_cannot_expand_approved_purpose_or_resource_scope(preparation, change):
    permission = {
        "network": "network_allowed",
        "real_reviews": "human_review_execution_allowed",
        "identity": "identity_merge_allowed",
        "release": "accepted_corpus_release_allowed",
        "training": "training_allowed",
        "step09": "step09_allowed",
    }
    if change in permission:
        preparation.config["permissions"][permission[change]] = True
    elif change == "limit":
        preparation.config["limits"]["max_new_artifact_bytes"] += 1
    elif change == "actors":
        preparation.config["actors"] = [{"actor_id": "fictional-injected-human"}]
    elif change == "targets":
        preparation.config["absent_target_observation_ids"] = ["observation-e"]
    elif change == "counts":
        preparation.config["expected_counts"]["adjudications"] = 1
    elif change == "normalized_coverage":
        preparation.config["normalized_inputs"].pop()
    elif change == "normalized_duplicates":
        preparation.config["normalized_inputs"].append(
            deepcopy(preparation.config["normalized_inputs"][0])
        )
    elif change == "roots":
        preparation.config["artifact_roots"].pop(0)
    else:
        preparation.config["reference_view"]["view_kind"] = "per_query_deletion"
    preparation.save_config()
    with pytest.raises(ValueError):
        preparation.prepare()
    assert not preparation.output.exists()


@pytest.mark.parametrize(
    "change", ["content", "self_rehash", "missing", "extra", "nonprivate"]
)
def test_saved_dry_run_tampering_is_rejected_even_after_rehash(preparation, change):
    preparation.prepare()
    target = preparation.output / "summary.json"
    if change == "missing":
        target.unlink()
    elif change == "extra":
        (preparation.output / "unbound-labels.json").write_bytes(b"[]\n")
    elif change == "nonprivate":
        target.chmod(0o644)
    else:
        content = json.loads(target.read_bytes())
        content["accepted_labels"] = 17
        replace_private(target, encoded(content))
        if change == "self_rehash":
            manifest_path = preparation.output / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["files"][target.name] = {
                "bytes": target.stat().st_size,
                "sha256": digest(target.read_bytes()),
            }
            replace_private(manifest_path, encoded(manifest))
    with pytest.raises(ValueError):
        preparation.validate()


@pytest.mark.parametrize("position", [1, 3, 5])
def test_interrupted_write_never_publishes_completion_or_overwrites_partial_work(
    preparation, monkeypatch, position
):
    original = readiness._write_payload
    writes = []

    def interrupted(directory_fd, name, payload):
        writes.append(name)
        if len(writes) == position:
            raise OSError("fictional C3 write interruption")
        original(directory_fd, name, payload)

    monkeypatch.setattr(readiness, "_write_payload", interrupted)
    with pytest.raises(OSError, match="fictional C3 write interruption"):
        preparation.prepare()
    assert not (preparation.output / "manifest.json").exists()
    saved = saved_tree(preparation.output)
    with pytest.raises(ValueError):
        preparation.validate()
    with pytest.raises(FileExistsError):
        preparation.prepare()
    assert saved_tree(preparation.output) == saved


def test_deadline_during_publication_keeps_manifest_absent(preparation, monkeypatch):
    clock = [0.0]
    guard = safe_guard(clock=lambda: clock[0])
    original = readiness._write_payload

    def expires(directory_fd, name, payload):
        original(directory_fd, name, payload)
        clock[0] = 3601.0

    monkeypatch.setattr(readiness, "_write_payload", expires)
    with pytest.raises(ResourceStop, match="session_deadline"):
        preparation.prepare(guard=guard)
    assert not (preparation.output / "manifest.json").exists()


def test_guard_mutating_written_payload_prevents_final_manifest(
    preparation, monkeypatch
):
    guard = safe_guard()
    original = guard.check
    changed = []

    def mutates_after_payload_writes(*args, **kwargs):
        result = original(*args, **kwargs)
        target = preparation.output / "graph.json"
        if (
            not changed
            and preparation.output.exists()
            and len(list(preparation.output.iterdir())) == 4
        ):
            replace_private(target, target.read_bytes() + b"\n")
            changed.append(True)
        return result

    monkeypatch.setattr(guard, "check", mutates_after_payload_writes)
    with pytest.raises(ValueError):
        preparation.prepare(guard=guard)
    assert changed == [True]
    assert not (preparation.output / "manifest.json").exists()


def test_new_artifact_root_limit_counts_unrelated_existing_files(preparation):
    unrelated = preparation.artifacts / "fictional-existing-large-log"
    with unrelated.open("wb") as stream:
        stream.truncate(16_000_001)
    with pytest.raises((ValueError, ResourceStop)):
        preparation.prepare()
    assert not preparation.output.exists()
    assert unrelated.stat().st_size == 16_000_001


@pytest.mark.parametrize("target", ["output", "parent", "config", "saved_artifact"])
def test_unsafe_storage_paths_fail_without_modifying_external_targets(
    preparation, target
):
    outside = preparation.root / "fictional-outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("Fictional preserved outside content.")
    action = preparation.prepare
    if target == "output":
        preparation.output.symlink_to(outside, target_is_directory=True)
    elif target == "parent":
        preparation.artifacts.rmdir()
        preparation.artifacts.symlink_to(outside, target_is_directory=True)
    elif target == "config":
        copied = outside / "config.json"
        copied.write_bytes(preparation.config_path.read_bytes())
        preparation.config_path.unlink()
        preparation.config_path.symlink_to(copied)
    else:
        preparation.prepare()
        copied = outside / "saved.json"
        saved = preparation.output / "graph.json"
        copied.write_bytes(saved.read_bytes())
        saved.unlink()
        saved.symlink_to(copied)
        action = preparation.validate
    before = saved_tree(outside)
    with pytest.raises((ValueError, OSError)):
        action()
    assert saved_tree(outside) == before


def test_cli_installs_network_denial_and_emits_only_aggregate_failure():
    code = """
import socket
from watchlist import corpus_adjudication as adjudication

def attempted_network(*args, **kwargs):
    socket.socket()
    raise RuntimeError('network denial absent')

adjudication.prepare_adjudication = attempted_network
raise SystemExit(adjudication.main(['prepare', '--config', 'fictional-secret-config.json', '--path', 'fictional-output']))
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["status"] == "failed_closed"
    assert "fictional-secret" not in completed.stdout
    assert completed.stderr == ""


def test_actual_fictional_continuation_through_c1_c2_and_c3_preserves_sources(tmp_path):
    from test_corpus import ContinuationInputs

    inputs = ContinuationInputs(tmp_path / "fictional-end-to-end")
    admitted = inputs.prepare()
    c1_payloads = readiness.assemble_readiness(admitted)
    (inputs.root / "config").mkdir()
    (inputs.root / "readiness-output").mkdir()
    output = inputs.root / "readiness-output" / "preparation"
    config_path = inputs.root / "config" / "corpus-readiness-v1.json"
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
        "expected_counts": json.loads(c1_payloads["summary.json"])["counts"],
        "limits": dict(readiness.LIMITS),
        "permissions": dict(readiness.RESTRICTIONS),
        "versions": {
            "normalization": links.READINESS_NORMALIZATION_VERSION,
            "nomination": links.READINESS_NOMINATION_VERSION,
            "unicode": links.READINESS_UNICODE_VERSION,
        },
        "entity_types": ["organization", "vessel"],
    }
    config_path.write_bytes(encoded(c1_config))
    original_sources = {
        item.path: (inputs.root / item.path).read_bytes() for item in admitted.evidence
    }
    readiness.prepare_readiness(
        config_path, output, project_root=inputs.root, guard=safe_guard()
    )
    c1 = SimpleNamespace(
        root=inputs.root,
        config_path=config_path,
        config=c1_config,
        output=output,
        preparation=admitted,
    )
    fixture = FictionalConfiguredPreparation(FictionalReviewPreparation(c1))
    result = fixture.prepare()
    assert fixture.validate() == result
    assert result["counts"]["observations"] == len(admitted.observations)
    assert result["counts"]["ledger_events"] == 0
    assert (
        result["accepted_labels"]
        == result["identity_merges"]
        == result["accepted_absent_families"]
        == 0
    )
    assert result["accepted_corpus_release"] is False
    assert original_sources == {
        path: (inputs.root / path).read_bytes() for path in original_sources
    }


@pytest.mark.parametrize("reference", ["42", "fictional-observation-e"])
def test_unresolved_incoming_referent_quarantines_possible_target_without_identity(
    tmp_path, reference
):
    def add_reference(observations):
        next(item for item in observations if item["observation_id"] == oid("a"))[
            "referents"
        ] = [reference]

    fixture = FictionalAdjudication(
        tmp_path / "fictional-incoming", mutate=add_reference
    )
    graph = fixture.graph()
    assert {oid("a"), oid("e")} <= quarantined_observations(graph)
    if reference == "42":
        assert oid("d") in quarantined_observations(graph)
    assert group_sets(graph, "identity_groups") == {
        frozenset((oid(x),)) for x in "abcde"
    }
    assert graph["counts"]["independent_accepted_families"] == 0


def test_unresolved_evidence_propagates_over_snapshot_dependence(tmp_path):
    def dependent_unknown(observations):
        original = next(
            item for item in observations if item["observation_id"] == oid("e")
        )
        original["referents"] = ["fictional-unresolved-external-record"]
        copied = deepcopy(original)
        copied["observation_id"] = oid("f")
        copied["snapshot_id"] = "fictional-later-e-snapshot"
        copied["primary_name"] = "Fictional Separately Written Garden"
        copied["referents"] = []
        copied["aliases"] = [
            {
                **copied["aliases"][0],
                "evidence_id": eid("f1"),
                "value": copied["primary_name"],
            }
        ]
        observations.append(copied)

    fixture = FictionalAdjudication(
        tmp_path / "fictional-dependent-incoming", mutate=dependent_unknown
    )
    graph = fixture.graph()
    assert {oid("e"), oid("f")} <= quarantined_observations(graph)
    assert frozenset((oid("e"), oid("f"))) in group_sets(graph, "dependence_groups")
    assert frozenset((oid("e"), oid("f"))) not in group_sets(graph, "identity_groups")
    assert graph["development_exposed"] is True


def test_derived_ancestry_expansion_stops_before_building_an_unbounded_view(
    resolved, monkeypatch
):
    graph = resolved.graph()
    # A deliberately smaller permitted budget exercises the same bounded path.
    monkeypatch.setitem(readiness.LIMITS, "max_witnesses", 10)
    derived = []
    for index in range(4):
        derived.append(
            {
                "representation_id": f"fictional-chain-{index}",
                "kind": "display",
                "parent_ids": [eid("a1"), eid("a2"), eid("a3"), eid("b1")]
                if index == 0
                else [f"fictional-chain-{index - 1}"],
                "version": "fictional-v1",
                "content_sha256": digest(b"fictional ancestry"),
            }
        )
    with pytest.raises(ValueError, match="expansion_limit"):
        reference_view(graph, "de", derived_representations=derived)


def test_query_expansion_respects_the_declared_limit(resolved, monkeypatch):
    graph = resolved.graph()
    view = reference_view(graph, "de")
    monkeypatch.setitem(adjudication.LIMITS, "max_queries", 1)
    with pytest.raises(ValueError, match="item_limit"):
        absent_candidates(graph, view, "ab")


@pytest.mark.parametrize("change", ["cross_case_evidence", "unapproved_purpose"])
def test_rehashed_invalid_adjudication_is_rejected_even_with_its_new_head(
    ledger, change
):
    ledger.decide()
    path = ledger.ledger_path / "events" / "000000000003.json"
    event = json.loads(path.read_bytes())
    if change == "cross_case_evidence":
        event["payload"]["evidence_refs"] = [
            eid("e1"),
            "fictional-identity-observation-e",
        ]
    else:
        event["payload"]["allowed_purpose"] = "model_training"
    event["event_sha256"] = digest(
        encoded({key: value for key, value in event.items() if key != "event_sha256"})
    )
    replace_private(path, encoded(event))
    with pytest.raises(ValueError):
        ledger.graph(expected_head=event["event_sha256"])


def test_restricted_long_alias_cannot_become_a_query_but_original_is_retained(ledger):
    for pair in (("a", "b"), ("a", "c"), ("b", "c")):
        ledger.decide(pair)
    graph = ledger.graph()
    view = reference_view(graph, "de")
    query = {
        "query_id": "fictional-overlength-query",
        "query_evidence_id": eid("b2"),
        "target_observation_ids": [oid("b")],
    }
    result = adjudication.build_absent_candidates(graph, view, queries=[query])
    assert result["candidates"][0]["status"] == "ineligible"
    assert "query_name_restricted" in result["candidates"][0]["reasons"]
    assert any(item["evidence_id"] == eid("b2") for item in graph["name_restrictions"])
    assert eid("b2") in {
        alias["evidence_id"]
        for item in rows(ledger.c1_payloads["observations.jsonl"])
        for alias in item["aliases"]
    }
