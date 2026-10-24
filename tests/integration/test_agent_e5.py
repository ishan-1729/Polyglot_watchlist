"""Explicit local-weight integration; no network or evaluation-output writes."""
import os
from pathlib import Path
import pytest

pytestmark=[pytest.mark.integration, pytest.mark.skipif(os.environ.get('RUN_AGENT_E5_INTEGRATION')!='1',reason='explicit local E5 opt-in required')]


def test_adapter_parity_and_restart(tmp_path):
    from watchlist.agent.retrieval import E5Retriever, make_recipe
    from watchlist.agent.storage import ReviewService
    from watchlist.embeddings import E5Encoder, cached_aliases
    from watchlist.entities import load_entities
    from watchlist.matching_embeddings import rank_vectors
    from uuid import uuid4
    class NeverRetrieve:
        def search(self, *args): raise AssertionError("resume must not retrieve")
    recipe=make_recipe(Path('eval/configs/embeddings.json'))
    encoder=E5Encoder(recipe['config']['model']);entities=load_entities()
    vectors,_=cached_aliases(entities,encoder,Path(recipe['config']['cache_path']))
    direct=rank_vectors(encoder.encode(['Lumen Sira']),vectors,entities,top_k=5)
    with ReviewService(tmp_path,E5Retriever()) as service:r=service.start('Lumen Sira',recipe)
    for a,b in zip(r['state']['candidates'],direct,strict=True):
        assert (a['entity_id'],a['matched_alias_id'],a['matched_alias'])==(b.entity_id,b.matched_alias_id,b.matched_alias)
        assert a['similarity_score']==pytest.approx(b.similarity_score,abs=1e-6)
        evidence=[e for e in r['state']['evidence'] if e['entity_id']==b.entity_id]
        assert {e['alias_id']:e['original_text'] for e in evidence}=={a.alias_id:a.name for e in entities if e.entity_id==b.entity_id for a in e.aliases}
        assert all(e['provenance'] is None and e['source']==b.source for e in evidence)
    with ReviewService(tmp_path,NeverRetrieve()) as service:
        v=dict(submission_id=str(uuid4()), review_revision=1, evidence_sha256=r['state']['evidence_sha256'],
               expected_checkpoint_id=r['checkpoint_id'], outcome='candidate_for_follow_up',
               candidate_entity_id=direct[0].entity_id, reason='Fictional integration check; further evidence required.')
        assert service.review(r['thread_id'],v)['completed']
