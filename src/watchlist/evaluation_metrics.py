"""Versioned retrieval metrics with explicit populations and observed depths.

An index population, a requested limit, a returned list and an evaluated cutoff
are different quantities. Missing targets contribute zero to MRR at the stated
cutoff; their unknown ranks outside the returned list are never invented.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
import math
from numbers import Real
from typing import Any


METRIC_PROTOCOL = 'retrieval-metrics-v2'
LABELS = ('positive', 'absent', 'ambiguous', 'unlabelable')


def metric(value: float | None, numerator: float | None, denominator: int,
           reason: str | None = None) -> dict:
    """Keep the established value/numerator/denominator representation."""
    return {'value': value, 'numerator': numerator, 'denominator': denominator, 'reason': reason}


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def _label(row: Mapping[str, Any]) -> str:
    presence, ambiguity = row.get('presence'), row.get('ambiguity')
    if (not isinstance(presence, str) or presence not in {'present', 'absent'}
            or not isinstance(ambiguity, str) or ambiguity not in {'unambiguous', 'ambiguous', 'unlabelable'}):
        raise ValueError('explicit presence and ambiguity labels are required')
    label = ambiguity if ambiguity != 'unambiguous' else 'positive' if presence == 'present' else 'absent'
    expected = {label} if label in {'positive', 'absent'} else {label, 'diagnostic'}
    if not isinstance(row.get('status'), str) or row['status'] not in expected:
        raise ValueError('status disagrees with presence/ambiguity labels')
    target = row.get('target_id')
    if target is not None and (not isinstance(target, str) or not target.strip()):
        raise ValueError('target_id must be nonblank text or null')
    if presence == 'absent' and target is not None:
        raise ValueError('absent target cannot have a target_id')
    if label == 'positive' and (target is None or not isinstance(row.get('group_id'), str)
                                or not row['group_id'].strip()):
        raise ValueError('positive target and group must be explicit')
    return label


def _candidate_ids(candidates: Sequence) -> list[str]:
    """Validate the observed order, including the deterministic entity-ID tie rule."""
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError('candidates must be an ordered sequence')
    ids, seen = [], set()
    previous = None
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            entity_id, score = candidate.get('entity_id'), candidate.get('similarity_score')
        else:
            entity_id = getattr(candidate, 'entity_id', None)
            score = getattr(candidate, 'similarity_score', None)
        if not isinstance(entity_id, str) or not entity_id.strip() or entity_id in seen:
            raise ValueError('candidate IDs must be distinct nonblank text')
        if isinstance(score, bool) or not isinstance(score, Real) or not math.isfinite(score):
            raise ValueError('candidate scores must be finite real numbers')
        order = (-score, entity_id)
        if previous is not None and order < previous:
            raise ValueError('candidate order must use descending scores and stable entity-ID ties')
        ids.append(entity_id)
        seen.add(entity_id)
        previous = order
    return ids


def _validate_row(row: Mapping[str, Any]) -> str:
    if not isinstance(row, Mapping) or row.get('metric_protocol_version') != METRIC_PROTOCOL:
        raise ValueError('explicit retrieval-metrics-v2 contract is required')
    label = _label(row)
    index = _integer(row.get('index_entity_count'), 'index_entity_count')
    requested = _integer(row.get('requested_k'), 'requested_k', 1)
    returned = _integer(row.get('returned_candidate_count'), 'returned_candidate_count')
    depth = _integer(row.get('evaluated_depth'), 'evaluated_depth', int(index > 0))
    if returned > min(index, requested) or depth > min(index, requested):
        raise ValueError('returned count/evaluated depth exceed index population or requested k')
    if 'candidate_count' in row:
        if _integer(row['candidate_count'], 'legacy candidate_count') != returned:
            raise ValueError('legacy candidate_count contradicts explicit returned count')
    rank = row.get('target_rank')
    if 'target_rank' not in row:
        raise ValueError('observed target_rank must be explicit, including null for misses')
    if rank is not None:
        _integer(rank, 'target_rank', 1)
        if rank > returned or row.get('target_id') is None:
            raise ValueError('target rank is outside the observed candidate list')
    if label == 'positive' and (index == 0 or returned == index and rank is None):
        raise ValueError('positive target missing from a claimed complete ranking')
    if 'candidates' in row:
        ids = _candidate_ids(row['candidates'])
        observed = ids.index(row['target_id']) + 1 if row.get('target_id') in ids else None
        if len(ids) != returned or observed != rank:
            raise ValueError('candidate count or target rank disagrees with observed evidence')
    return label


def ranking_fields(query: Mapping[str, Any], candidates: Sequence, *, index_entity_count: int,
                   requested_k: int, evaluated_depth: int | None = None) -> dict:
    """Derive metric fields from returned records without exposing gold to retrieval.

    Call this only after retrieval. The retriever needs query text and its
    approved alias view; labels and target IDs are used here to score its output.
    """
    if not isinstance(query, Mapping):
        raise ValueError('metric query must be an object')
    index = _integer(index_entity_count, 'index_entity_count')
    requested = _integer(requested_k, 'requested_k', 1)
    ids = _candidate_ids(candidates)
    fields = {
        'metric_protocol_version': METRIC_PROTOCOL,
        'index_entity_count': index, 'requested_k': requested,
        'returned_candidate_count': len(ids),
        'evaluated_depth': min(index, requested) if evaluated_depth is None else evaluated_depth,
        'target_rank': ids.index(query['target_id']) + 1 if query.get('target_id') in ids else None,
    }
    labels = {key: query.get(key) for key in ('status', 'presence', 'ambiguity', 'target_id', 'group_id')}
    _validate_row({**labels, **fields, 'candidates': candidates})
    return fields


def _reciprocal(row: Mapping[str, Any]) -> float:
    rank = row['target_rank']
    return 1 / rank if rank is not None and rank <= row['evaluated_depth'] else 0.0


def summarize(rows: list[dict]) -> dict:
    """Summarize an explicit metric contract; legacy rows need the named adapter.

    Recall retains the historical small-index policy: a cutoff covering the
    whole index is uninformative. An insufficient evaluated depth is a different
    exclusion. Returned count never determines Recall@K eligibility.
    """
    if not isinstance(rows, list):
        raise ValueError('metric rows must be a list')
    classified = [(row, _validate_row(row)) for row in rows]
    labels = Counter(label for _, label in classified)
    positive = [row for row, label in classified if label == 'positive']
    absent = [row for row, label in classified if label == 'absent']
    count = len(positive)
    result = {
        'metric_protocol_version': METRIC_PROTOCOL,
        'query_count': len(rows), 'positive_queries': count,
        'absent_queries': len(absent), 'ambiguous_queries': labels['ambiguous'],
        'unlabelable_queries': labels['unlabelable'], 'excluded_queries': len(rows) - count,
        'label_counts': {label: labels[label] for label in LABELS},
        'entity_count': len({row['target_id'] for row in positive}),
        'group_count': len({row['group_id'] for row in positive}),
        'status_counts': dict(sorted(Counter(row['status'] for row in rows).items())),
        'recall_policy': 'positive queries with index_entity_count > k and evaluated_depth >= k',
    }
    for cutoff in (1, 10, 50):
        eligible = [row for row in positive if row['index_entity_count'] > cutoff
                    and row['evaluated_depth'] >= cutoff]
        hits = sum(row['target_rank'] is not None and row['target_rank'] <= cutoff for row in eligible)
        result[f'recall_at_{cutoff}'] = {
            **metric(hits / len(eligible) if eligible else None, hits if eligible else None, len(eligible),
                     None if eligible else 'no positives with informative index and sufficient evaluated depth'),
            'uninformative_queries': sum(row['index_entity_count'] <= cutoff for row in positive),
            'insufficient_depth_queries': sum(row['index_entity_count'] > cutoff
                                              and row['evaluated_depth'] < cutoff for row in positive),
        }
    complete = [row for row in positive if row['returned_candidate_count'] == row['index_entity_count']
                and row['evaluated_depth'] == row['index_entity_count']]
    result['full_ranking_queries'] = len(complete)
    if count and len(complete) == count:
        reciprocal = sum(_reciprocal(row) for row in positive)
        result['mrr'] = metric(reciprocal / count, reciprocal, count)
    else:
        result['mrr'] = metric(None, None, 0, 'no eligible positive queries' if not count
                               else 'full ranking is unavailable for one or more positive queries')
    by_depth = {}
    for requested, depth in sorted({(row['requested_k'], row['evaluated_depth']) for row in positive}):
        selected = [row for row in positive if (row['requested_k'], row['evaluated_depth']) == (requested, depth)]
        reciprocal = sum(_reciprocal(row) for row in selected)
        by_depth[f'requested={requested},evaluated={depth}'] = {
            **metric(reciprocal / len(selected), reciprocal, len(selected)),
            'requested_k': requested, 'k': depth,
        }
    result['mrr_by_depth'] = by_depth
    result['mrr_at_k'] = next(iter(by_depth.values())).copy() if len(by_depth) == 1 else {
        **metric(None, None, 0, 'mixed requested/evaluated depths; use mrr_by_depth' if count
                 else 'no eligible positive queries'), 'requested_k': None, 'k': None,
    }
    suggested = sum(row['returned_candidate_count'] > 0 for row in absent)
    result['absent_suggestion_rate'] = metric(suggested / len(absent) if absent else None,
                                             suggested if absent else None, len(absent),
                                             None if absent else 'no eligible absent queries')
    result['threshold_false_positive_rate'] = metric(None, None, 0, 'no decision threshold in this baseline')
    return result


def adapt_legacy_full_ranking(rows: list[dict], *, index_entity_count: int | Mapping[str, int]) -> list[dict]:
    """Explicitly adapt saved full rankings for regression-only metric replay.

    The caller supplies an independently known population (or a view-to-size
    mapping). A legacy returned count is never treated as proof of index size.
    Historical diagnostic labels remain unlabelable, without new adjudication.
    """
    if not isinstance(rows, list):
        raise ValueError('legacy rows must be a list')
    if isinstance(index_entity_count, Mapping):
        for view, population in index_entity_count.items():
            if not isinstance(view, str) or not view.strip():
                raise ValueError('population mapping requires nonblank view names')
            _integer(population, 'independently supplied index population', 1)
    else:
        _integer(index_entity_count, 'independently supplied index population', 1)
    result = []
    for row in rows:
        if not isinstance(row, Mapping) or 'metric_protocol_version' in row:
            raise ValueError('legacy adapter requires legacy full-ranking rows')
        if isinstance(index_entity_count, Mapping):
            view = row.get('view')
            if not isinstance(view, str) or view not in index_entity_count:
                raise ValueError('legacy view has no independently supplied index population')
            index = index_entity_count[view]
        else:
            index = index_entity_count
        _integer(index, 'independently supplied index population', 1)
        returned = _integer(row.get('candidate_count'), 'legacy candidate_count')
        if 'target_rank' not in row:
            raise ValueError('legacy target_rank must be explicit, including null for misses')
        if row['target_rank'] is not None:
            _integer(row['target_rank'], 'legacy target_rank', 1)
        if returned != index or not isinstance(row.get('candidates'), list) or len(row['candidates']) != index:
            raise ValueError('legacy evidence is not a full ranking of the supplied population')
        status = row.get('status')
        if not isinstance(status, str) or status not in {'positive', 'absent', 'diagnostic'}:
            raise ValueError('unknown legacy label')
        labels = {'presence': 'absent' if row.get('target_id') is None else 'present',
                  'ambiguity': 'unlabelable' if status == 'diagnostic' else 'unambiguous'}
        adapted = {**row, **labels, 'regression_only': True, 'legacy_metric_adapter': 'explicit-full-ranking-v1'}
        fields = ranking_fields(adapted, row['candidates'], index_entity_count=index, requested_k=index)
        if row.get('target_rank') != fields['target_rank']:
            raise ValueError('legacy target rank disagrees with candidate evidence')
        result.append({**adapted, **fields})
    return result
