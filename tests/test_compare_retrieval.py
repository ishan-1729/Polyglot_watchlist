"""Comparison boundaries use synthetic sources and a deterministic fake encoder."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
np = pytest.importorskip("numpy", reason="install the embeddings extra for vector tests")
from watchlist import compare_retrieval as comparison
from watchlist.compare_retrieval import multilingual_benchmark,phase3_benchmark,compare
from watchlist.entities import Alias, Entity
from watchlist.evaluation_data import build_authored_benchmark, build_benchmark, fingerprint
from watchlist.matching import Candidate


class FakeEncoder:
    config={'dimension':2}
    metadata={'model':'mock'}
    load_seconds=0.0
    def __init__(self, *_):
        self.calls=[]
    def encode(self,texts):
        self.calls.append(list(texts))
        return np.array([[1,len(t)] for t in texts],dtype=np.float32)


def test_phase3_frozen_fixture_and_comparison(tmp_path):
    views,qs,evidence=phase3_benchmark('fictional')
    result=compare(views,qs[:3],FakeEncoder(),tmp_path,1,regression_only=True)
    a=result['methods']['rapidfuzz']['queries'];b=result['methods']['e5_small']['queries']
    assert [q['query_id'] for q in a]==[q['query_id'] for q in b]
    for x,y in zip(a,b):
        assert {c['entity_id'] for c in x['candidates']}=={c['entity_id'] for c in y['candidates']}
    assert result['methods']['e5_small']['timing']['observations']==3
    assert result['regression_only'] is True
    assert evidence['regression_only'] is True
    assert len(qs)==94
    saved=json.loads(Path('eval/results/phase04/fictional/results.json').read_text())
    assert fingerprint(qs)==saved['query_fingerprint']
    assert all('protocol_version' not in q for q in qs)


def test_cross_script_fixture_and_ambiguity():
    views,qs,evidence=multilingual_benchmark()
    assert all(len(v)==10 for v in views.values())
    test=[q for q in qs if q['partition']=='test' and q['kind']=='cross_script']
    assert len(test)==12
    assert all(q['script'] not in q['reference_scripts'] for q in test)
    assert {q['target_id'] for q in qs if q['partition']=='ambiguity'}=={'ml-009','ml-010'}
    assert all(q['status']=='diagnostic' for q in qs if q['partition']=='ambiguity')
    assert evidence['regression_only'] is True
    saved=json.loads(Path('eval/results/phase04/multilingual/results.json').read_text())
    assert fingerprint(qs)==saved['query_fingerprint']


def small_benchmark():
    records=(
        Entity('a','Fictional Cedar','organisation',
               (Alias('a1','Fictional Cedar'),Alias('a2','Cedar Imaginary Workshop')),True,'fixture'),
        Entity('b','Invented Moon','organisation',
               (Alias('b1','Invented Moon'),Alias('b2','Moon Imaginary Workshop')),True,'fixture'),
    )
    assignments={e.entity_id:{'partition':'test','group_id':e.entity_id} for e in records}
    return build_benchmark(records,assignments)


def forbid_retrieval(monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail('invalid input reached cache, encoder, or retrieval')
    for name in ('cached_aliases','rank_candidates','rank_vectors'):
        monkeypatch.setattr(comparison,name,forbidden)
    monkeypatch.setattr(FakeEncoder,'encode',forbidden)


@pytest.mark.parametrize('field,value',[
    ('target_id','b'),('alias_id','b1'),('base_text','Changed ancestor'),
    ('text','Changed query'),('normalized','changed normalization'),
    ('group_id','changed-group'),('partition','development'),('status','absent'),
    ('presence','absent'),('ambiguity','ambiguous'),('script','ARABIC'),
    ('reference_scripts',['ARABIC']),('source_fingerprint','0'*64),
    ('view_fingerprint','0'*64),('view','missing'),('seed',43),
])
def test_changed_queries_fail_before_cache_or_model(monkeypatch,tmp_path,field,value):
    views,queries,_=small_benchmark()
    query=deepcopy(next(q for q in queries if q['target_id']=='a' and q['kind']=='exact'))
    query[field]=value
    forbid_retrieval(monkeypatch)
    with pytest.raises(ValueError):
        compare(views,[query],FakeEncoder(),tmp_path,1)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('replacement',['changed','plain','heldout-leak'])
def test_changed_or_unsealed_views_fail_before_cache(monkeypatch,tmp_path,replacement):
    views,queries,_=small_benchmark()
    query=next(q for q in queries if q['kind']=='heldout_alias')
    if replacement=='changed':
        views['heldout']=tuple(replace(e,aliases=(Alias(e.entity_id+'new','Replaced Reference'),))
                               for e in views['heldout'])
    elif replacement=='plain':
        views=dict(views)
    else:
        views['heldout']=views['full']
    forbid_retrieval(monkeypatch)
    with pytest.raises(ValueError):
        compare(views,[query],FakeEncoder(),tmp_path,1)


def test_legacy_comparison_requires_explicit_regression_opt_in(monkeypatch,tmp_path):
    views,queries,_=phase3_benchmark('fictional')
    forbid_retrieval(monkeypatch)
    with pytest.raises(ValueError,match='regression'):
        compare(views,queries[:1],FakeEncoder(),tmp_path,1)


def test_only_used_alias_view_reaches_cache_and_rankers(monkeypatch,tmp_path):
    views,queries,_=small_benchmark()
    query=next(q for q in queries if q['target_id']=='a' and q['kind']=='heldout_alias')
    expected=views['heldout']
    cache_calls=[]
    fuzzy_calls=[]
    vector_calls=[]
    cache=comparison.cached_aliases
    fuzzy=comparison.rank_candidates
    vectors=comparison.rank_vectors
    def cache_spy(entities,encoder,root):
        cache_calls.append(entities)
        assert entities is expected
        return cache(entities,encoder,root)
    def fuzzy_spy(text,entities,top_k):
        fuzzy_calls.append(text)
        assert text==query['text'] and entities is expected and top_k==len(expected)
        return fuzzy(text,entities,top_k)
    def vector_spy(vector,matrix,entities,top_k):
        vector_calls.append(vector)
        assert entities is expected and top_k==len(expected)
        return vectors(vector,matrix,entities,top_k)
    def no_reload(*args,**kwargs):
        pytest.fail('comparison reloaded a source instead of using its supplied view')
    monkeypatch.setattr(comparison,'cached_aliases',cache_spy)
    monkeypatch.setattr(comparison,'rank_candidates',fuzzy_spy)
    monkeypatch.setattr(comparison,'rank_vectors',vector_spy)
    monkeypatch.setattr(comparison,'load_entities',no_reload)
    monkeypatch.setattr(comparison,'load_database',no_reload)
    encoder=FakeEncoder()
    result=compare(views,[query],encoder,tmp_path,2)
    assert cache_calls==[expected]
    assert len(fuzzy_calls)==len(vector_calls)==3
    assert encoder.calls==[[a.name for e in expected for a in e.aliases]]+[[query['text']]]*3
    assert set(result['reference_cache'])=={'heldout'}
    for method in result['methods'].values():
        assert all(c['matched_alias']!=query['text'] for c in method['queries'][0]['candidates'])


def test_shortlists_use_index_population_and_never_invent_missing_rank(monkeypatch,tmp_path):
    entities=tuple(Entity(f'e{i:04d}',f'Fictional Entity {i:04d}','organisation',
                          (Alias(f'a{i:04d}',f'Fictional Entity {i:04d}'),),True,'fixture')
                   for i in range(1000))
    assignments={e.entity_id:{'partition':'test','group_id':e.entity_id} for e in entities}
    specs=[{'target_id':entities[i].entity_id,'alias_id':entities[i].aliases[0].alias_id,
            'text':entities[i].name,'kind':'exact','view':'full'} for i in (29,50)]
    views,queries,_=build_authored_benchmark(entities,assignments,{'full':entities},specs)
    def ranked(reference,top_k):
        return [Candidate(e.entity_id,e.name,e.entity_type,e.aliases[0].alias_id,e.aliases[0].name,
                          float(1000-i),e.synthetic,e.source,e.provenance)
                for i,e in enumerate(reference[:top_k])]
    monkeypatch.setattr(comparison,'rank_candidates',lambda text,es,top_k:ranked(es,top_k))
    monkeypatch.setattr(comparison,'rank_vectors',lambda vector,matrix,es,top_k:ranked(es,top_k))
    result=compare(views,queries,FakeEncoder(),tmp_path,1,requested_k=50)
    for method in result['methods'].values():
        first,miss=method['queries']
        assert first['index_entity_count']==1000
        assert first['returned_candidate_count']==first['evaluated_depth']==first['requested_k']==50
        assert first['target_rank']==30 and miss['target_rank'] is None
        metric=next(a for a in method['aggregates'] if (a['partition'],a['suite'],a['slice'])==('test','sanity','all'))
        assert metric['recall_at_50']['value']==.5 and metric['recall_at_50']['denominator']==2
        assert metric['mrr']['value'] is None
        assert metric['mrr_at_k']['value']==pytest.approx(1/60)
        assert metric['mrr_at_k']['k']==50
    rendered=comparison.report({**result,'dataset':'fictional-shortlist'})
    assert 'MRR@K' in rendered and 'K=50' in rendered


@pytest.mark.parametrize('text,expected',[('Fictional ميناء',False),('ميناء خيالي',True)])
def test_cross_script_uses_target_retained_alias_script_sets(tmp_path,text,expected):
    entities=(Entity('a','Fictional Harbor','organisation',
                     (Alias('a1','Fictional Harbor'),Alias('a2',text)),True,'fixture'),
              Entity('b','مرجع آخر','organisation',(Alias('b1','مرجع آخر'),),True,'fixture'))
    assignments={e.entity_id:{'partition':'test','group_id':e.entity_id} for e in entities}
    views,queries,_=build_benchmark(entities,assignments)
    held=next(q for q in queries if q['target_id']=='a' and q['kind']=='heldout_alias')
    result=compare(views,[held],FakeEncoder(),tmp_path,1)
    assert result['methods']['rapidfuzz']['queries'][0]['cross_script_only'] is expected


def test_current_factories_keep_independent_roles_and_leave_history_unchanged(tmp_path):
    for factory in (lambda:comparison.current_phase3_benchmark('fictional'),comparison.current_multilingual_benchmark):
        views,queries,evidence=factory()
        assert views.regression_only is False and evidence['regression_only'] is True
        assert views.dataset_regression_only is True and evidence['legacy_contract'] is False
        assert evidence['audit']['regression_only'] is True
        assert all(q['protocol_version']=='evaluation-v2' for q in queries)
        assert not {'ambiguity','absent'} & {q['partition'] for q in queries}
        migrated=[q for q in queries if q.get('legacy_partition')=='ambiguity']
        assert migrated and all(q['partition']=='development' and q['status']=='diagnostic' for q in migrated)
        result=compare(views,queries[:1],FakeEncoder(),tmp_path,1)
        assert result['regression_only'] is True and result['legacy_contract'] is False
        assert all(method['queries'][0]['regression_only'] for method in result['methods'].values())
    _,legacy,_=phase3_benchmark('fictional')
    assert len(legacy)==94 and all('protocol_version' not in q for q in legacy)


@pytest.mark.parametrize('field,value',[
    ('alias_id','ml-002-ar'),('base_text','Invented parent'),('normalized','invented'),
    ('script','LATIN'),('partition','test'),('status','absent'),('pair_type','invented'),
])
def test_authored_fixture_claims_are_validated_before_current_conversion(monkeypatch,field,value):
    original=Path.read_text
    def changed(path,*args,**kwargs):
        text=original(path,*args,**kwargs)
        if path==Path('eval/fixtures/multilingual_queries.json'):
            rows=json.loads(text)
            rows[0][field]=value
            return json.dumps(rows)
        return text
    monkeypatch.setattr(Path,'read_text',changed)
    with pytest.raises(ValueError):
        comparison.current_multilingual_benchmark()


def cli_config(tmp_path,datasets=('fictional',)):
    config=json.loads(Path('eval/configs/embeddings.json').read_text())
    config.update(datasets=list(datasets),timing_repetitions=1,cache_path=str(tmp_path/'unused-cache'))
    path=tmp_path/'config.json'
    path.write_text(json.dumps(config))
    return path


def cli_args(monkeypatch,config,*args):
    monkeypatch.setattr(sys,'argv',['watchlist.compare_retrieval','--config',str(config),*map(str,args)])


def test_cli_requires_explicit_output_root(monkeypatch,tmp_path):
    def forbidden(*args,**kwargs):
        pytest.fail('missing required destination reached model construction')
    monkeypatch.setattr(comparison,'E5Encoder',forbidden)
    cli_args(monkeypatch,cli_config(tmp_path))
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert error.value.code==2


@pytest.mark.parametrize('destination',['historical','existing'])
def test_cli_rejects_historical_or_existing_outputs_before_model(monkeypatch,tmp_path,destination):
    output=Path('eval/results/phase04') if destination=='historical' else tmp_path/'output'
    if destination=='existing':
        (output/'fictional').mkdir(parents=True)
        (output/'fictional'/'results.json').write_text('preserve this artifact')
    def forbidden(*args,**kwargs):
        pytest.fail('unsafe output destination reached model construction')
    monkeypatch.setattr(comparison,'E5Encoder',forbidden)
    cli_args(monkeypatch,cli_config(tmp_path),'--output-root',output)
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert error.value.code==2
    if destination=='existing':
        assert (output/'fictional'/'results.json').read_text()=='preserve this artifact'


def test_cli_audits_every_dataset_before_constructing_model(monkeypatch,tmp_path):
    valid=small_benchmark()
    broken=small_benchmark()
    broken[1][0]['base_text']='Changed source'
    monkeypatch.setattr(comparison,'current_phase3_benchmark',lambda *args,**kwargs:valid)
    monkeypatch.setattr(comparison,'current_multilingual_benchmark',lambda:broken)
    def forbidden(*args,**kwargs):
        pytest.fail('invalid later dataset reached model construction')
    monkeypatch.setattr(comparison,'E5Encoder',forbidden)
    cli_args(monkeypatch,cli_config(tmp_path,('fictional','multilingual')),'--output-root',tmp_path/'output')
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert error.value.code==2
    assert not (tmp_path/'output').exists()


def test_cli_writes_new_temporary_destination_and_refuses_second_run(monkeypatch,tmp_path):
    monkeypatch.setattr(comparison,'E5Encoder',FakeEncoder)
    output=tmp_path/'new-results'
    cli_args(monkeypatch,cli_config(tmp_path),'--output-root',output,'--requested-k','1')
    assert comparison.main()==0
    result=json.loads((output/'fictional'/'results.json').read_text())
    assert result['regression_only'] is True and result['legacy_contract'] is False
    assert result['evidence']['regression_only'] is True
    assert result['requested_k']==1
    assert (output/'fictional'/'report.md').is_file()
    original=(output/'fictional'/'results.json').read_bytes()
    with pytest.raises(SystemExit):
        comparison.main()
    assert (output/'fictional'/'results.json').read_bytes()==original


def test_public_database_override_is_explicit(monkeypatch):
    def reject(path):
        raise ValueError(f'loaded:{path}')
    monkeypatch.setattr(comparison,'load_database',reject)
    with pytest.raises(ValueError,match='loaded:data/watchlist.sqlite'):
        phase3_benchmark('public-small')
    with pytest.raises(ValueError,match='loaded:data/source-v3/watchlist.sqlite'):
        phase3_benchmark('public-small',database=Path('data/source-v3/watchlist.sqlite'))


@pytest.mark.parametrize('options',[
    {'repetitions':False},{'repetitions':0},{'repetitions':1.5},
    {'requested_k':False},{'requested_k':0},{'requested_k':1.5},{'regression_only':'yes'},
])
def test_invalid_options_fail_before_model_or_cache(monkeypatch,tmp_path,options):
    views,queries,_=small_benchmark()
    forbid_retrieval(monkeypatch)
    arguments={'repetitions':1,**options}
    with pytest.raises(ValueError):
        compare(views,queries[:1],FakeEncoder(),tmp_path,**arguments)


@pytest.mark.parametrize('corruption',['unknown-entity','unknown-alias','duplicate','nan-score','reversed','too-short'])
def test_retriever_outputs_must_match_view_and_observed_order(monkeypatch,tmp_path,corruption):
    views,queries,_=small_benchmark()
    query=next(q for q in queries if q['kind']=='exact')
    original=comparison.rank_candidates
    def invalid(text,entities,top_k):
        candidates=original(text,entities,top_k)
        if corruption=='unknown-entity':
            candidates[0]=replace(candidates[0],entity_id='unknown')
        elif corruption=='unknown-alias':
            candidates[0]=replace(candidates[0],matched_alias_id='not-retained',matched_alias='Leaked alias')
        elif corruption=='duplicate':
            candidates[1]=candidates[0]
        elif corruption=='nan-score':
            candidates[0]=replace(candidates[0],similarity_score=float('nan'))
        elif corruption=='reversed':
            candidates.reverse()
        else:
            candidates.pop()
        return candidates
    monkeypatch.setattr(comparison,'rank_candidates',invalid)
    with pytest.raises(ValueError):
        compare(views,[query],FakeEncoder(),tmp_path,1)


def test_output_cache_symlink_cannot_redirect_writes(monkeypatch,tmp_path):
    output=tmp_path/'output'
    output.mkdir()
    untouched=tmp_path/'other-cache'
    untouched.mkdir()
    (output/'reference-cache').symlink_to(untouched,target_is_directory=True)
    def forbidden(*args,**kwargs):
        pytest.fail('redirected cache destination reached model construction')
    monkeypatch.setattr(comparison,'E5Encoder',forbidden)
    cli_args(monkeypatch,cli_config(tmp_path),'--output-root',output)
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert error.value.code==2 and not list(untouched.iterdir())


def test_public_group_ownership_is_checked_against_database(monkeypatch):
    views,_,_=small_benchmark()
    provenance=SimpleNamespace(snapshot_id='fictional-snapshot',raw_sha256='a'*64)
    manifest={'snapshot_id':provenance.snapshot_id,'raw_sha256':provenance.raw_sha256,
              'assignments':{e.entity_id:{'partition':'test','group_id':e.entity_id}
                             for e in views['full']}}
    manifest['assignments']['a']['group_id']='invented-provider-group'
    monkeypatch.setattr(comparison,'load_database',lambda path:(views['full'],provenance,False))
    class Connection:
        closed=False
        def execute(self,statement):
            assert statement=='SELECT entity_id, group_id FROM entities'
            return [('a','a'),('b','b')]
        def close(self):
            self.closed=True
    connection=Connection()
    def connect(path,*,readonly):
        assert path==Path('explicit-fictional-database.sqlite') and readonly is True
        return connection
    monkeypatch.setattr(comparison,'connect_database',connect)
    original=Path.read_text
    def changed(path,*args,**kwargs):
        if path==Path('data/manifests/splits.json'):
            return json.dumps(manifest)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',changed)
    with pytest.raises(ValueError,match='group'):
        comparison.current_phase3_benchmark('public-small',database=Path('explicit-fictional-database.sqlite'))
    assert connection.closed


@pytest.mark.parametrize('ranker',['rank_candidates','rank_vectors'])
def test_timed_repetitions_cannot_silently_change_results(monkeypatch,tmp_path,ranker):
    views,queries,_=small_benchmark()
    original=getattr(comparison,ranker)
    calls=0
    def drifting(*args):
        nonlocal calls
        calls+=1
        candidates=original(*args)
        if calls==2:
            candidates[0]=replace(candidates[0],similarity_score=candidates[0].similarity_score+.125)
        return candidates
    monkeypatch.setattr(comparison,ranker,drifting)
    with pytest.raises(ValueError,match='changed across timing repetitions'):
        compare(views,queries[:1],FakeEncoder(),tmp_path,1)
