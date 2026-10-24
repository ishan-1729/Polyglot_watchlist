"""Deterministic entity retrieval using character-edit similarity."""

from dataclasses import dataclass
from typing import Sequence

from rapidfuzz.distance import Levenshtein

from watchlist.entities import Entity, Provenance
from watchlist.normalize import normalize_name

SCORER_NAME = "rapidfuzz.normalized_levenshtein_similarity_x100"


@dataclass(frozen=True)
class Candidate:
    """One possible record match and the alias responsible for its score."""

    entity_id: str
    display_name: str
    entity_type: str
    matched_alias_id: str
    matched_alias: str
    similarity_score: float
    synthetic: bool
    source: str
    provenance: Provenance | None = None


def rank_candidates(
    query: str, entities: Sequence[Entity], top_k: int = 5
) -> list[Candidate]:
    """Return up to top_k distinct entities from validated reference records.

    Score each normalized alias with unit-cost Levenshtein similarity. Keep
    its original text as evidence. Equal scores use alias ID, then entity ID,
    for stable ordering. There is no probability mapping or rejection threshold.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    normalized_query = normalize_name(query)
    candidates: list[Candidate] = []
    seen_ids: set[str] = set()
    for entity in entities:
        if entity.entity_id in seen_ids:
            raise ValueError(f"duplicate entity_id: {entity.entity_id}")
        seen_ids.add(entity.entity_id)
        if not entity.aliases:
            raise ValueError(f"{entity.entity_id}: at least one alias is required")
        scored_aliases = [
            (
                100.0
                * Levenshtein.normalized_similarity(
                    normalized_query, normalize_name(alias.name)
                ),
                alias,
            )
            for alias in entity.aliases
        ]
        score, best_alias = min(
            scored_aliases, key=lambda item: (-item[0], item[1].alias_id)
        )
        candidates.append(
            Candidate(
                entity_id=entity.entity_id,
                display_name=entity.name,
                entity_type=entity.entity_type,
                matched_alias_id=best_alias.alias_id,
                matched_alias=best_alias.name,
                similarity_score=score,
                synthetic=entity.synthetic,
                source=entity.source,
                provenance=entity.provenance,
            )
        )
    candidates.sort(key=lambda candidate: (-candidate.similarity_score, candidate.entity_id))
    return candidates[:top_k]
