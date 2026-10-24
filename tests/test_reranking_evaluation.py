"""Offline, hand-calculated paired ranking checks."""
import json
from pathlib import Path
import pytest
np = pytest.importorskip('numpy')
from watchlist.entities import Alias, Entity
from watchlist.evaluate_reranking import evaluate, frozen_benchmark, summarize


def test_hand_calculated_denominators_and_misses():
    rows = [dict(status='positive', group_id=str(i), index_entity_count=6,
                 baseline_rank=b, reranked_rank=a)
            for i, (b,a) in enumerate([(2,1),(1,1),(1,2),(None,None)])]
    rows.append(dict(status='ambiguous'))
    result = summarize(rows,5,'e5_cross_encoder')
    assert result['retrieval_recall_at_k']['value'] == .75
    assert result['recall_at_1']['value'] == .5
    assert result['conditional_reranking_accuracy']['value'] == 2/3
    assert result['mrr_at_k']['value'] == .625
    assert result['excluded_queries'] == 1
    assert result['recall_at_1']['denominator'] == 4
    assert result['conditional_reranking_accuracy']['denominator'] == 3
    assert summarize(rows,10,'e5')['retrieval_recall_at_k']['value'] is None
    assert summarize([],5,'e5')['mrr_at_k']['value'] is None


def test_frozen_fictional_artifact_and_hash_guard():
    config=json.loads(Path('eval/configs/reranking.json').read_text())
    views,queries,old=frozen_benchmark('fictional',config['phase4_result_sha256']['fictional'])
    assert len(queries)==94 and views
    with pytest.raises(ValueError,match='checksum'):
        frozen_benchmark('fictional','changed')


def fixture():
    entities=[Entity(str(i),str(i),'organisation',(Alias(str(i),str(i)),),True,'fictional') for i in range(6)]
    queries=[dict(query_id=str(i),text='Q',target_id=target,view='v',status='positive',
                  partition='test',kind='word_order',script='Latin',group_id=target)
             for i,target in enumerate(['3','5'])]
    old={'methods':{'e5_small':{'queries':[{'candidates':[{'entity_id':str(i)} for i in range(6)],'cross_script_only':False} for q in queries],
           'timing':{'per_query':[{'query_id':q['query_id'],'samples_ms':[1.0]} for q in queries]}}}}
    return {'v':entities},queries,old


class Scorer:
    def score(self,pairs):return np.array([float(alias) for query,alias in pairs])


def test_pipeline_keeps_shortlist_and_scores_unretrieved_target_zero():
    views,queries,old=fixture()
    result=evaluate(views,queries,old,Scorer(),5,2)
    a,b=result['queries']
    assert result['complete']
    assert (a['baseline_rank'],a['reranked_rank'])==(4,2)
    assert b['baseline_rank'] is b['reranked_rank'] is None
    assert 'absent' in b['failure']
    assert [c['entity_id'] for c in a['reranked_candidates']]==['4','3','2','1','0']
    assert len(a['reranking_latency']['samples_ms'])==2
    assert a['index_entity_count']==6 and a['returned_candidate_count']==5


def test_budget_stop_records_partial_results():
    class Limited(Scorer):
        calls=0
        def score(self,pairs):
            self.calls+=1
            if self.calls>2:raise TimeoutError('budget')
            return super().score(pairs)
    result=evaluate(*fixture(),Limited(),5,1)
    assert not result['complete'] and len(result['queries'])==1
    assert result['error']['type']=='TimeoutError'
