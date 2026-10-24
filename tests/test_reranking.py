"""Offline scoring and acquisition contracts; all HTTP/model outputs are mocked."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
np = pytest.importorskip("numpy")
from watchlist.entities import Alias, Entity
from watchlist import reranking as r


def entity(eid, *names):
    return Entity(eid, names[0], 'organisation', tuple(Alias(eid+str(i), n) for i,n in enumerate(names)), True, 'fictional')


class Scores:
    def __init__(self, values): self.values = values
    def score(self, pairs):
        self.pairs = pairs
        return np.array(self.values)


def test_membership_best_alias_original_text_and_no_extra_entities():
    scorer = Scores([-.5, 3, 2])
    result = r.rerank('Moon', ['b','a'], [entity('a','Moon'),entity('b','قمر','Moon B'),entity('c','Excluded')],scorer)
    assert [x['entity_id'] for x in result] == ['b','a']
    assert result[0]['matched_alias']=='Moon B'
    assert result[0]['available_aliases'][0]['name']=='قمر'
    assert result[0]['source']=='fictional' and result[0]['raw_logit']==3
    assert ('Moon','Excluded') not in scorer.pairs


def test_ties_negative_logits_empty_and_withheld_alias():
    result=r.rerank('Q',['b','a'],[entity('a','A'),entity('b','B')],Scores([-8,-8]))
    assert [x['entity_id'] for x in result]==['a','b']
    scorer=Scores([1]);r.rerank('withheld',['a'],[entity('a','allowed')],scorer)
    assert scorer.pairs==[('withheld','allowed')]
    assert r.rerank('Q',[],[],Scores([]))==[]


@pytest.mark.parametrize('ids,values,message', [(['a','a'],[1,2],'duplicate'),(['missing'],[1],'not present'),(['a'],[1,2],'score'),(['a'],[float('nan')],'score'),(['a'],[float('inf')],'score')])
def test_invalid_candidates_and_scores(ids,values,message):
    with pytest.raises(ValueError,match=message):r.rerank('Q',ids,[entity('a','A')],Scores(values))


def test_pinned_config_rejects_substitution():
    config=json.loads(Path('eval/configs/reranking.json').read_text())['model']
    r.validate_config(config)
    config['revision']='main'
    with pytest.raises(ValueError,match='approved'):r.validate_config(config)


def test_mock_acquisition_integrity_license_and_cap(tmp_path,monkeypatch):
    payloads={name:(b'license: apache-2.0\n' if name=='README.md' else b'mock file') for name in r.FILES}
    siblings=[{'rfilename':n,'size':len(b),'blobId':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()} for n,b in payloads.items()]
    meta={'sha':r.REVISION,'cardData':{'license':'apache-2.0'},'siblings':siblings}
    def response(url,timeout):
        return io.BytesIO(json.dumps(meta).encode() if '/api/' in url else b'Apache License' if url==r.LICENSE_URL else payloads[url.rsplit('/',1)[1]])
    monkeypatch.setattr(r,'urlopen',response)
    config=json.loads(Path('eval/configs/reranking.json').read_text())['model'];config['model_path']=str(tmp_path/'good')
    receipt=r.fetch_model(config)
    assert r.verify_model(config)==receipt
    (tmp_path/'good/config.json').write_text('broken')
    with pytest.raises(ValueError,match='checksum'):r.verify_model(config)
    config['model_path']=str(tmp_path/'badlicense');meta['cardData']['license']='unknown'
    with pytest.raises(ValueError,match='license'):r.fetch_model(config)
    assert not Path(config['model_path']).exists()
    meta['cardData']['license']='apache-2.0';meta['siblings'][0]['size']=600_000_000
    with pytest.raises(ValueError,match='cap'):r.fetch_model(config)
    meta['siblings'][0]['size']=len(payloads['README.md']);meta['siblings'][0]['blobId']='0'*40
    with pytest.raises(ValueError,match='checksum'):r.fetch_model(config)


def test_pair_tokenization_no_prefix_raw_logits_and_no_truncation():
    torch=pytest.importorskip('torch')
    class Tokenizer:
        def __call__(self,left,right,**kw):
            self.left,self.right,self.kw=left,right,kw
            return {'input_ids':torch.ones((len(left),4),dtype=torch.long)}
    scorer=r.MiniLMScorer.__new__(r.MiniLMScorer)
    scorer.torch=torch;scorer.config={'batch_size':8,'max_tokens':512};scorer.check_budget=lambda:None
    scorer.tokenizer=Tokenizer();scorer.model=lambda **kw:SimpleNamespace(logits=torch.tensor([[-2.0],[3.0]]))
    assert scorer.score([(' Q ',' ALIAS '),('سيرا','لومين')]).tolist()==[-2,3]
    assert scorer.tokenizer.left==['q','سيرا'] and scorer.tokenizer.right==['alias','لومين']
    assert scorer.tokenizer.kw['truncation'] is False
    scorer.config['max_tokens']=3
    with pytest.raises(ValueError,match='token limit'):scorer.score([('Q','A')])


def test_same_name_ids_stay_separate_with_provenance_and_alias_tie():
    from dataclasses import replace, asdict
    from watchlist.entities import Provenance
    provenance=Provenance('snapshot','fixture','provider','publisher','https://example.test/source',
                          'https://example.test/download','2026-10-21',None,None,'abc','https://example.test/license')
    first=replace(entity('a','Same Name','Other Alias'),provenance=provenance)
    second=entity('b','Same Name')
    ranked=r.rerank('Same Name',['b','a'],[first,second],Scores([2,2,2]))
    assert [c['entity_id'] for c in ranked]==['a','b']
    assert ranked[0]['matched_alias_id']=='a0'
    assert ranked[0]['provenance']==asdict(provenance)
    assert ranked[1]['provenance'] is None
