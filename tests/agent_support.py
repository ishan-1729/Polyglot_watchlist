"""Fictional mock data and subprocess worker; never used by the application."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from watchlist.agent.storage import ReviewService


class FakeRetriever:
    def __init__(self, empty=False, fail=False, alias='Luma Vesper'):
        self.calls = 0
        self.empty, self.fail, self.alias = empty, fail, alias

    def search(self, query, recipe):
        self.calls += 1
        if self.fail: raise RuntimeError('retrieval must not run')
        candidates, evidence = [], []
        for rank, entity in enumerate([] if self.empty else ['syn-001', 'syn-012'], 1):
            aid = entity + '-alias'
            evidence.append(dict(evidence_id=aid, entity_id=entity, alias_id=aid,
                                 original_text=self.alias, source='fictional-synthetic-v1', synthetic=True,
                                 provenance=None, attribution='Authored fixture'))
            candidates.append(dict(entity_id=entity, display_name=self.alias, entity_type='person', rank=rank,
                                   matched_alias_id=aid, matched_alias=self.alias, evidence_ids=[aid],
                                   similarity_score=1.0, score_kind='cosine_similarity'))
        return dict(candidates=candidates, evidence=evidence, retrieval={'top_k': 5, 'reranker': 'disabled', 'model': 'MOCK'})


def form(result, **changes):
    return dict(submission_id=str(uuid4()), review_revision=1,
                evidence_sha256=result['state']['evidence_sha256'], expected_checkpoint_id=result['checkpoint_id'],
                outcome='candidate_for_follow_up', candidate_entity_id='syn-001', reason='Fictional test; investigate further.', **changes)


def worker():
    action, root, stage = sys.argv[1:4]
    def crash(point):
        if point == stage: os._exit(77)
    fake = FakeRetriever(fail=action != 'start' and stage not in ('after_case', 'after_packet'))
    with ReviewService(Path(root), fake, crash if action in ('start', 'review') else lambda s: None) as service:
        if action == 'start': result = service.start('  LUMA   VESPER ', {'fixture': 'v1'})
        else:
            thread = service.db.execute('SELECT thread_id FROM cases').fetchone()[0]
            if action == 'review': result = service.review(thread, json.loads(Path(sys.argv[4]).read_text()))
            elif action == 'status': result = service.status(thread)
            else: result = service.recover(thread)
    print(json.dumps(result))


if __name__ == '__main__': worker()
