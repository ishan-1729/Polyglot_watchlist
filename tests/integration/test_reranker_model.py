"""Opt-in real-model checks. Only already acquired local weights are used."""
import json
import os
from pathlib import Path
import pytest
np=pytest.importorskip('numpy')
pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.environ.get('RUN_RERANKER_INTEGRATION')!='1',reason='opt-in local MiniLM weights')]


def test_local_pinned_model_finite_repeatable_logits():
    from watchlist.reranking import MiniLMScorer
    config=json.loads(Path('eval/configs/reranking.json').read_text())['model']
    scorer=MiniLMScorer(config)
    pairs=[('Moon Harbor','Moon Harbor'),('Moon Harbor','Orchid Foods'),('ميناء القمر','Moon Harbor')]
    first=scorer.score(pairs)
    assert first.shape==(3,) and np.isfinite(first).all()
    np.testing.assert_allclose(first,scorer.score(pairs),rtol=0,atol=1e-6)
