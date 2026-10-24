import json
import hashlib
from pathlib import Path
import stat
from uuid import uuid4

import pytest
from agent_support import FakeRetriever, form
from watchlist.agent import cli
from watchlist.agent.cli import main, load_config
from watchlist.agent.state import digest
from watchlist.agent.storage import ReviewService


def test_status_cli_escapes_controls_without_model(tmp_path,capsys):
    with ReviewService(tmp_path/'store',FakeRetriever(alias='\x1b[2Jمرحبا')) as s:r=s.start('Luma',{})
    config=json.loads(open('config/agent.json').read());config['workspace']=str(tmp_path/'store')
    config['embedding_config']='does-not-exist.json'
    p=tmp_path/'config.json';p.write_text(json.dumps(config))
    assert main(['status','--config',str(p),'--thread-id',r['thread_id']])==0
    output=capsys.readouterr().out
    assert '\x1b' not in output and '\\u001b' in output
    assert json.loads(output)['pending_interrupt']


def test_policy_cannot_enable_reranker(tmp_path):
    config=json.loads(open('config/agent.json').read());config['reranker']='MiniLM'
    p=tmp_path/'config.json';p.write_text(json.dumps(config))
    with pytest.raises(ValueError):load_config(p)


def test_status_lists_ids_for_early_crash_recovery(tmp_path,capsys):
    with ReviewService(tmp_path/'store',FakeRetriever()) as s:r=s.start('Luma',{})
    config=json.loads(open('config/agent.json').read());config['workspace']=str(tmp_path/'store')
    p=tmp_path/'config.json';p.write_text(json.dumps(config))
    assert main(['status','--config',str(p)])==0
    assert json.loads(capsys.readouterr().out)['cases']==[{'thread_id':r['thread_id'],'audit_id':r['audit_id']}]


@pytest.fixture
def cli_inputs(tmp_path):
    workspace = tmp_path / 'workspace'
    embedding = tmp_path / 'embedding.json'
    embedding.write_text('{}')
    config = {
        'schema_version': 'review-v1', 'workflow_version': 'phase-07a-v1', 'top_k': 5,
        'reranker': 'disabled', 'review_policy': 'human_only',
        'workspace': str(workspace), 'embedding_config': str(embedding),
    }
    path = tmp_path / 'agent.json'
    path.write_text(json.dumps(config))
    return path, config, workspace


@pytest.fixture
def forbid_storage_and_retrieval(monkeypatch):
    """Invalid input must fail before any service, recipe, or retriever is created."""
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Invalid CLI input reached storage or retrieval preparation')

    for name in ('ReviewService', 'E5Retriever', 'make_recipe', 'ReviewReader'):
        if hasattr(cli, name):
            monkeypatch.setattr(cli, name, forbidden)
    return calls


def cli_snapshot(root):
    """Ignore access times while detecting changed bytes, schema files, or modes."""
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        value = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_ino,
                 info.st_mtime_ns, info.st_ctime_ns)
        if path.is_file():
            value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
        result[str(path.relative_to(root))] = value
    return result


def rejected_before_storage(arguments, inputs, calls, capsys):
    config_path, _, workspace = inputs
    before = cli_snapshot(config_path.parent)
    assert main([*arguments, '--config', str(config_path)]) == 2
    output = capsys.readouterr()
    error = json.loads(output.out)
    assert isinstance(error['error'], str) and error['error']
    assert error['completed'] is False
    assert 'Traceback' not in output.out + output.err
    assert calls == []
    assert not workspace.exists()
    assert cli_snapshot(config_path.parent) == before


@pytest.mark.parametrize('value', [None, True, False, 42, 5.0, 'fictional', [], ['workspace'], [{}], {}])
def test_config_json_requires_an_object_before_storage(cli_inputs, forbid_storage_and_retrieval, capsys, value):
    cli_inputs[0].write_text(json.dumps(value))
    rejected_before_storage(['status'], cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('value', [True, False, 5.0, '5', None, [], {}])
def test_policy_top_k_requires_exact_approved_integer(cli_inputs, forbid_storage_and_retrieval, capsys, value):
    path, config, _ = cli_inputs
    config['top_k'] = value
    path.write_text(json.dumps(config))
    rejected_before_storage(['status'], cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('field', ['workspace', 'embedding_config'])
@pytest.mark.parametrize('value', [None, True, 42, [], {}, '', '   ', 'fictional\x00path'])
def test_config_path_values_are_validated_before_storage(cli_inputs, forbid_storage_and_retrieval, capsys, field, value):
    path, config, _ = cli_inputs
    config[field] = value
    path.write_text(json.dumps(config))
    rejected_before_storage(['status'], cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('kind', ['symlink_directory', 'missing_child_below_file', 'parent_traversal'])
def test_workspace_path_structure_is_checked_before_recipe_or_storage(
        cli_inputs, forbid_storage_and_retrieval, capsys, kind):
    path, config, _ = cli_inputs
    if kind == 'symlink_directory':
        directory = path.parent / 'existing-directory'
        directory.mkdir()
        workspace = path.parent / 'linked-workspace'
        workspace.symlink_to(directory, target_is_directory=True)
    elif kind == 'missing_child_below_file':
        parent = path.parent / 'ordinary-file'
        parent.write_text('Fictional file must not be treated as a directory')
        workspace = parent / 'missing-workspace'
    else:
        directory = path.parent / 'container'
        directory.mkdir()
        workspace = directory / '..' / 'workspace'
    config['workspace'] = str(workspace)
    path.write_text(json.dumps(config))
    rejected_before_storage(['start', '--name', 'Fictional Luma'], cli_inputs,
                            forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('damage', ['duplicate', 'nan', 'infinity', 'invalid_json', 'missing', 'directory'])
def test_config_file_contract_is_checked_before_storage(cli_inputs, forbid_storage_and_retrieval, capsys, damage):
    path, config, _ = cli_inputs
    if damage == 'duplicate':
        path.write_text(json.dumps(config)[:-1] + ', "top_k": 5}')
    elif damage in ('nan', 'infinity'):
        config['workspace'] = float('nan') if damage == 'nan' else float('inf')
        path.write_text(json.dumps(config))
    elif damage == 'invalid_json':
        path.write_text('{broken')
    else:
        path.unlink()
        if damage == 'directory':
            path.mkdir()
    rejected_before_storage(['status'], cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('arguments', [
    [],
    ['start'], ['review'], ['review', '--thread-id', 'fictional-thread'], ['recover'], ['audit-verify'],
    ['status', '--thread-id', ''], ['recover', '--thread-id', ''],
    ['start', '--name', 'Luma', '--thread-id', 'fictional-thread'],
    ['start', '--name', 'Luma', '--review-file', 'fictional.json'],
    ['status', '--name', ''], ['status', '--db', 'fictional.sqlite'],
    ['status', '--review-file', 'fictional.json'],
    ['review', '--thread-id', 'fictional-thread', '--review-file', 'fictional.json', '--name', ''],
    ['review', '--thread-id', 'fictional-thread', '--review-file', 'fictional.json', '--db', 'fictional.sqlite'],
    ['recover', '--thread-id', 'fictional-thread', '--name', ''],
    ['recover', '--thread-id', 'fictional-thread', '--db', 'fictional.sqlite'],
    ['recover', '--thread-id', 'fictional-thread', '--review-file', 'fictional.json'],
    ['audit-verify', '--thread-id', 'fictional-thread', '--name', ''],
    ['audit-verify', '--thread-id', 'fictional-thread', '--db', 'fictional.sqlite'],
    ['audit-verify', '--thread-id', 'fictional-thread', '--review-file', 'fictional.json'],
    ['start', '--name'], ['status', '--unknown-option'],
])
def test_action_argument_contract_precedes_storage(cli_inputs, forbid_storage_and_retrieval, capsys, arguments):
    rejected_before_storage(arguments, cli_inputs, forbid_storage_and_retrieval, capsys)


def test_help_retains_success_exit_without_storage(cli_inputs, forbid_storage_and_retrieval, capsys):
    before = cli_snapshot(cli_inputs[0].parent)
    with pytest.raises(SystemExit) as result:
        main(['--help'])
    assert result.value.code == 0
    output = capsys.readouterr()
    assert 'usage:' in output.out
    assert output.err == ''
    assert forbid_storage_and_retrieval == []
    assert cli_snapshot(cli_inputs[0].parent) == before


def review_shape():
    return {'submission_id': str(uuid4()), 'review_revision': 1, 'evidence_sha256': 'a' * 64,
            'expected_checkpoint_id': str(uuid4()), 'outcome': 'unresolved',
            'candidate_entity_id': None, 'reason': 'Fictional analyst note.'}


def reject_review(value, cli_inputs, calls, capsys):
    review_path = cli_inputs[0].parent / 'form.json'
    review_path.write_text(json.dumps(value))
    rejected_before_storage(['review', '--thread-id', str(uuid4()), '--review-file', str(review_path)],
                            cli_inputs, calls, capsys)


@pytest.mark.parametrize('value', [None, True, False, 42, 1.0, 'fictional', [], ['reason'], [{}], {}])
def test_review_json_requires_an_object_before_storage(cli_inputs, forbid_storage_and_retrieval, capsys, value):
    reject_review(value, cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('field,value', [
    ('submission_id', None), ('submission_id', 42), ('submission_id', 'not-a-uuid'),
    ('review_revision', True), ('review_revision', 1.0), ('review_revision', None),
    ('evidence_sha256', None), ('evidence_sha256', []), ('evidence_sha256', 'not-a-digest'),
    ('expected_checkpoint_id', None), ('expected_checkpoint_id', []), ('expected_checkpoint_id', ''),
    ('outcome', None), ('outcome', []), ('outcome', 'automatically_clear'),
    ('candidate_entity_id', True), ('candidate_entity_id', {}), ('candidate_entity_id', 'syn-001'),
    ('reason', None), ('reason', 42), ('reason', []), ('reason', ''),
])
def test_review_field_types_and_shape_precede_storage(cli_inputs, forbid_storage_and_retrieval, capsys, field, value):
    candidate = review_shape()
    candidate[field] = value
    reject_review(candidate, cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('damage', ['extra_field', 'missing_field', 'duplicate', 'nan', 'infinity',
                                    'invalid_json', 'missing_file', 'directory', 'oversized'])
def test_review_file_contract_precedes_storage(cli_inputs, forbid_storage_and_retrieval, capsys, damage):
    path = cli_inputs[0].parent / 'form.json'
    value = review_shape()
    if damage == 'extra_field':
        value['query'] = 'injected replacement'
    elif damage == 'missing_field':
        del value['reason']
    elif damage in ('nan', 'infinity'):
        value['reason'] = float('nan') if damage == 'nan' else float('inf')
    path.write_text(json.dumps(value))
    if damage == 'duplicate':
        path.write_text(json.dumps(value)[:-1] + ', "review_revision": 1}')
    elif damage == 'invalid_json':
        path.write_text('{broken')
    elif damage in ('missing_file', 'directory'):
        path.unlink()
        if damage == 'directory':
            path.mkdir()
    elif damage == 'oversized':
        path.write_text(' ' * 8001)
    rejected_before_storage(['review', '--thread-id', str(uuid4()), '--review-file', str(path)],
                            cli_inputs, forbid_storage_and_retrieval, capsys)


@pytest.mark.parametrize('action', ['status', 'audit-verify'])
def test_inspection_never_creates_missing_workspace(cli_inputs, monkeypatch, capsys, action):
    config_path, _, workspace = cli_inputs
    fake = FakeRetriever(fail=True)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    arguments = [action, '--config', str(config_path)]
    if action == 'audit-verify':
        arguments.extend(['--thread-id', str(uuid4())])
    before = cli_snapshot(config_path.parent)
    assert main(arguments) == 2
    assert isinstance(json.loads(capsys.readouterr().out)['error'], str)
    assert not workspace.exists()
    assert fake.calls == 0
    assert cli_snapshot(config_path.parent) == before


@pytest.mark.parametrize('action', ['status', 'audit-verify', 'list'])
def test_inspection_does_not_change_existing_workspace_permissions_or_bytes(cli_inputs, monkeypatch, capsys, action):
    config_path, _, workspace = cli_inputs
    with ReviewService(workspace, FakeRetriever()) as service:
        case = service.start('Fictional Luma', {'fixture': 'cli-read-only'})
    workspace.chmod(0o750)
    for path in workspace.iterdir():
        if path.is_file():
            path.chmod(0o640)
    before = cli_snapshot(workspace)
    fake = FakeRetriever(fail=True)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    arguments = ['status' if action == 'list' else action, '--config', str(config_path)]
    if action != 'list':
        arguments.extend(['--thread-id', case['thread_id']])
    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    if action == 'list':
        assert result['cases'] == [{'thread_id': case['thread_id'], 'audit_id': case['audit_id']}]
    else:
        assert result['completed'] is False
    assert fake.calls == 0
    assert cli_snapshot(workspace) == before


@pytest.mark.parametrize('name', ['', '   ', 'A' * 201])
def test_supplied_invalid_name_retains_audited_invalid_query_behavior(cli_inputs, monkeypatch, capsys, name):
    config_path, _, workspace = cli_inputs
    fake = FakeRetriever(fail=True)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    monkeypatch.setattr(cli, 'make_recipe', lambda *_args: {'fixture': 'invalid-query-cli'})
    assert main(['start', '--config', str(config_path), '--name', name]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['completed'] is True
    assert result['state']['query'] == name
    assert result['state']['error'] is not None
    assert result['audit']['count'] == 2
    assert workspace.is_dir()
    assert fake.calls == 0


@pytest.mark.parametrize('exception', [TypeError, RuntimeError])
def test_unexpected_programmer_errors_are_not_swallowed(cli_inputs, monkeypatch, exception):
    def fail_recipe(*_args):
        raise exception('Fictional programming defect')

    monkeypatch.setattr(cli, 'make_recipe', fail_recipe)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: FakeRetriever(fail=True))
    with pytest.raises(exception, match='Fictional programming defect'):
        main(['start', '--config', str(cli_inputs[0]), '--name', 'Fictional Luma'])


def test_valid_start_and_review_cli_roundtrip_remains_supported(cli_inputs, monkeypatch, capsys):
    config_path, _, _ = cli_inputs
    fake = FakeRetriever()
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    monkeypatch.setattr(cli, 'make_recipe', lambda *_args: {'fixture': 'valid-cli-roundtrip'})
    assert main(['start', '--config', str(config_path), '--name', 'Fictional Luma']) == 0
    pending = json.loads(capsys.readouterr().out)
    assert pending['pending_interrupt'] is True
    review_path = config_path.parent / 'review.json'
    review_path.write_text(json.dumps(form(pending)))
    assert main(['review', '--config', str(config_path), '--thread-id', pending['thread_id'],
                 '--review-file', str(review_path)]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed['completed'] is True
    assert completed['state']['reviewer_decision']['reason'] == 'Fictional test; investigate further.'
    assert completed['audit']['count'] == 4
    assert fake.calls == 1


@pytest.fixture
def recipe_inputs(cli_inputs):
    """Use valid-shaped local metadata and tiny fake files, never model weights."""
    from watchlist.embeddings import MODEL_FILES

    config_path, config, _ = cli_inputs
    embedding = json.loads((Path(__file__).resolve().parents[1] / 'eval/configs/embeddings.json').read_text())
    model_root = config_path.parent / 'fictional-model'
    model_root.mkdir()
    embedding['model']['model_path'] = str(model_root)
    embedding['cache_path'] = str(config_path.parent / 'fictional-cache')
    files = {}
    for relative in MODEL_FILES:
        member = model_root / relative
        member.parent.mkdir(parents=True, exist_ok=True)
        content = ('Fictional inert fixture: ' + relative + '\n').encode()
        member.write_bytes(content)
        files[relative] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    receipt = {
        'model_id': embedding['model']['model_id'], 'revision': embedding['model']['revision'],
        'license': 'MIT', 'source': 'https://example.invalid/fictional-fixture',
        'bytes': sum(value['bytes'] for value in files.values()), 'metadata_bytes': 0, 'files': files,
    }
    embedding_path = Path(config['embedding_config'])
    embedding_path.write_text(json.dumps(embedding))
    receipt_path = model_root / 'acquisition.json'
    receipt_path.write_text(json.dumps(receipt))
    return {'inputs': cli_inputs, 'embedding': embedding, 'embedding_path': embedding_path,
            'receipt': receipt, 'receipt_path': receipt_path}


@pytest.fixture
def forbid_recipe_delegation_and_storage(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Malformed recipe input reached recipe delegation or storage')

    monkeypatch.setattr(cli, '_make_recipe', forbidden, raising=False)
    for name in ('ReviewService', 'E5Retriever', 'ReviewReader'):
        if hasattr(cli, name):
            monkeypatch.setattr(cli, name, forbidden)
    return calls


@pytest.mark.parametrize('document', ['embedding', 'model', 'receipt'])
@pytest.mark.parametrize('value', [None, True, 42, 'fictional', [], [{}]])
def test_start_recipe_metadata_requires_objects_before_storage(
        recipe_inputs, forbid_recipe_delegation_and_storage, capsys, document, value):
    fixture = recipe_inputs
    if document == 'receipt':
        fixture['receipt_path'].write_text(json.dumps(value))
    else:
        content = value if document == 'embedding' else {**fixture['embedding'], 'model': value}
        fixture['embedding_path'].write_text(json.dumps(content))
    rejected_before_storage(['start', '--name', 'Fictional Luma'], fixture['inputs'],
                            forbid_recipe_delegation_and_storage, capsys)


@pytest.mark.parametrize('damage', [
    'model_path_null', 'model_path_array', 'cache_path_bool', 'batch_size_bool', 'batch_size_float',
    'dimension_float', 'files_array', 'file_info_null', 'file_bytes_bool', 'file_hash_invalid',
    'embedding_duplicate', 'embedding_nan', 'receipt_duplicate', 'receipt_nan',
    'embedding_missing', 'embedding_directory', 'receipt_missing', 'receipt_directory',
])
def test_start_recipe_paths_types_and_json_contract_precede_storage(
        recipe_inputs, forbid_recipe_delegation_and_storage, capsys, damage):
    fixture = recipe_inputs
    embedding, receipt = fixture['embedding'], fixture['receipt']
    if damage == 'model_path_null':
        embedding['model']['model_path'] = None
    elif damage == 'model_path_array':
        embedding['model']['model_path'] = []
    elif damage == 'cache_path_bool':
        embedding['cache_path'] = True
    elif damage == 'batch_size_bool':
        embedding['model']['batch_size'] = True
    elif damage == 'batch_size_float':
        embedding['model']['batch_size'] = 8.0
    elif damage == 'dimension_float':
        embedding['model']['dimension'] = 384.0
    elif damage == 'files_array':
        receipt['files'] = []
    elif damage in ('file_info_null', 'file_bytes_bool', 'file_hash_invalid'):
        relative = next(iter(receipt['files']))
        if damage == 'file_info_null':
            receipt['files'][relative] = None
        elif damage == 'file_bytes_bool':
            receipt['files'][relative]['bytes'] = True
        else:
            receipt['files'][relative]['sha256'] = 'not-a-digest'
    elif damage == 'embedding_nan':
        embedding['model']['batch_size'] = float('nan')
    elif damage == 'receipt_nan':
        receipt['metadata_bytes'] = float('nan')
    fixture['embedding_path'].write_text(json.dumps(embedding))
    fixture['receipt_path'].write_text(json.dumps(receipt))
    if damage == 'embedding_duplicate':
        fixture['embedding_path'].write_text(json.dumps(embedding)[:-1] + ', "model": ' + json.dumps(embedding['model']) + '}')
    elif damage == 'receipt_duplicate':
        fixture['receipt_path'].write_text(json.dumps(receipt)[:-1] + ', "files": ' + json.dumps(receipt['files']) + '}')
    elif damage.endswith(('_missing', '_directory')):
        path = fixture['embedding_path'] if damage.startswith('embedding_') else fixture['receipt_path']
        path.unlink()
        if damage.endswith('_directory'):
            path.mkdir()
    rejected_before_storage(['start', '--name', 'Fictional Luma'], fixture['inputs'],
                            forbid_recipe_delegation_and_storage, capsys)


def test_valid_recipe_metadata_delegates_without_loading_a_model_or_opening_storage(recipe_inputs, monkeypatch):
    calls = []
    fixture = recipe_inputs
    expected = {'config': fixture['embedding'], 'db': None, 'reference_sha256': 'f' * 64,
                'model_receipt_sha256': digest(fixture['receipt']), 'packages': {}}

    def fake_recipe(config_path, database=None):
        calls.append((config_path, database))
        return expected

    monkeypatch.setattr(cli, '_make_recipe', fake_recipe, raising=False)
    before = cli_snapshot(fixture['embedding_path'].parent)
    assert cli.make_recipe(fixture['embedding_path']) == expected
    assert calls == [(fixture['embedding_path'], None)]
    assert cli_snapshot(fixture['embedding_path'].parent) == before


@pytest.mark.parametrize('rejection', ['stale_digest', 'stale_checkpoint', 'cross_case', 'duplicate', 'unknown_thread'])
def test_rejected_review_does_not_mutate_existing_workspace(cli_inputs, monkeypatch, capsys, rejection):
    config_path, _, workspace = cli_inputs
    with ReviewService(workspace, FakeRetriever()) as service:
        first = service.start('Fictional Luma', {'fixture': 'preflight-review'})
        second = service.start('Fictional Mira', {'fixture': 'preflight-review'})
        value = form(first)
        if rejection == 'duplicate':
            service.review(first['thread_id'], value)
    thread = first['thread_id']
    if rejection == 'stale_digest':
        value['evidence_sha256'] = '0' * 64
    elif rejection == 'stale_checkpoint':
        value['expected_checkpoint_id'] = str(uuid4())
    elif rejection == 'cross_case':
        value = form(second)
    elif rejection == 'unknown_thread':
        thread = str(uuid4())
    review_path = config_path.parent / 'rejected-review.json'
    review_path.write_text(json.dumps(value))
    fake = FakeRetriever(fail=True)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    before = cli_snapshot(workspace)
    assert main(['review', '--config', str(config_path), '--thread-id', thread,
                 '--review-file', str(review_path)]) == 2
    assert isinstance(json.loads(capsys.readouterr().out)['error'], str)
    assert fake.calls == 0
    assert cli_snapshot(workspace) == before


def test_cross_case_reused_submission_id_is_rejected_before_writer_creation(cli_inputs, monkeypatch, capsys):
    config_path, _, workspace = cli_inputs
    with ReviewService(workspace, FakeRetriever()) as service:
        first = service.start('Fictional completed Luma', {'fixture': 'submission-uniqueness'})
        accepted = form(first)
        service.review(first['thread_id'], accepted)
        second = service.start('Fictional pending Mira', {'fixture': 'submission-uniqueness'})
    reused = {**form(second), 'submission_id': accepted['submission_id']}
    review_path = config_path.parent / 'cross-case-reused-submission.json'
    review_path.write_text(json.dumps(reused))
    writer_calls = []

    def forbidden_writer(*args, **kwargs):
        writer_calls.append((args, kwargs))
        raise AssertionError('Cross-case reused submission ID reached the writer constructor')

    fake = FakeRetriever(fail=True)
    monkeypatch.setattr(cli, 'ReviewService', forbidden_writer)
    monkeypatch.setattr(cli, 'E5Retriever', lambda: fake)
    before = cli_snapshot(workspace)
    assert main(['review', '--config', str(config_path), '--thread-id', second['thread_id'],
                 '--review-file', str(review_path)]) == 2
    assert isinstance(json.loads(capsys.readouterr().out)['error'], str)
    assert writer_calls == []
    assert fake.calls == 0
    assert cli_snapshot(workspace) == before
