"""Hand-calculated rankings and metrics, plus offline reproducibility."""
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import pytest
from watchlist.evaluate import summarize, latency_summary, evaluate_queries, run
from watchlist.entities import Entity, Alias
from watchlist.evaluation_data import build_benchmark
from watchlist import evaluate


def row(rank, count=100, status='positive', eid='a'):
    return {'metric_protocol_version': 'retrieval-metrics-v2', 'status':status,
            'presence': 'absent' if status == 'absent' else 'present',
            'ambiguity': 'unlabelable' if status == 'diagnostic' else 'unambiguous',
            'index_entity_count':count,'requested_k':count,'returned_candidate_count':count,
            'evaluated_depth':count,'target_rank':rank,
            'target_id':None if status == 'absent' else eid,'group_id':eid}


def benchmark():
    entities = [
        Entity('a', 'Luma Vesper', 'person', (Alias('a1', 'Luma Vesper'), Alias('a2', 'Lumi Vesper')), True, 'fixture'),
        Entity('b', 'Tavi Orinel', 'person', (Alias('b1', 'Tavi Orinel'), Alias('b2', 'Tav Orinel')), True, 'fixture'),
    ]
    assignments = {entity.entity_id: {'group_id': entity.entity_id, 'partition': 'test'} for entity in entities}
    return build_benchmark(entities, assignments)


def test_hand_calculated_metrics():
    result=summarize([row(r,eid=str(i)) for i,r in enumerate([1,2,12,60])])
    assert result['recall_at_1']['value']==.25
    assert result['recall_at_10']['value']==.5
    assert result['recall_at_50']['value']==.75
    assert result['mrr']['value']==pytest.approx(.4)
    assert result['mrr']['denominator']==4


def test_uninformative_and_empty_metrics_are_null():
    r=summarize([row(1,20),row(12,20)])
    assert r['recall_at_50']['value'] is None
    assert r['recall_at_50']['uninformative_queries']==2
    assert r['recall_at_10']['value']==.5
    assert summarize([])['mrr']['value'] is None
    assert summarize([row(1,3)])['recall_at_10']['value'] is None


def test_absent_and_ambiguous_do_not_change_positive_denominator():
    r=summarize([row(2),row(None,status='absent'),row(1,status='diagnostic')])
    assert r['mrr']['value']==.5 and r['mrr']['denominator']==1
    assert r['absent_suggestion_rate']['value']==1
    assert r['threshold_false_positive_rate']['value'] is None
    missing = {**row(None), 'index_entity_count': 1000}
    assert summarize([missing])['mrr_at_k']['value']==0


def test_latency_definition():
    result=latency_summary([10,2,5,3,4])
    assert result['median_ms']==4 and result['p95_ms']==10
    assert latency_summary([])['p95_ms'] is None


def test_actual_ranking_has_hand_checkable_tie_failure():
    es=[Entity(i,'Luma','person',(Alias(i+'1','Luma'),),True,'fictional') for i in ['a','b']]
    views, queries, _ = build_benchmark(es, {i: {'group_id': i, 'partition': 'test'} for i in ['a', 'b']})
    q = next(q for q in queries if q['target_id'] == 'b' and q['kind'] == 'exact')
    rows,timing=evaluate_queries(views,[q],1)
    assert rows[0]['target_rank']==2
    assert rows[0]['status'] == 'diagnostic' and rows[0]['failure'] is None
    assert [c['similarity_score'] for c in rows[0]['candidates']]==[100,100]
    assert timing['observations']==1


def test_full_fictional_run_is_reproducible_except_timing():
    config=json.loads(Path('eval/configs/baseline.json').read_text());config['timing_repetitions']=1
    config['benchmark_mode'] = 'regression_only_legacy'
    a,qa=run(config);b,qb=run(config)
    a.pop('timing');b.pop('timing')
    assert a==b and qa==qb
    assert a['scorer']=='rapidfuzz.normalized_levenshtein_similarity_x100'
    assert a['protocol_version'] == 'baseline-evaluation-v2' and a['regression_only'] is True
    assert all(q['partition'] not in {'train','calibration_fit','threshold_selection'} for q in qa)


def test_cli_writes_real_reports(tmp_path):
    config=json.loads(Path('eval/configs/baseline.json').read_text())
    config.update(output=str(tmp_path/'result'),timing_repetitions=1,benchmark_mode='regression_only_legacy')
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    proc=subprocess.run([sys.executable,'-B','-m','watchlist.evaluate','--config',str(path)],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    result=json.loads((tmp_path/'result/results.json').read_text())
    assert result['queries'] and (tmp_path/'result/queries.jsonl').exists()
    assert 'N/A' in (tmp_path/'result/report.md').read_text()
    assert result['regression_only'] is True and result['metric_protocol_version'] == 'retrieval-metrics-v2'


def test_invalid_repetitions_rejected():
    with pytest.raises(ValueError,match='repetitions'):
        evaluate_queries({},[],0)


def test_failure_explanation_uses_scorer_name():
    from watchlist.evaluate import ranking_failure
    from types import SimpleNamespace
    candidates=[SimpleNamespace(similarity_score=.9),SimpleNamespace(similarity_score=.2)]
    assert ranking_failure('positive',2,candidates,'cosine similarity')=='another record has higher cosine similarity'
    assert ranking_failure('positive',2,candidates)=='another record has higher normalized edit similarity'
    candidates[1].similarity_score = .9
    assert 'stable entity-ID ordering' in ranking_failure('positive', 2, candidates)


def test_bound_context_is_required_before_search(monkeypatch):
    views, queries, _ = benchmark()
    monkeypatch.setattr(evaluate, 'rank_candidates', lambda *args, **kwargs: pytest.fail('search before audit'))
    with pytest.raises(ValueError, match='context|bound'):
        evaluate_queries(dict(views), queries, 1)


def test_all_queries_are_audited_before_the_first_search(monkeypatch):
    views, queries, _ = benchmark()
    changed = deepcopy(queries)
    changed[-1]['text'] = 'Invented Ancestry'
    monkeypatch.setattr(evaluate, 'rank_candidates', lambda *args, **kwargs: pytest.fail('search before audit'))
    with pytest.raises(ValueError, match='ancestry|evidence'):
        evaluate_queries(views, changed, 1)


def test_changed_view_is_rejected_before_search(monkeypatch):
    views, queries, _ = benchmark()
    views['heldout'] = views['full']
    monkeypatch.setattr(evaluate, 'rank_candidates', lambda *args, **kwargs: pytest.fail('search before audit'))
    with pytest.raises(ValueError, match='view|reference'):
        evaluate_queries(views, queries, 1)


def test_search_receives_only_text_and_selected_alias_tuple(monkeypatch):
    views, queries, _ = benchmark()
    query = next(q for q in queries if q['kind'] == 'heldout_alias' and q['status'] == 'positive')
    actual, calls = evaluate.rank_candidates, []

    def observed(text, entities, top_k):
        assert type(text) is str and type(entities) is tuple
        assert entities is views[query['view']]
        assert all(isinstance(entity, Entity) for entity in entities)
        assert query['alias_id'] not in {alias.alias_id for entity in entities for alias in entity.aliases}
        calls.append((text, entities, top_k))
        return actual(text, entities, top_k)

    monkeypatch.setattr(evaluate, 'rank_candidates', observed)
    rows, _ = evaluate_queries(views, [query], 1, requested_k=1)
    assert len(calls) == 2
    assert rows[0]['index_entity_count'] == 2
    assert rows[0]['requested_k'] == rows[0]['returned_candidate_count'] == rows[0]['evaluated_depth'] == 1
    assert 'candidate_count' not in rows[0]


def test_ranked_alias_must_belong_to_approved_view(monkeypatch):
    views, queries, _ = benchmark()
    query = next(q for q in queries if q['kind'] == 'heldout_alias' and q['status'] == 'positive')
    actual = evaluate.rank_candidates

    def leaked(text, entities, top_k):
        candidates = actual(text, entities, top_k)
        candidates[0] = replace(candidates[0], matched_alias_id=query['alias_id'], matched_alias=query['base_text'])
        return candidates

    monkeypatch.setattr(evaluate, 'rank_candidates', leaked)
    with pytest.raises(ValueError, match='alias|view'):
        evaluate_queries(views, [query], 1)


def test_timed_repetitions_cannot_change_the_saved_ranking(monkeypatch):
    views, queries, _ = benchmark()
    actual, calls = evaluate.rank_candidates, 0

    def changing(text, entities, top_k):
        nonlocal calls
        calls += 1
        candidates = actual(text, entities, top_k)
        return candidates if calls == 1 else list(reversed(candidates))

    monkeypatch.setattr(evaluate, 'rank_candidates', changing)
    with pytest.raises(ValueError, match='repeat|ranking'):
        evaluate_queries(views, queries[:1], 1)


@pytest.mark.parametrize('requested', [0, -1, True, 1.5])
def test_invalid_requested_depth_rejected(requested):
    with pytest.raises(ValueError, match='requested'):
        evaluate_queries({}, [], 1, requested_k=requested)


def test_saved_config_requires_an_explicit_legacy_choice():
    config = json.loads(Path('eval/configs/baseline.json').read_text())
    config['timing_repetitions'] = 1
    with pytest.raises(ValueError):
        run(config)


@pytest.mark.parametrize('mode', [[], {}])
def test_benchmark_mode_rejects_nontext_values(mode):
    with pytest.raises(ValueError, match='benchmark_mode'):
        run({'benchmark_mode': mode})


@pytest.mark.parametrize('output', [None, [], 3, ''])
def test_cli_rejects_invalid_output_before_retrieval(tmp_path, monkeypatch, capsys, output):
    path = tmp_path / 'invalid-output.json'
    path.write_text(json.dumps({'output': output}))
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--config', str(path)])
    monkeypatch.setattr(evaluate, 'run', lambda config: pytest.fail('retrieval before output validation'))
    with pytest.raises(SystemExit) as error:
        evaluate.main()
    assert error.value.code == 2
    assert 'output' in capsys.readouterr().err


def test_cli_never_overwrites_an_existing_output(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    evidence = output / 'results.json'
    evidence.write_text('preserved historical evidence\n')
    config = json.loads(Path('eval/configs/baseline.json').read_text())
    config.update(output=str(output), timing_repetitions=1, benchmark_mode='regression_only_legacy')
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    before = (evidence.read_bytes(), evidence.stat().st_mtime_ns, output.stat().st_mtime_ns)
    process = subprocess.run([sys.executable, '-B', '-m', 'watchlist.evaluate', '--config', str(path)],
                             capture_output=True, text=True)
    assert process.returncode != 0
    assert 'exist' in process.stderr.lower()
    assert (evidence.read_bytes(), evidence.stat().st_mtime_ns, output.stat().st_mtime_ns) == before
    assert sorted(p.name for p in output.iterdir()) == ['results.json']
