"""C3 offline, fictional adjudication mechanics and provisional family inventories.

Only C2's persisted, externally pinned ledger may supply decisions. Real C2
remains blank. Identity, record equivalence, conservative dependence and open
nominations have separate meanings. Every result is a development-exposed dry
run: no accepted family, training label, partition or corpus release is created.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterator, Mapping
import json
import os
from pathlib import Path
import sys
from typing import Callable

from watchlist import corpus, corpus_readiness as readiness
from watchlist import readiness_review as review
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import ResourceGuard, ResourceStop, _artifact_size

SCOPE = "08B-C3-offline-adjudication"
GRAPH_VERSION = "corpus-family-graph-v1"
VIEW_VERSION = "corpus-reference-view-v1"
ABSENCE_VERSION = "corpus-absence-candidates-v1"
MAX_BYTES = 16_000_000
LIMITS = {
    "max_new_artifact_bytes": MAX_BYTES,
    "max_queries": 20_000,
    "max_representations": 100_000,
    "session_seconds": 3600,
}
RESTRICTIONS = dict(readiness.RESTRICTIONS)
PAYLOAD_NAMES = frozenset(
    {"graph.json", "reference-view.json", "absent-candidates.json", "summary.json"}
)
DERIVED_KINDS = frozenset(
    {"normalized_index", "display", "embedding_cache", "reviewer_memory"}
)
_TOKEN = object()


class AdjudicationError(ValueError):
    """An offline evidence or dry-run boundary failed, without source text."""


def _canonical(value: object) -> bytes:
    return readiness._canonical(value)


def _sha(payload: bytes) -> str:
    return readiness._sha(payload)


def _fields(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise AdjudicationError("unexpected_adjudication_fields")
    return value


def _json(payload: bytes) -> dict:
    try:
        return corpus._json_object(payload, "adjudication object")
    except (ValueError, TypeError, UnicodeError):
        raise AdjudicationError("invalid_adjudication_json") from None


def _strings(value: object, *, maximum: int, nonempty: bool = False) -> list[str]:
    values = review._strings(value, nonempty=nonempty)
    if len(values) > maximum:
        raise AdjudicationError("adjudication_item_limit")
    return values


def _seal(value: dict, field: str) -> dict:
    return {**value, field: _sha(_canonical(value))}


class FamilyGraph(Mapping[str, object]):
    """Immutable admitted graph, including private original-evidence snapshots.

    Public lookup returns a detached copy. A rehashed dictionary is not an
    admitted graph and cannot be used to manufacture absence validation. The
    filesystem validator independently repeats admission and ledger replay.
    This is an API boundary, not a sandbox against malicious Python code.
    """

    __slots__ = ("_encoded", "_observations", "_events", "_check", "_verify")

    def __init__(
        self,
        encoded: bytes,
        observations: bytes,
        events: bytes,
        check: Callable[[], None],
        verify: Callable[[], None],
        *,
        _token: object = None,
    ) -> None:
        if _token is not _TOKEN:
            raise AdjudicationError("admitted_family_graph_required")
        object.__setattr__(self, "_encoded", encoded)
        object.__setattr__(self, "_observations", observations)
        object.__setattr__(self, "_events", events)
        object.__setattr__(self, "_check", check)
        object.__setattr__(self, "_verify", verify)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("family_graph_is_immutable")

    def to_dict(self) -> dict:
        return _json(self._encoded)

    def __getitem__(self, key: str) -> object:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())


def _admitted(graph: FamilyGraph) -> tuple[dict, list[dict], list[dict]]:
    if type(graph) is not FamilyGraph:
        raise AdjudicationError("admitted_family_graph_required")
    graph._check()
    graph._verify()
    return (
        graph.to_dict(),
        review._rows(graph._observations, readiness.LIMITS["max_records"]),
        json.loads(graph._events),
    )


class _Components:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def root(self, member: int) -> int:
        while self.parent[member] != member:
            self.parent[member] = self.parent[self.parent[member]]
            member = self.parent[member]
        return member

    def join(self, left: int, right: int) -> None:
        a, b = sorted((self.root(left), self.root(right)))
        self.parent[b] = a

    def groups(self) -> list[list[int]]:
        groups: dict[int, list[int]] = defaultdict(list)
        for member in range(len(self.parent)):
            groups[self.root(member)].append(member)
        return sorted(groups.values())


def _packet_matches_c1(
    c1: dict[str, bytes], packet: dict[str, bytes], summary: dict
) -> None:
    """Rebuild C2 cases so evidence ownership and task purpose cannot drift."""
    identities: dict[str, list[str]] = {}
    for name, payload in packet.items():
        if not name.endswith(".jsonl"):
            continue
        for case in review._rows(payload, review.LIMITS["max_cases"]):
            for oid, refs in case["identity_evidence_refs"].items():
                if oid in identities and identities[oid] != refs:
                    raise AdjudicationError("inconsistent_identity_evidence")
                identities[oid] = refs
    rebuilt = review.assemble_review_packets(
        c1,
        c1_manifest_sha256=summary["c1_manifest_sha256"],
        fictional=summary["mode"] == "fictional_fixture",
        fictional_identity_evidence=identities,
        metadata=summary["metadata"],
    )
    if rebuilt != packet:
        raise AdjudicationError("packet_c1_evidence_or_purpose_mismatch")


def _derive_graph(
    c1: dict[str, bytes],
    *,
    c1_pin: str,
    packet_pin: str,
    head: str,
    packet_summary: dict,
    cases: dict[str, dict],
    replay: dict,
    events: list[dict],
    check: Callable[[], None],
    verify: Callable[[], None],
) -> FamilyGraph:
    observations = review._rows(
        c1["observations.jsonl"], readiness.LIMITS["max_records"]
    )
    index = {item["observation_id"]: i for i, item in enumerate(observations)}
    identity, dependence, affected = (_Components(len(observations)) for _ in range(3))
    adjudications = []
    pair_decisions: dict[tuple[int, int], list[dict]] = defaultdict(list)
    name_conflicts: set[int] = set()
    unresolved_records: set[int] = set()
    for event in events:
        check()
        if event["kind"] != "adjudication":
            continue
        value = event["payload"]
        case = cases[value["case_id"]]
        ids = [index[oid] for oid in case["observation_ids"]]
        item = {
            "adjudication_id": value["adjudication_id"],
            "case_id": value["case_id"],
            "kind": case["kind"],
            "observations": ids,
            "outcome": value["outcome"],
            "evidence_refs": value["evidence_refs"],
            "identity_evidence_refs": case["identity_evidence_refs"],
            "event_sha256": event["event_sha256"],
            "direction": value["direction"],
            "relationship_annotation": value["relationship_annotation"],
        }
        adjudications.append(item)
        if len(ids) == 2:
            pair_decisions[tuple(sorted(ids))].append(item)
        elif case["kind"] == "proposed_positive":
            if value["outcome"] == "supported_distinct":
                name_conflicts.update(ids)
            elif value["outcome"] != "supported_same":
                unresolved_records.update(ids)
        elif case["kind"] == "flagged":
            # A flag review cannot resolve identity or erase source restrictions.
            unresolved_records.update(ids)
    identity_edges, distinct_edges, dependence_edges, uncertain_edges = [], [], [], []
    for pair, decisions in sorted(pair_decisions.items()):
        check()
        outcomes = {d["outcome"] for d in decisions}
        if {"supported_same", "supported_distinct"} <= outcomes:
            raise AdjudicationError("contradictory_pair_adjudications")
        for outcome, relation, destination in (
            ("supported_same", "same_entity", identity_edges),
            ("supported_distinct", "distinct_entity", distinct_edges),
        ):
            supporting = [d for d in decisions if d["outcome"] == outcome]
            if supporting:
                destination.append(
                    {
                        "left": pair[0],
                        "right": pair[1],
                        "relation": relation,
                        "adjudication_ids": sorted(
                            d["adjudication_id"] for d in supporting
                        ),
                    }
                )
        if "supported_same" in outcomes:
            identity.join(*pair)
            dependence.join(*pair)
            affected.join(*pair)
    for edge in distinct_edges:
        if identity.root(edge["left"]) == identity.root(edge["right"]):
            raise AdjudicationError("transitive_identity_contradiction")
    histories: dict[tuple[str, str], list[int]] = defaultdict(list)
    possible_referents: dict[str, set[int]] = defaultdict(set)
    for i, observation in enumerate(observations):
        possible_referents[observation["provider_id"]].add(i)
        possible_referents[observation["observation_id"]].add(i)
    referent_pairs: set[tuple[int, int]] = set()
    for i, observation in enumerate(observations):
        histories[tuple(observation["source_record_key"])].append(i)
        if observation["referents"]:
            # Raw referents do not prove a namespace. Conservatively quarantine
            # every literal possible endpoint; this never asserts identity.
            unresolved_records.add(i)
        for position, referent in enumerate(observation["referents"]):
            check()
            for target in sorted(possible_referents.get(referent, set()) - {i}):
                pair = tuple(sorted((i, target)))
                affected.join(*pair)
                unresolved_records.add(target)
                if pair not in referent_pairs:
                    if len(referent_pairs) >= readiness.LIMITS["max_pairs"]:
                        raise AdjudicationError("unresolved_referent_pair_limit")
                    referent_pairs.add(pair)
                    uncertain_edges.append(
                        {
                            "left": pair[0],
                            "right": pair[1],
                            "nomination_id": None,
                            "reason": "unresolved_provider_referent",
                            "referent_observation": i,
                            "referent_position": position,
                        }
                    )
    for members in histories.values():
        for right in members[1:]:
            left = members[0]
            dependence.join(left, right)
            affected.join(left, right)
            dependence_edges.append(
                {"left": left, "right": right, "basis": "source_record_history"}
            )
    for edge in identity_edges:
        dependence_edges.append(
            {
                "left": edge["left"],
                "right": edge["right"],
                "basis": "supported_identity",
            }
        )
    unresolved_pairs = set()
    for nomination in review._rows(
        c1["nominations.jsonl"], readiness.LIMITS["max_pairs"]
    ):
        check()
        pair = tuple(sorted((index[nomination["left"]], index[nomination["right"]])))
        outcomes = {d["outcome"] for d in pair_decisions.get(pair, [])}
        if not outcomes or outcomes & {"insufficient_evidence", "ineligible"}:
            affected.join(*pair)
            unresolved_pairs.add(pair)
            unresolved_records.update(pair)
            uncertain_edges.append(
                {
                    "left": pair[0],
                    "right": pair[1],
                    "nomination_id": nomination["nomination_id"],
                    "reason": "unresolved_duplicate_candidate",
                }
            )
    for group in dependence.groups():
        for member in group[1:]:
            affected.join(group[0], member)
    quarantine = []
    for members in affected.groups():
        reasons = []
        if unresolved_records.intersection(members):
            reasons.append("unresolved_evidence_or_incoming_link")
        if name_conflicts.intersection(members):
            reasons.append("contradictory_record_name_label")
        if reasons:
            quarantine.append({"members": members, "reasons": reasons})
    restrictions = []
    for row in review._rows(c1["quarantine.jsonl"], readiness.LIMITS["max_records"]):
        for restriction in row["name_restrictions"]:
            restrictions.append(
                {"observation": index[row["observation_id"]], **restriction}
            )
    counts = {
        "observations": len(observations),
        "name_entries": sum(len(o["aliases"]) for o in observations),
        "uncertain_pairs": len(unresolved_pairs),
        "unresolved_referent_pairs": len(referent_pairs),
        "review_tasks": packet_summary["counts"]["total"],
        "ledger_events": replay["event_count"],
        "adjudications": len(adjudications),
        "provisional_record_groups": len(observations),
        "provisional_identity_groups": len(identity.groups()),
        "provisional_dependence_groups": len(dependence.groups()),
        "quarantined_observations": sum(len(q["members"]) for q in quarantine),
        "independent_accepted_families": 0,
        "accepted_labels": 0,
        "real_identity_merges": 0,
    }
    graph = _seal(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "graph_version": GRAPH_VERSION,
            "mode": packet_summary["mode"],
            "custody": "development",
            "development_exposed": True,
            "fresh_final_eligible": False,
            "c1_manifest_sha256": c1_pin,
            "input_manifest_sha256": _sha(c1["input-manifest.json"]),
            "packet_sha256": packet_pin,
            "ledger_head_sha256": head,
            "observations": [
                {
                    "observation_id": o["observation_id"],
                    "source_record_key": o["source_record_key"],
                    "c1_row": i,
                }
                for i, o in enumerate(observations)
            ],
            "membership_encoding": "zero_based_indices_into_pinned_c1_observations",
            "record_equivalence_groups": [[i] for i in range(len(observations))],
            "identity_groups": identity.groups(),
            "dependence_groups": dependence.groups(),
            "identity_edges": identity_edges,
            "distinct_edges": distinct_edges,
            "dependence_edges": dependence_edges,
            "uncertain_edges": uncertain_edges,
            "quarantine": quarantine,
            "name_restrictions": restrictions,
            "adjudications": adjudications,
            "counts": counts,
            "permissions": RESTRICTIONS,
            "accepted_corpus_release": False,
            "actual_partitions": [],
            "independence_limitation": "provisional_source_or_graph_counts_are_not_independent_accepted_families",
        },
        "graph_sha256",
    )
    encoded = _canonical(graph)
    if len(encoded) > MAX_BYTES:
        raise AdjudicationError("graph_output_byte_limit")
    check()
    return FamilyGraph(
        encoded,
        c1["observations.jsonl"],
        _canonical(events),
        check,
        verify,
        _token=_TOKEN,
    )


def build_family_graph(
    c1_payloads: dict[str, bytes],
    *,
    c1_manifest_sha256: str,
    packet_path: Path,
    ledger_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    actors: tuple[dict, ...] = (),
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> FamilyGraph:
    """Replay genuine pinned C2 events under its lock and derive a dry-run graph."""
    ledger, packet, guard = review._ledger_context(
        ledger_path, packet_path, project_root, guard, expected_packet_sha256
    )
    check = readiness._checkpoint(guard)
    c1 = review._c1_payloads(c1_payloads, c1_manifest_sha256, check)
    packet_bytes, summary, cases = review._load_packet(
        packet, expected_packet_sha256, guard
    )
    if summary["c1_manifest_sha256"] != c1_manifest_sha256:
        raise AdjudicationError("graph_c1_packet_binding_mismatch")
    _packet_matches_c1(c1, packet_bytes, summary)
    with review._locked(ledger) as (_, eventfd, check_lock):
        replay, _, _, _, saved = review._replay(
            ledger,
            eventfd,
            expected_packet_sha256=expected_packet_sha256,
            expected_head=expected_head,
            summary=summary,
            cases=cases,
            actors=actors,
            guard=guard,
        )
        events = [_json(raw) for name, raw in saved if name.startswith("events/")]

        def verify_current() -> None:
            # A snapshot is immutable, but a later or replaced ledger invalidates
            # its use until a new externally pinned graph is explicitly built.
            with review._locked(ledger) as (_, current_events, current_lock):
                review._verify_saved_ledger(ledger, current_events, saved)
                review._verify_packet_saved(
                    packet, expected_packet_sha256, packet_bytes
                )
                current_lock()

        result = _derive_graph(
            c1,
            c1_pin=c1_manifest_sha256,
            packet_pin=expected_packet_sha256,
            head=expected_head,
            packet_summary=summary,
            cases=cases,
            replay=replay,
            events=events,
            check=check,
            verify=verify_current,
        )
        guard.check()
        review._verify_saved_ledger(ledger, eventfd, saved)
        review._verify_packet_saved(packet, expected_packet_sha256, packet_bytes)
        check_lock()
        return result


def _name_index(observations: list[dict]) -> dict[str, tuple[int, dict]]:
    return {
        a["evidence_id"]: (i, a)
        for i, o in enumerate(observations)
        for a in o["aliases"]
    }


def _membership(groups: list[list[int]]) -> dict[int, frozenset[int]]:
    """Share one closure per component, avoiding quadratic duplicate sets."""
    result = {}
    for group in groups:
        members = frozenset(group)
        result.update((i, members) for i in group)
    return result


def _representations(
    values: object, names: dict[str, tuple[int, dict]], check: Callable[[], None]
) -> tuple[list[dict], dict[str, set[str]]]:
    """Resolve every derivative to original name evidence; reject unknown ancestry."""
    if type(values) not in (tuple, list) or len(values) > LIMITS["max_representations"]:
        raise AdjudicationError("invalid_derived_representations")
    indexed = {}
    parent_count = 0
    encoded_bytes = 0
    for value in values:
        check()
        value = _fields(
            value,
            {"representation_id", "kind", "parent_ids", "version", "content_sha256"},
        )
        identifier = review._text(value["representation_id"])
        if (
            identifier in indexed
            or identifier in names
            or value["kind"] not in DERIVED_KINDS
        ):
            raise AdjudicationError("invalid_or_duplicate_representation")
        review._text(value["version"])
        review._hash(value["content_sha256"])
        parents = _strings(
            value["parent_ids"], maximum=LIMITS["max_representations"], nonempty=True
        )
        parent_count += len(parents)
        # Bound before JSON serialization, including worst-case escaping.
        encoded_bytes += 6 * sum(len(parent) for parent in parents)
        encoded_bytes += (
            6
            * sum(
                len(value[field])
                for field in ("representation_id", "kind", "version", "content_sha256")
            )
            + 200
        )
        if (
            parent_count > readiness.LIMITS["max_witnesses"]
            or encoded_bytes > MAX_BYTES
        ):
            raise AdjudicationError("representation_input_expansion_limit")
        indexed[identifier] = {**value, "parent_ids": sorted(parents)}
    ancestry = {name: {name} for name in names}
    pending = set(indexed)
    # Iterative topological traversal avoids recursion limits and detects cycles.
    children: dict[str, list[str]] = defaultdict(list)
    remaining = {}
    for identifier, value in indexed.items():
        parents = value["parent_ids"]
        if any(parent not in names and parent not in indexed for parent in parents):
            raise AdjudicationError("unknown_representation_ancestor")
        remaining[identifier] = sum(parent in indexed for parent in parents)
        for parent in parents:
            children[parent].append(identifier)
    ready = sorted(identifier for identifier, count in remaining.items() if not count)
    ancestry_count = 0
    while ready:
        check()
        identifier = ready.pop()
        ancestors: set[str] = set()
        for parent in indexed[identifier]["parent_ids"]:
            check()
            if (
                ancestry_count + len(ancestors) + len(ancestry[parent])
                > readiness.LIMITS["max_witnesses"]
            ):
                raise AdjudicationError("representation_ancestry_expansion_limit")
            ancestors.update(ancestry[parent])
            if ancestry_count + len(ancestors) > readiness.LIMITS["max_witnesses"]:
                raise AdjudicationError("representation_ancestry_expansion_limit")
        ancestry[identifier] = ancestors
        ancestry_count += len(ancestors)
        if len(ancestry[identifier]) > readiness.LIMITS["max_names"]:
            raise AdjudicationError("representation_ancestry_limit")
        pending.remove(identifier)
        for child in children[identifier]:
            remaining[child] -= 1
            if not remaining[child]:
                ready.append(child)
    if pending:
        raise AdjudicationError("cyclic_representation_ancestry")
    return [indexed[key] for key in sorted(indexed)], ancestry


def build_reference_view(
    graph: FamilyGraph,
    *,
    view_id: str,
    observation_ids: list[str],
    evidence_ids: list[str] | None = None,
    universe_id: str | None = None,
    view_kind: str = "corpus_level",
    membership_complete: bool = True,
    derived_representations: tuple[dict, ...] | list[dict] = (),
    included_representation_ids: list[str] | None = None,
) -> dict:
    """Declare one complete provisional universe, including searchable descendants.

    With ``evidence_ids=None``, every original alias of every selected observation
    is present, including restricted or historical aliases. An explicit list can
    model withheld aliases and stale cache entries. No retrieval top-k or
    per-query deletion is a corpus-level absence universe.
    """
    data, observations, _ = _admitted(graph)
    review._text(view_id)
    universe_id = view_id if universe_id is None else review._text(universe_id)
    if view_kind != "corpus_level" or membership_complete is not True:
        raise AdjudicationError("complete_corpus_level_reference_required")
    ids = _strings(observation_ids, maximum=readiness.LIMITS["max_records"])
    by_id = {o["observation_id"] for o in observations}
    if not set(ids) <= by_id:
        raise AdjudicationError("unknown_reference_observation")
    names = _name_index(observations)
    if evidence_ids is not None:
        refs = _strings(evidence_ids, maximum=readiness.LIMITS["max_names"])
        if not set(refs) <= names.keys():
            raise AdjudicationError("unknown_reference_name_evidence")
        evidence_ids = sorted(refs)
    representations, _ = _representations(derived_representations, names, graph._check)
    all_representations = {r["representation_id"] for r in representations}
    included = (
        sorted(all_representations)
        if included_representation_ids is None
        else sorted(
            _strings(included_representation_ids, maximum=LIMITS["max_representations"])
        )
    )
    if not set(included) <= all_representations:
        raise AdjudicationError("unknown_included_representation")
    view = _seal(
        {
            "schema_version": 1,
            "view_version": VIEW_VERSION,
            "view_id": view_id,
            "universe_id": universe_id,
            "view_kind": view_kind,
            "membership_complete": True,
            "membership_status": "provisional_dry_run",
            "graph_sha256": data["graph_sha256"],
            "c1_manifest_sha256": data["c1_manifest_sha256"],
            "observation_ids": sorted(ids),
            "evidence_ids": evidence_ids,
            "name_membership_policy": "all_original_names_of_selected_observations"
            if evidence_ids is None
            else "explicit_original_name_evidence",
            "derived_representations": representations,
            "included_representation_ids": included,
            "query_scope": None,
            "accepted_reference_families": 0,
            "permissions": RESTRICTIONS,
        },
        "reference_view_sha256",
    )
    if len(_canonical(view)) > MAX_BYTES:
        raise AdjudicationError("reference_view_byte_limit")
    return view


def _validate_view(graph: FamilyGraph, view: object) -> dict:
    if type(view) is not dict:
        raise AdjudicationError("explicit_reference_view_required")
    try:
        rebuilt = build_reference_view(
            graph,
            view_id=view["view_id"],
            universe_id=view["universe_id"],
            observation_ids=view["observation_ids"],
            evidence_ids=view["evidence_ids"],
            view_kind=view["view_kind"],
            membership_complete=view["membership_complete"],
            derived_representations=view["derived_representations"],
            included_representation_ids=view["included_representation_ids"],
        )
    except KeyError:
        raise AdjudicationError("incomplete_reference_view") from None
    if rebuilt != view:
        raise AdjudicationError("reference_view_binding_or_content_mismatch")
    return rebuilt


def _view_membership(
    graph: FamilyGraph, view: dict, observations: list[dict]
) -> tuple[set[int], set[str], dict[str, set[str]]]:
    names = _name_index(observations)
    by_id = {o["observation_id"]: i for i, o in enumerate(observations)}
    members = {by_id[oid] for oid in view["observation_ids"]}
    evidence = (
        set(view["evidence_ids"])
        if view["evidence_ids"] is not None
        else {ref for ref, (i, _) in names.items() if i in members}
    )
    _, ancestry = _representations(view["derived_representations"], names, graph._check)
    for identifier in view["included_representation_ids"]:
        evidence.update(ancestry[identifier])
    members.update(names[ref][0] for ref in evidence)
    return members, evidence, ancestry


def _queries(
    graph: FamilyGraph, observations: list[dict], target_ids: object, queries: object
) -> list[dict]:
    by_id = {o["observation_id"]: o for o in observations}
    ids = _strings(target_ids, maximum=LIMITS["max_queries"])
    if not set(ids) <= by_id.keys():
        raise AdjudicationError("unknown_absence_target")
    if queries is not None and ids:
        raise AdjudicationError("ambiguous_absence_query_construction")
    if queries is None:
        result = []
        for oid in sorted(ids):
            graph._check()
            aliases = sorted(
                by_id[oid]["aliases"], key=lambda alias: alias["evidence_id"]
            )
            if not aliases:
                raise AdjudicationError("natural_query_evidence_required")
            evidence_id = aliases[0]["evidence_id"]
            result.append(
                {
                    "query_id": "absence-query-" + _sha(_canonical([oid, evidence_id])),
                    "query_evidence_id": evidence_id,
                    "target_observation_ids": [oid],
                }
            )
        return result
    if type(queries) is not list or len(queries) > LIMITS["max_queries"]:
        raise AdjudicationError("invalid_absence_queries")
    result, seen = [], set()
    encoded_bytes = 0
    names = _name_index(observations)
    for query in queries:
        query = _fields(
            query, {"query_id", "query_evidence_id", "target_observation_ids"}
        )
        identifier = review._text(query["query_id"])
        review._text(query["query_evidence_id"])
        targets = _strings(
            query["target_observation_ids"],
            maximum=readiness.LIMITS["max_records"],
            nonempty=True,
        )
        if (
            identifier in seen
            or query["query_evidence_id"] not in names
            or not set(targets) <= by_id.keys()
        ):
            raise AdjudicationError("unknown_or_duplicate_absence_query")
        seen.add(identifier)
        encoded_bytes += len(_canonical(query))
        if encoded_bytes > MAX_BYTES:
            raise AdjudicationError("absence_query_input_byte_limit")
        result.append({**query, "target_observation_ids": sorted(targets)})
    return sorted(result, key=lambda item: item["query_id"])


def build_absent_candidates(
    graph: FamilyGraph,
    reference_view: dict,
    *,
    target_observation_ids: list[str] | None = None,
    queries: list[dict] | None = None,
) -> dict:
    """Check complete identity/dependence/alias exclusion in one frozen universe.

    A supported dry-run absence needs fictional identity and natural-name review,
    no unresolved incident evidence, and no target copy in any declared field.
    It says nothing about unknown real-world equivalence or all sanctions lists.
    """
    data, observations, _ = _admitted(graph)
    view = _validate_view(graph, reference_view)
    requests = _queries(
        graph,
        observations,
        [] if target_observation_ids is None else target_observation_ids,
        queries,
    )
    members, present_evidence, _ = _view_membership(graph, view, observations)
    names = _name_index(observations)
    by_id = {o["observation_id"]: i for i, o in enumerate(observations)}
    dependence = _membership(data["dependence_groups"])
    identity = _membership(data["identity_groups"])
    identity_roots = {i: group[0] for group in data["identity_groups"] for i in group}
    quarantine = {i for q in data["quarantine"] for i in q["members"]}
    restricted = {r["evidence_id"] for r in data["name_restrictions"]}
    supports: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for event in data["adjudications"]:
        if event["outcome"] != "supported_same":
            continue
        for ref in event["evidence_refs"]:
            if ref not in names:
                continue
            i, _ = names[ref]
            oid = observations[i]["observation_id"]
            if set(event["identity_evidence_refs"].get(oid, [])).intersection(
                event["evidence_refs"]
            ):
                supports[i][ref].add(event["adjudication_id"])
    supported_keys: dict[tuple[int, str], set[str]] = defaultdict(set)
    for i, references in supports.items():
        for ref, decisions in references.items():
            graph._check()
            supported_keys[
                (identity_roots[i], links.readiness_name_key(names[ref][1]["value"]))
            ].update(decisions)
    present_keys: dict[str, set[int]] = defaultdict(set)
    for ref in present_evidence:
        graph._check()
        i, name = names[ref]
        present_keys[links.readiness_name_key(name["value"])].add(i)
    candidates = []
    candidate_bytes = 0
    independent = set()
    for query in requests:
        graph._check()
        targets = {by_id[oid] for oid in query["target_observation_ids"]}
        excluded = set().union(*{dependence[i] for i in targets})
        query_index, query_name = names[query["query_evidence_id"]]
        query_key = links.readiness_name_key(query_name["value"])
        reasons, support_ids = [], set()
        if query["query_evidence_id"] in restricted:
            reasons.append("query_name_restricted")
        if not supports[query_index].get(query["query_evidence_id"]):
            reasons.append("query_name_review_required")
        for target in sorted(targets):
            matching_support = supported_keys.get(
                (identity_roots[target], query_key), set()
            )
            if not matching_support:
                reasons.append("natural_query_and_identity_review_required")
            support_ids.update(matching_support)
        if not any(query_index in identity[target] for target in targets):
            reasons.append("query_target_identity_not_supported")
        elif not all(query_index in identity[target] for target in targets):
            reasons.append("multiple_distinct_target_identities_require_query_review")
        if present_keys.get(query_key, set()) - excluded:
            reasons.append("reference_name_collision_requires_query_review")
        if data["mode"] != "fictional_fixture":
            reasons.append("real_adjudication_application_disabled")
        if excluded & quarantine:
            reasons.append("unresolved_family_or_incoming_link")
        present = excluded & members
        if present:
            reasons.append("target_family_representation_present")
            status = "supported_presence"
        elif (
            "query_name_restricted" in reasons
            or "query_target_identity_not_supported" in reasons
        ):
            status = "ineligible"
        elif reasons:
            status = "unresolved_membership"
        else:
            status = "supported_absence_dry_run"
            for target in targets:
                independent.add(dependence[target])
        candidate = {
            **query,
            "excluded_family_observation_ids": sorted(
                observations[i]["observation_id"] for i in excluded
            ),
            "present_family_observation_ids": sorted(
                observations[i]["observation_id"] for i in present
            ),
            "adjudication_ids": sorted(support_ids),
            "status": status,
            "reasons": sorted(set(reasons)),
            "construction": "all_equivalent_copies_withheld",
            "accepted_label": False,
        }
        candidate_bytes += len(_canonical(candidate))
        if candidate_bytes > MAX_BYTES:
            raise AdjudicationError("absence_candidate_expansion_limit")
        candidates.append(candidate)
    result = _seal(
        {
            "schema_version": 1,
            "absence_version": ABSENCE_VERSION,
            "graph_sha256": data["graph_sha256"],
            "reference_view_sha256": view["reference_view_sha256"],
            "universe_id": view["universe_id"],
            "ledger_head_sha256": data["ledger_head_sha256"],
            "requests": requests,
            "candidates": candidates,
            "counts": {
                "queries": len(candidates),
                "supported_absence_dry_run": sum(
                    c["status"] == "supported_absence_dry_run" for c in candidates
                ),
                "distinct_dry_run_families": len(independent),
                "supported_presence": sum(
                    c["status"] == "supported_presence" for c in candidates
                ),
                "unresolved_membership": sum(
                    c["status"] == "unresolved_membership" for c in candidates
                ),
                "ineligible": sum(c["status"] == "ineligible" for c in candidates),
                "accepted_absent_families": 0,
                "accepted_labels": 0,
            },
            "permissions": RESTRICTIONS,
            "accepted_corpus_release": False,
            "limitation": "absence_is_relative_to_declared_view_and_reviewed_graph_only",
        },
        "absence_sha256",
    )
    if len(_canonical(result)) > MAX_BYTES:
        raise AdjudicationError("absence_output_byte_limit")
    return result


def validate_absent_candidates(
    graph: FamilyGraph, reference_view: dict, candidates: dict
) -> dict:
    """Regenerate decisions and receipts; editable status/self-hash is insufficient."""
    if type(candidates) is not dict or "requests" not in candidates:
        raise AdjudicationError("complete_absence_candidates_required")
    rebuilt = build_absent_candidates(
        graph, reference_view, queries=candidates["requests"]
    )
    if rebuilt != candidates:
        raise AdjudicationError("absence_candidate_binding_or_content_mismatch")
    return rebuilt


def validate_held_alias_query(
    graph: FamilyGraph,
    reference_view: dict,
    *,
    query_evidence_id: str,
    target_observation_ids: list[str],
) -> dict:
    """Check positive alias withholding separately from corpus-level absence."""
    data, observations, _ = _admitted(graph)
    view = _validate_view(graph, reference_view)
    names = _name_index(observations)
    queries = _queries(
        graph,
        observations,
        [],
        [
            {
                "query_id": "held-alias-check",
                "query_evidence_id": query_evidence_id,
                "target_observation_ids": target_observation_ids,
            }
        ],
    )
    _, evidence, _ = _view_membership(graph, view, observations)
    by_id = {o["observation_id"]: i for i, o in enumerate(observations)}
    identities = _membership(data["identity_groups"])
    targets = set().union(
        *(identities[by_id[oid]] for oid in queries[0]["target_observation_ids"])
    )
    dependencies = _membership(data["dependence_groups"])
    leakage_targets = set().union(*{dependencies[i] for i in targets})
    qindex, qname = names[query_evidence_id]
    key = links.readiness_name_key(qname["value"])
    copies = {
        ref
        for ref, (i, name) in names.items()
        if i in leakage_targets and links.readiness_name_key(name["value"]) == key
    }
    independent = {
        ref for ref in evidence if names[ref][0] in targets and ref not in copies
    }
    restricted = {r["evidence_id"] for r in data["name_restrictions"]}
    independent -= restricted
    quarantine = {i for q in data["quarantine"] for i in q["members"]}
    adequate = any(
        e["kind"] == "proposed_positive"
        and e["outcome"] == "supported_same"
        and e["direction"]["adequacy"] == "adequate"
        and e["direction"]["query_evidence_id"] == query_evidence_id
        and e["direction"]["reference_evidence_id"] in independent
        for e in data["adjudications"]
    )
    status = "supported_held_alias_dry_run"
    if copies & evidence:
        status = "query_alias_leakage"
    elif not independent:
        status = "target_representation_missing"
    elif (
        any(qindex not in identities[by_id[oid]] for oid in target_observation_ids)
        or query_evidence_id in restricted
        or targets & quarantine
        or not adequate
    ):
        status = "unresolved_membership"
    return {
        "status": status,
        "graph_sha256": data["graph_sha256"],
        "reference_view_sha256": view["reference_view_sha256"],
        "query_evidence_id": query_evidence_id,
        "accepted_label": False,
    }


def _load_config(path: Path, root: Path) -> tuple[dict, bytes, dict]:
    raw = corpus._read_saved(path, 2_000_000, "adjudication config")
    config = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "c2",
            "output_path",
            "artifact_roots",
            "normalized_inputs",
            "expected_counts",
            "limits",
            "permissions",
            "versions",
            "reference_view",
            "absent_target_observation_ids",
            "actors",
        },
    )
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["scope"] != SCOPE
    ):
        raise AdjudicationError("unapproved_adjudication_scope")
    if config["limits"] != LIMITS or any(
        type(v) is not int for v in config["limits"].values()
    ):
        raise AdjudicationError("unapproved_adjudication_limits")
    if (
        config["permissions"] != RESTRICTIONS
        or any(type(v) is not bool for v in config["permissions"].values())
        or config["actors"] != []
        or config["absent_target_observation_ids"] != []
    ):
        raise AdjudicationError("real_adjudication_application_disabled")
    if config["versions"] != {
        "graph": GRAPH_VERSION,
        "view": VIEW_VERSION,
        "absence": ABSENCE_VERSION,
    }:
        raise AdjudicationError("unapproved_adjudication_versions")
    c2 = _fields(
        config["c2"], {"configuration", "manifest", "ledger_path", "expected_head"}
    )
    for key in ("configuration", "manifest"):
        _fields(c2[key], {"path", "sha256"})
        readiness._relative(c2[key]["path"])
        review._hash(c2[key]["sha256"])
    readiness._relative(c2["ledger_path"])
    review._hash(c2["expected_head"])
    c2raw = readiness._reference(root, c2["configuration"], maximum=2_000_000)
    c2config, loaded = review._load_config(root / c2["configuration"]["path"], root)
    if (
        loaded != c2raw
        or c2["ledger_path"] != c2config["ledger_path"]
        or Path(c2["manifest"]["path"]).parent.as_posix() != c2config["output_path"]
    ):
        raise AdjudicationError("c2_configuration_or_path_binding_mismatch")
    roots = _strings(config["artifact_roots"], maximum=8, nonempty=True)
    output = root / readiness._relative(config["output_path"])
    if (
        not set(c2config["artifact_roots"]) <= set(roots)
        or output.parent.relative_to(root).as_posix() not in roots
    ):
        raise AdjudicationError("historical_artifact_roots_missing")
    if output.parent in {root / relative for relative in c2config["artifact_roots"]}:
        raise AdjudicationError("separate_c3_artifact_root_required")
    for relative in roots:
        fd = corpus._open_directory(root / readiness._relative(relative))
        os.close(fd)
    counts = _fields(
        config["expected_counts"],
        {
            "observations",
            "name_entries",
            "uncertain_pairs",
            "review_tasks",
            "ledger_events",
            "adjudications",
        },
    )
    if (
        any(type(v) is not int or v < 0 for v in counts.values())
        or counts["ledger_events"]
        or counts["adjudications"]
    ):
        raise AdjudicationError("invalid_real_graph_expected_counts")
    refs = config["normalized_inputs"]
    if type(refs) is not list or not 1 <= len(refs) <= 32:
        raise AdjudicationError("invalid_adjudication_normalized_inputs")
    paths = []
    for ref in refs:
        _fields(ref, {"path", "sha256"})
        paths.append(readiness._relative(ref["path"]))
        review._hash(ref["sha256"])
    if len(paths) != len(set(paths)):
        raise AdjudicationError("duplicate_normalized_reservation")
    declaration = _fields(
        config["reference_view"],
        {"view_id", "universe_id", "selection", "view_kind", "membership_complete"},
    )
    review._text(declaration["view_id"])
    review._text(declaration["universe_id"])
    if (
        declaration["selection"] != "all_observations"
        or declaration["view_kind"] != "corpus_level"
        or declaration["membership_complete"] is not True
    ):
        raise AdjudicationError("unapproved_real_reference_view")
    return config, raw, c2config


def _account_inputs(
    root: Path, config: dict, c2config: dict, guard: ResourceGuard
) -> None:
    manifest = _json(
        readiness._reference(root, config["c2"]["manifest"], maximum=2_000_000)
    )
    if manifest["configuration"] != config["c2"]["configuration"]:
        raise AdjudicationError("c2_manifest_configuration_mismatch")
    required = {ref["path"]: ref["sha256"] for ref in c2config["normalized_inputs"]}
    packet = Path(c2config["output_path"])
    for name, ref in manifest["files"].items():
        required[(packet / name).as_posix()] = ref["sha256"]
    required[config["c2"]["manifest"]["path"]] = config["c2"]["manifest"]["sha256"]
    required[(Path(config["c2"]["ledger_path"]) / "header.json").as_posix()] = config[
        "c2"
    ]["expected_head"]
    provided = {ref["path"]: ref["sha256"] for ref in config["normalized_inputs"]}
    if not required.items() <= provided.items():
        raise AdjudicationError("normalized_input_coverage_missing")
    total = 0
    for ref in config["normalized_inputs"]:
        guard.check()
        total += len(readiness._reference(root, ref, maximum=100_000_000))
    total += _artifact_size((root / config["output_path"]).parent, required=True)
    guard.normalized_bytes = max(guard.normalized_bytes, total)
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")


def _assemble_configured(
    root: Path, config: dict, c2config: dict, guard: ResourceGuard
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    _account_inputs(root, config, c2config, guard)
    c1 = review._admit_c1(root, c2config, guard)
    graph = build_family_graph(
        c1,
        c1_manifest_sha256=c2config["c1"]["manifest"]["sha256"],
        packet_path=root / c2config["output_path"],
        ledger_path=root / config["c2"]["ledger_path"],
        expected_packet_sha256=config["c2"]["manifest"]["sha256"],
        expected_head=config["c2"]["expected_head"],
        project_root=root,
        guard=guard,
    )
    data = graph.to_dict()
    if {key: data["counts"][key] for key in config["expected_counts"]} != config[
        "expected_counts"
    ]:
        raise AdjudicationError("adjudication_counts_differ_from_approval")
    declaration = config["reference_view"]
    view = build_reference_view(
        graph,
        view_id=declaration["view_id"],
        universe_id=declaration["universe_id"],
        observation_ids=[o["observation_id"] for o in data["observations"]],
    )
    absent = build_absent_candidates(graph, view, target_observation_ids=[])
    summary = {
        "schema_version": 1,
        "scope": SCOPE,
        "status": "complete_provisional_dry_run",
        "mode": data["mode"],
        "counts": data["counts"],
        "absence_counts": absent["counts"],
        "graph_sha256": data["graph_sha256"],
        "reference_view_sha256": view["reference_view_sha256"],
        "absence_sha256": absent["absence_sha256"],
        "ledger_head_sha256": data["ledger_head_sha256"],
        "permissions": RESTRICTIONS,
        "accepted_corpus_release": False,
        "actual_partitions": [],
        "human_decisions": 0,
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_reference_families": 0,
        "accepted_absent_families": 0,
    }
    return {
        "graph.json": graph._encoded,
        "reference-view.json": _canonical(view),
        "absent-candidates.json": _canonical(absent),
        "summary.json": _canonical(summary),
    }, c1


def _manifest(payloads: dict[str, bytes], configuration: dict, config: dict) -> bytes:
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "artifact_kind": "adjudication_dry_run",
            "status": "complete_provisional_dry_run",
            "configuration": configuration,
            "c2": config["c2"],
            "files": {
                name: {"sha256": _sha(raw), "bytes": len(raw)}
                for name, raw in sorted(payloads.items())
            },
            "permissions": RESTRICTIONS,
            "human_decisions": 0,
            "accepted_labels": 0,
            "identity_merges": 0,
            "accepted_corpus_release": False,
        }
    )


def _recheck(
    root: Path,
    config_path: Path,
    config_raw: bytes,
    config: dict,
    c2config: dict,
    c1: dict[str, bytes],
    guard: ResourceGuard,
) -> None:
    if corpus._read_saved(config_path, 2_000_000, "adjudication config") != config_raw:
        raise AdjudicationError("adjudication_configuration_changed")
    c2raw = readiness._reference(root, config["c2"]["configuration"], maximum=2_000_000)
    review._recheck_c1(
        root, root / config["c2"]["configuration"]["path"], c2raw, c2config, c1, guard
    )
    _account_inputs(root, config, c2config, guard)
    review.replay_ledger(
        root / config["c2"]["ledger_path"],
        packet_path=root / c2config["output_path"],
        expected_packet_sha256=config["c2"]["manifest"]["sha256"],
        expected_head=config["c2"]["expected_head"],
        project_root=root,
        guard=guard,
    )
    # Resource probes and replay may call application code. Finish them before
    # the last complete byte check, leaving no callback before publication.
    guard.check()
    _final_input_pins(root, config_path, config_raw, config, c2config, c1)


def _final_input_pins(
    root: Path,
    config_path: Path,
    config_raw: bytes,
    config: dict,
    c2config: dict,
    c1: dict[str, bytes],
) -> None:
    """Check every admitted input without running resource or user callbacks."""
    references = list(config["normalized_inputs"])
    original = _json(c1["input-manifest.json"])
    references.extend([original["receipt"], *original["evidence"]])
    for source in original["sources"]:
        references.extend([source["selection"], source["permission"]])
    references.extend(c2config["c1"].values())
    references.extend([config["c2"]["configuration"], config["c2"]["manifest"]])
    seen = set()
    for reference in references:
        key = (reference["path"], reference["sha256"])
        if key not in seen:
            readiness._reference(root, reference, maximum=100_000_000)
            seen.add(key)
    c1_directory = (root / c2config["c1"]["manifest"]["path"]).parent
    for name, raw in c1.items():
        if (
            corpus._read_saved(c1_directory / name, readiness.MAX_BYTES, "C1 evidence")
            != raw
        ):
            raise AdjudicationError("c1_evidence_changed_before_publication")
    packet = root / c2config["output_path"]
    directory = corpus._open_directory(packet)
    try:
        if set(os.listdir(directory)) != review.PAYLOAD_NAMES | {"manifest.json"}:
            raise AdjudicationError("packet_changed_before_publication")
        readiness._same_directory(packet, directory)
    finally:
        os.close(directory)
    with review._locked(root / config["c2"]["ledger_path"]) as (_, eventfd, check_lock):
        if os.listdir(eventfd):
            raise AdjudicationError("real_ledger_changed_before_publication")
        readiness._reference(
            root,
            {
                "path": (Path(config["c2"]["ledger_path"]) / "header.json").as_posix(),
                "sha256": config["c2"]["expected_head"],
            },
            maximum=2_000_000,
        )
        check_lock()
    if corpus._read_saved(config_path, 2_000_000, "adjudication config") != config_raw:
        raise AdjudicationError("adjudication_configuration_changed")


def _write_artifacts(
    output: Path,
    payloads: dict[str, bytes],
    manifest: bytes,
    guard: ResourceGuard,
    recheck: Callable[[], None],
) -> None:
    """Publish private immutable files exclusively; the completion manifest is last."""
    parent = corpus._open_directory(output.parent)
    directory = None
    try:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("adjudication_output_exists")
        amount = (
            sum(map(len, payloads.values()))
            + len(manifest)
            + max(map(len, payloads.values()))
        )
        if _artifact_size(output.parent, required=True) + amount > MAX_BYTES:
            raise AdjudicationError("new_adjudication_artifact_limit")
        guard.reserve_artifact(amount, normalized=True)
        readiness._same_directory(output.parent, parent)
        os.mkdir(output.name, 0o700, dir_fd=parent)
        directory = os.open(
            output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.fsync(parent)
        for name, raw in sorted(payloads.items()):
            guard.check()
            readiness._same_directory(output, directory)
            readiness._write_payload(directory, name, raw)
        for name, raw in payloads.items():
            if (
                corpus._read_saved(output / name, MAX_BYTES, "adjudication payload")
                != raw
            ):
                raise AdjudicationError("written_adjudication_content_mismatch")
        guard.check()
        recheck()
        # The upstream check may itself run cooperative checks. Re-read the
        # output after it, then publish without another callback.
        for name, raw in payloads.items():
            review._private(output / name)
            if (
                corpus._read_saved(output / name, MAX_BYTES, "adjudication payload")
                != raw
            ):
                raise AdjudicationError("written_adjudication_content_mismatch")
        readiness._same_directory(output, directory)
        if set(os.listdir(directory)) != PAYLOAD_NAMES:
            raise AdjudicationError("unexpected_adjudication_artifact_files")
        readiness._write_payload(directory, "manifest.json", manifest)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def prepare_adjudication(
    config_path: Path,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Prepare the authorized real blank-ledger inventory, with zero accepted use."""
    root = Path(project_root).absolute()
    config_path, output = (
        readiness._path(root, config_path),
        readiness._path(root, output),
    )
    config, raw, c2config = _load_config(config_path, root)
    if output != root / config["output_path"]:
        raise AdjudicationError("unapproved_adjudication_output_path")
    if output.exists() or output.is_symlink():
        raise FileExistsError("adjudication_output_exists")
    guard = review._guard(root, config["artifact_roots"], output.parent, guard)
    payloads, c1 = _assemble_configured(root, config, c2config, guard)
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
        config,
    )
    _write_artifacts(
        output,
        payloads,
        manifest,
        guard,
        lambda: _recheck(root, config_path, raw, config, c2config, c1, guard),
    )
    return _json(payloads["summary.json"])


def validate_adjudication(
    input_path: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
    config_path: Path | None = None,
) -> dict:
    """Regenerate from pinned sources and ledger; saved self-hashes grant no trust."""
    root = Path(project_root).absolute()
    config_path = readiness._path(
        root, config_path or "config/corpus-adjudication-v1.json"
    )
    input_path = readiness._path(root, input_path)
    config, raw, c2config = _load_config(config_path, root)
    if input_path != root / config["output_path"]:
        raise AdjudicationError("unapproved_adjudication_input_path")
    guard = review._guard(root, config["artifact_roots"], input_path.parent, guard)
    payloads, c1 = _assemble_configured(root, config, c2config, guard)
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
        config,
    )
    directory = corpus._open_directory(input_path)
    try:
        review._private(input_path, directory=True)
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise AdjudicationError("incomplete_or_extra_adjudication_files")
        for name, expected in {**payloads, "manifest.json": manifest}.items():
            guard.check()
            review._private(input_path / name)
            if (
                corpus._read_saved(
                    input_path / name, MAX_BYTES, "adjudication artifact"
                )
                != expected
            ):
                raise AdjudicationError("adjudication_content_or_manifest_mismatch")
        _recheck(root, config_path, raw, config, c2config, c1, guard)
        readiness._same_directory(input_path, directory)
        # Detect cooperative modifications during upstream rechecking as well.
        for name, expected in {**payloads, "manifest.json": manifest}.items():
            if (
                corpus._read_saved(
                    input_path / name, MAX_BYTES, "adjudication artifact"
                )
                != expected
            ):
                raise AdjudicationError("adjudication_changed_during_validation")
    finally:
        os.close(directory)
    return _json(payloads["summary.json"])


def deny_network(event: str, arguments: tuple) -> None:
    review.deny_network(event, arguments)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline C3 provisional adjudication dry-run"
    )
    parser.add_argument("action", choices=("prepare", "validate"))
    parser.add_argument(
        "--config", type=Path, default=Path("config/corpus-adjudication-v1.json")
    )
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    sys.addaudithook(deny_network)
    try:
        result = (
            prepare_adjudication(args.config, args.path, project_root=args.project_root)
            if args.action == "prepare"
            else validate_adjudication(
                args.path, project_root=args.project_root, config_path=args.config
            )
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "failed_closed", "scope": SCOPE}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
