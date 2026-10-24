"""Independent adversarial checks of query integrity and scorer information flow.

The authored records are fictional. No model, saved embedding, source database,
or network is needed to verify these boundaries.
"""

from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from watchlist.entities import Alias, Entity
from watchlist.evaluation_data import (
    audit_queries,
    build_authored_benchmark,
    build_benchmark,
    build_legacy_benchmark,
    fingerprint,
)
from watchlist.normalize import normalize_name


def authored_records():
    names = (
        ("Orchid Observatory", "Orchid Sky Room"),
        ("Lantern Studio", "Lantern Color House"),
        ("Juniper Workshop", "Juniper Clock Room"),
        ("Silver Harbor", "Silver Sail House"),
        ("Willow Atelier", "Willow Pattern Room"),
        ("Amber Beacon", "Amber Signal House"),
    )
    return tuple(
        Entity(f"fictional-{index}", name, "organisation",
               (Alias(f"alias-{index}-a", name), Alias(f"alias-{index}-z", held)),
               True, "authored-protocol-fixture")
        for index, (name, held) in enumerate(names)
    )


def authored_assignments():
    return {
        entity.entity_id: {"group_id": f"family-{index}",
                           "partition": "development" if index % 2 == 0 else "test"}
        for index, entity in enumerate(authored_records())
    }


@pytest.fixture
def protocol():
    entities, assignments = authored_records(), authored_assignments()
    views, queries, receipt = build_benchmark(entities, assignments, absent=[
        {"id": "absent-cobalt", "text": "Cobalt Comet Library", "partition": "test"},
    ])
    return entities, assignments, views, queries, receipt


def selected(queries, *, target="fictional-0", kind="heldout_alias"):
    return deepcopy(next(query for query in queries
                         if query["target_id"] == target and query["kind"] == kind))


def refresh_public_query_hash(query):
    """An attacker can recompute a public digest, but not the sealed manifest."""
    query.pop("query_id")
    query["query_id"] = fingerprint(["evaluation-v2", query])


def test_intact_subset_and_reordering_keep_independent_labels(protocol):
    _, assignments, views, queries, _ = protocol
    present = selected(queries)
    absent = selected(queries, target=None, kind="absent")
    assert present["presence"] == "present" and present["ambiguity"] == "unambiguous"
    assert present["status"] == "positive" and present["partition"] == "development"
    assert absent["presence"] == "absent" and absent["ambiguity"] == "unambiguous"
    assert absent["status"] == "absent" and absent["partition"] == "test"
    assert absent["alias_id"] is None and absent["generation"]["parent_alias_id"] is None
    assert present["scripts"] == ["LATIN"] and present["reference_scripts"] == ["LATIN"]
    audit_queries([absent, present], views, assignments)
    audit_queries([present], views)
    audit_queries([], views, assignments)


@pytest.mark.parametrize("attack", [
    "changed-text", "foreign-parent", "changed-generation", "changed-script-evidence",
    "changed-labels", "changed-provenance", "changed-view", "invented-id",
])
def test_recomputed_public_hash_does_not_authorize_query_changes(protocol, attack):
    entities, assignments, views, queries, _ = protocol
    query = selected(queries)
    if attack == "changed-text":
        query.update(text="Orchid Counterfeit Room", normalized="orchid counterfeit room")
    elif attack == "foreign-parent":
        parent = entities[1].aliases[-1]
        query.update(alias_id=parent.alias_id, base_text=parent.name,
                     text=parent.name, normalized=normalize_name(parent.name))
        query["generation"]["parent_alias_id"] = parent.alias_id
    elif attack == "changed-generation":
        query.update(seed=73, operation="unrecorded transform")
        query["generation"].update(seed=73, operation="unrecorded transform")
    elif attack == "changed-script-evidence":
        query.update(script="Arabic", scripts=["ARABIC"], reference_scripts=["CYRILLIC"])
    elif attack == "changed-labels":
        query.update(presence="absent", ambiguity="unlabelable", status="diagnostic",
                     reason="invented adjudication", exclusion_reasons=["invented adjudication"])
    elif attack == "changed-provenance":
        query.update(source="fictional-replacement", source_fingerprint="0" * 64, provenance={})
    elif attack == "changed-view":
        query.update(view="full", view_fingerprint=fingerprint([asdict(e) for e in views["full"]]))
    refresh_public_query_hash(query)
    if attack == "invented-id":
        query["query_id"] = "invented-query"
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments)


@pytest.mark.parametrize("attack", ["missing-generation", "invalid-view", "invalid-partition", "fake-target", "alias-collision"])
def test_absent_rows_cannot_bypass_ancestry_validation(protocol, attack):
    entities, assignments, views, queries, _ = protocol
    query = selected(queries, target=None, kind="absent")
    if attack == "missing-generation":
        query.pop("generation")
    elif attack == "invalid-view":
        query["view"] = "undeclared"
    elif attack == "invalid-partition":
        query["partition"] = "absent"
    elif attack == "fake-target":
        query.update(target_id="fictional-0", presence="present", status="positive")
    else:
        query.update(text=entities[0].name, base_text=entities[0].name,
                     normalized=normalize_name(entities[0].name))
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments)


@pytest.mark.parametrize("text", ["Orchid Observatory", "Ｏｒｃｈｉｄ　Ｏｂｓｅｒｖａｔｏｒｙ", "Orchid Sky Room"])
def test_authored_absence_rejects_full_and_withheld_normalized_aliases(text):
    with pytest.raises(ValueError, match="collid"):
        build_benchmark(authored_records(), authored_assignments(), absent=[
            {"id": "absent-collision", "text": text, "partition": "test"},
        ])


@pytest.mark.parametrize("declaration", [
    {"id": "absent-cobalt", "text": "Cobalt Comet Library"},
    {"id": "absent-cobalt", "text": "Cobalt Comet Library", "partition": "absent"},
    {"id": "absent-cobalt", "text": "Cobalt Comet Library", "partition": "ambiguity"},
    {"id": "family-0", "text": "Cobalt Comet Library", "partition": "test"},
])
def test_absent_declaration_has_its_own_explicit_valid_family_and_partition(declaration):
    with pytest.raises(ValueError):
        build_benchmark(authored_records(), authored_assignments(), absent=[declaration])


def test_plain_dict_cannot_lose_the_evaluator_manifest(protocol):
    _, assignments, views, queries, _ = protocol
    with pytest.raises(ValueError, match="context"):
        audit_queries([selected(queries)], dict(views), assignments)


def test_restored_withheld_alias_is_rejected_despite_synchronized_public_hashes(protocol):
    _, assignments, views, queries, receipt = protocol
    query = selected(queries)
    assert all(normalize_name(alias.name) != query["normalized"]
               for entity in views["heldout"] if entity.entity_id == query["target_id"]
               for alias in entity.aliases)
    views["heldout"] = views["full"]
    changed_hash = fingerprint([asdict(entity) for entity in views["heldout"]])
    receipt["view_fingerprints"]["heldout"] = changed_hash
    query["view_fingerprint"] = changed_hash
    query["index_exact_ids"] = [query["target_id"]]
    refresh_public_query_hash(query)
    receipt["queries_fingerprint"] = fingerprint([query])
    with pytest.raises(ValueError, match="view"):
        audit_queries([query], views, assignments)


def test_assignment_mutation_is_rejected_even_for_untouched_queries(protocol):
    _, assignments, views, queries, receipt = protocol
    query = selected(queries)
    assignments[query["target_id"]] = {"group_id": "replacement-family", "partition": "test"}
    receipt["assignments"] = deepcopy(assignments)
    with pytest.raises(ValueError, match="assignments"):
        audit_queries([query], views, assignments)
    query.update(assignments[query["target_id"]])
    refresh_public_query_hash(query)
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments)


def test_authored_query_cannot_claim_another_entitys_parent_alias():
    entities, assignments = authored_records(), authored_assignments()
    foreign = entities[1].aliases[0]
    with pytest.raises(ValueError, match="owned"):
        build_authored_benchmark(entities, assignments, {"full": entities}, [{
            "target_id": entities[0].entity_id, "alias_id": foreign.alias_id,
            "text": foreign.name, "kind": "exact", "view": "full",
        }])


def test_cross_script_authorship_rejects_shared_latin_in_mixed_aliases():
    reference, query_alias = Alias("mixed-a", "Orchid نجمة"), Alias("mixed-z", "Orchid Звезда")
    entity = Entity("mixed", reference.name, "organisation", (reference, query_alias), True, "fictional")
    views = {"reference": (replace(entity, aliases=(reference,)),)}
    with pytest.raises(ValueError, match="overlaps"):
        build_authored_benchmark((entity,), {"mixed": {"group_id": "mixed", "partition": "test"}}, views, [{
            "target_id": "mixed", "alias_id": query_alias.alias_id, "text": query_alias.name,
            "kind": "cross_script", "view": "reference",
        }])


def test_legacy_context_needs_explicit_regression_opt_in():
    views, queries, _ = build_legacy_benchmark(authored_records(), authored_assignments())
    with pytest.raises(ValueError, match="regression_only"):
        audit_queries(queries, views)
    audit_queries(queries, views, regression_only=True)


def test_frozen_reranking_scores_only_text_pairs_from_the_shortlisted_view(monkeypatch):
    """Exercise the actual historical evaluate -> rerank -> PairScorer boundary."""
    np = pytest.importorskip("numpy")
    import watchlist.evaluate_reranking as evaluation
    import watchlist.reranking as reranking

    original = authored_records()
    # The canonical name itself is withheld here; keeping it in Entity.name
    # would expose a removed alias even if the model used only Entity.aliases.
    entities = (replace(original[0], name=original[0].aliases[-1].name), *original[1:])
    assignments = authored_assignments()
    views, queries, _ = build_benchmark(entities, assignments)
    selected_queries = [selected(queries), selected(queries, target="fictional-5")]
    audit_queries(selected_queries, views, assignments)
    ids = [entity.entity_id for entity in views["heldout"]]
    allowed = {alias.name for entity in views["heldout"][:5] for alias in entity.aliases}
    forbidden = {query["text"] for query in selected_queries}
    assert allowed.isdisjoint(forbidden)
    calls = []
    boundary_calls = []
    actual_rerank = evaluation.rerank

    def unexpected_io(*args, **kwargs):
        raise AssertionError("the saved-ranking scorer test must not load a source or model")

    for name in ("phase3_benchmark", "multilingual_benchmark", "frozen_benchmark", "MiniLMScorer"):
        monkeypatch.setattr(evaluation, name, unexpected_io)
    for name in ("MiniLMScorer", "fetch_model", "verify_model", "urlopen"):
        monkeypatch.setattr(reranking, name, unexpected_io)

    def checked_rerank(text, candidate_ids, reference_entities, scorer):
        assert type(reference_entities) is tuple
        assert not hasattr(reference_entities, "_context")
        assert reference_entities == views["heldout"]
        withheld = {normalize_name(value) for value in forbidden}
        for entity in reference_entities:
            assert normalize_name(entity.name) not in withheld
            assert all(normalize_name(alias.name) not in withheld for alias in entity.aliases)
            assert set(asdict(entity)) == {"entity_id", "name", "entity_type", "aliases",
                                          "synthetic", "source", "provenance"}
        boundary_calls.append((text, tuple(candidate_ids)))
        return actual_rerank(text, candidate_ids, reference_entities, scorer)

    monkeypatch.setattr(evaluation, "rerank", checked_rerank)

    class SpyPairScorer:
        def score(self, pairs):
            assert type(pairs) is list
            assert all(type(pair) is tuple and len(pair) == 2
                       and all(type(value) is str for value in pair) for pair in pairs)
            assert len(pairs) == 5
            assert {right for _, right in pairs} == allowed
            assert not {right for _, right in pairs} & forbidden
            assert len({left for left, _ in pairs}) == 1
            assert pairs[0][0] in forbidden
            calls.append(deepcopy(pairs))
            return np.arange(len(pairs), dtype=float)

    old = {"methods": {"e5_small": {
        "queries": [{"candidates": [{"entity_id": entity_id} for entity_id in ids],
                     "cross_script_only": False} for _ in selected_queries],
        "timing": {"per_query": [{"query_id": query["query_id"], "samples_ms": [1.0]}
                                 for query in selected_queries]},
    }}}
    result = evaluation.evaluate(views, selected_queries, old, SpyPairScorer(), k=5, repetitions=1)
    assert result["complete"] and result["error"] is None
    assert len(calls) == 4  # One warm-up and one measured pass for each query.
    assert len(boundary_calls) == 4
    for query, observed in zip(selected_queries, (calls[:2], calls[2:])):
        expected = [(query["text"], alias.name) for entity in views["heldout"][:5]
                    for alias in entity.aliases]
        assert observed == [expected, expected]
    first, missing = result["queries"]
    assert (first["baseline_rank"], first["reranked_rank"]) == (1, 5)
    assert missing["baseline_rank"] is missing["reranked_rank"] is None
    assert "absent from E5 shortlist" in missing["failure"]
    for row in result["queries"]:
        assert row["index_entity_count"] == 6 and row["returned_candidate_count"] == 5
        assert row["pair_count"] == 5
        assert {candidate["entity_id"] for candidate in row["reranked_candidates"]} == set(ids[:5])

