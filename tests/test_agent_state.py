import copy
import pytest
from agent_support import FakeRetriever, form
from watchlist.agent import state as state_contract
from watchlist.agent.state import validate_packet, validate_review, digest, packet
from watchlist.agent.storage import ReviewService


@pytest.fixture
def pending(tmp_path):
    with ReviewService(tmp_path, FakeRetriever()) as service:
        yield service.start('Luma', {})


@pytest.mark.parametrize('field,value', [('outcome','match'), ('outcome','clear'), ('reason',''),
    ('review_revision',True), ('candidate_entity_id','unknown'), ('submission_id','not-uuid'),
    ('evidence_sha256','stale'), ('expected_checkpoint_id','stale'), ('reason','x'*1001)])
def test_review_validation(pending, field, value):
    v=form(pending);v.update(reviewer_id='tester',submitted_at='2026-10-22');v[field]=value
    with pytest.raises(ValueError): validate_review(v,pending['state'],pending['checkpoint_id'])


@pytest.mark.parametrize('score', [float('nan'),float('inf'),True,1.1,-1.1,'0.5'])
def test_invalid_scores(pending, score):
    state=copy.deepcopy(pending['state']);state['candidates'][0]['similarity_score']=score
    with pytest.raises(ValueError):validate_packet(state)


def test_packet_alias_links_and_digest(pending):
    s=copy.deepcopy(pending['state']);original=digest(packet(s))
    s['review_status']='recorded';assert digest(packet(s))==original
    s['candidates'][0]['matched_alias']='other'
    with pytest.raises(ValueError):validate_packet(s)
    assert digest(packet(s))!=original


@pytest.fixture
def caller_form():
    """A standalone fictional form, without opening a review workspace."""
    return {
        'submission_id': '11111111-1111-4111-8111-111111111111',
        'review_revision': 1,
        'evidence_sha256': 'a' * 64,
        'expected_checkpoint_id': 'fictional-checkpoint',
        'outcome': 'candidate_for_follow_up',
        'candidate_entity_id': 'syn-001',
        'reason': 'Fictional test annotation for follow-up.',
    }


@pytest.mark.parametrize('value', [None, 42, True, [], ['reason'], [{'reason': 'text'}], 'text'])
def test_review_form_rejects_nonobjects_as_value_errors(value):
    with pytest.raises(ValueError):
        state_contract.validate_review_form(value)


@pytest.mark.parametrize('field,value', [
    ('submission_id', None), ('submission_id', 42), ('submission_id', 'not-a-uuid'),
    ('review_revision', True), ('review_revision', 1.0), ('review_revision', 2),
    ('evidence_sha256', 'short'), ('evidence_sha256', 'g' * 64),
    ('evidence_sha256', ['a' * 64]),
    ('expected_checkpoint_id', ''), ('expected_checkpoint_id', []),
    ('expected_checkpoint_id', 'x' * 1001),
    ('outcome', ['unresolved']), ('outcome', None), ('outcome', 'clear'),
    ('candidate_entity_id', None), ('candidate_entity_id', []),
    ('candidate_entity_id', ' '), ('reason', None), ('reason', []),
    ('reason', ' '), ('reason', 'x' * 1001),
])
def test_review_form_rejects_invalid_field_shapes_and_values(caller_form, field, value):
    caller_form[field] = value
    with pytest.raises(ValueError):
        state_contract.validate_review_form(caller_form)


@pytest.mark.parametrize('field', ['reason', 'reviewer_id', 'submitted_at', 'query'])
def test_review_form_requires_exact_caller_fields(caller_form, field):
    if field == 'reason':
        del caller_form[field]
    else:
        caller_form[field] = 'caller may not set this field'
    with pytest.raises(ValueError):
        state_contract.validate_review_form(caller_form)


@pytest.mark.parametrize('outcome', ['none_selected', 'unresolved'])
def test_review_form_requires_null_candidate_when_unselected(caller_form, outcome):
    caller_form['outcome'] = outcome
    with pytest.raises(ValueError):
        state_contract.validate_review_form(caller_form)
    caller_form['candidate_entity_id'] = None
    assert state_contract.validate_review_form(caller_form) == caller_form


def test_review_form_accepts_valid_boundary_text_without_changing_it(caller_form):
    caller_form.update(reason='x' * 1000, expected_checkpoint_id='c' * 1000)
    before = copy.deepcopy(caller_form)
    assert state_contract.validate_review_form(caller_form) == before
    assert caller_form == before


def test_enriched_review_reuses_form_validation_and_saved_links(caller_form):
    decision = {**caller_form, 'reviewer_id': 'local-tester', 'submitted_at': '2026-10-24'}
    state = {'review_revision': 1, 'evidence_sha256': caller_form['evidence_sha256'],
             'candidates': [{'entity_id': 'syn-001'}]}
    validate_review(decision, state, caller_form['expected_checkpoint_id'])
    decision['reviewer_id'] = []
    with pytest.raises(ValueError):
        validate_review(decision, state, caller_form['expected_checkpoint_id'])


@pytest.mark.parametrize('value', [None, 42, True, [], ['reason'], [{'reason': 'text'}]])
def test_enriched_review_rejects_nonobjects_as_value_errors(value, caller_form):
    with pytest.raises(ValueError):
        validate_review(value, {}, caller_form['expected_checkpoint_id'])


@pytest.mark.parametrize('query', ['', '   ', '  LUMA  ', 'x' * 1000])
def test_query_envelope_preserves_blank_and_normalization_failures_for_audit(query):
    assert state_contract.validate_query_envelope(query) == query


@pytest.mark.parametrize('query', [None, 42, True, [], {}, 'x' * 1001])
def test_query_envelope_rejects_invalid_outer_inputs(query):
    with pytest.raises(ValueError):
        state_contract.validate_query_envelope(query)


@pytest.mark.parametrize('recipe', [
    None, 42, True, [], {'invalid': float('nan')}, {'invalid': float('inf')},
    {'nested': [float('-inf')]}, {'invalid': b'bytes'}, {'invalid': object()},
    {1: 'non-string key'}, {'nested': {2: 'non-string key'}}, {'invalid': (1, 2)},
])
def test_recipe_validation_rejects_nonobjects_and_non_json_values(recipe):
    with pytest.raises(ValueError):
        state_contract.validate_recipe(recipe)


def test_recipe_validation_accepts_finite_json_and_preserves_inputs():
    recipe = {'fixture': 'fictional', 'values': [None, True, 1, 0.25, {'name': 'اسم'}]}
    before = copy.deepcopy(recipe)
    assert state_contract.validate_recipe(recipe) == before
    assert state_contract.validate_start_inputs(' ', recipe) == (' ', before)
    assert recipe == before


def test_recipe_validation_rejects_circular_containers():
    recipe = {}
    recipe['self'] = recipe
    with pytest.raises(ValueError):
        state_contract.validate_recipe(recipe)


def test_recipe_validation_accepts_shared_values_and_detaches_caller_data():
    shared = {'names': ['Fictional Luma']}
    recipe = {'first': shared, 'second': shared}
    accepted = state_contract.validate_recipe(recipe)
    shared['names'].append('Later caller edit')
    assert accepted == {'first': {'names': ['Fictional Luma']},
                        'second': {'names': ['Fictional Luma']}}


def test_input_text_must_be_storable_as_utf8(caller_form):
    with pytest.raises(ValueError):
        state_contract.validate_query_envelope('\ud800')
    with pytest.raises(ValueError):
        state_contract.validate_recipe({'invalid': '\ud800'})
    caller_form['reason'] = '\ud800'
    with pytest.raises(ValueError):
        state_contract.validate_review_form(caller_form)


def test_unexpected_recipe_programming_error_is_not_recast(monkeypatch):
    def broken_serializer(value):
        raise TypeError('unexpected serializer implementation error')
    monkeypatch.setattr(state_contract, 'canonical', broken_serializer)
    with pytest.raises(TypeError, match='unexpected serializer implementation error'):
        state_contract.validate_recipe({'fixture': 'fictional'})


@pytest.fixture
def fictional_packet():
    return {
        'schema_version': 'review-v1', 'workflow_version': 'phase-07a-v1',
        'workflow_sha256': 'a' * 64,
        'thread_id': '11111111-1111-4111-8111-111111111111',
        'audit_id': '22222222-2222-4222-8222-222222222222',
        'query': 'Luma', 'normalized_query': 'luma', 'recipe': {},
        'review_revision': 1, **FakeRetriever().search('luma', {}),
    }


@pytest.mark.parametrize('field,value', [
    ('candidates', [None]), ('candidates', [42]), ('candidates', [['entity_id']]),
    ('evidence', [None]), ('evidence', [42]), ('evidence', [['evidence_id']]),
    ('query', None),
])
def test_malformed_packet_items_raise_value_errors(fictional_packet, field, value):
    fictional_packet[field] = value
    with pytest.raises(ValueError):
        validate_packet(fictional_packet)


def test_malformed_packet_evidence_links_raise_value_errors(fictional_packet):
    fictional_packet['candidates'][0]['evidence_ids'] = [['unhashable']]
    with pytest.raises(ValueError):
        validate_packet(fictional_packet)


def test_out_of_range_integer_score_is_rejected_without_float_overflow(fictional_packet):
    fictional_packet['candidates'][0]['similarity_score'] = 10 ** 1000
    with pytest.raises(ValueError):
        validate_packet(fictional_packet)


@pytest.mark.parametrize('value', [None, 42, True, [], {}])
def test_missing_packet_shape_raises_value_error(value):
    with pytest.raises(ValueError):
        validate_packet(value)
