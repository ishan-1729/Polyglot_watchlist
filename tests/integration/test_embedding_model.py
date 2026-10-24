import pytest
np = pytest.importorskip("numpy", reason="install the embeddings extra for vector tests")
"""Opt in with RUN_EMBEDDING_INTEGRATION=1; never downloads missing weights."""
import json
import os
from pathlib import Path
from watchlist.embeddings import E5Encoder

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.environ.get('RUN_EMBEDDING_INTEGRATION')!='1',reason='explicit local-model opt-in required')]


def test_local_model_shapes_normalization_and_repeatability():
    encoder=E5Encoder(json.loads(Path('eval/configs/embeddings.json').read_text())['model'])
    texts=['Golden Moon Bakery','مخبز القمر الذهبي']
    a=encoder.encode(texts);b=encoder.encode(texts)
    assert a.shape==(2,384) and a.dtype==np.float32
    np.testing.assert_allclose(np.linalg.norm(a,axis=1),1,atol=1e-6)
    np.testing.assert_allclose(a,b,atol=1e-6,rtol=1e-6)
