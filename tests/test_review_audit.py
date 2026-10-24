import json
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from urllib.parse import unquote, urlsplit
from uuid import uuid4
import pytest
from agent_support import FakeRetriever, form
from watchlist.agent.audit import append_event, verify_chain
from watchlist.agent.storage import ReviewService
from watchlist.agent import storage
from watchlist.agent.state import canonical, digest, packet


@pytest.mark.parametrize('tamper', ['payload','hash','missing','packet','submission','header','final_receipt'])
def test_detect_tampering(tmp_path,tamper):
    with ReviewService(tmp_path,FakeRetriever()) as s:
        r=s.start('Luma',{});done=s.review(r['thread_id'],form(r))
        if tamper=='payload':s.db.execute("UPDATE audit_events SET payload_json='{}' WHERE sequence=2")
        elif tamper=='hash':s.db.execute("UPDATE audit_events SET event_sha256='broken' WHERE sequence=2")
        elif tamper=='missing':s.db.execute('DELETE FROM audit_events WHERE sequence=2')
        elif tamper=='packet':s.db.execute("UPDATE review_packets SET packet_json='{}'")
        elif tamper=='submission':s.db.execute("UPDATE review_submissions SET sha256='broken'")
        elif tamper=='header':s.db.execute("UPDATE cases SET initial_json='{}'")
        else:
            s.graph.update_state(s.config(r['thread_id']),{'audit_head_sha256':'broken'})
        s.db.commit()
        with pytest.raises((ValueError,KeyError)):s.status(r['thread_id'])


def test_idempotent_events_conflicts_and_external_anchor(tmp_path):
    with ReviewService(tmp_path,FakeRetriever()) as s:
        r=s.start('Luma',{});aid=r['audit_id']
        with s.ledger.transaction():
            a=append_event(s.db,aid,'test',{'value':1})
            assert append_event(s.db,aid,'test',{'value':1})==a
            with pytest.raises(ValueError,match='conflicting'):append_event(s.db,aid,'test',{'value':2})
        anchor=verify_chain(s.db,aid)
        s.db.execute("DELETE FROM audit_events WHERE event_key='test'");s.db.commit()
        assert verify_chain(s.db,aid)['count']==2  # a chain alone cannot detect a missing tail
        with pytest.raises(ValueError,match='anchor'):verify_chain(s.db,aid,anchor)


def test_foreign_key_and_cross_case_submission_id(tmp_path):
    import sqlite3
    with ReviewService(tmp_path,FakeRetriever()) as s:
        a=s.start('Luma',{});b=s.start('Other',{})
        f=form(a);s.review(a['thread_id'],f)
        g=form(b);g['submission_id']=f['submission_id']
        with pytest.raises(ValueError,match='duplicate'):s.review(b['thread_id'],g)
        with pytest.raises(sqlite3.IntegrityError):
            with s.ledger.transaction():
                s.db.execute("INSERT INTO review_packets VALUES ('unknown',1,'{}','fake')")
        assert not s.status(b['thread_id'])['completed']


def _workspace_snapshot(root):
    """Record bytes, membership and metadata; reading may change access times."""
    if not root.exists():
        return None
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        metadata = path.lstat()
        value = (metadata.st_mode, metadata.st_dev, metadata.st_ino, metadata.st_nlink,
                 metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)
        if stat.S_ISREG(metadata.st_mode):
            value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
        result[str(path.relative_to(root))] = value
    return result


def _inspect_workspace(root, operation, thread_id='missing-fictional-thread'):
    """Exercise the dedicated reader without constructing a writable service."""
    with storage.ReviewReader(root) as service:
        if operation == 'status':
            return service.status(thread_id)
        return service.list_cases()


@pytest.mark.parametrize('operation', ['status', 'list'])
def test_read_only_inspection_does_not_create_a_missing_workspace(tmp_path, operation):
    root = tmp_path / 'missing-review'
    with pytest.raises((ValueError, OSError)):
        _inspect_workspace(root, operation)
    assert not root.exists()


@pytest.mark.parametrize('operation', ['status', 'list'])
def test_read_only_inspection_preserves_existing_bytes_and_permissions(tmp_path, operation):
    root = tmp_path / 'review'
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'read-only-inspection'})
    root.chmod(0o750)
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o640)
    before = _workspace_snapshot(root)
    result = _inspect_workspace(root, operation, pending['thread_id'])
    if operation == 'status':
        assert result['thread_id'] == pending['thread_id']
    else:
        assert result == [{'thread_id': pending['thread_id'], 'audit_id': pending['audit_id']}]
    assert _workspace_snapshot(root) == before


@pytest.mark.parametrize('operation', ['status', 'list'])
@pytest.mark.parametrize('missing', ['cases.sqlite', 'checkpoints.sqlite', 'writer.lock'])
def test_read_only_inspection_rejects_missing_store_members_before_opening_sqlite(tmp_path, monkeypatch, operation, missing):
    root = tmp_path / 'review'
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'missing-member'})
    (root / missing).unlink()
    root.chmod(0o750)
    before = _workspace_snapshot(root)

    def forbidden(*args, **kwargs):
        pytest.fail('Incomplete inspection workspace reached SQLite')

    with monkeypatch.context() as guarded:
        guarded.setattr(sqlite3, 'connect', forbidden)
        with pytest.raises((ValueError, OSError)):
            _inspect_workspace(root, operation, pending['thread_id'])
    assert _workspace_snapshot(root) == before


def test_reader_never_opens_original_sqlite_or_builds_runtime_resources(tmp_path, monkeypatch):
    root = (tmp_path / 'review').resolve()
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'no-runtime-inspection'})
    before = _workspace_snapshot(root)
    actual_connect = sqlite3.connect
    copied_database_paths = []

    def copied_databases_only(database, *args, **kwargs):
        raw = os.fspath(database)
        if raw != ':memory:':
            path = Path(unquote(urlsplit(raw).path) if raw.startswith('file:') else raw).resolve()
            assert not path.is_relative_to(root), 'Inspection opened original SQLite storage'
            copied_database_paths.append(path)
        return actual_connect(database, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail('Inspection initialized a ledger/saver, graph, retriever or model')

    from langgraph.checkpoint.sqlite import SqliteSaver
    from watchlist.agent import graph
    from watchlist.agent.retrieval import E5Retriever
    with monkeypatch.context() as guarded:
        guarded.setattr(sqlite3, 'connect', copied_databases_only)
        guarded.setattr(storage.Ledger, '__init__', forbidden)
        guarded.setattr(SqliteSaver, 'setup', forbidden)
        guarded.setattr(graph, 'build_graph', forbidden)
        guarded.setattr(FakeRetriever, 'search', forbidden)
        guarded.setattr(E5Retriever, '__init__', forbidden)
        guarded.setattr(E5Retriever, 'search', forbidden)
        with storage.ReviewReader(root) as reader:
            assert reader.status(pending['thread_id'])['state'] == pending['state']
            assert reader.list_cases() == [{'thread_id': pending['thread_id'], 'audit_id': pending['audit_id']}]
    assert copied_database_paths, 'The copied stores must undergo real SQLite validation'
    assert all(not path.exists() for path in copied_database_paths), 'Inspection scratch databases were retained'
    assert _workspace_snapshot(root) == before


def test_reader_sees_committed_wal_data_without_touching_original_sidecars(tmp_path):
    root = (tmp_path / 'review').resolve()
    with ReviewService(root, FakeRetriever()) as service:
        first = service.start('Luma Vesper', {'fixture': 'before-wal'})
    keepers = [sqlite3.connect(root / name) for name in ('cases.sqlite', 'checkpoints.sqlite')]
    try:
        for connection in keepers:
            assert connection.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
            connection.execute('PRAGMA wal_autocheckpoint=0')
            # Pin the original snapshot so the writer's close cannot checkpoint
            # newly committed frames into the original main database.
            connection.execute('BEGIN')
            connection.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
        main_bytes = (root / 'cases.sqlite').read_bytes()
        with ReviewService(root, FakeRetriever()) as service:
            committed = service.start('Tavi Orinel', {'fixture': 'committed-in-wal'})
        assert (root / 'cases.sqlite').read_bytes() == main_bytes
        assert (root / 'cases.sqlite-wal').stat().st_size > 0
        assert (root / 'checkpoints.sqlite-wal').stat().st_size > 0
        # This fixture-only probe deliberately ignores WAL and proves the new
        # committed case is absent from the main database's bytes alone.
        main_only = sqlite3.connect((root / 'cases.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            assert committed['thread_id'] not in {row[0] for row in main_only.execute('SELECT thread_id FROM cases')}
        finally:
            main_only.close()
        root.chmod(0o750)
        for path in root.iterdir():
            if path.is_file():
                path.chmod(0o640)
        before = _workspace_snapshot(root)
        with storage.ReviewReader(root) as reader:
            status = reader.status(committed['thread_id'])
            cases = reader.list_cases()
        assert status['state'] == committed['state']
        assert status['pending_interrupt'] is True
        assert {case['thread_id'] for case in cases} == {first['thread_id'], committed['thread_id']}
        assert _workspace_snapshot(root) == before
    finally:
        for connection in keepers:
            connection.close()


@pytest.mark.parametrize('user_version', [0, 1, 2, 99])
def test_ledger_ownership_initialize_rejects_unrelated_database_unchanged(tmp_path, user_version):
    root = tmp_path / 'unrelated-store'
    root.mkdir(mode=0o750)
    path = root / 'fictional-notes.sqlite'
    connection = sqlite3.connect(path)
    try:
        connection.execute('CREATE TABLE fictional_notes (note TEXT NOT NULL)')
        connection.execute("INSERT INTO fictional_notes VALUES ('Luma Vesper fixture only')")
        connection.execute(f'PRAGMA user_version={user_version}')
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o640)
    before = _workspace_snapshot(root)
    failure = None
    connection = sqlite3.connect(path)
    try:
        try:
            storage.Ledger(connection, initialize=True)
        except ValueError as exc:
            failure = exc
        observed_version = connection.execute('PRAGMA user_version').fetchone()[0]
    finally:
        connection.close()
    assert _workspace_snapshot(root) == before, 'Rejected initialization changed unrelated storage'
    assert observed_version == user_version
    assert failure is not None, 'Unrelated nonempty storage was accepted for initialization'


@pytest.mark.parametrize('application_id', [0x12345678, 0x50575231, 0x50574331])
def test_ledger_ownership_initialize_rejects_empty_claimed_database_unchanged(tmp_path, application_id):
    root = tmp_path / 'claimed-store'
    root.mkdir(mode=0o750)
    path = root / 'claimed.sqlite'
    connection = sqlite3.connect(path)
    try:
        connection.execute(f'PRAGMA application_id={application_id}')
        connection.commit()
    finally:
        connection.close()
    path.chmod(0o640)
    before = _workspace_snapshot(root)
    failure = None
    connection = sqlite3.connect(path)
    try:
        try:
            storage.Ledger(connection, initialize=True)
        except ValueError as exc:
            failure = exc
        identity = tuple(connection.execute(f'PRAGMA {name}').fetchone()[0]
                         for name in ('application_id', 'user_version'))
    finally:
        connection.close()
    assert _workspace_snapshot(root) == before, 'Initialization rewrote a claimed database'
    assert identity == (application_id, 0)
    assert failure is not None, 'An existing application ID was treated as an empty new database'


class _AcceptedReviewStop(BaseException):
    """Leave a durable accepted submission without exercising error logging."""


def _audit_workspace(tmp_path, *, completed=False):
    """Create two fictional cases; only the first receives a human annotation."""
    root = (tmp_path / 'review').resolve()

    def stop(point):
        if point == 'after_submission' and not completed:
            raise _AcceptedReviewStop()

    with ReviewService(root, FakeRetriever(), stop) as service:
        pending = service.start('Luma Vesper', {'fixture': 'audit-reconciliation'})
        peer = service.start('Tavi Orinel', {'fixture': 'other-fictional-case'})
        review = form(pending)
        if completed:
            final = service.review(pending['thread_id'], review)
        else:
            with pytest.raises(_AcceptedReviewStop):
                service.review(pending['thread_id'], review)
            final = None
        accepted = service.ledger.submission(pending['audit_id'])
    return {'root': root, 'pending': pending, 'peer': peer, 'form': review,
            'accepted': accepted, 'final': final}


def _replace_audit_events(connection, audit_id, events):
    """Rebuild a valid hash chain so tests isolate protocol relationships."""
    connection.execute('DELETE FROM audit_events WHERE audit_id=?', (audit_id,))
    for key, payload in events:
        append_event(connection, audit_id, key, payload)
    connection.commit()
    assert verify_chain(connection, audit_id)['count'] == len(events)


def _saved_audit_events(connection, audit_id):
    return [(row['event_key'], json.loads(row['payload_json'])) for row in connection.execute(
        'SELECT event_key, payload_json FROM audit_events WHERE audit_id=? ORDER BY sequence',
        (audit_id,),
    )]


def _assert_invalid_store_stops_on_copies(root, monkeypatch):
    """Invalid established stores cannot reach original SQLite or any runtime."""
    before = _workspace_snapshot(root)
    actual_connect = sqlite3.connect
    copied_paths = []

    def copies_only(database, *args, **kwargs):
        raw = os.fspath(database)
        if raw != ':memory:':
            path = Path(unquote(urlsplit(raw).path) if raw.startswith('file:') else raw).resolve()
            assert not path.is_relative_to(root), 'Invalid store reached original SQLite before reconciliation'
            copied_paths.append(path)
        return actual_connect(database, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail('Invalid store initialized runtime or appended an attempt_error')

    from langgraph.checkpoint.sqlite import SqliteSaver
    from watchlist.agent import graph
    with monkeypatch.context() as guarded:
        guarded.setattr(sqlite3, 'connect', copies_only)
        guarded.setattr(storage.Ledger, '__init__', forbidden)
        guarded.setattr(storage.Ledger, 'attempt_error', forbidden)
        guarded.setattr(SqliteSaver, 'setup', forbidden)
        guarded.setattr(graph, 'build_graph', forbidden)
        guarded.setattr(FakeRetriever, 'search', forbidden)
        for opener in (storage.ReviewReader(root),
                       ReviewService(root, FakeRetriever(fail=True), mode='existing')):
            with pytest.raises(ValueError):
                with opener:
                    pytest.fail('Inconsistent established store was accepted')
            assert _workspace_snapshot(root) == before, 'Rejected store changed original bytes or metadata'
    assert copied_paths, 'Reconciliation must examine real private SQLite copies'
    assert all(not path.exists() for path in copied_paths), 'Rejected store retained scratch databases'
    assert _workspace_snapshot(root) == before, 'Rejected store changed original bytes or metadata'


@pytest.mark.parametrize('checkpoint_target', ['missing', 'foreign_case', 'before_review'])
def test_accepted_submission_requires_its_own_saved_pending_checkpoint(tmp_path, monkeypatch, checkpoint_target):
    saved = _audit_workspace(tmp_path)
    pending = saved['pending']
    if checkpoint_target == 'foreign_case':
        target = saved['peer']['checkpoint_id']
    elif checkpoint_target == 'before_review':
        with sqlite3.connect(saved['root'] / 'checkpoints.sqlite') as checkpoints:
            target = checkpoints.execute(
                'SELECT checkpoint_id FROM checkpoints WHERE thread_id=? ORDER BY checkpoint_id LIMIT 1',
                (pending['thread_id'],),
            ).fetchone()[0]
    else:
        target = str(uuid4())
    replacement = {**saved['accepted'], 'expected_checkpoint_id': target}
    with sqlite3.connect(saved['root'] / 'cases.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('UPDATE review_submissions SET payload_json=?, sha256=? WHERE audit_id=?',
                           (canonical(replacement), digest(replacement), pending['audit_id']))
        events = _saved_audit_events(connection, pending['audit_id'])
        events = [(key, {'submission': replacement} if key == 'review_submitted' else value)
                  for key, value in events]
        _replace_audit_events(connection, pending['audit_id'], events)
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


@pytest.mark.parametrize('mutation', ['submission_row_id', 'case_thread', 'case_parent',
                                    'missing_submission_event', 'extra_semantic_event', 'event_order'])
def test_coherent_hashes_do_not_hide_audit_or_case_identity_conflicts(tmp_path, monkeypatch, mutation):
    saved = _audit_workspace(tmp_path)
    pending, peer = saved['pending'], saved['peer']
    with sqlite3.connect(saved['root'] / 'cases.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        if mutation == 'submission_row_id':
            connection.execute('UPDATE review_submissions SET submission_id=? WHERE audit_id=?',
                               (str(uuid4()), pending['audit_id']))
        elif mutation == 'case_thread':
            connection.execute('UPDATE cases SET thread_id=? WHERE audit_id=?',
                               (str(uuid4()), pending['audit_id']))
        elif mutation == 'case_parent':
            connection.execute('UPDATE cases SET parent_audit_id=? WHERE audit_id=?',
                               (peer['audit_id'], pending['audit_id']))
        else:
            events = _saved_audit_events(connection, pending['audit_id'])
            if mutation == 'missing_submission_event':
                events = [(key, value) for key, value in events if key != 'review_submitted']
            elif mutation == 'extra_semantic_event':
                events.append(('unrecognized_case_transition', {'fixture': True}))
            else:
                events[1], events[2] = events[2], events[1]
            _replace_audit_events(connection, pending['audit_id'], events)
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        verify_chain(connection, pending['audit_id'])
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


@pytest.mark.parametrize('orphan', ['checkpoint_thread', 'checkpoint_other_case', 'checkpoint_namespace',
                                  'write_checkpoint', 'write_thread', 'write_namespace'])
def test_unowned_checkpoint_rows_or_writes_fail_before_original_access(tmp_path, monkeypatch, orphan):
    saved = _audit_workspace(tmp_path)
    with sqlite3.connect(saved['root'] / 'checkpoints.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        table = 'checkpoints' if orphan.startswith('checkpoint_') else 'writes'
        row = dict(connection.execute(f'SELECT * FROM {table} LIMIT 1').fetchone())
        if orphan.endswith('_namespace'):
            row['checkpoint_ns'] = 'unapproved-fictional-namespace'
        elif orphan == 'checkpoint_other_case':
            original = row['thread_id']
            row['thread_id'] = next(case['thread_id'] for case in (saved['pending'], saved['peer'])
                                    if case['thread_id'] != original)
        else:
            row['checkpoint_id' if orphan == 'write_checkpoint' else 'thread_id'] = str(uuid4())
        placeholders = ','.join('?' for _ in row)
        connection.execute(f'INSERT INTO {table} VALUES ({placeholders})', tuple(row.values()))
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


def _replace_checkpoint_field(root, checkpoint_id, field, value):
    """Alter only our trusted fictional checkpoint, preserving its encoded type."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    serializer = JsonPlusSerializer()
    with sqlite3.connect(root / 'checkpoints.sqlite') as connection:
        saved_type, saved_blob = connection.execute(
            'SELECT type, checkpoint FROM checkpoints WHERE checkpoint_id=?', (checkpoint_id,),
        ).fetchone()
        checkpoint = serializer.loads_typed((saved_type, saved_blob))
        checkpoint['channel_values'][field] = value
        encoded_type, encoded = serializer.dumps_typed(checkpoint)
        connection.execute('UPDATE checkpoints SET type=?, checkpoint=? WHERE checkpoint_id=?',
                           (encoded_type, encoded, checkpoint_id))
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('field', ['audit_head_sha256', 'audit_event_id', 'reviewer_decision',
                                 'evidence_sha256', 'thread_id', 'parent_audit_id'])
def test_completed_checkpoint_receipt_and_identity_must_match_durable_ledger(tmp_path, monkeypatch, field):
    saved = _audit_workspace(tmp_path, completed=True)
    changes = {
        'audit_head_sha256': 'f' * 64,
        'audit_event_id': saved['pending']['audit_id'] + ':999',
        'reviewer_decision': {**saved['accepted'], 'reason': 'Altered fictional review note'},
        'evidence_sha256': 'f' * 64,
        'thread_id': saved['peer']['thread_id'],
        'parent_audit_id': saved['peer']['audit_id'],
    }
    _replace_checkpoint_field(saved['root'], saved['final']['checkpoint_id'], field, changes[field])
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


@pytest.mark.parametrize('missing', ['final_event', 'submission', 'peer_packet'])
def test_completed_checkpoint_cannot_bless_missing_ledger_receipts(tmp_path, monkeypatch, missing):
    saved = _audit_workspace(tmp_path, completed=True)
    with sqlite3.connect(saved['root'] / 'cases.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        if missing == 'final_event':
            connection.execute("DELETE FROM audit_events WHERE audit_id=? AND event_key='case_finalized'",
                               (saved['pending']['audit_id'],))
            assert verify_chain(connection, saved['pending']['audit_id'])['count'] == 3
        elif missing == 'submission':
            connection.execute('DELETE FROM review_submissions WHERE audit_id=?',
                               (saved['pending']['audit_id'],))
        else:
            connection.execute('DELETE FROM review_packets WHERE audit_id=?', (saved['peer']['audit_id'],))
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


def test_internal_accepted_review_recovery_is_once_and_external_duplicate_stays_rejected(tmp_path):
    saved = _audit_workspace(tmp_path)
    fake = FakeRetriever(fail=True)
    with ReviewService(saved['root'], fake, mode='existing') as service:
        pending = service.status(saved['pending']['thread_id'])
        assert pending['pending_interrupt'] is True and pending['completed'] is False
        # This valid writer may create its normal read-side WAL/SHM handles.
        # Freeze the boundary after inspection, before either rejected form.
        before = _workspace_snapshot(saved['root'])
        with pytest.raises(ValueError, match='duplicate review'):
            service.review(saved['pending']['thread_id'], saved['form'])
        assert _workspace_snapshot(saved['root']) == before
        done = service.recover(saved['pending']['thread_id'])
        assert done['completed'] is True
        assert done['state']['reviewer_decision'] == saved['accepted']
        assert done['state']['candidates'] == saved['pending']['state']['candidates']
        assert done['state']['evidence_sha256'] == saved['pending']['state']['evidence_sha256']
        before = _workspace_snapshot(saved['root'])
        assert service.recover(saved['pending']['thread_id']) == done
        with pytest.raises(ValueError, match='duplicate review'):
            service.review(saved['pending']['thread_id'], saved['form'])
        assert _workspace_snapshot(saved['root']) == before
        assert service.db.execute('SELECT COUNT(*) FROM review_submissions WHERE audit_id=?',
                                  (saved['pending']['audit_id'],)).fetchone()[0] == 1
        events = _saved_audit_events(service.db, saved['pending']['audit_id'])
        assert [key for key, _ in events] == ['request_created', 'suggestions_ready',
                                             'review_submitted', 'case_finalized']
        assert done['audit']['count'] == 4
    assert fake.calls == 0


@pytest.mark.parametrize('conflict', ['changed_accepted_note', 'unaccepted_peer'])
def test_saved_resume_command_requires_the_exact_accepted_review(tmp_path, monkeypatch, conflict):
    """A validly encoded command cannot substitute another human decision."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    saved = _audit_workspace(tmp_path)
    pending = saved['pending'] if conflict == 'changed_accepted_note' else saved['peer']
    submitted = {**saved['accepted'], 'reason': 'A different fictional opinion'}
    encoded_type, encoded = JsonPlusSerializer().dumps_typed(submitted)
    with sqlite3.connect(saved['root'] / 'checkpoints.sqlite') as connection:
        # This is the pinned saver's global resume control row. It is valid SQL
        # and MessagePack; only its relationship to the accepted review is bad.
        connection.execute(
            'INSERT INTO writes VALUES (?,?,?,?,?,?,?,?,?)',
            (pending['thread_id'], '', pending['checkpoint_id'],
             '00000000-0000-0000-0000-000000000000', '', -4,
             '__resume__', encoded_type, encoded),
        )
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


@pytest.mark.parametrize('completed', [False, True], ids=['accepted', 'completed'])
def test_accepted_review_requires_its_saved_interrupt_even_after_completion(tmp_path, monkeypatch, completed):
    """A review must retain evidence that its exact checkpoint requested it."""
    saved = _audit_workspace(tmp_path, completed=completed)
    with sqlite3.connect(saved['root'] / 'checkpoints.sqlite') as connection:
        deleted = connection.execute(
            "DELETE FROM writes WHERE thread_id=? AND checkpoint_id=? "
            "AND channel IN ('__interrupt__', '__resume__')",
            (saved['pending']['thread_id'], saved['accepted']['expected_checkpoint_id']),
        ).rowcount
        assert deleted >= 1
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    _assert_invalid_store_stops_on_copies(saved['root'], monkeypatch)


@pytest.mark.parametrize('stage', ['during_explanation', 'after_final_audit'])
def test_operational_error_events_do_not_replace_or_repeat_the_final_receipt(tmp_path, stage):
    """Recover a caught runtime failure as well as an abruptly killed process."""
    root = (tmp_path / 'review').resolve()

    def fail(point):
        if point == stage:
            raise RuntimeError('Fictional interrupted review operation')

    with ReviewService(root, FakeRetriever(), fail) as service:
        pending = service.start('Luma Vesper', {'fixture': 'logged-recovery-error'})
        with pytest.raises(RuntimeError, match='Fictional interrupted review operation'):
            service.review(pending['thread_id'], form(pending))
        accepted = service.ledger.submission(pending['audit_id'])
        original_rows = [dict(row) for row in service.db.execute(
            'SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence',
            (pending['audit_id'],),
        )]
        errors = [row for row in original_rows if row['event_key'].startswith('attempt:')]
        assert errors and all(json.loads(row['payload_json'])['error_type'] == 'RuntimeError'
                              for row in errors)
        saved_final = next((row for row in original_rows if row['event_key'] == 'case_finalized'), None)
        assert (saved_final is not None) == (stage == 'after_final_audit')
        if saved_final is not None:
            assert all(row['sequence'] > saved_final['sequence'] for row in errors)

    retriever = FakeRetriever(fail=True)
    with ReviewService(root, retriever, mode='existing') as service:
        done = service.recover(pending['thread_id'])
        assert done['completed'] is True
        assert done['state']['reviewer_decision'] == accepted
        assert done['state']['evidence_sha256'] == pending['state']['evidence_sha256']
        rows = [dict(row) for row in service.db.execute(
            'SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence',
            (pending['audit_id'],),
        )]
        assert rows[:len(original_rows)] == original_rows
        assert [row['event_key'] for row in rows if not row['event_key'].startswith('attempt:')] == [
            'request_created', 'suggestions_ready', 'review_submitted', 'case_finalized',
        ]
        final = next(row for row in rows if row['event_key'] == 'case_finalized')
        if saved_final is not None:
            assert final == saved_final
        assert done['state']['audit_event_id'] == f"{pending['audit_id']}:{final['sequence']}"
        assert done['state']['audit_head_sha256'] == final['event_sha256']
        assert done['audit'] == verify_chain(service.db, pending['audit_id'])
        before = _workspace_snapshot(root)
        assert service.recover(pending['thread_id']) == done
        assert _workspace_snapshot(root) == before
    assert retriever.calls == 0


def _saved_task_write_batch(tmp_path, step=1):
    """Retain a real output batch at the boundary before its next checkpoint.

    The pinned saver commits a node's writes and its following checkpoint
    independently. Trim a disposable, completed review to the former boundary;
    do not invent its task IDs, state, serialized values or schedule metadata.
    """
    root = (tmp_path / 'review').resolve()
    with ReviewService(root, FakeRetriever()) as service:
        pending = service.start('Luma Vesper', {'fixture': 'pending-retrieval-write-batch'})
        completed = service.review(pending['thread_id'], form(pending))
    with sqlite3.connect(root / 'checkpoints.sqlite') as connection:
        cutoff = next(row[0] for row in connection.execute(
            'SELECT checkpoint_id, metadata FROM checkpoints WHERE thread_id=?',
            (pending['thread_id'],),
        ) if json.loads(row[1])['step'] == step)
        for table in ('writes', 'checkpoints'):
            connection.execute(f'DELETE FROM {table} WHERE thread_id=? AND checkpoint_id>?',
                               (pending['thread_id'], cutoff))
        rows = connection.execute(
            'SELECT task_id, channel FROM writes WHERE thread_id=? AND checkpoint_id=?',
            (pending['thread_id'], cutoff),
        ).fetchall()
        assert rows
        assert len({row[0] for row in rows if row[0] != '00000000-0000-0000-0000-000000000000'}) == 1
        if step == 1:
            assert {row[1] for row in rows} == {
                'candidates', 'evidence', 'retrieval', 'branch:to:format_candidates',
            }
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with sqlite3.connect(root / 'cases.sqlite') as connection:
        if step < 4:
            connection.execute('DELETE FROM review_submissions')
            connection.execute("DELETE FROM audit_events WHERE event_key='review_submitted'")
        if step < 3:
            connection.execute('DELETE FROM review_packets')
            connection.execute("DELETE FROM audit_events WHERE event_key='suggestions_ready'")
        if step < 6:
            connection.execute("DELETE FROM audit_events WHERE event_key='case_finalized'")
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    return root, pending, completed, cutoff


@pytest.mark.parametrize('step,retrieval_calls', [
    (-1, 1), (0, 1), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0),
], ids=['input', 'normalize', 'retrieve', 'format', 'prepare', 'human_review', 'explain', 'audit'])
def test_complete_saved_task_write_batch_recovers_without_repeating_work(tmp_path, step, retrieval_calls):
    root, original, completed, cutoff = _saved_task_write_batch(tmp_path, step)
    fake = FakeRetriever(fail=retrieval_calls == 0)
    with ReviewService(root, fake, mode='existing') as service:
        saved_rows = service.checkpoints.execute(
            'SELECT * FROM writes WHERE checkpoint_id=? ORDER BY task_id,idx', (cutoff,),
        ).fetchall()
        recovered = service.recover(original['thread_id'])
        assert recovered['completed'] is (step >= 4)
        if not recovered['completed']:
            assert recovered['pending_interrupt'] is True
        for field in ('candidates', 'evidence', 'retrieval', 'evidence_sha256'):
            assert recovered['state'][field] == original['state'][field]
        assert service.checkpoints.execute(
            'SELECT * FROM writes WHERE checkpoint_id=? ORDER BY task_id,idx', (cutoff,),
        ).fetchall() == saved_rows
        if recovered['completed']:
            assert recovered['state']['reviewer_decision'] == completed['state']['reviewer_decision']
            done = recovered
        else:
            done = service.review(recovered['thread_id'], form(recovered))
        assert done['completed'] is True
        assert done['audit']['count'] == 4
    assert fake.calls == retrieval_calls


def test_changed_retrieval_write_task_identity_fails_before_original_access(tmp_path, monkeypatch):
    root, pending, _, cutoff = _saved_task_write_batch(tmp_path)
    with sqlite3.connect(root / 'checkpoints.sqlite') as connection:
        connection.execute('UPDATE writes SET task_id=? WHERE thread_id=? AND checkpoint_id=?',
                           (str(uuid4()), pending['thread_id'], cutoff))
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    # Archive inspection intentionally treats task IDs as opaque. Execution
    # needs the additional live binding or the runtime ignores this saved batch.
    from watchlist.review.compat_v1 import read_v1
    with storage._copied_databases(root) as (project, normalized):
        _, details = read_v1(project, 'review', normalized)
        assert details[pending['audit_id']]['checkpoint']['next'] == ['retrieve_e5']
    _assert_invalid_store_stops_on_copies(root, monkeypatch)


def test_first_application_checkpoint_cannot_claim_later_packet_progress(tmp_path, monkeypatch):
    """An absent input write batch cannot make early scheduling bless a packet."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    root, pending, _, cutoff = _saved_task_write_batch(tmp_path, step=0)
    saved_packet = packet(pending['state'])
    with sqlite3.connect(root / 'cases.sqlite') as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('INSERT INTO review_packets VALUES (?,1,?,?)',
                           (pending['audit_id'], canonical(saved_packet), pending['state']['evidence_sha256']))
        append_event(connection, pending['audit_id'], 'suggestions_ready',
                     {'packet_sha256': pending['state']['evidence_sha256']})
        connection.commit()
        assert verify_chain(connection, pending['audit_id'])['count'] == 2
    serializer = JsonPlusSerializer()
    with sqlite3.connect(root / 'checkpoints.sqlite') as connection:
        saved_type, saved_blob = connection.execute(
            'SELECT type,checkpoint FROM checkpoints WHERE checkpoint_id=?', (cutoff,),
        ).fetchone()
        checkpoint = serializer.loads_typed((saved_type, saved_blob))
        checkpoint['channel_values'].update(saved_packet)
        checkpoint['channel_values']['evidence_sha256'] = pending['state']['evidence_sha256']
        encoded_type, encoded = serializer.dumps_typed(checkpoint)
        connection.execute('UPDATE checkpoints SET type=?,checkpoint=? WHERE checkpoint_id=?',
                           (encoded_type, encoded, cutoff))
        connection.execute('DELETE FROM writes')
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    from watchlist.review.compat_v1 import read_v1
    with storage._copied_databases(root) as (project, normalized):
        _, details = read_v1(project, 'review', normalized)
        assert details[pending['audit_id']]['checkpoint']['next'] == ['normalize']
    _assert_invalid_store_stops_on_copies(root, monkeypatch)


@pytest.mark.parametrize('field,replacement', [
    ('audit_event_id', 'unrelated-event:999'),
    ('audit_head_sha256', 'f' * 64),
    ('audit_status', 'pending'),
])
def test_saved_final_receipt_writes_must_match_the_committed_event(tmp_path, monkeypatch, field, replacement):
    """A saved audit task result is checked before it becomes a checkpoint."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    root, pending, _, cutoff = _saved_task_write_batch(tmp_path, step=6)
    encoded_type, encoded = JsonPlusSerializer().dumps_typed(replacement)
    with sqlite3.connect(root / 'checkpoints.sqlite') as connection:
        changed = connection.execute(
            'UPDATE writes SET type=?,value=? WHERE thread_id=? AND checkpoint_id=? AND channel=?',
            (encoded_type, encoded, pending['thread_id'], cutoff, field),
        ).rowcount
        assert changed == 1
        connection.commit()
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    _assert_invalid_store_stops_on_copies(root, monkeypatch)


def test_failure_before_first_checkpoint_keeps_the_untouched_request_recoverable(tmp_path, monkeypatch):
    """Logging an executor startup failure must not fabricate durable progress."""
    root = (tmp_path / 'review').resolve()
    fake = FakeRetriever()
    with ReviewService(root, fake) as service:
        def unavailable(*args, **kwargs):
            raise RuntimeError('Fictional executor failure before its first checkpoint')

        with monkeypatch.context() as broken_executor:
            broken_executor.setattr(service.graph, 'invoke', unavailable)
            with pytest.raises(RuntimeError, match='before its first checkpoint'):
                service.start('Luma Vesper', {'fixture': 'initial-executor-error'})
        thread_id, audit_id = service.db.execute('SELECT thread_id,audit_id FROM cases').fetchone()
        assert service.checkpoints.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0] == 0
        assert [key for key, _ in _saved_audit_events(service.db, audit_id)] == ['request_created']
        assert fake.calls == 0
        pending = service.recover(thread_id)
        assert pending['pending_interrupt'] is True
        assert fake.calls == 1
        done = service.review(thread_id, form(pending))
        assert done['completed'] is True
        assert done['audit']['count'] == 4
        assert fake.calls == 1
