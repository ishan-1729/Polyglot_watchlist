"""Hand-calculated scores, entity grouping, ambiguity, and stable ordering."""

from dataclasses import replace

import pytest

from watchlist.entities import Alias, Entity, SYNTHETIC_SOURCE, load_entities
from watchlist.matching import rank_candidates


def entity(entity_id: str, *names: str) -> Entity:
    return Entity(
        entity_id=entity_id,
        name=names[0],
        entity_type="person",
        aliases=tuple(Alias(f"{entity_id}-a{i}", name) for i, name in enumerate(names, 1)),
        synthetic=True,
        source=SYNTHETIC_SOURCE,
    )


def test_exact_and_one_edit_have_hand_calculated_scores() -> None:
    candidates = rank_candidates("Luma", [entity("syn-b", "Lumo"), entity("syn-a", "Luma")])
    assert [c.entity_id for c in candidates] == ["syn-a", "syn-b"]
    assert [c.similarity_score for c in candidates] == pytest.approx([100, 75])


def test_best_alias_preserves_evidence_and_one_slot_per_entity() -> None:
    candidates = rank_candidates("  LUMA ", [entity("syn-a", "Lumo", "Luma")], top_k=50)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.matched_alias_id == "syn-a-a2"
    assert candidate.matched_alias == "Luma"
    assert candidate.display_name == "Lumo"
    assert candidate.source == SYNTHETIC_SOURCE and candidate.synthetic is True
    assert candidate.similarity_score == 100


def test_alias_and_entity_ties_do_not_depend_on_input_order() -> None:
    a = entity("syn-a", "Lumo", "Lumi")
    b = entity("syn-b", "Lumo", "Lumi")
    expected = rank_candidates("Luma", [a, b])
    reversed_input = [replace(b, aliases=tuple(reversed(b.aliases))), replace(a, aliases=tuple(reversed(a.aliases)))]
    assert rank_candidates("Luma", reversed_input) == expected
    assert [(c.entity_id, c.matched_alias_id) for c in expected] == [
        ("syn-a", "syn-a-a1"), ("syn-b", "syn-b-a1")
    ]


def test_shared_name_returns_both_fictional_entities() -> None:
    candidates = rank_candidates("Luma Vesper", load_entities(), top_k=2)
    assert [c.entity_id for c in candidates] == ["syn-001", "syn-012"]
    assert [c.similarity_score for c in candidates] == [100, 100]


def test_top_k_is_capped_at_distinct_entity_count() -> None:
    candidates = rank_candidates("Luma", load_entities(), top_k=50)
    assert len(candidates) == len({c.entity_id for c in candidates}) == 12


def test_empty_corpus_returns_no_candidates() -> None:
    assert rank_candidates("Luma", []) == []


def test_unrelated_query_still_returns_zero_score_candidates() -> None:
    candidates = rank_candidates("ЖЖЖЖЖ", load_entities())
    assert len(candidates) == 5
    assert all(c.similarity_score == 0 for c in candidates)
    assert [c.entity_id for c in candidates] == [f"syn-{i:03d}" for i in range(1, 6)]


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "3"])
def test_invalid_top_k(top_k: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        rank_candidates("Luma", [], top_k=top_k)  # type: ignore[arg-type]


@pytest.mark.parametrize("query", [" ", "a" * 201])
def test_query_validation_even_on_empty_corpus(query: str) -> None:
    with pytest.raises(ValueError):
        rank_candidates(query, [])


def test_duplicate_entity_objects_are_rejected() -> None:
    item = entity("syn-a", "Luma")
    with pytest.raises(ValueError, match="duplicate entity_id"):
        rank_candidates("Luma", [item, item])


def test_entity_without_aliases_is_rejected() -> None:
    item = replace(entity("syn-a", "Luma"), aliases=())
    with pytest.raises(ValueError, match="at least one alias"):
        rank_candidates("Luma", [item])


@pytest.mark.parametrize(
    ("query", "expected_id"), [("МИРА ВЕЛУНЕ", "syn-005"), ("سيرا لومين", "syn-007")]
)
def test_explicit_non_latin_alias_lookup(query: str, expected_id: str) -> None:
    candidate = rank_candidates(query, load_entities(), top_k=1)[0]
    assert candidate.entity_id == expected_id
    assert candidate.similarity_score == 100


def test_public_provenance_is_carried_without_changing_scores() -> None:
    from watchlist.entities import Provenance

    provenance = Provenance(
        "test-snapshot", "mock-public-dataset", "Fictional test provider",
        "Fictional test publisher", "https://example.invalid/source", "",
        "test-only", None, None, "0" * 64, "https://example.invalid/license",
    )
    fictional = entity("fixture-a", "Moonberry Loom")
    public_branch = replace(fictional, synthetic=False, source="mock-public", provenance=provenance)
    candidate = rank_candidates("Moonberry Loom", [public_branch])[0]
    assert candidate.similarity_score == rank_candidates("Moonberry Loom", [fictional])[0].similarity_score
    assert candidate.provenance == provenance
    assert candidate.synthetic is False and candidate.entity_id == "fixture-a"
