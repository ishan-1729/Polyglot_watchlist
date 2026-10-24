"""Hand-checked retrieval depths and denominators; no model inference."""

import pytest

from watchlist.evaluate import summarize


def metric_row(rank, *, index=1000, requested=50, returned=50, depth=50,
               status='positive', ambiguity='unambiguous', target='target'):
    return {
        'metric_protocol_version': 'retrieval-metrics-v2',
        'status': status, 'presence': 'absent' if status == 'absent' else 'present',
        'ambiguity': ambiguity, 'target_id': None if status == 'absent' else target,
        'group_id': target, 'index_entity_count': index, 'requested_k': requested,
        'returned_candidate_count': returned, 'evaluated_depth': depth,
        'target_rank': rank, 'candidate_count': returned,
    }


def test_top50_in_large_index_counts_rank30_as_a_hit():
    result = summarize([metric_row(30)])
    assert result['recall_at_50']['value'] == 1
    assert result['recall_at_50']['denominator'] == 1


def test_truncated_ranking_does_not_claim_full_mrr():
    result = summarize([metric_row(30), metric_row(None, target='missing')])
    assert result['mrr']['value'] is None
    assert result['mrr_at_k']['k'] == 50
    assert result['mrr_at_k']['value'] == pytest.approx(1 / 60)


def test_rank_beyond_returned_records_is_rejected():
    with pytest.raises(ValueError, match='rank'):
        summarize([metric_row(51)])


def test_cutoff_boundaries_and_missing_target_are_hand_checkable():
    rows = [metric_row(rank, target=str(i)) for i, rank in enumerate([1, 10, 30, 50, None])]
    result = summarize(rows)
    assert result['recall_at_1']['value'] == .2
    assert result['recall_at_10']['value'] == .4
    assert result['recall_at_50']['value'] == .8
    assert result['mrr_at_k']['value'] == pytest.approx((1 + .1 + 1 / 30 + .02) / 5)
    assert result['mrr_at_k']['denominator'] == 5


def test_observed_rank51_outside_evaluated50_is_a_miss():
    result = summarize([metric_row(51, requested=100, returned=100)])
    assert result['recall_at_50']['value'] == 0
    assert result['mrr_at_k']['value'] == 0
    assert result['mrr']['value'] is None


def test_full_ranking_preserves_hand_calculated_mrr():
    result = summarize([
        metric_row(rank, index=100, requested=100, returned=100, depth=100, target=str(i))
        for i, rank in enumerate([1, 2, 12, 60])
    ])
    assert result['mrr']['value'] == pytest.approx(.4)
    assert result['recall_at_50']['value'] == .75


def test_all_label_denominators_are_explicit_and_separate():
    rows = [metric_row(30), metric_row(None, target='missing'),
            metric_row(None, status='absent', returned=1, target='absent-one'),
            metric_row(None, status='absent', returned=0, target='absent-two'),
            metric_row(1, status='diagnostic', ambiguity='ambiguous', target='ambiguous'),
            metric_row(None, status='diagnostic', ambiguity='unlabelable', target='unlabelable')]
    result = summarize(rows)
    assert result['label_counts'] == {'positive': 2, 'absent': 2, 'ambiguous': 1, 'unlabelable': 1}
    assert result['positive_queries'] == 2
    assert result['excluded_queries'] == 4
    assert result['recall_at_50']['denominator'] == 2
    assert result['recall_at_50']['value'] == .5
    assert result['absent_suggestion_rate']['denominator'] == 2
    assert result['absent_suggestion_rate']['value'] == .5
    assert result['threshold_false_positive_rate']['value'] is None


def test_index_coverage_and_insufficient_depth_have_different_exclusions():
    result = summarize([metric_row(12, index=20, requested=20, returned=20, depth=20),
                        metric_row(3, index=1000, requested=5, returned=5, depth=5, target='shallow')])
    assert result['recall_at_50']['value'] is None
    assert result['recall_at_50']['uninformative_queries'] == 1
    assert result['recall_at_50']['insufficient_depth_queries'] == 1
    assert result['recall_at_10']['denominator'] == 1
    assert result['recall_at_10']['value'] == 0


def test_underreturned_ranking_still_measures_requested_cutoff():
    result = summarize([metric_row(None, returned=0)])
    assert result['recall_at_50']['denominator'] == 1
    assert result['recall_at_50']['value'] == 0
    assert result['mrr_at_k']['value'] == 0


def test_mixed_depths_never_become_one_unlabeled_mrr():
    result = summarize([metric_row(10), metric_row(5, requested=10, returned=10, depth=10, target='short')])
    assert result['mrr_at_k']['value'] is None
    assert result['mrr_at_k']['k'] is None
    assert len(result['mrr_by_depth']) == 2
    assert sorted(value['value'] for value in result['mrr_by_depth'].values()) == [.1, .2]


@pytest.mark.parametrize('field,value', [
    ('index_entity_count', -1), ('index_entity_count', True),
    ('requested_k', 0), ('requested_k', 1.5),
    ('returned_candidate_count', -1), ('returned_candidate_count', 51),
    ('evaluated_depth', -1), ('evaluated_depth', 51),
    ('target_rank', 0), ('target_rank', True), ('target_rank', 1.5),
    ('presence', 'unknown'), ('presence', []), ('ambiguity', 'maybe'),
    ('ambiguity', {}), ('status', 'absent'), ('status', []),
    ('metric_protocol_version', 'future-version'),
])
def test_impossible_metric_rows_are_rejected(field, value):
    row = metric_row(1)
    row[field] = value
    with pytest.raises(ValueError):
        summarize([row])


def test_missing_explicit_contract_never_falls_back_to_candidate_count():
    with pytest.raises(ValueError, match='contract|protocol|explicit'):
        summarize([{'status': 'positive', 'candidate_count': 100,
                    'target_rank': 1, 'target_id': 'a', 'group_id': 'a'}])


def test_full_positive_without_target_is_impossible():
    with pytest.raises(ValueError, match='target|rank'):
        summarize([metric_row(None, index=50)])


def test_ranking_helper_proves_stable_order_and_observed_rank():
    from watchlist.evaluation_metrics import ranking_fields
    query = metric_row(None)
    candidates = [{'entity_id': 'a', 'similarity_score': 90.0},
                  {'entity_id': 'target', 'similarity_score': 90.0}]
    result = ranking_fields(query, candidates, index_entity_count=1000, requested_k=50)
    assert result['target_rank'] == 2
    assert result['returned_candidate_count'] == 2
    assert result['evaluated_depth'] == 50
    assert 'candidate_count' not in result


@pytest.mark.parametrize('query', [None, [], 'not a query'])
def test_ranking_helper_rejects_nonobject_queries(query):
    from watchlist.evaluation_metrics import ranking_fields
    with pytest.raises(ValueError, match='query'):
        ranking_fields(query, [], index_entity_count=1000, requested_k=50)


@pytest.mark.parametrize('candidates', [
    [{'entity_id': 'a', 'similarity_score': 1}, {'entity_id': 'a', 'similarity_score': 1}],
    [{'entity_id': 'b', 'similarity_score': 1}, {'entity_id': 'a', 'similarity_score': 1}],
    [{'entity_id': 'a', 'similarity_score': 1}, {'entity_id': 'b', 'similarity_score': 2}],
    [{'entity_id': 'a', 'similarity_score': float('nan')}],
    [{'entity_id': 'a', 'similarity_score': float('inf')}],
    [{'entity_id': '', 'similarity_score': 1}],
])
def test_invalid_candidate_rankings_are_rejected(candidates):
    from watchlist.evaluation_metrics import ranking_fields
    with pytest.raises(ValueError):
        ranking_fields(metric_row(None), candidates, index_entity_count=1000, requested_k=50)


def test_candidate_evidence_must_agree_with_claimed_rank_and_count():
    row = metric_row(1, returned=1)
    row['candidates'] = [{'entity_id': 'other', 'similarity_score': 1}]
    with pytest.raises(ValueError, match='rank|target'):
        summarize([row])


def test_explicit_legacy_adapter_requires_full_ranking_evidence():
    from watchlist.evaluation_metrics import adapt_legacy_full_ranking
    old = {'status': 'positive', 'target_id': 'b', 'group_id': 'b', 'target_rank': 2,
           'candidate_count': 3, 'candidates': [
               {'entity_id': 'a', 'similarity_score': 3},
               {'entity_id': 'b', 'similarity_score': 2},
               {'entity_id': 'c', 'similarity_score': 1},
           ]}
    adapted = adapt_legacy_full_ranking([old], index_entity_count=3)
    assert adapted[0]['regression_only'] is True
    assert adapted[0]['metric_protocol_version'] == 'retrieval-metrics-v2'
    assert summarize(adapted)['mrr']['value'] == .5
    assert 'metric_protocol_version' not in old
    with pytest.raises(ValueError, match='full|count|population'):
        adapt_legacy_full_ranking([old], index_entity_count=1000)


@pytest.mark.parametrize('field,value', [
    ('candidate_count', True), ('candidate_count', 1.0),
    ('target_rank', True), ('target_rank', 1.0), ('status', []),
])
def test_legacy_adapter_rejects_malformed_original_fields(field, value):
    from watchlist.evaluation_metrics import adapt_legacy_full_ranking
    old = {'status': 'positive', 'target_id': 'a', 'group_id': 'a', 'target_rank': 1,
           'candidate_count': 1, 'candidates': [{'entity_id': 'a', 'similarity_score': 1}]}
    old[field] = value
    with pytest.raises(ValueError):
        adapt_legacy_full_ranking([old], index_entity_count=1)


def test_legacy_absent_rank_must_be_explicit_even_when_null():
    from watchlist.evaluation_metrics import adapt_legacy_full_ranking
    old = {'status': 'absent', 'target_id': None, 'candidate_count': 1,
           'candidates': [{'entity_id': 'a', 'similarity_score': 1}]}
    with pytest.raises(ValueError, match='rank'):
        adapt_legacy_full_ranking([old], index_entity_count=1)


@pytest.mark.parametrize('population', [True, 1.0, 0, {'full': True}, {'full': 1.0}])
def test_legacy_population_is_validated_even_for_empty_replays(population):
    from watchlist.evaluation_metrics import adapt_legacy_full_ranking
    with pytest.raises(ValueError, match='population'):
        adapt_legacy_full_ranking([], index_entity_count=population)


def test_legacy_population_map_requires_a_named_view():
    from watchlist.evaluation_metrics import adapt_legacy_full_ranking
    old = {'status': 'positive', 'target_id': 'a', 'group_id': 'a', 'target_rank': 1,
           'candidate_count': 1, 'view': [],
           'candidates': [{'entity_id': 'a', 'similarity_score': 1}]}
    with pytest.raises(ValueError, match='view'):
        adapt_legacy_full_ranking([old], index_entity_count={'full': 1})
