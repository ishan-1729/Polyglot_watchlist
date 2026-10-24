"""Single-user case ledger, OS writer lock, and checkpoint reconciliation."""

from __future__ import annotations

from contextlib import ExitStack, closing, contextmanager, nullcontext
import fcntl
from functools import lru_cache
import getpass
import hashlib
from importlib.metadata import version
import json
import math
from numbers import Real
import os
from pathlib import Path
import re
import sqlite3
import stat
from tempfile import TemporaryDirectory
import time
from typing import Any, Literal
from uuid import UUID, uuid4

from watchlist.agent.audit import append_event, verify_chain, now
from watchlist.agent.state import (SCHEMA, WORKFLOW, ReviewState, ReviewerDecision, canonical, digest, packet,
                                    validate_packet, validate_review, validate_review_form,
                                    validate_start_inputs, workflow_hash)
from watchlist.normalize import normalize_name


_DATABASE_NAMES = ('cases.sqlite', 'checkpoints.sqlite')
_SIDECARS = ('-wal', '-shm', '-journal')
_LEDGER_APPLICATION_ID = 0x50575231  # PWR1: review ledger, schema v1.
_CHECKPOINT_APPLICATION_ID = 0x50574331  # PWC1: pinned checkpoint schema.
_SCHEMA_CHECKED = object()

# Explicit v1 adapters: do not derive historical ownership from mutable setup
# files or call a checkpoint saver's migration code to recognize an old store.
# Both the legacy zero-ID stores and newly tagged stores use these exact tables.
_LEDGER_SCHEMA_V1 = '''
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
'''
_CHECKPOINT_SCHEMA_V1 = '''
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
'''
_OWNED_SCHEMAS = {
    'cases.sqlite': (_LEDGER_APPLICATION_ID, 1, _LEDGER_SCHEMA_V1),
    'checkpoints.sqlite': (_CHECKPOINT_APPLICATION_ID, 0, _CHECKPOINT_SCHEMA_V1),
}
_SQL_TOKEN = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|\[[^\]]*\]|\w+|[^\s]")


def _checked_path(path: Path, *, allow_missing: bool = False) -> Path:
    """Reject links before resolving, including links in ancestor directories."""
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('workspace path must not contain parent traversal')
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                return path
            raise ValueError('existing review workspace is missing') from None
        if stat.S_ISLNK(mode):
            raise ValueError('review workspace paths must not contain symlinks')
        if component != path and not stat.S_ISDIR(mode):
            raise ValueError('workspace parent must be a directory')
    return path


def _file_state(path: Path) -> tuple[int, ...]:
    """Record source identity and metadata without modifying access permissions."""
    metadata = _checked_path(path).lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError('review workspace files must be regular files')
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
            metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)


def _workspace_files(root: Path) -> dict[str, tuple[int, ...]]:
    """Require an established pair and lock; inventory its current journal files."""
    root = _checked_path(root)
    if not root.is_dir():
        raise ValueError('existing review workspace must be a directory')
    names = ['writer.lock', *_DATABASE_NAMES]
    names += [name + suffix for name in _DATABASE_NAMES for suffix in _SIDECARS
              if os.path.lexists(root / (name + suffix))]
    files = {name: _file_state(root / name) for name in names}
    if sum(value[4] for value in files.values()) > 100_000_000:
        raise ValueError('review workspace exceeds 100 MB pilot budget')
    return files


def _file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _validated_lock_timeout(value: object) -> float:
    """Accept finite nonnegative real seconds before touching the workspace."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError('lock_timeout must be finite nonnegative seconds')
    try:
        timeout = float(value)
    except (OverflowError, ValueError):
        raise ValueError('lock_timeout must be finite nonnegative seconds') from None
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError('lock_timeout must be finite nonnegative seconds')
    return timeout


def _acquire_lock(lock, *, shared: bool, timeout: float) -> None:
    """Wait at most the configured deadline; zero still tries once immediately."""
    deadline = time.monotonic() + timeout
    operation = (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB
    while True:
        try:
            fcntl.flock(lock, operation)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('review workspace is busy; lock wait timed out') from None
            time.sleep(min(0.05, remaining))


@contextmanager
def _existing_lock(root: Path, *, shared: bool = False, lock_timeout: float = 5.0):
    """Acquire the OS lock before copies or SQLite, through a read-only handle."""
    _workspace_files(root)
    with (root / 'writer.lock').open('rb') as lock:
        _acquire_lock(lock, shared=shared, timeout=lock_timeout)
        try:
            expected = _workspace_files(root)['writer.lock']
            actual = os.fstat(lock.fileno())
            if (actual.st_dev, actual.st_ino) != expected[:2]:
                raise ValueError('workspace lock changed while opening')
            yield lock
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _sql_tokens(statement: str | None) -> tuple[str, ...] | None:
    """Ignore SQL formatting/case while preserving quoted names and literals."""
    if statement is None:
        return None
    return tuple(token if token[0] in "'\"`[" else token.lower()
                 for token in _SQL_TOKEN.findall(statement))


def _schema_signature(db: sqlite3.Connection) -> tuple[Any, ...]:
    """Describe all main-schema objects and their columns, keys and indexes.

    SQL tokens retain constraints not exposed by PRAGMA, including CHECK clauses,
    collations and deferred foreign keys. PRAGMA adds complete column and index
    details, including generated columns, expression keys and partial indexes.
    Internal autoindexes are included; additional objects are never ignored.
    """
    objects = tuple((kind, name, table, _sql_tokens(sql)) for kind, name, table, sql in
                    db.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_master ORDER BY type,name'))
    tables = []
    for kind, name, _, _ in objects:
        if kind != 'table':
            continue
        columns = tuple(tuple(row) for row in db.execute("SELECT * FROM pragma_table_xinfo(?, 'main') ORDER BY cid", (name,)))
        foreign_keys = tuple(tuple(row) for row in db.execute("SELECT * FROM pragma_foreign_key_list(?, 'main') ORDER BY id,seq", (name,)))
        indexes = []
        for row in db.execute("SELECT * FROM pragma_index_list(?, 'main') ORDER BY name", (name,)):
            index = tuple(row)
            keys = tuple(tuple(key) for key in db.execute("SELECT * FROM pragma_index_xinfo(?, 'main') ORDER BY seqno", (index[1],)))
            indexes.append((index, keys))
        tables.append((name, columns, foreign_keys, tuple(indexes)))
    return objects, tuple(tables)


@lru_cache(maxsize=2)
def _expected_schema(name: str) -> tuple[Any, ...]:
    """Compile only a fixed, trusted v1 contract in an isolated memory store."""
    with closing(sqlite3.connect(':memory:')) as reference:
        reference.executescript(_OWNED_SCHEMAS[name][2])
        return _schema_signature(reference)


def _require_owned_schema(db: sqlite3.Connection, name: str) -> None:
    """Accept a tagged store or the exact legacy zero-ID schema without writes."""
    application_id, user_version, _ = _OWNED_SCHEMAS[name]
    try:
        identity = db.execute('PRAGMA main.application_id').fetchone()[0]
        revision = db.execute('PRAGMA main.user_version').fetchone()[0]
        if identity not in (0, application_id) or revision != user_version:
            raise ValueError(f'unrecognized review database identity/version: {name}')
        if _schema_signature(db) != _expected_schema(name):
            raise ValueError(f'unrecognized review database schema: {name}')
    except sqlite3.DatabaseError as exc:
        raise ValueError(f'unrecognized review database schema: {name}') from exc


def _require_owned_pair(root: Path) -> None:
    """Recognize both normalized copies before accessing original stores."""
    for name in _DATABASE_NAMES:
        with closing(sqlite3.connect((root / name).as_uri() + '?mode=ro&immutable=1', uri=True)) as snapshot:
            _require_owned_schema(snapshot, name)


def _require_live_execution(checkpoints: sqlite3.Connection, details: dict[str, dict[str, Any]]) -> None:
    """Bind inert v1 history and saved writes to the pinned executor's tasks.

    The archive reader deliberately treats task IDs as opaque. A live executor
    instead uses their deterministic XXH3 identity to reuse saved node outputs;
    an unrelated ID would silently discard those outputs and rerun the node.
    Decode only with the frozen inert decoder, never the runtime serializer.
    """
    if version('langgraph') != '1.2.16':
        raise ValueError('unsupported checkpoint executor version')
    from watchlist.review.compat_v1 import _pv1_decode
    from xxhash import xxh3_128_hexdigest

    by_thread = {detail['initial']['thread_id']: detail for detail in details.values()}
    normalization = {}
    for thread, detail in by_thread.items():
        try:
            normalization[thread] = (normalize_name(detail['initial']['query']), None)
        except ValueError as exc:
            normalization[thread] = (None, {'code': 'invalid_query', 'stage': 'normalize',
                                           'message': str(exc), 'retryable': False})
    normal_path = ('__start__', 'normalize', 'retrieve_e5', 'format_candidates',
                   'prepare_review', 'human_review', 'explain', 'audit_record', None)
    error_path = ('__start__', 'normalize', 'explain', 'audit_record', None)
    tasks = {}
    for thread, checkpoint_id, kind, blob, metadata_blob in checkpoints.execute(
        'SELECT thread_id,checkpoint_id,type,checkpoint,metadata FROM checkpoints'
    ):
        initial = by_thread[thread]['initial']
        checkpoint = _pv1_decode(kind, blob, 'live checkpoint')
        step = json.loads(metadata_blob)['step']
        state = None if step == -1 else {key: checkpoint['channel_values'][key] for key in initial}
        if step == 0 and state != initial:
            raise ValueError('initial checkpoint differs from its saved request; recovery required')
        if step >= 1 and (state['normalized_query'], state['error']) != normalization[thread]:
            raise ValueError('checkpoint normalization differs from its saved query; recovery required')
        path = error_path if state and state['error'] is not None else normal_path
        node = path[step + 1]
        expected = None
        if node is not None:
            trigger = '__start__' if node == '__start__' else 'branch:to:' + node
            # LangGraph 1.2.16's v4 sequential PULL task identity. XXH3 is
            # already a pinned runtime dependency; no graph code is executed.
            parts = (node, str(step + 1), node, '__pregel_pull', trigger)
            hexdigest = xxh3_128_hexdigest(UUID(checkpoint_id).bytes + ''.join(parts).encode())
            expected = str(UUID(hex=hexdigest))
        tasks[(thread, checkpoint_id)] = (node, expected, state)
    for thread, checkpoint_id, task_id, channel, kind, blob in checkpoints.execute(
        'SELECT thread_id,checkpoint_id,task_id,channel,type,value FROM writes'
    ):
        node, expected, state = tasks[(thread, checkpoint_id)]
        if task_id != '00000000-0000-0000-0000-000000000000' and task_id != expected:
            raise ValueError('checkpoint write task identity differs from its scheduled task; recovery required')
        if channel == '__interrupt__':
            value = _pv1_decode(kind, blob, 'live interrupt', allow_interrupt=True)
            if value[0].decoded['id'] != xxh3_128_hexdigest(f'{node}:{task_id}'.encode()):
                raise ValueError('saved interruption differs from its scheduled task; recovery required')
        elif node == 'normalize' and channel in ('normalized_query', 'error'):
            value = _pv1_decode(kind, blob, 'live normalization output')
            normalized, error = normalization[thread]
            wanted_channel = 'normalized_query' if error is None else 'error'
            if channel != wanted_channel or value != (normalized if error is None else error):
                raise ValueError('saved normalization output differs from its query; recovery required')
        elif node == 'format_candidates' and channel == 'evidence_sha256':
            if _pv1_decode(kind, blob, 'live packet digest') != digest(packet(state)):
                raise ValueError('saved format output differs from checkpoint evidence; recovery required')
        elif node == 'audit_record' and channel in ('audit_status', 'audit_event_id', 'audit_head_sha256'):
            detail = by_thread[thread]
            final = next((event for event in detail['audit_events'] if event['event_key'] == 'case_finalized'), None)
            if final is None:
                raise ValueError('saved audit output lacks its final event; recovery required')
            receipt = {'audit_status': 'committed', 'audit_head_sha256': final['event_sha256'],
                       'audit_event_id': f"{detail['initial']['audit_id']}:{final['sequence']}"}
            if _pv1_decode(kind, blob, 'live audit receipt') != receipt[channel]:
                raise ValueError('saved audit output differs from its final receipt; recovery required')


def _read_live_pair(project: Path, normalized: Path, *, code_hash: str | None = None) -> dict[str, dict[str, Any]]:
    """Admit a complete v1 protocol on private copies, before runtime decoding.

    The frozen reader verifies every case, audit event, checkpoint and write.
    These additional live checks reject progress that could otherwise replay
    retrieval or accept a review without its saved human-review interruption.
    An unanchored v1 pair cannot reveal a coherent rollback of both stores.
    """
    root = normalized / 'review'
    _require_owned_pair(root)
    from watchlist.review.compat_v1 import read_v1
    _, details = read_v1(project, 'review', normalized)
    with closing(sqlite3.connect((root / 'checkpoints.sqlite').as_uri() + '?mode=ro&immutable=1', uri=True)) as checkpoints:
        _require_live_execution(checkpoints, details)
        for detail in details.values():
            initial, state = detail['initial'], detail['latest_state']
            saved_packet, submission = detail['packet'], detail['submission']
            if code_hash is not None and (initial['schema_version'], initial['workflow_version'], initial['workflow_sha256']) != (SCHEMA, WORKFLOW, code_hash):
                raise ValueError('workflow/schema changed; pending case requires original implementation')
            if detail['checkpoint'] is None and detail['case']['event_keys'] != ['request_created']:
                raise ValueError('missing checkpoint history is only valid for an untouched request; recovery required')
            if saved_packet is not None and (state is None or state['evidence_sha256'] != detail['case']['packet_sha256']):
                raise ValueError('saved packet lacks its latest matching checkpoint evidence; recovery required')
            if state is not None and state['review_status'] != 'not_requested' and saved_packet is None:
                raise ValueError('review checkpoint lacks its saved packet; recovery required')
            if submission is not None and checkpoints.execute(
                "SELECT 1 FROM writes WHERE thread_id=? AND checkpoint_ns='' AND checkpoint_id=? AND channel='__interrupt__'",
                (initial['thread_id'], submission['expected_checkpoint_id']),
            ).fetchone() is None:
                raise ValueError('accepted submission lacks its saved pending interruption; recovery required')
    return details


def _require_empty_database(db: sqlite3.Connection) -> None:
    """Allow initialization only for an empty, unclaimed, version-zero store."""
    if (db.execute('PRAGMA main.application_id').fetchone()[0] != 0
            or db.execute('PRAGMA main.user_version').fetchone()[0] != 0
            or db.execute('SELECT 1 FROM main.sqlite_master LIMIT 1').fetchone() is not None):
        raise ValueError('new case database is not empty or is already claimed')


@contextmanager
def _copied_databases(root: Path, *, locked: bool = False, lock_timeout: float = 5.0):
    """Yield normalized temporary copies, accounting for committed WAL frames.

    ``locked`` is only for a writer already holding this workspace's exclusive
    lock. Normal readers acquire the existing lock in shared mode for the copy.
    """
    _workspace_files(root)
    with TemporaryDirectory(prefix='watchlist-read-') as temporary:
        scratch = Path(temporary).resolve()
        copied, normalized, project = scratch / 'copied', scratch / 'normalized', scratch / 'project'
        copied.mkdir()
        (normalized / 'review').mkdir(parents=True)
        project.mkdir()
        with (nullcontext() if locked else _existing_lock(root, shared=True, lock_timeout=lock_timeout)):
            before = _workspace_files(root)
            hashes = {}
            for name in before:
                if name == 'writer.lock':
                    continue
                source = root / name
                result = hashlib.sha256()
                with source.open('rb') as incoming, (copied / name).open('xb') as outgoing:
                    for block in iter(lambda: incoming.read(1024 * 1024), b''):
                        outgoing.write(block)
                        result.update(block)
                hashes[name] = result.hexdigest()
            if before != _workspace_files(root) or any(_file_digest(root / name) != sha for name, sha in hashes.items()):
                raise ValueError('review workspace changed during the locked copy')
        for name in _DATABASE_NAMES:
            # Never use immutable here: it would ignore copied WAL frames.
            with closing(sqlite3.connect((copied / name).as_uri() + '?mode=rw', uri=True)) as source:
                source.execute('PRAGMA trusted_schema=OFF')
                with closing(sqlite3.connect(normalized / 'review' / name)) as destination:
                    source.backup(destination)
                    destination.execute('PRAGMA journal_mode=DELETE')
                    destination.commit()
        yield project, normalized


class ReviewReader:
    """Inspect a stable private copy while leaving the original workspace intact.

    The existing writer lock coordinates the pair. Ordinary SQLite recovery and
    backup run only on copies, so committed WAL frames remain visible without
    permitting SQLite to create, recover, or rewrite files in the source.
    """

    def __init__(self, root: Path, *, lock_timeout: float = 5.0):
        self.lock_timeout = _validated_lock_timeout(lock_timeout)
        self.root = Path(root)
        self._details: dict[str, dict[str, Any]] | None = None
        self.code_hash: str | None = None

    def __enter__(self) -> ReviewReader:
        if self._details is not None:
            raise RuntimeError('reader is already open')
        self.root = _checked_path(self.root)
        _workspace_files(self.root)
        # The directory is private and removed before returning, on both the
        # successful path and any decoding, backup, or validation error.
        with _copied_databases(self.root, lock_timeout=self.lock_timeout) as (project, normalized):
            details = _read_live_pair(project, normalized)
            current_hash = workflow_hash()
        self._details, self.code_hash = details, current_hash
        return self

    def __exit__(self, *args) -> None:
        self._details = None
        self.code_hash = None

    def _case(self, thread_id: str) -> dict[str, Any]:
        if self._details is None:
            raise RuntimeError('use ReviewReader inside a context manager')
        matches = [detail for detail in self._details.values() if detail['case']['thread_id'] == thread_id]
        if len(matches) != 1:
            raise ValueError('unknown thread ID')
        detail = matches[0]
        initial = detail['initial']
        if (initial['schema_version'], initial['workflow_version'], initial['workflow_sha256']) != (SCHEMA, WORKFLOW, self.code_hash):
            raise ValueError('workflow/schema changed; pending case requires original implementation')
        return detail

    def list_cases(self) -> list[dict[str, str]]:
        """List current-workflow case identities without query or reviewer text."""
        if self._details is None:
            raise RuntimeError('use ReviewReader inside a context manager')
        ordered = sorted(self._details.values(), key=lambda detail: (detail['initial']['created_at'], detail['case']['audit_id']))
        result = []
        for detail in ordered:
            thread_id = detail['case']['thread_id']
            checked = self._case(thread_id)
            result.append({'thread_id': thread_id, 'audit_id': checked['case']['audit_id']})
        return result

    def status(self, thread_id: str) -> dict[str, Any]:
        """Return the original status shape from verified durable checkpoint data."""
        detail = self._case(thread_id)
        case, checkpoint = detail['case'], detail['checkpoint']
        state = detail['latest_state'] or detail['initial']
        pending = bool(checkpoint and checkpoint['next'] == ['human_review']
                       and '__interrupt__' in checkpoint['control_channels'])
        return {'thread_id': thread_id, 'audit_id': case['audit_id'], 'state': state,
                'checkpoint_id': case['latest_checkpoint_id'], 'pending_interrupt': pending,
                'next': checkpoint['next'] if checkpoint else [],
                'audit': {'audit_id': case['audit_id'], 'count': case['audit_count'], 'head_sha256': case['audit_head_sha256']},
                'completed': case['completed_audit_checkpoint']}

    def validate_review(self, thread_id: str, form: object) -> None:
        """Preflight a caller form without opening the original stores writable."""
        validated = validate_review_form(form)
        detail = self._case(thread_id)
        if detail['submission'] is not None:
            raise ValueError('duplicate review; use recover for an interrupted accepted submission')
        if any(case['submission'] is not None and case['submission']['submission_id'] == validated['submission_id']
               for case in self._details.values()):
            raise ValueError('duplicate or conflicting submission ID')
        status = self.status(thread_id)
        if not status['pending_interrupt'] or status['state']['review_status'] != 'pending':
            raise ValueError('case is not awaiting human review')
        value = {**validated, 'reviewer_id': getpass.getuser(), 'submitted_at': now()}
        validate_review(value, status['state'], status['checkpoint_id'])


class Ledger:
    def __init__(self, db: sqlite3.Connection, *, initialize: bool = True, schema_checked: object = False):
        self.db = db
        db.row_factory = sqlite3.Row
        if initialize:
            _require_empty_database(db)
            db.executescript(Path(__file__).with_name('schema.sql').read_text())
        else:
            # Only the writer's copied-pair preflight can skip a second schema
            # read on the original. A caller-provided True is not that proof.
            if schema_checked is not _SCHEMA_CHECKED:
                _require_owned_schema(db, 'cases.sqlite')
            db.execute('PRAGMA foreign_keys=ON')

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def create(self, state: ReviewState) -> None:
        with self.transaction():
            if self.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0] >= 100: raise ValueError('100-case pilot limit reached')
            self.db.execute('INSERT INTO cases VALUES (?,?,?,?)',
                            (state['audit_id'], state['thread_id'], canonical(state), state['parent_audit_id']))
            append_event(self.db, state['audit_id'], 'request_created', state)

    def initial(self, thread_id: str) -> dict:
        row = self.db.execute('SELECT initial_json FROM cases WHERE thread_id=?', (thread_id,)).fetchone()
        if row is None: raise ValueError('unknown thread ID')
        return json.loads(row[0])

    def prepare(self, state: dict) -> None:
        validate_packet(state)
        value, sha = canonical(packet(state)), digest(packet(state))
        if sha != state['evidence_sha256']: raise ValueError('packet digest mismatch')
        with self.transaction():
            old = self.db.execute('SELECT packet_json,sha256 FROM review_packets WHERE audit_id=? AND revision=1', (state['audit_id'],)).fetchone()
            if old:
                if tuple(old) != (value, sha): raise ValueError('conflicting packet replay')
            else:
                self.db.execute('INSERT INTO review_packets VALUES (?,1,?,?)', (state['audit_id'], value, sha))
            append_event(self.db, state['audit_id'], 'suggestions_ready', {'packet_sha256': sha})

    def submission(self, audit_id: str) -> dict | None:
        row = self.db.execute('SELECT payload_json,sha256 FROM review_submissions WHERE audit_id=?', (audit_id,)).fetchone()
        if row is None: return None
        result = json.loads(row[0])
        if digest(result) != row[1]: raise ValueError('submission checksum mismatch')
        return result

    def submit(self, state: dict, value: dict) -> None:
        with self.transaction():
            if self.submission(state['audit_id']) is not None: raise ValueError('duplicate review; use recover for an interrupted accepted submission')
            try:
                self.db.execute('INSERT INTO review_submissions VALUES (?,?,1,?,?)',
                                (value['submission_id'], state['audit_id'], canonical(value), digest(value)))
            except sqlite3.IntegrityError as exc: raise ValueError('duplicate or conflicting submission ID') from exc
            append_event(self.db, state['audit_id'], 'review_submitted', {'submission': value})

    def finalize(self, state: dict) -> dict:
        if not state['error'] and (state['review_status'] != 'recorded' or self.submission(state['audit_id']) != state['reviewer_decision']):
            raise ValueError('cannot finalize without accepted human annotation')
        with self.transaction():
            return append_event(self.db, state['audit_id'], 'case_finalized', final_payload(state))

    def attempt_error(self, audit_id: str, exc: Exception) -> None:
        """Best effort only; never claim that a storage failure was durably logged."""
        try:
            with self.transaction():
                count = self.db.execute("SELECT COUNT(*) FROM audit_events WHERE audit_id=? AND event_key LIKE 'attempt:%'", (audit_id,)).fetchone()[0]
                if count < 100:
                    append_event(self.db, audit_id, 'attempt:' + str(uuid4()), {'error_type': type(exc).__name__, 'message': str(exc)[:1000]})
        except Exception:
            pass

    def verify(self, initial: dict, state: dict | None = None, anchor: dict | None = None) -> dict:
        """Check relational integrity, hashes and links between the two stores."""
        db, aid = self.db, initial['audit_id']
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('SQLite integrity failure')
        head = verify_chain(db, aid, anchor)
        events = {r['event_key']: dict(r) for r in db.execute('SELECT * FROM audit_events WHERE audit_id=?', (aid,))}
        def payload(key):
            if key not in events: raise ValueError(f'missing audit event: {key}')
            return json.loads(events[key]['payload_json'])
        if payload('request_created') != initial: raise ValueError('case header differs from audit')
        row = db.execute('SELECT * FROM review_packets WHERE audit_id=?', (aid,)).fetchone()
        if row:
            saved = json.loads(row['packet_json'])
            if digest(saved) != row['sha256'] or payload('suggestions_ready') != {'packet_sha256': row['sha256']}: raise ValueError('saved packet integrity failure')
            if saved['audit_id'] != aid or saved['thread_id'] != initial['thread_id']: raise ValueError('cross-case packet')
            if state and state['evidence_sha256']:
                validate_packet(state)
                if packet(state) != saved or state['evidence_sha256'] != row['sha256']: raise ValueError('checkpoint/packet mismatch')
        elif 'suggestions_ready' in events or state and state['review_status'] != 'not_requested': raise ValueError('missing packet receipt')
        submission = self.submission(aid)
        if submission:
            if row is None or payload('review_submitted') != {'submission': submission}: raise ValueError('submission/audit mismatch')
            validate_review(submission, {**saved, 'evidence_sha256': row['sha256']}, submission['expected_checkpoint_id'])
        elif 'review_submitted' in events: raise ValueError('missing submission receipt')
        if state:
            for k in ('thread_id', 'audit_id', 'query', 'recipe', 'workflow_sha256', 'schema_version', 'workflow_version'):
                if state[k] != initial[k]: raise ValueError('checkpoint/header mismatch')
            if state['reviewer_decision'] is not None and state['reviewer_decision'] != submission: raise ValueError('checkpoint/submission mismatch')
            if 'case_finalized' in events and payload('case_finalized') != final_payload(state):
                raise ValueError('final event differs from checkpoint evidence')
            if state['audit_status'] == 'committed':
                event = events.get('case_finalized')
                if event is None or payload('case_finalized') != final_payload(state): raise ValueError('final checkpoint/audit mismatch')
                if state['audit_head_sha256'] != event['event_sha256'] or state['audit_event_id'] != f"{aid}:{event['sequence']}": raise ValueError('final receipt mismatch')
        return head


def final_payload(state: dict) -> dict:
    return {k: state[k] for k in ('evidence_sha256', 'reviewer_decision', 'explanation', 'error')}


class ReviewService:
    """Explicit writer context; use ReviewReader for status and listing commands.

    ``auto`` preserves existing Python callers: only a missing or empty directory
    is initialized. ``existing`` never creates a store or changes permissions.
    """

    def __init__(self, root: Path, retriever, failpoint=lambda stage: None, *,
                 mode: Literal['auto', 'create', 'existing'] = 'auto', lock_timeout: float = 5.0):
        self.lock_timeout = _validated_lock_timeout(lock_timeout)
        if mode not in ('auto', 'create', 'existing'):
            raise ValueError('unknown review workspace open mode')
        self.root, self.retriever, self.failpoint = Path(root), retriever, failpoint
        self.mode = mode
        self.lock = None
        self._lock_context = None

    def __enter__(self):
        if self.lock is not None:
            raise RuntimeError('review service is already open')
        self.root = _checked_path(self.root, allow_missing=True)
        if self.root.exists() and not self.root.is_dir():
            raise ValueError('review workspace must be a directory')
        empty = not self.root.exists() or not any(self.root.iterdir())
        create = self.mode == 'create' or self.mode == 'auto' and empty
        if create and not empty:
            raise ValueError('new review workspace must be missing or empty')
        if not create:
            _workspace_files(self.root)
        # The setup bypass below is a pinned saver contract, not a generic
        # promise that future saver versions use the same initialization flag.
        if version('langgraph-checkpoint-sqlite') != '3.1.2':
            raise ValueError('unsupported checkpoint saver version')
        try:
            if create:
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.root.chmod(0o700)
                self.lock = (self.root / 'writer.lock').open('xb')
                os.chmod(self.root / 'writer.lock', 0o600)
                _acquire_lock(self.lock, shared=False, timeout=self.lock_timeout)
                for name in _DATABASE_NAMES:
                    with (self.root / name).open('xb'):
                        pass
                    (self.root / name).chmod(0o600)
            else:
                self._lock_context = _existing_lock(self.root, lock_timeout=self.lock_timeout)
                self.lock = self._lock_context.__enter__()
                # Even a schema SELECT can create WAL/SHM on an original store.
                # Verify the entire protocol on copies before opening originals
                # or allowing the runtime serializer to decode their contents.
                # An intact historical store may open this context; _admit
                # enforces the current workflow before any case operation.
                with _copied_databases(self.root, locked=True) as (project, normalized):
                    _read_live_pair(project, normalized)
            self.db = sqlite3.connect((self.root / 'cases.sqlite').as_uri() + '?mode=rw', uri=True, check_same_thread=False)
            self.ledger = Ledger(self.db, initialize=create, schema_checked=_SCHEMA_CHECKED if not create else False)
            self.checkpoints = sqlite3.connect((self.root / 'checkpoints.sqlite').as_uri() + '?mode=rw', uri=True, check_same_thread=False)
            from langgraph.checkpoint.sqlite import SqliteSaver
            saver = SqliteSaver(self.checkpoints)
            if create:
                saver.setup()
                self.checkpoints.execute(f'PRAGMA application_id={_CHECKPOINT_APPLICATION_ID}')
                self.checkpoints.commit()
            else:
                saver.is_setup = True
            from watchlist.agent.graph import build_graph
            self.graph = build_graph(saver, self.ledger, self.retriever, self.failpoint)
            self.code_hash = workflow_hash()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        try:
            with ExitStack() as resources:
                for name in ('db', 'checkpoints'):
                    if hasattr(self, name):
                        resources.callback(getattr(self, name).close)
                        delattr(self, name)
        finally:
            lock, context = self.lock, self._lock_context
            self.lock = self._lock_context = None
            for name in ('graph', 'ledger', 'code_hash'):
                if hasattr(self, name):
                    delattr(self, name)
            if context is not None:
                context.__exit__(*args)
            elif lock is not None:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                finally:
                    lock.close()

    @staticmethod
    def config(thread_id: str) -> dict:
        return {'configurable': {'thread_id': thread_id}, 'callbacks': []}

    def _admit(self, thread_id: str | None = None) -> dict[str, Any] | None:
        """Recheck the whole locked pair before each operation, without writes."""
        if self.lock is None:
            raise RuntimeError('use ReviewService inside a context manager')
        with _copied_databases(self.root, locked=True) as (project, normalized):
            details = _read_live_pair(project, normalized, code_hash=self.code_hash)
        if thread_id is None:
            return None
        matches = [detail for detail in details.values() if detail['initial']['thread_id'] == thread_id]
        if len(matches) != 1:
            raise ValueError('unknown thread ID')
        return matches[0]

    def inspect(self, thread_id: str):
        detail = self._admit(thread_id)
        initial = detail['initial']
        config = self.config(thread_id)
        if detail['checkpoint'] is not None:
            # The pinned runtime's live view hides a task whose output batch is
            # saved before its next checkpoint. Inspect the durable step so
            # recover(None) can consume that batch without repeating the task.
            config['configurable']['checkpoint_id'] = detail['checkpoint']['checkpoint_id']
        snap = self.graph.get_state(config)
        state = dict(snap.values) if snap.values else None
        expected_next = detail['checkpoint']['next'] if detail['checkpoint'] else []
        if state != detail['latest_state'] or list(snap.next) != expected_next:
            raise ValueError('runtime checkpoint differs from admitted evidence; recovery required')
        anchor = self.ledger.verify(initial, state)
        if state and not snap.next and state['audit_status'] != 'committed': raise ValueError('terminal checkpoint has no committed audit')
        return initial, snap, state, anchor

    def status(self, thread_id: str) -> dict:
        initial, snap, state, anchor = self.inspect(thread_id)
        state = state or initial
        pending = any(t.interrupts for t in snap.tasks)
        return {'thread_id': thread_id, 'audit_id': initial['audit_id'], 'state': state,
                'checkpoint_id': snap.config['configurable'].get('checkpoint_id') if snap.config else None,
                'pending_interrupt': pending, 'next': list(snap.next), 'audit': anchor,
                'completed': bool(snap.values) and not snap.next and state['audit_status'] == 'committed'}

    def invoke(self, thread_id: str, value) -> dict:
        detail = self._admit(thread_id)
        if detail['checkpoint'] is None:
            if value != detail['initial']:
                raise ValueError('a new case must start from its saved request')
        elif value is not None:
            from langgraph.types import Command
            if (not isinstance(value, Command) or detail['submission'] is None
                    or value.resume != detail['submission'] or value.update is not None
                    or value.goto or value.graph is not None
                    or detail['checkpoint']['next'] != ['human_review']
                    or detail['checkpoint']['checkpoint_id'] != detail['submission']['expected_checkpoint_id']
                    or '__interrupt__' not in detail['checkpoint']['control_channels']):
                raise ValueError('existing checkpoint requires recovery or its accepted review')
        elif not detail['checkpoint']['next']:
            raise ValueError('completed case has no work to invoke')
        try:
            self.graph.invoke(value, self.config(thread_id), durability='sync')
        except Exception as exc:
            exc.add_note(f'Recover using thread_id={thread_id}')
            self._record_attempt_error(thread_id, exc)
            raise
        # Admission failures must not append operational-error events.
        return self.status(thread_id)

    def _record_attempt_error(self, thread_id: str, exc: Exception) -> None:
        """Log an operational failure only while the pair still passes admission."""
        try:
            detail = self._admit(thread_id)
        except (ValueError, OSError, sqlite3.Error):
            return
        # Before the first checkpoint, preserve the sole request_created event:
        # that untouched envelope is the only admitted fresh-start exception.
        # The caller still receives the original operational exception.
        if detail['checkpoint'] is None:
            return
        self.ledger.attempt_error(detail['initial']['audit_id'], exc)

    def start(self, query: str, recipe: dict, parent_audit_id: str | None = None) -> dict:
        query, recipe = validate_start_inputs(query, recipe)
        self._admit()
        state: ReviewState = dict(schema_version=SCHEMA, workflow_version=WORKFLOW, workflow_sha256=self.code_hash,
            thread_id=str(uuid4()), audit_id=str(uuid4()), parent_audit_id=parent_audit_id, created_at=now(),
            query=query, normalized_query=None, recipe=recipe, candidates=[], evidence=[], retrieval=None,
            evidence_sha256=None, review_revision=1, review_status='not_requested', reviewer_decision=None,
            explanation=None, error=None, audit_status='pending', audit_event_id=None, audit_head_sha256=None)
        self.ledger.create(state)
        self.failpoint('after_case')
        return self.invoke(state['thread_id'], state)

    def review(self, thread_id: str, form: dict) -> dict:
        form = validate_review_form(form)
        initial, snap, state, _ = self.inspect(thread_id)
        if self.ledger.submission(initial['audit_id']): raise ValueError('duplicate review; use recover for an interrupted accepted submission')
        if state is None or not any(t.interrupts for t in snap.tasks) or state['review_status'] != 'pending': raise ValueError('case is not awaiting human review')
        # Caller mistakes are rejected before the operational-error audit path.
        value = {**form, 'reviewer_id': getpass.getuser(), 'submitted_at': now()}
        validate_review(value, state, snap.config['configurable']['checkpoint_id'])
        # Recheck globally while holding the writer lock: another case may have
        # accepted this ID after the read-only preflight finished.
        if self.db.execute('SELECT 1 FROM review_submissions WHERE submission_id=?', (value['submission_id'],)).fetchone():
            raise ValueError('duplicate or conflicting submission ID')
        try:
            self.ledger.submit(state, value)
            self.failpoint('after_submission')
        except Exception as exc:
            self._record_attempt_error(thread_id, exc)
            raise
        from langgraph.types import Command
        return self.invoke(thread_id, Command(resume=value))

    def recover(self, thread_id: str) -> dict:
        initial, snap, state, _ = self.inspect(thread_id)
        if state is None:
            # A saved __start__ envelope has no application state yet. Resume
            # that checkpoint instead of creating a second input/history root.
            checkpoint_id = snap.config['configurable'].get('checkpoint_id') if snap.config else None
            return self.invoke(thread_id, None if checkpoint_id is not None else initial)
        if not snap.next: return self.status(thread_id)
        if any(task.result is not None for task in snap.tasks):
            # A complete saved task batch is already accepted work, including a
            # human-review result. Consume it without submitting another resume.
            return self.invoke(thread_id, None)
        if any(t.interrupts for t in snap.tasks):
            submitted = self.ledger.submission(initial['audit_id'])
            from langgraph.types import Command
            return self.invoke(thread_id, Command(resume=submitted)) if submitted else self.status(thread_id)
        return self.invoke(thread_id, None)
