"""Exact NumPy cosine retrieval, keeping one candidate per entity."""

from typing import Sequence
import numpy as np
from watchlist.entities import Entity
from watchlist.matching import Candidate

SCORER_NAME = 'multilingual_e5_small_cosine'


def unit_vectors(values: np.ndarray) -> np.ndarray:
    """Normalize finite nonzero rows; reject corrupt model/cache output."""
    array = np.asarray(values, dtype=np.float32)
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError('vectors must be a finite two-dimensional matrix')
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if np.any(norms <= 0) or not np.isfinite(norms).all():
        raise ValueError('zero or invalid vector norm')
    return array / norms


def rank_vectors(query: np.ndarray, vectors: np.ndarray, entities: Sequence[Entity],
                 top_k: int = 5) -> list[Candidate]:
    """Cosine over every alias, then best alias per ID; retain original evidence."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError('top_k must be a positive integer')
    if len({e.entity_id for e in entities}) != len(entities):
        raise ValueError('duplicate entity IDs')
    if any(not e.aliases for e in entities):
        raise ValueError('entity has no aliases')
    matrix = unit_vectors(vectors)
    q = unit_vectors(query)
    if q.shape != (1, matrix.shape[1]) or len(matrix) != sum(len(e.aliases) for e in entities):
        raise ValueError('vector dimension or alias row count mismatch')
    # Clip float32 rounding excursions; this is still raw cosine, not probability.
    scores = np.clip(matrix @ q[0], -1.0, 1.0)
    output, offset = [], 0
    for entity in entities:
        pairs = [(float(scores[offset + i]), alias) for i, alias in enumerate(entity.aliases)]
        score, alias = min(pairs, key=lambda item: (-item[0], item[1].alias_id))
        offset += len(entity.aliases)
        output.append(Candidate(entity.entity_id, entity.name, entity.entity_type,
                                alias.alias_id, alias.name, score, entity.synthetic,
                                entity.source, entity.provenance))
    return sorted(output, key=lambda c: (-c.similarity_score, c.entity_id))[:top_k]
