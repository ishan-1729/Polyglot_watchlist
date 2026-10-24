"""Small graph functions; only prepare/audit nodes write the case ledger."""

import json
from langgraph.types import interrupt
from watchlist.normalize import normalize_name
from watchlist.agent.state import LIMITATION, packet, digest, validate_packet, validate_review


def normalize(state: dict) -> dict:
    try:
        return {'normalized_query': normalize_name(state['query'])}
    except ValueError as exc:
        return {'error': {'code': 'invalid_query', 'stage': 'normalize', 'message': str(exc), 'retryable': False}}


def format_candidates(state: dict) -> dict:
    validate_packet(state)
    return {'evidence_sha256': digest(packet(state))}


def explain(state: dict) -> dict:
    """Only supplied facts and explicitly attributed reviewer opinions are rendered."""
    if state['error']:
        message = f"Input validation failed: {state['error']['message']}. No review conclusion was recorded."
        refs = []
    else:
        d = state['reviewer_decision']
        refs = [eid for c in state['candidates'] if c['entity_id'] == d['candidate_entity_id'] for eid in c['evidence_ids']]
        message = (f"Saved retrieval returned {len(state['candidates'])} candidate records. "
                   f"Reviewer {json.dumps(d['reviewer_id'], ensure_ascii=True)} recorded {d['outcome']}"
                   f" with selected record {json.dumps(d['candidate_entity_id'])}. "
                   f"Reviewer opinion: {json.dumps(d['reason'], ensure_ascii=True)}. "
                   f"Evidence references: {', '.join(refs) or 'saved candidate packet; no selected record'}. "
                   f"Packet SHA-256: {state['evidence_sha256']}.")
    return {'explanation': {'template_version': 'evidence-v1', 'text': message,
                            'evidence_ids': refs, 'limitations': LIMITATION}}


def make_nodes(ledger, retriever, failpoint):
    """Inject local resources rather than serializing them into checkpoints."""
    def retrieve_e5(state):
        return retriever.search(state['normalized_query'], state['recipe'])

    def prepare_review(state):
        ledger.prepare(state)
        failpoint('after_packet')
        return {'review_status': 'pending'}

    def human_review(state):
        # Must stay unconditional and side-effect-free before interrupt.
        value = interrupt({'thread_id': state['thread_id'], 'audit_id': state['audit_id'],
                           'review_revision': state['review_revision'], 'evidence_sha256': state['evidence_sha256'],
                           'message': 'Explicit human annotation required. ' + LIMITATION})
        saved = ledger.submission(state['audit_id'])
        if saved is None or saved != value: raise ValueError('resume does not match durable submission')
        validate_review(value, state, saved['expected_checkpoint_id'])
        return {'reviewer_decision': value, 'review_status': 'recorded'}

    def explanation(state):
        failpoint('during_explanation')
        return explain(state)

    def audit_record(state):
        receipt = ledger.finalize(state)
        failpoint('after_final_audit')
        return {**receipt, 'audit_status': 'committed'}

    return {'normalize': normalize, 'retrieve_e5': retrieve_e5, 'format_candidates': format_candidates,
            'prepare_review': prepare_review, 'human_review': human_review,
            'explain': explanation, 'audit_record': audit_record}
