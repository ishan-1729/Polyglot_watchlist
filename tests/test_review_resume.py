import json
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import pytest
from agent_support import FakeRetriever, form
from watchlist.agent.storage import ReviewService
from watchlist.agent import storage

WORKER=Path(__file__).with_name('agent_support.py')

def run(action, root, stage='none', review=None):
    args=[sys.executable,str(WORKER),action,str(root),stage]
    if review:args.append(str(review))
    return subprocess.run(args, text=True,capture_output=True,timeout=30)


def parsed(result):
    assert result.returncode==0,result.stderr+result.stdout
    return json.loads(result.stdout)


def test_process_restart_pause_resume_and_duplicate(tmp_path):
    start=parsed(run('start',tmp_path))
    status=parsed(run('status',tmp_path))
    assert status['state']==start['state']
    p=tmp_path/'form.json';p.write_text(json.dumps(form(start)))
    done=parsed(run('review',tmp_path,review=p))
    assert done['completed'] and done['audit']['count']==4
    again=run('review',tmp_path,review=p)
    assert again.returncode!=0 and 'duplicate review' in again.stderr
    assert parsed(run('recover',tmp_path))['completed']


@pytest.mark.parametrize('stage',['after_case','after_packet','after_submission','during_explanation','after_final_audit'])
def test_killed_process_recovery(tmp_path,stage):
    if stage in ('after_case','after_packet'):
        assert run('start',tmp_path,stage).returncode==77
        start=parsed(run('recover',tmp_path,stage))
    else:start=parsed(run('start',tmp_path))
    p=tmp_path/'form.json';p.write_text(json.dumps(form(start)))
    if stage not in ('after_case','after_packet'):
        assert run('review',tmp_path,stage,p).returncode==77
        done=parsed(run('recover',tmp_path))
    else:done=parsed(run('review',tmp_path,review=p))
    assert done['completed'] and done['audit']['count']==4
    assert parsed(run('recover',tmp_path))['audit']==done['audit']


def test_concurrent_review_one_winner(tmp_path):
    start=parsed(run('start',tmp_path));p=tmp_path/'form.json';p.write_text(json.dumps(form(start)))
    args=[sys.executable,str(WORKER),'review',str(tmp_path),'none',str(p)]
    a=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    b=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    a.communicate(timeout=30);b.communicate(timeout=30)
    assert sorted([a.returncode,b.returncode])==[0,1]
    with ReviewService(tmp_path,FakeRetriever(fail=True)) as s:
        assert s.db.execute('SELECT COUNT(*) FROM review_submissions').fetchone()[0]==1
        assert s.db.execute("SELECT COUNT(*) FROM audit_events WHERE event_key='case_finalized'").fetchone()[0]==1


def test_stale_cross_case_unknown_fields_and_version(tmp_path):
    with ReviewService(tmp_path,FakeRetriever()) as s:
        a=s.start('Luma',{});b=s.start('Other',{})
        for v in [form(b),{**form(a),'unexpected':'state injection'}, {**form(a),'expected_checkpoint_id':'old'}]:
            with pytest.raises(ValueError):s.review(a['thread_id'],v)
        with pytest.raises(ValueError,match='unknown thread'):s.status('missing')
        s.code_hash='changed'
        with pytest.raises(ValueError,match='workflow/schema'):s.recover(a['thread_id'])


def _stored_files(root):
    if not root.exists():
        return None
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        metadata = path.lstat()
        result[str(path.relative_to(root))] = (
            metadata.st_mode, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns,
            metadata.st_ctime_ns, hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return result


@pytest.mark.parametrize('missing', ['workspace', 'writer.lock', 'cases.sqlite', 'checkpoints.sqlite'])
def test_existing_writer_open_rejects_missing_storage_without_initializing(tmp_path, missing):
    root = tmp_path / 'review'
    if missing != 'workspace':
        with ReviewService(root, FakeRetriever()) as service:
            service.start('Luma Vesper', {'fixture': 'existing-open-only'})
        (root / missing).unlink()
        root.chmod(0o750)
        for path in root.iterdir():
            if path.is_file():
                path.chmod(0o640)
    before = _stored_files(root)
    with pytest.raises((ValueError, OSError)):
        with ReviewService(root, FakeRetriever(fail=True), mode='existing'):
            pytest.fail('An incomplete existing workspace was opened as a writer')
    assert _stored_files(root) == before


def test_existing_writer_open_preserves_store_permissions_and_bytes(tmp_path):
    root = tmp_path / 'review'
    with ReviewService(root, FakeRetriever()) as service:
        service.start('Luma Vesper', {'fixture': 'existing-open-permissions'})
    root.chmod(0o750)
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o640)
    before = _stored_files(root)
    with ReviewService(root, FakeRetriever(fail=True), mode='existing'):
        pass
    assert _stored_files(root) == before


def test_existing_writer_open_skips_schema_scripts_and_saver_setup(tmp_path, monkeypatch):
    root = (tmp_path / 'review').resolve()
    with ReviewService(root, FakeRetriever()) as service:
        service.start('Luma Vesper', {'fixture': 'no-existing-store-setup'})
    before = _stored_files(root)
    actual_connect = sqlite3.connect
    forbidden_attempts = []
    schema_actions = {
        getattr(sqlite3, f'SQLITE_{action}_{kind}')
        for action in ('CREATE', 'DROP')
        for kind in ('INDEX', 'TABLE', 'TRIGGER', 'VIEW', 'TEMP_INDEX', 'TEMP_TABLE', 'TEMP_TRIGGER', 'TEMP_VIEW')
    } | {sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_REINDEX}

    def reject_schema_changes(action, first, second, database, trigger):
        if action in schema_actions or (
            action == sqlite3.SQLITE_PRAGMA and second is not None
            and first.lower() in {'journal_mode', 'schema_version', 'user_version'}
        ):
            forbidden_attempts.append((action, first, second))
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    class GuardedConnection(sqlite3.Connection):
        def executescript(self, sql_script, /):
            forbidden_attempts.append('schema script')
            pytest.fail('Opening an existing writer ran an initialization script')

    def guarded_connect(database, *args, **kwargs):
        raw = os.fspath(database)
        path = Path(unquote(urlsplit(raw).path) if raw.startswith('file:') else raw).resolve()
        original = path.is_relative_to(root)
        if original:
            kwargs['factory'] = GuardedConnection
        connection = actual_connect(database, *args, **kwargs)
        if original:
            connection.set_authorizer(reject_schema_changes)
        return connection

    def forbidden_setup(*args, **kwargs):
        forbidden_attempts.append('checkpoint saver setup')
        pytest.fail('Opening an existing writer ran checkpoint saver setup')

    from langgraph.checkpoint.sqlite import SqliteSaver
    with monkeypatch.context() as guarded:
        guarded.setattr(sqlite3, 'connect', guarded_connect)
        guarded.setattr(SqliteSaver, 'setup', forbidden_setup)
        with ReviewService(root, FakeRetriever(fail=True), mode='existing'):
            pass
    assert forbidden_attempts == []
    assert _stored_files(root) == before


@pytest.mark.parametrize('operation', ['status', 'list'])
def test_current_inspection_rejects_changed_fingerprint_while_archive_reading_survives(tmp_path, monkeypatch, operation):
    """Current workflow checks stay strict; frozen inspection never resumes a case."""
    root = (tmp_path / 'review').resolve()
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'fingerprint-boundary'})
    project = tmp_path.resolve() / 'copied-project'
    shutil.copytree(root, project / 'data/review')
    spec = importlib.util.spec_from_file_location(
        'step02_test_preservation', Path(__file__).resolve().parents[1] / 'scripts/preserve_v1.py'
    )
    assert spec is not None and spec.loader is not None
    preservation = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = preservation
    spec.loader.exec_module(preservation)
    normalized = tmp_path.resolve() / 'normalized-copies'
    preservation._backup_databases(project, ['data/review/cases.sqlite', 'data/review/checkpoints.sqlite'], normalized)

    from watchlist.review.compat_v1 import inspect_v1, verify_v1
    archive_before = verify_v1(project, 'data/review', normalized)
    root_before = _stored_files(root)
    monkeypatch.setattr(storage, 'workflow_hash', lambda: '0' * 64)
    assert pending['state']['workflow_sha256'] != '0' * 64
    with pytest.raises(ValueError, match='workflow|fingerprint|implementation'):
        with storage.ReviewReader(root) as reader:
            if operation == 'status':
                reader.status(pending['thread_id'])
            else:
                reader.list_cases()
    assert _stored_files(root) == root_before
    with pytest.raises(ValueError, match='workflow/schema changed'):
        with ReviewService(root, FakeRetriever(fail=True), mode='existing') as service:
            service.recover(pending['thread_id'])
    assert _stored_files(root) == root_before
    assert verify_v1(project, 'data/review', normalized) == archive_before
    archived = inspect_v1(project, 'data/review', normalized, pending['thread_id'])
    assert archived['latest_state'] == pending['state']
    assert archived['case']['status'] == 'packet_saved_pending_review'


@pytest.mark.parametrize('operation', ['status', 'recover', 'review', 'start', 'invoke'])
def test_writer_operations_reject_changed_fingerprint_before_runtime_or_writes(tmp_path, monkeypatch, operation):
    root = tmp_path / 'changed-workflow'
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'operation-fingerprint-boundary'})
    before = _stored_files(root)
    monkeypatch.setattr(storage, 'workflow_hash', lambda: '0' * 64)
    assert pending['state']['workflow_sha256'] != '0' * 64
    retriever, forbidden_calls = FakeRetriever(fail=True), []

    def forbidden(name):
        def reject(*args, **kwargs):
            forbidden_calls.append(name)
            pytest.fail(f'Fingerprint mismatch reached {name}')
        return reject

    with ReviewService(root, retriever, mode='existing') as service:
        assert _stored_files(root) == before
        for name in ('get_state', 'invoke'):
            monkeypatch.setattr(service.graph, name, forbidden('graph.' + name))
        for name in ('create', 'prepare', 'submit', 'finalize', 'attempt_error'):
            monkeypatch.setattr(service.ledger, name, forbidden('ledger.' + name))
        with pytest.raises(ValueError, match='workflow/schema changed'):
            if operation == 'start':
                service.start('Tavi Orinel', {'fixture': 'changed-workflow'})
            elif operation == 'review':
                service.review(pending['thread_id'], form(pending))
            elif operation == 'invoke':
                service.invoke(pending['thread_id'], None)
            else:
                getattr(service, operation)(pending['thread_id'])
        assert forbidden_calls == []
        assert retriever.calls == 0
        assert _stored_files(root) == before
    assert _stored_files(root) == before


# These fixed fixtures describe the accepted legacy shape independently of the
# current initializer. Their default application_id is zero by SQLite design.
_LEGACY_REVIEW_DDL = {
    'cases.sqlite': '''
CREATE TABLE cases (
 audit_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL UNIQUE,
 initial_json TEXT NOT NULL, parent_audit_id TEXT REFERENCES cases(audit_id)
);
CREATE TABLE review_packets (
 audit_id TEXT NOT NULL REFERENCES cases(audit_id), revision INTEGER NOT NULL CHECK(revision=1),
 packet_json TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(audit_id, revision)
);
CREATE TABLE review_submissions (
 submission_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL, sha256 TEXT NOT NULL,
 UNIQUE(audit_id, revision),
 FOREIGN KEY(audit_id, revision) REFERENCES review_packets(audit_id, revision)
);
CREATE TABLE audit_events (
 audit_id TEXT NOT NULL REFERENCES cases(audit_id), sequence INTEGER NOT NULL,
 event_key TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL,
 PRIMARY KEY(audit_id, sequence), UNIQUE(audit_id, event_key)
);
PRAGMA user_version = 1;
''',
    'checkpoints.sqlite': '''
CREATE TABLE checkpoints (
 thread_id TEXT NOT NULL,
 checkpoint_ns TEXT NOT NULL DEFAULT '',
 checkpoint_id TEXT NOT NULL,
 parent_checkpoint_id TEXT,
 type TEXT,
 checkpoint BLOB,
 metadata BLOB,
 PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE writes (
 thread_id TEXT NOT NULL,
 checkpoint_ns TEXT NOT NULL DEFAULT '',
 checkpoint_id TEXT NOT NULL,
 task_id TEXT NOT NULL,
 task_path TEXT NOT NULL DEFAULT '',
 idx INTEGER NOT NULL,
 channel TEXT NOT NULL,
 type TEXT,
 value BLOB,
 PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
''',
}


def _legacy_review_workspace(root, *, changed_name=None, changed_ddl=None):
    """Build a small empty historical pair without invoking current setup."""
    root.mkdir(mode=0o750)
    (root / 'writer.lock').touch(mode=0o640)
    for name, original_ddl in _LEGACY_REVIEW_DDL.items():
        path = root / name
        connection = sqlite3.connect(path)
        try:
            connection.executescript(changed_ddl if name == changed_name else original_ddl)
        finally:
            connection.close()
        path.chmod(0o640)


def _open_ownership_fixture(root, opener):
    if opener == 'reader':
        with storage.ReviewReader(root) as reader:
            return reader.list_cases()
    with ReviewService(root, FakeRetriever(fail=True), mode='existing'):
        return None


def _assert_review_ownership_rejected(root, opener, monkeypatch):
    """Reject at the copied-schema boundary, before original SQLite/runtime use."""
    before = _stored_files(root)
    actual_connect = sqlite3.connect

    def copies_only(database, *args, **kwargs):
        raw = os.fspath(database)
        if raw != ':memory:':
            path = Path(unquote(urlsplit(raw).path) if raw.startswith('file:') else raw).resolve()
            assert not path.is_relative_to(root.resolve()), 'Unrecognized original reached SQLite'
        return actual_connect(database, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail('Unrecognized storage reached graph or retrieval initialization')

    from watchlist.agent import graph
    from watchlist.agent.retrieval import E5Retriever
    try:
        with monkeypatch.context() as guarded:
            guarded.setattr(sqlite3, 'connect', copies_only)
            guarded.setattr(graph, 'build_graph', forbidden)
            guarded.setattr(FakeRetriever, 'search', forbidden)
            guarded.setattr(E5Retriever, '__init__', forbidden)
            guarded.setattr(E5Retriever, 'search', forbidden)
            with pytest.raises(ValueError):
                _open_ownership_fixture(root, opener)
    finally:
        assert _stored_files(root) == before, 'Ownership rejection modified original storage'


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name', ['cases.sqlite', 'checkpoints.sqlite'])
@pytest.mark.parametrize('user_version', [0, 1, 2, 99])
def test_review_ownership_rejects_unrelated_database(tmp_path, monkeypatch, opener, name, user_version):
    root = tmp_path / 'foreign-pair'
    unrelated = f'''
CREATE TABLE fictional_notes (note TEXT NOT NULL);
INSERT INTO fictional_notes VALUES ('Tavi Orinel fixture only');
PRAGMA user_version={user_version};
'''
    _legacy_review_workspace(root, changed_name=name, changed_ddl=unrelated)
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name', ['cases.sqlite', 'checkpoints.sqlite'])
def test_review_ownership_rejects_forged_expected_table_names(tmp_path, monkeypatch, opener, name):
    tables = (('cases', 'review_packets', 'review_submissions', 'audit_events')
              if name == 'cases.sqlite' else ('checkpoints', 'writes'))
    forged = '\n'.join(f'CREATE TABLE {table} (fictional_text TEXT, task_path TEXT);' for table in tables)
    forged += f'\nPRAGMA user_version={1 if name == "cases.sqlite" else 0};'
    root = tmp_path / 'forged-pair'
    _legacy_review_workspace(root, changed_name=name, changed_ddl=forged)
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name,table', [('cases.sqlite', 'review_submissions'), ('checkpoints.sqlite', 'writes')])
@pytest.mark.parametrize('missing', ['all-schema', 'one-table'])
def test_review_ownership_rejects_empty_or_partial_companion_schema(tmp_path, monkeypatch, opener, name, table, missing):
    root = tmp_path / 'partial-schema'
    ddl = '' if missing == 'all-schema' else _LEGACY_REVIEW_DDL[name] + f'DROP TABLE {table};'
    _legacy_review_workspace(root, changed_name=name, changed_ddl=ddl)
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name,user_version', [
    ('cases.sqlite', 0), ('cases.sqlite', 2), ('cases.sqlite', 99),
    ('checkpoints.sqlite', 1), ('checkpoints.sqlite', 2), ('checkpoints.sqlite', 99),
])
def test_review_ownership_rejects_correct_shape_with_wrong_version(tmp_path, monkeypatch, opener, name, user_version):
    root = tmp_path / 'wrong-version'
    ddl = _LEGACY_REVIEW_DDL[name] + f'PRAGMA user_version={user_version};'
    _legacy_review_workspace(root, changed_name=name, changed_ddl=ddl)
    _assert_review_ownership_rejected(root, opener, monkeypatch)


_MALFORMED_REVIEW_SCHEMAS = [
    ('ledger-missing-column', 'cases.sqlite', 'initial_json TEXT NOT NULL, ', ''),
    ('ledger-wrong-type', 'cases.sqlite', 'initial_json TEXT NOT NULL', 'initial_json INTEGER NOT NULL'),
    ('ledger-missing-not-null', 'cases.sqlite', 'initial_json TEXT NOT NULL', 'initial_json TEXT'),
    ('ledger-missing-unique', 'cases.sqlite', 'thread_id TEXT NOT NULL UNIQUE', 'thread_id TEXT NOT NULL'),
    ('ledger-missing-primary-key', 'cases.sqlite', 'PRIMARY KEY(audit_id, sequence), ', ''),
    ('ledger-wrong-primary-key', 'cases.sqlite', 'PRIMARY KEY(audit_id, sequence)', 'PRIMARY KEY(sequence, audit_id)'),
    ('ledger-missing-foreign-key', 'cases.sqlite', 'parent_audit_id TEXT REFERENCES cases(audit_id)', 'parent_audit_id TEXT'),
    ('ledger-wrong-foreign-key-action', 'cases.sqlite', 'parent_audit_id TEXT REFERENCES cases(audit_id)', 'parent_audit_id TEXT REFERENCES cases(audit_id) ON DELETE CASCADE'),
    ('ledger-missing-check', 'cases.sqlite', ' CHECK(revision=1)', ''),
    ('ledger-weakened-check', 'cases.sqlite', 'CHECK(revision=1)', 'CHECK(revision>=1)'),
    ('checkpoint-missing-column', 'checkpoints.sqlite', " task_path TEXT NOT NULL DEFAULT '',\n", ''),
    ('checkpoint-wrong-type', 'checkpoints.sqlite', 'checkpoint BLOB', 'checkpoint TEXT'),
    ('checkpoint-wrong-default', 'checkpoints.sqlite', "task_path TEXT NOT NULL DEFAULT ''", "task_path TEXT NOT NULL DEFAULT 'other'"),
    ('checkpoint-missing-not-null', 'checkpoints.sqlite', 'channel TEXT NOT NULL', 'channel TEXT'),
    ('checkpoint-missing-primary-key', 'checkpoints.sqlite', ' value BLOB,\n PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)', ' value BLOB'),
    ('checkpoint-wrong-primary-key', 'checkpoints.sqlite', 'PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)', 'PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, idx, task_id)'),
]


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('label,name,old,new', _MALFORMED_REVIEW_SCHEMAS, ids=[case[0] for case in _MALFORMED_REVIEW_SCHEMAS])
def test_review_ownership_rejects_malformed_schema(tmp_path, monkeypatch, opener, label, name, old, new):
    original = _LEGACY_REVIEW_DDL[name]
    assert original.count(old) == 1, 'The fixture must change exactly one schema declaration'
    root = tmp_path / label
    _legacy_review_workspace(root, changed_name=name, changed_ddl=original.replace(old, new))
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name,table,column', [('cases.sqlite', 'cases', 'thread_id'), ('checkpoints.sqlite', 'writes', 'task_id')])
@pytest.mark.parametrize('extra', ['table', 'index', 'unique-index', 'partial-index', 'expression-index', 'trigger', 'view'])
def test_review_ownership_rejects_unexpected_schema_objects(tmp_path, monkeypatch, opener, name, table, column, extra):
    statements = {
        'table': 'CREATE TABLE unexpected_notes (note TEXT);',
        'index': f'CREATE INDEX unexpected_index ON {table}({column});',
        'unique-index': f'CREATE UNIQUE INDEX unexpected_index ON {table}({column});',
        'partial-index': f'CREATE INDEX unexpected_index ON {table}({column}) WHERE {column} IS NOT NULL;',
        'expression-index': f'CREATE INDEX unexpected_index ON {table}(lower({column}));',
        'trigger': f'CREATE TRIGGER unexpected_trigger AFTER INSERT ON {table} BEGIN SELECT 1; END;',
        'view': f'CREATE VIEW unexpected_view AS SELECT {column} FROM {table};',
    }
    root = tmp_path / 'unexpected-object'
    _legacy_review_workspace(root, changed_name=name, changed_ddl=_LEGACY_REVIEW_DDL[name] + statements[extra])
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('name,application_id', [
    ('cases.sqlite', 0x12345678), ('cases.sqlite', 0x50574331),
    ('checkpoints.sqlite', 0x12345678), ('checkpoints.sqlite', 0x50575231),
])
def test_review_ownership_rejects_unsupported_application_identity(tmp_path, monkeypatch, opener, name, application_id):
    root = tmp_path / 'foreign-application'
    _legacy_review_workspace(root, changed_name=name, changed_ddl=_LEGACY_REVIEW_DDL[name] + f'PRAGMA application_id={application_id};')
    _assert_review_ownership_rejected(root, opener, monkeypatch)


@pytest.mark.parametrize('opener', ['writer', 'reader'])
def test_review_ownership_accepts_exact_legacy_without_upgrade(tmp_path, opener):
    root = tmp_path / 'exact-legacy'
    _legacy_review_workspace(root)
    before = _stored_files(root)
    result = _open_ownership_fixture(root, opener)
    assert result == ([] if opener == 'reader' else None)
    assert _stored_files(root) == before
    for name, expected_version in [('cases.sqlite', 1), ('checkpoints.sqlite', 0)]:
        connection = sqlite3.connect((root / name).as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            assert connection.execute('PRAGMA application_id').fetchone()[0] == 0
            assert connection.execute('PRAGMA user_version').fetchone()[0] == expected_version
        finally:
            connection.close()


@pytest.mark.parametrize('name,application_id,user_version', [
    ('cases.sqlite', 0x50575231, 1), ('checkpoints.sqlite', 0x50574331, 0),
])
def test_review_ownership_tags_new_stores_without_changing_schema_versions(tmp_path, name, application_id, user_version):
    root = tmp_path / 'new-owned-pair'
    with ReviewService(root, FakeRetriever(), mode='create') as service:
        service.start('Luma Vesper', {'fixture': 'new-application-identity'})
    connection = sqlite3.connect((root / name).as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        assert connection.execute('PRAGMA application_id').fetchone()[0] == application_id
        assert connection.execute('PRAGMA user_version').fetchone()[0] == user_version
    finally:
        connection.close()


@pytest.mark.parametrize('opener', ['writer', 'reader'])
@pytest.mark.parametrize('missing', ['cases.sqlite', 'checkpoints.sqlite', 'writer.lock'])
def test_review_ownership_never_regenerates_a_legacy_companion(tmp_path, monkeypatch, opener, missing):
    root = tmp_path / 'incomplete-legacy'
    _legacy_review_workspace(root)
    (root / missing).unlink()
    _assert_review_ownership_rejected(root, opener, monkeypatch)


_RECOVERY_SUBPROCESS = r'''
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading

sys.path.insert(0, sys.argv[1])
from agent_support import FakeRetriever
from langgraph.checkpoint.sqlite import SqliteSaver
from watchlist.agent.storage import ReviewService

request = json.loads(sys.argv[2])
root = Path(request['root'])

class CountedRetriever(FakeRetriever):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def search(self, query, recipe):
        self.attempts += 1
        if not request['allow_retrieval']:
            raise RuntimeError('Unexpected retrieval after durable review evidence')
        if request.get('checkpoint_snapshot'):
            source = sqlite3.connect(root / 'checkpoints.sqlite')
            destination = sqlite3.connect(request['checkpoint_snapshot'])
            try:
                source.backup(destination)
                destination.execute('PRAGMA journal_mode=DELETE')
                destination.commit()
            finally:
                destination.close()
                source.close()
        return super().search(query, recipe)

retriever = CountedRetriever()

def crash(point):
    if point == request.get('stage'):
        thread_id = request.get('thread_id')
        if request['action'] == 'start':
            thread_id = service.db.execute('SELECT thread_id FROM cases ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        print(json.dumps({'crashed_at': point, 'thread_id': thread_id,
                          'retrieval_calls': retriever.attempts}), flush=True)
        os._exit(77)

original_put = SqliteSaver.put
original_put_writes = SqliteSaver.put_writes

def put_with_checkpoint_crash(self, config, checkpoint, metadata, new_versions):
    values = checkpoint['channel_values']
    if request.get('stage') == 'after_retrieval_writes' and values.get('retrieval') is not None:
        # Hold the next checkpoint before SQLite access so the saved-output
        # crash cannot race with a subsequent checkpoint commit.
        threading.Event().wait(5)
        raise AssertionError('Retrieval writes did not reach the crash boundary')
    result = original_put(self, config, checkpoint, metadata, new_versions)
    if metadata.get('source') == 'input':
        crash('after_input_checkpoint')
    if values.get('retrieval') is not None and values.get('evidence_sha256') is None:
        crash('after_retrieval_checkpoint')
    return result

def put_writes_with_retrieval_crash(self, config, writes, task_id, task_path=''):
    result = original_put_writes(self, config, writes, task_id, task_path)
    if any(channel == 'retrieval' and value is not None for channel, value in writes):
        crash('after_retrieval_writes')
    return result

SqliteSaver.put = put_with_checkpoint_crash
SqliteSaver.put_writes = put_writes_with_retrieval_crash

try:
    with ReviewService(root, retriever, crash,
                       mode='auto' if request['action'] == 'start' else 'existing') as service:
        if request['action'] == 'start':
            result = service.start(request.get('query', 'Luma Vesper'), {'fixture': 'subprocess-reconciliation'})
        elif request['action'] == 'review':
            result = service.review(request['thread_id'], request['form'])
        elif request['action'] == 'recover':
            result = service.recover(request['thread_id'])
        else:
            raise AssertionError('Unknown fixture action')
    response = {'ok': True, 'result': result, 'retrieval_calls': retriever.attempts}
    returncode = 0
except Exception as exc:
    response = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc),
                'retrieval_calls': retriever.attempts}
    returncode = 2
print(json.dumps(response), flush=True)
sys.exit(returncode)
'''


def _recovery_process(root, action, *, thread_id=None, stage=None, review_form=None,
                      allow_retrieval=False, query='Luma Vesper', checkpoint_snapshot=None):
    """Use a new interpreter; durable-evidence recovery has no retrieval allowance."""
    request = {'root': str(root), 'action': action, 'thread_id': thread_id,
               'stage': stage, 'form': review_form, 'allow_retrieval': allow_retrieval,
               'query': query, 'checkpoint_snapshot': str(checkpoint_snapshot) if checkpoint_snapshot else None}
    return subprocess.run([sys.executable, '-B', '-c', _RECOVERY_SUBPROCESS,
                           str(WORKER.parent), json.dumps(request)],
                          text=True, capture_output=True, timeout=30)


def _recovery_success(process, *, retrieval_calls=0):
    assert process.returncode == 0, process.stderr + process.stdout
    response = json.loads(process.stdout)
    assert response['ok'] is True
    assert response['retrieval_calls'] == retrieval_calls
    return response['result']


def _recovery_crash(process, stage, *, retrieval_calls=0):
    assert process.returncode == 77, process.stderr + process.stdout
    response = json.loads(process.stdout)
    assert response['crashed_at'] == stage
    assert response['retrieval_calls'] == retrieval_calls
    return response['thread_id']


def _replace_fixture_checkpoints(root, database_bytes):
    """Replace only a deliberately disposable fixture generation before testing."""
    for suffix in ('-wal', '-shm', '-journal'):
        (root / ('checkpoints.sqlite' + suffix)).unlink(missing_ok=True)
    (root / 'checkpoints.sqlite').write_bytes(database_bytes)


def _fixture_checkpoint_snapshot(root: Path) -> bytes:
    """Include committed WAL data when saving a disposable crash fixture."""
    with tempfile.TemporaryDirectory(prefix='watchlist-recovery-fixture-') as directory:
        path = Path(directory) / 'checkpoints.sqlite'
        source = sqlite3.connect((root / 'checkpoints.sqlite').as_uri() + '?mode=ro', uri=True)
        destination = sqlite3.connect(path)
        try:
            source.backup(destination)
            destination.execute('PRAGMA journal_mode=DELETE')
            destination.commit()
        finally:
            destination.close()
            source.close()
        return path.read_bytes()


def _assert_recovery_rejection_preserves_store(root, thread_id):
    root.chmod(0o750)
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o640)
    before = _stored_files(root)
    process = _recovery_process(root, 'recover', thread_id=thread_id)
    after = _stored_files(root)
    response = json.loads(process.stdout)
    changed = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
    observed = (process.returncode, response['ok'], response['retrieval_calls'], changed)
    assert observed == (2, False, 0, []), (
        f'Rejection must fail before retrieval or storage changes; observed={observed}; '
        f'error={response.get("error_type")}: {response.get("error")}; stderr={process.stderr}'
    )


@pytest.mark.parametrize('stage', ['after_case', 'after_packet', 'after_submission', 'during_explanation', 'after_final_audit'])
def test_recovery_subprocess_crash_windows_preserve_evidence_without_retrieval(tmp_path, stage):
    root = tmp_path / 'crash-window'
    if stage in ('after_case', 'after_packet'):
        thread_id = _recovery_crash(
            _recovery_process(root, 'start', stage=stage, allow_retrieval=True), stage,
            retrieval_calls=int(stage == 'after_packet'),
        )
        pending = _recovery_success(
            _recovery_process(root, 'recover', thread_id=thread_id, allow_retrieval=stage == 'after_case'),
            retrieval_calls=int(stage == 'after_case'),
        )
        assert pending['pending_interrupt'] and not pending['completed']
        accepted_form = form(pending)
        done = _recovery_success(_recovery_process(root, 'review', thread_id=thread_id, review_form=accepted_form))
    else:
        pending = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
        thread_id, accepted_form = pending['thread_id'], form(pending)
        assert _recovery_crash(
            _recovery_process(root, 'review', thread_id=thread_id, stage=stage, review_form=accepted_form), stage,
        ) == thread_id
        done = _recovery_success(_recovery_process(root, 'recover', thread_id=thread_id))
    assert done['completed']
    assert done['state']['reviewer_decision']['submission_id'] == accepted_form['submission_id']
    assert done['state']['evidence_sha256'] == pending['state']['evidence_sha256']
    assert done['audit']['count'] == 4
    again = _recovery_success(_recovery_process(root, 'recover', thread_id=thread_id))
    assert again['completed'] and again['audit'] == done['audit']
    assert again['state'] == done['state']
    connection = sqlite3.connect((root / 'cases.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        assert connection.execute('SELECT COUNT(*) FROM review_submissions').fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_key='case_finalized'").fetchone()[0] == 1
    finally:
        connection.close()


def _two_durable_cases(root, state):
    peer = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True, query='Tavi Orinel'), retrieval_calls=1)
    target = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
    if state != 'pending':
        process = _recovery_process(root, 'review', thread_id=target['thread_id'], review_form=form(target),
                                    stage='after_submission' if state == 'accepted' else None)
        if state == 'accepted':
            _recovery_crash(process, 'after_submission')
        else:
            _recovery_success(process)
    return peer, target


@pytest.mark.parametrize('state', ['pending', 'accepted', 'completed'])
@pytest.mark.parametrize('damage', ['delete-target-history', 'delete-all-history', 'empty-schema-replacement'])
def test_recovery_subprocess_rejects_lost_checkpoint_history_unchanged(tmp_path, state, damage):
    root = tmp_path / 'lost-history'
    peer, target = _two_durable_cases(root, state)
    if damage == 'empty-schema-replacement':
        empty = sqlite3.connect(':memory:')
        try:
            empty.executescript(_LEGACY_REVIEW_DDL['checkpoints.sqlite'])
            empty.execute('PRAGMA application_id=0x50574331')
            replacement = empty.serialize()
        finally:
            empty.close()
        _replace_fixture_checkpoints(root, replacement)
    else:
        connection = sqlite3.connect(root / 'checkpoints.sqlite')
        try:
            for table in ('writes', 'checkpoints'):
                if damage == 'delete-target-history':
                    connection.execute(f'DELETE FROM {table} WHERE thread_id=?', (target['thread_id'],))
                else:
                    connection.execute(f'DELETE FROM {table}')
            connection.commit()
            if damage == 'delete-target-history':
                assert connection.execute('SELECT COUNT(*) FROM checkpoints WHERE thread_id=?', (peer['thread_id'],)).fetchone()[0] > 0
        finally:
            connection.close()
    _assert_recovery_rejection_preserves_store(root, target['thread_id'])


def test_recovery_subprocess_rejects_real_pre_retrieval_checkpoint_rollback(tmp_path):
    root = tmp_path / 'checkpoint-rollback'
    before_retrieval = tmp_path / 'before-retrieval.sqlite'
    _recovery_success(_recovery_process(root, 'start', allow_retrieval=True, query='Tavi Orinel'), retrieval_calls=1)
    target = _recovery_success(
        _recovery_process(root, 'start', allow_retrieval=True, checkpoint_snapshot=before_retrieval), retrieval_calls=1,
    )
    assert target['state']['evidence_sha256'] is not None
    _replace_fixture_checkpoints(root, before_retrieval.read_bytes())
    _assert_recovery_rejection_preserves_store(root, target['thread_id'])


def test_recovery_subprocess_rejects_prior_peer_generation_even_for_healthy_target(tmp_path):
    root = tmp_path / 'mixed-generations'
    peer = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True, query='Tavi Orinel'), retrieval_calls=1)
    peer_only_generation = (root / 'checkpoints.sqlite').read_bytes()
    later = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
    assert later['thread_id'] != peer['thread_id']
    _replace_fixture_checkpoints(root, peer_only_generation)
    _assert_recovery_rejection_preserves_store(root, peer['thread_id'])


def test_recovery_subprocess_rejects_other_workspace_checkpoint_generation(tmp_path):
    root, other = tmp_path / 'original-workspace', tmp_path / 'other-workspace'
    target = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
    foreign = _recovery_success(_recovery_process(other, 'start', allow_retrieval=True, query='Tavi Orinel'), retrieval_calls=1)
    assert target['thread_id'] != foreign['thread_id']
    _replace_fixture_checkpoints(root, (other / 'checkpoints.sqlite').read_bytes())
    other_before = _stored_files(other)
    _assert_recovery_rejection_preserves_store(root, target['thread_id'])
    assert _stored_files(other) == other_before


@pytest.mark.parametrize('damage,name', [
    ('missing', 'cases.sqlite'), ('missing', 'checkpoints.sqlite'), ('missing', 'writer.lock'),
    ('truncated', 'cases.sqlite'), ('truncated', 'checkpoints.sqlite'),
])
def test_recovery_subprocess_rejects_missing_or_truncated_storage_unchanged(tmp_path, damage, name):
    root = tmp_path / 'broken-files'
    pending = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
    done = _recovery_success(_recovery_process(root, 'review', thread_id=pending['thread_id'], review_form=form(pending)))
    assert done['completed']
    path = root / name
    if damage == 'missing':
        path.unlink()
    else:
        original = path.read_bytes()
        assert len(original) > 4096
        path.write_bytes(original[:len(original) // 2])
    _assert_recovery_rejection_preserves_store(root, pending['thread_id'])


def test_recovery_subprocess_resumes_input_only_checkpoint_without_new_input(tmp_path):
    """A committed input checkpoint is a real root even before state is visible."""
    root = tmp_path / 'input-only-checkpoint'
    thread_id = _recovery_crash(
        _recovery_process(root, 'start', stage='after_input_checkpoint', allow_retrieval=True),
        'after_input_checkpoint',
    )
    connection = sqlite3.connect(':memory:')
    connection.deserialize(_fixture_checkpoint_snapshot(root))
    try:
        original = connection.execute(
            'SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata '
            'FROM checkpoints WHERE thread_id=?', (thread_id,),
        ).fetchall()
        assert len(original) == 1
        assert json.loads(original[0][4])['source'] == 'input'
        assert original[0][1] is None
    finally:
        connection.close()
    pending = _recovery_success(
        _recovery_process(root, 'recover', thread_id=thread_id, allow_retrieval=True), retrieval_calls=1,
    )
    assert pending['pending_interrupt'] and not pending['completed']
    connection = sqlite3.connect((root / 'checkpoints.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        rows = connection.execute(
            'SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata '
            'FROM checkpoints WHERE thread_id=? ORDER BY checkpoint_id', (thread_id,),
        ).fetchall()
        assert [row for row in rows if json.loads(row[4])['source'] == 'input'] == original
        assert sum(row[1] is None for row in rows) == 1
    finally:
        connection.close()
    done = _recovery_success(_recovery_process(root, 'review', thread_id=thread_id, review_form=form(pending)))
    assert done['completed'] and done['audit']['count'] == 4


@pytest.mark.parametrize('stage', ['after_retrieval_writes', 'after_retrieval_checkpoint'])
def test_recovery_subprocess_uses_saved_retrieval_before_packet_commit(tmp_path, stage):
    root = tmp_path / 'retrieval-before-packet'
    thread_id = _recovery_crash(
        _recovery_process(root, 'start', stage=stage, allow_retrieval=True),
        stage, retrieval_calls=1,
    )
    connection = sqlite3.connect((root / 'cases.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        assert connection.execute('SELECT COUNT(*) FROM review_packets').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0] == 1
    finally:
        connection.close()
    pending = _recovery_success(_recovery_process(root, 'recover', thread_id=thread_id))
    assert pending['pending_interrupt'] and not pending['completed']
    assert pending['state']['retrieval']['model'] == 'MOCK'
    assert pending['state']['evidence_sha256'] is not None
    done = _recovery_success(_recovery_process(root, 'review', thread_id=thread_id, review_form=form(pending)))
    assert done['completed'] and done['audit']['count'] == 4


@pytest.mark.parametrize('state', ['pending', 'accepted', 'completed'])
def test_recovery_subprocess_rejects_input_only_rollback_after_durable_progress(tmp_path, state):
    root = tmp_path / 'input-only-rollback'
    thread_id = _recovery_crash(
        _recovery_process(root, 'start', stage='after_input_checkpoint', allow_retrieval=True),
        'after_input_checkpoint',
    )
    input_generation = _fixture_checkpoint_snapshot(root)
    pending = _recovery_success(
        _recovery_process(root, 'recover', thread_id=thread_id, allow_retrieval=True), retrieval_calls=1,
    )
    if state != 'pending':
        process = _recovery_process(root, 'review', thread_id=thread_id, review_form=form(pending),
                                    stage='after_submission' if state == 'accepted' else None)
        if state == 'accepted':
            _recovery_crash(process, 'after_submission')
        else:
            assert _recovery_success(process)['completed']
    _replace_fixture_checkpoints(root, input_generation)
    _assert_recovery_rejection_preserves_store(root, thread_id)


@pytest.mark.parametrize('checkpoint_stage', ['pending', 'during_explanation'])
def test_recovery_subprocess_rejects_completed_case_rolled_back_before_explanation(tmp_path, checkpoint_stage):
    root = tmp_path / 'completed-rollback'
    pending = _recovery_success(_recovery_process(root, 'start', allow_retrieval=True), retrieval_calls=1)
    thread_id, accepted_form = pending['thread_id'], form(pending)
    if checkpoint_stage == 'during_explanation':
        _recovery_crash(
            _recovery_process(root, 'review', thread_id=thread_id, review_form=accepted_form,
                              stage='during_explanation'), 'during_explanation',
        )
    old_generation = _fixture_checkpoint_snapshot(root)
    if checkpoint_stage == 'pending':
        done = _recovery_success(_recovery_process(root, 'review', thread_id=thread_id, review_form=accepted_form))
    else:
        done = _recovery_success(_recovery_process(root, 'recover', thread_id=thread_id))
    assert done['completed'] and done['audit']['count'] == 4
    _replace_fixture_checkpoints(root, old_generation)
    _assert_recovery_rejection_preserves_store(root, thread_id)


@pytest.mark.parametrize('operation', ['recover', 'review', 'start'])
@pytest.mark.parametrize('missing_case', ['target', 'peer'])
def test_recovery_rechecks_checkpoint_history_after_writer_admission(tmp_path, operation, missing_case):
    root = tmp_path / 'post-admission-loss'
    peer, target = _two_durable_cases(root, 'pending')
    retriever = FakeRetriever(fail=True)
    with ReviewService(root, retriever, mode='existing') as service:
        lost_thread = (target if missing_case == 'target' else peer)['thread_id']
        for table in ('writes', 'checkpoints'):
            service.checkpoints.execute(f'DELETE FROM {table} WHERE thread_id=?', (lost_thread,))
        service.checkpoints.commit()
        logical_before = {
            name: {
                table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                for table in tables
            }
            for name, connection, tables in [
                ('cases.sqlite', service.db, ('cases', 'review_packets', 'review_submissions', 'audit_events')),
                ('checkpoints.sqlite', service.checkpoints, ('checkpoints', 'writes')),
            ]
        }
        before = _stored_files(root)
        with pytest.raises(ValueError):
            if operation == 'recover':
                service.recover(target['thread_id'])
            elif operation == 'review':
                service.review(target['thread_id'], form(target))
            else:
                service.start('Tavi Orinel', {'fixture': 'post-admission-loss'})
        assert retriever.calls == 0
        assert _stored_files(root) == before
    # Closing the fixture's own earlier mutation may flush WAL and remove its
    # sidecars. The rejected operation above must do neither; closure may only
    # change the physical representation of the already-committed fixture.
    for name, tables in logical_before.items():
        connection = sqlite3.connect((root / name).as_uri() + '?mode=ro', uri=True)
        try:
            for table, rows in tables.items():
                assert connection.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() == rows
        finally:
            connection.close()
