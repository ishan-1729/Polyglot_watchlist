"""Append-only application API with limited, locally verifiable hash chaining."""

from datetime import datetime, timezone
import json
import sqlite3

from watchlist.agent.state import canonical, digest


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def envelope(row: dict) -> dict:
    return {k: row[k] for k in ('audit_id', 'sequence', 'event_key', 'payload_json', 'created_at', 'previous_sha256')}


def verify_chain(db: sqlite3.Connection, audit_id: str, anchor: dict | None = None) -> dict:
    """Recompute every event; a separately retained anchor detects deleted tails."""
    previous, count = '', 0
    for row in db.execute('SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence', (audit_id,)):
        count += 1
        if row['sequence'] != count or row['previous_sha256'] != previous or digest(envelope(row)) != row['event_sha256']:
            raise ValueError('audit chain integrity failure')
        if canonical(json.loads(row['payload_json'])) != row['payload_json']: raise ValueError('noncanonical audit payload')
        previous = row['event_sha256']
    result = {'audit_id': audit_id, 'count': count, 'head_sha256': previous}
    if anchor is not None and result != anchor: raise ValueError('audit anchor mismatch')
    return result


def append_event(db: sqlite3.Connection, audit_id: str, key: str, payload: dict) -> dict:
    """Caller holds BEGIN IMMEDIATE. Replays return the same durable receipt."""
    chain = verify_chain(db, audit_id)
    old = db.execute('SELECT * FROM audit_events WHERE audit_id=? AND event_key=?', (audit_id, key)).fetchone()
    encoded = canonical(payload)
    if old:
        if old['payload_json'] != encoded: raise ValueError('conflicting event replay')
        row = dict(old)
    else:
        row = {'audit_id': audit_id, 'sequence': chain['count'] + 1, 'event_key': key,
               'payload_json': encoded, 'created_at': now(), 'previous_sha256': chain['head_sha256']}
        row['event_sha256'] = digest(envelope(row))
        db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)', tuple(row[k] for k in
                   ('audit_id', 'sequence', 'event_key', 'payload_json', 'created_at', 'previous_sha256', 'event_sha256')))
    return {'audit_event_id': f"{audit_id}:{row['sequence']}", 'audit_head_sha256': row['event_sha256']}
