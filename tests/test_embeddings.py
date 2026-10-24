import pytest
np = pytest.importorskip("numpy", reason="install the embeddings extra for vector tests")
from dataclasses import replace
import json
from watchlist.embeddings import E5Encoder,cached_aliases,validate_config
from watchlist.entities import Entity,Alias


class FakeEncoder:
    config={'dimension':2}
    metadata={'model':'mock-v1','prefix':'query: '}
    calls=0
    def encode(self,texts):
        self.calls+=1
        return np.array([[1,2] for _ in texts],dtype=np.float32)


def test_cache_hit_and_metadata_invalidation(tmp_path):
    es=(Entity('a','Moon','organisation',(Alias('a1','Moon'),),True,'fictional'),)
    encoder=FakeEncoder()
    first,info=cached_aliases(es,encoder,tmp_path)
    second,other=cached_aliases(es,encoder,tmp_path)
    assert not info['hit'] and other['hit'] and encoder.calls==1
    np.testing.assert_array_equal(first,second)
    encoder.metadata={'model':'mock-v2'}
    _,new=cached_aliases(es,encoder,tmp_path)
    assert new['key']!=info['key'] and encoder.calls==2
    changed=(replace(es[0],source='different-source'),)
    _,new2=cached_aliases(changed,encoder,tmp_path)
    assert new2['key']!=new['key']


def test_cache_corruption_fails(tmp_path):
    es=(Entity('a','Moon','organisation',(Alias('a1','Moon'),),True,'fictional'),)
    _,info=cached_aliases(es,FakeEncoder(),tmp_path)
    (tmp_path/(info['key']+'.npy')).write_bytes(b'bad')
    with pytest.raises(ValueError,match='checksum'):cached_aliases(es,FakeEncoder(),tmp_path)


def test_encoder_prefix_and_no_silent_truncation():
    class Model:
        def tokenizer(self,texts,**kwargs):
            self.inputs=texts
            return {'input_ids':[[1,2,3] for _ in texts]}
        def encode(self,texts,**kwargs):
            return np.array([[1,0] for _ in texts],dtype=np.float32)
    encoder=E5Encoder.__new__(E5Encoder)
    encoder.model=Model();encoder.config={'prefix':'query: ','max_tokens':3,'batch_size':8,'dimension':2}
    assert encoder.encode(['  MOON  ']).shape==(1,2)
    assert encoder.model.inputs==['query: moon']
    encoder.config['max_tokens']=2
    with pytest.raises(ValueError,match='truncated'):encoder.encode(['Moon'])


def test_unapproved_model_refused():
    with pytest.raises(ValueError,match='approved'):validate_config({'model_id':'some-other-model'})


def test_bounded_model_fetch_and_checksum_failure(tmp_path,monkeypatch):
    import io,hashlib
    from watchlist import embeddings as module
    config=json.loads(__import__('pathlib').Path('eval/configs/embeddings.json').read_text())['model']
    config['model_path']=str(tmp_path/'good')
    payload=b'authored mock file'
    metadata={'sha':module.REVISION,'siblings':[{'rfilename':name,'size':len(payload),
                'lfs':{'sha256':hashlib.sha256(payload).hexdigest()}} for name in module.MODEL_FILES]}
    def response(url,timeout):
        return io.BytesIO(json.dumps(metadata).encode() if '/api/' in url else payload)
    monkeypatch.setattr(module,'urlopen',response)
    receipt=module.fetch_model(config)
    assert receipt['bytes']==len(payload)*len(module.MODEL_FILES)
    assert module.verify_model(config)==receipt
    config['model_path']=str(tmp_path/'bad')
    metadata['siblings'][0]['lfs']['sha256']='0'*64
    with pytest.raises(ValueError,match='checksum'):module.fetch_model(config)
    assert not (tmp_path/'bad/acquisition.json').exists()
    config['model_path']=str(tmp_path/'oversize')
    metadata['siblings'][0]['size']=600_000_001
    with pytest.raises(ValueError,match='limit'):module.fetch_model(config)
