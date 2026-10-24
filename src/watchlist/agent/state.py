"""JSON state contracts and strict human-input/evidence validation."""

from importlib.metadata import version
import hashlib
import json
import math
from pathlib import Path
from typing import Literal, TypedDict
from uuid import UUID

from watchlist.normalize import normalize_name
from watchlist.entities import Provenance

SCHEMA = 'review-v1'
WORKFLOW = 'phase-07a-v1'
LIMITATION = ('Candidate suggestions for human verification only. Cosine similarity is not '
              'identity probability. Names and this snapshot cannot establish identity or wrongdoing; '
              'selecting none does not establish absence. DOB and nationality were not compared.')


class AliasEvidence(TypedDict):
    evidence_id: str
    entity_id: str
    alias_id: str
    original_text: str
    source: str
    synthetic: bool
    provenance: dict | None
    attribution: str


class CandidateEntity(TypedDict):
    entity_id: str
    display_name: str
    entity_type: str
    rank: int
    matched_alias_id: str
    matched_alias: str
    evidence_ids: list[str]
    similarity_score: float
    score_kind: Literal['cosine_similarity']


class ReviewerDecision(TypedDict):
    submission_id: str
    review_revision: int
    evidence_sha256: str
    expected_checkpoint_id: str
    outcome: Literal['candidate_for_follow_up', 'none_selected', 'unresolved']
    candidate_entity_id: str | None
    reviewer_id: str
    reason: str
    submitted_at: str


class ReviewState(TypedDict):
    schema_version: str
    workflow_version: str
    workflow_sha256: str
    thread_id: str
    audit_id: str
    parent_audit_id: str | None
    created_at: str
    query: str
    normalized_query: str | None
    recipe: dict
    candidates: list[CandidateEntity]
    evidence: list[AliasEvidence]
    retrieval: dict | None
    evidence_sha256: str | None
    review_revision: int
    review_status: Literal['not_requested', 'pending', 'recorded']
    reviewer_decision: ReviewerDecision | None
    explanation: dict | None
    error: dict | None
    audit_status: Literal['pending', 'committed']
    audit_event_id: str | None
    audit_head_sha256: str | None


def canonical(value: object) -> str:
    """One finite JSON representation for hashing and SQLite storage."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def workflow_hash() -> str:
    """Bind pending cases to this implementation, including SQL and baseline code."""
    root = Path(__file__).resolve().parent
    paths = sorted(root.glob('*.py')) + sorted(root.glob('*.sql'))
    paths += [root.parent / n for n in ('normalize.py', 'embeddings.py', 'matching_embeddings.py', 'entities.py', 'database.py')]
    return digest({'files': {str(p.relative_to(root.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                   'packages': {n: version(n) for n in ('langgraph', 'langgraph-checkpoint', 'langgraph-checkpoint-sqlite', 'ormsgpack')}})


def packet(state: dict) -> dict:
    """Exclude changing review/audit fields from the immutable evidence packet."""
    keys = ('schema_version', 'workflow_version', 'workflow_sha256', 'thread_id', 'audit_id',
            'query', 'normalized_query', 'recipe', 'candidates', 'evidence', 'retrieval', 'review_revision')
    return {k: state[k] for k in keys}


def text(value: object, label: str, limit: int = 1000) -> None:
    """Require bounded, nonblank Unicode text that can enter the UTF-8 ledger."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} must be nonblank text of at most {limit} characters')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{label} must contain valid Unicode text') from exc


def validate_query_envelope(query: object) -> str:
    """Validate transport shape while preserving names for audited normalization.

    Blank names and names longer than the normalizer's 200-character limit are
    intentionally accepted up to the existing 1000-character query envelope.
    The workflow records those normalization failures after case creation.
    """
    if not isinstance(query, str) or len(query) > 1000:
        raise ValueError('query envelope must be text of at most 1000 characters')
    try:
        query.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('query must contain valid Unicode text') from exc
    return query


def validate_recipe(recipe: object) -> dict:
    """Return a detached finite JSON object suitable for durable case storage.

    Only JSON primitives, lists, and objects with string keys are accepted.
    Check shapes before serialization, including cycles, so malformed caller
    values become ValueError without hiding unrelated TypeError exceptions.
    """
    if type(recipe) is not dict:
        raise ValueError('recipe must be a JSON object')
    active: set[int] = set()
    pending: list[tuple[object, bool]] = [(recipe, False)]
    while pending:
        value, leaving = pending.pop()
        if leaving:
            active.remove(id(value))
            continue
        if type(value) in (dict, list):
            if id(value) in active:
                raise ValueError('recipe must not contain circular containers')
            active.add(id(value))
            pending.append((value, True))
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    raise ValueError('recipe object keys must be strings')
                children = value.values()
            else:
                children = value
            pending.extend((child, False) for child in children)
        elif type(value) is float:
            if not math.isfinite(value):
                raise ValueError('recipe numbers must be finite')
        elif type(value) not in (str, int, bool, type(None)):
            raise ValueError('recipe must contain only JSON values')
    try:
        encoded = canonical(recipe)
        encoded.encode('utf-8')
        return json.loads(encoded)
    except (ValueError, RecursionError) as exc:
        raise ValueError('recipe cannot be represented as finite UTF-8 JSON') from exc


def validate_start_inputs(query: object, recipe: object) -> tuple[str, dict]:
    """Validate both caller inputs before any workspace or ledger mutation."""
    return validate_query_envelope(query), validate_recipe(recipe)


def validate_review_form(form: object) -> dict:
    """Validate the seven caller-owned fields without opening a saved case.

    Actor identity and submission time belong to the local service. Validation
    here checks the form's shape; validate_review also binds it to saved state.
    """
    expected = set(ReviewerDecision.__annotations__) - {'reviewer_id', 'submitted_at'}
    if not isinstance(form, dict) or set(form) != expected:
        raise ValueError('review form fields mismatch')
    for key in ('submission_id', 'evidence_sha256', 'expected_checkpoint_id', 'reason'):
        text(form[key], key)
    try:
        UUID(form['submission_id'])
    except ValueError as exc:
        raise ValueError('submission_id must be a UUID') from exc
    if type(form['review_revision']) is not int or form['review_revision'] != 1:
        raise ValueError('review_revision must be the integer 1')
    evidence = form['evidence_sha256']
    if len(evidence) != 64 or any(char not in '0123456789abcdef' for char in evidence):
        raise ValueError('evidence_sha256 must be a lowercase SHA-256 digest')
    outcome = form['outcome']
    if not isinstance(outcome, str) or outcome not in ('candidate_for_follow_up', 'none_selected', 'unresolved'):
        raise ValueError('invalid review outcome')
    if outcome == 'candidate_for_follow_up':
        text(form['candidate_entity_id'], 'candidate_entity_id', 10000)
    elif form['candidate_entity_id'] is not None:
        raise ValueError('this outcome requires a null candidate')
    return dict(form)


def validate_packet(state: object) -> None:
    """Check finite scores, unique IDs and every winning alias/evidence link."""
    if not isinstance(state, dict):
        raise ValueError('packet state must be an object')
    try:
        saved_packet = packet(state)
    except KeyError as exc:
        raise ValueError('packet state is missing a required field') from exc
    if not isinstance(state['query'], str):
        raise ValueError('packet query must be text')
    if state['normalized_query'] != normalize_name(state['query']):
        raise ValueError('normalization mismatch')
    candidates, evidence = state['candidates'], state['evidence']
    if not isinstance(candidates, list) or len(candidates) > 5 or not isinstance(evidence, list):
        raise ValueError('invalid candidate/evidence list')
    by_id = {}
    for e in evidence:
        if not isinstance(e, dict) or set(e) != set(AliasEvidence.__annotations__): raise ValueError('evidence fields mismatch')
        for k in ('evidence_id', 'entity_id', 'alias_id', 'original_text', 'source', 'attribution'): text(e[k], k, 10000)
        if type(e['synthetic']) is not bool: raise ValueError('synthetic must be boolean')
        if not e['synthetic'] and not isinstance(e['provenance'], dict): raise ValueError('missing source provenance')
        if e['provenance'] is not None:
            if not isinstance(e['provenance'], dict) or set(e['provenance']) != set(Provenance.__annotations__): raise ValueError('provenance fields mismatch')
            for key in set(Provenance.__annotations__) - {'source_updated_at', 'export_version'}: text(e['provenance'][key], key, 10000)
        if e['evidence_id'] in by_id: raise ValueError('duplicate evidence ID')
        by_id[e['evidence_id']] = e
    ids = set()
    used = set()
    for rank, c in enumerate(candidates, 1):
        if not isinstance(c, dict) or set(c) != set(CandidateEntity.__annotations__): raise ValueError('candidate fields mismatch')
        for k in ('entity_id', 'display_name', 'entity_type', 'matched_alias_id', 'matched_alias'): text(c[k], k, 10000)
        if c['entity_id'] in ids or type(c['rank']) is not int or c['rank'] != rank: raise ValueError('duplicate entity or invalid rank')
        ids.add(c['entity_id'])
        score = c['similarity_score']
        if type(score) not in (int, float) or not -1 <= score <= 1 or not math.isfinite(score): raise ValueError('invalid cosine')
        if c['score_kind'] != 'cosine_similarity': raise ValueError('invalid score kind')
        refs = c['evidence_ids']
        if (not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs)
                or len(set(refs)) != len(refs)): raise ValueError('invalid evidence links')
        linked = [by_id.get(k) for k in refs]
        if any(e is None or e['entity_id'] != c['entity_id'] for e in linked): raise ValueError('cross-entity evidence')
        if not any(e['alias_id'] == c['matched_alias_id'] and e['original_text'] == c['matched_alias'] for e in linked): raise ValueError('winning alias missing')
        used.update(refs)
    if used != set(by_id): raise ValueError('orphan evidence')
    if not isinstance(state['retrieval'], dict) or state['retrieval'].get('reranker') != 'disabled': raise ValueError('invalid retrieval manifest')
    if state['retrieval'].get('top_k') != 5: raise ValueError('unapproved top K')
    canonical(saved_packet)


def validate_review(value: object, state: dict, checkpoint: str) -> None:
    """Reject arbitrary state updates, stale packets and unsupported decisions."""
    if not isinstance(value, dict) or set(value) != set(ReviewerDecision.__annotations__):
        raise ValueError('review fields mismatch')
    validate_review_form({key: field for key, field in value.items()
                          if key not in ('reviewer_id', 'submitted_at')})
    for key in ('reviewer_id', 'submitted_at'):
        text(value[key], key)
    if value['review_revision'] != state['review_revision']: raise ValueError('stale review revision')
    if value['evidence_sha256'] != state['evidence_sha256'] or value['expected_checkpoint_id'] != checkpoint: raise ValueError('stale evidence or checkpoint')
    outcome = value['outcome']
    candidate = value['candidate_entity_id']
    if outcome == 'candidate_for_follow_up':
        if candidate not in {c['entity_id'] for c in state['candidates']}: raise ValueError('candidate is not in saved shortlist')
