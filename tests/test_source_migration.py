"""Offline migration uses independently authored legacy databases and inputs."""

from dataclasses import asdict, dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

from watchlist.entities import Provenance
from watchlist.ingest.fetch_source import DATASET, LICENSE_URL
from watchlist.ingest.parse_opensanctions import PARSER_VERSION, parse_records, read_records


FIXTURE = Path(__file__).parent / 'fixtures/opensanctions_synthetic.ftm.json'
LEGACY_SCHEMA = """
CREATE TABLE sources (
 snapshot_id TEXT PRIMARY KEY NOT NULL, dataset TEXT NOT NULL,
 synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)), raw_sha256 TEXT NOT NULL,
 parser_version TEXT NOT NULL, selection_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
 receipt_json TEXT NOT NULL, report_json TEXT NOT NULL);
CREATE TABLE entities (
 snapshot_id TEXT NOT NULL REFERENCES sources(snapshot_id), entity_id TEXT NOT NULL,
 display_name TEXT NOT NULL, entity_type TEXT NOT NULL, source_schema TEXT NOT NULL,
 source TEXT NOT NULL, referents_json TEXT NOT NULL, raw_records_json TEXT NOT NULL,
 group_id TEXT NOT NULL, PRIMARY KEY (snapshot_id, entity_id));
CREATE TABLE aliases (
 snapshot_id TEXT NOT NULL, entity_id TEXT NOT NULL, alias_id TEXT NOT NULL,
 original_name TEXT NOT NULL, property_name TEXT NOT NULL, normalized_name TEXT,
 unsearchable_reason TEXT, PRIMARY KEY (snapshot_id, alias_id),
 UNIQUE (snapshot_id, entity_id, property_name, original_name),
 FOREIGN KEY (snapshot_id, entity_id) REFERENCES entities(snapshot_id, entity_id),
 CHECK (unsearchable_reason IS NOT NULL OR normalized_name IS NOT NULL));
CREATE INDEX alias_entity ON aliases(snapshot_id, entity_id);
PRAGMA user_version=2;
"""


@dataclass(frozen=True)
class SavedSource:
    root: Path
    raw: Path
    metadata: Path
    receipt: Path
    legacy: Path
    snapshot_id: str
    sample: bool

    def options(self):
        return {'sample': self.sample, 'receipt_path': None if self.sample else self.receipt}


def make_legacy(root, *, sample=False):
    """Reproduce historical v2 storage without using the new database writer."""
    raw, metadata_path, receipt_path = root / 'original.jsonl', root / 'metadata.json', root / 'receipt.json'
    raw.write_bytes(FIXTURE.read_bytes())
    metadata = {'name': 'fictional-ftm-v1' if sample else DATASET, 'synthetic': sample,
                'version': 'authored-migration-fixture', 'last_change': None,
                'description': 'Every record is authored fiction; public mode is a format test.'}
    metadata_path.write_text(json.dumps(metadata))
    raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    metadata_hash = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    if sample:
        receipt = {'dataset': 'fictional-ftm-v1', 'provider': 'Authored fictional fixture',
                   'publisher': 'Polyglot Watchlist learning project', 'synthetic': True,
                   'source_url': 'local:tests/fixtures/opensanctions_synthetic.ftm.json',
                   'download_url': '', 'retrieved_at': 'not applicable: authored offline fixture',
                   'raw_sha256': raw_hash, 'metadata_sha256': metadata_hash,
                   'license': 'authored-fictional-fixture', 'license_url': '',
                   'attribution': 'Authored fictional examples; not OpenSanctions or UN records.'}
    else:
        receipt = {'dataset': DATASET, 'provider': 'OpenSanctions', 'publisher': 'United Nations Security Council',
                   'synthetic': False, 'source_url': 'https://example.invalid/authored-fixture',
                   'download_url': 'https://example.invalid/authored-fixture.jsonl',
                   'retrieved_at': '2026-10-24T00:00:00+00:00', 'raw_sha256': raw_hash,
                   'metadata_sha256': metadata_hash, 'license': 'CC-BY-NC-4.0', 'license_url': LICENSE_URL,
                   'attribution': 'Fictional local format test; no public records downloaded.',
                   'bytes': raw.stat().st_size, 'metadata_bytes': metadata_path.stat().st_size}
    receipt_path.write_text(json.dumps(receipt))
    records, report = parse_records(read_records(raw), synthetic=sample, limit=20)
    report['stored_aliases'] = sum(len(record.aliases) for record in records)
    report['searchable_aliases'] = sum(len(record.entity.aliases) for record in records)
    selection = {'limit': 20, 'order': 'provider_id_ascending', 'non_person_only': True}
    snapshot_id = hashlib.sha256(json.dumps([raw_hash, PARSER_VERSION, selection, sample, metadata_hash],
                                          sort_keys=True).encode()).hexdigest()
    provenance = Provenance(snapshot_id=snapshot_id, dataset=receipt['dataset'], provider=receipt['provider'],
                            publisher=receipt['publisher'], source_url=receipt['source_url'],
                            download_url=receipt['download_url'], retrieved_at=receipt['retrieved_at'],
                            source_updated_at=metadata['last_change'], export_version=metadata['version'],
                            raw_sha256=raw_hash, license_url=receipt['license_url'])
    legacy = root / 'legacy-v2.sqlite'
    connection = sqlite3.connect(legacy)
    try:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)', (
            snapshot_id, provenance.dataset, int(sample), raw_hash, PARSER_VERSION,
            json.dumps(selection, sort_keys=True), json.dumps(asdict(provenance), sort_keys=True),
            json.dumps(receipt, sort_keys=True), json.dumps(report, sort_keys=True)))
        for record in records:
            entity = record.entity
            connection.execute('INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?)', (
                snapshot_id, entity.entity_id, entity.name, entity.entity_type, record.schema, entity.source,
                json.dumps(record.referents), json.dumps([json.loads(v) for v in record.raw_records], ensure_ascii=False),
                record.group_id))
            connection.executemany('INSERT INTO aliases VALUES (?,?,?,?,?,?,?)', [
                (snapshot_id, entity.entity_id, alias.alias_id, alias.name, alias.property_name,
                 alias.normalized, alias.unsearchable_reason) for alias in record.aliases])
        connection.commit()
    finally:
        connection.close()
    legacy.chmod(0o640)
    return SavedSource(root, raw, metadata_path, receipt_path, legacy, snapshot_id, sample)


@pytest.fixture
def saved_source(tmp_path):
    return make_legacy(tmp_path)


@pytest.fixture
def migration():
    return importlib.import_module('watchlist.ingest.migrate_source')


def snapshot(root):
    values = {}
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        value = (stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_ino,
                 info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)
        if stat.S_ISREG(info.st_mode):
            value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
        elif stat.S_ISLNK(info.st_mode):
            value += (os.readlink(path),)
        values[str(path.relative_to(root))] = value
    return values


def verify(migration, fixture, **changes):
    return migration.verify_legacy(fixture.legacy, fixture.raw, fixture.metadata, **{**fixture.options(), **changes})


def rebuild(migration, fixture, destination, **changes):
    return migration.rebuild_legacy(fixture.legacy, fixture.raw, fixture.metadata, destination,
                                    **{**fixture.options(), **changes})


def test_verify_and_rebuild_clean_legacy_preserve_all_originals(migration, saved_source):
    from watchlist.database import load_database, verify_snapshot

    before = snapshot(saved_source.root)
    checked = verify(migration, saved_source)
    assert checked['status'] == 'verified'
    assert checked['snapshot_id'] == saved_source.snapshot_id
    assert snapshot(saved_source.root) == before
    destination = saved_source.root / 'rebuilt-v3.sqlite'
    result = rebuild(migration, saved_source, destination)
    assert result['status'] == 'rebuilt'
    assert verify_snapshot(destination)['status'] == 'verified'
    entities, provenance, _ = load_database(destination)
    assert len(entities) == 3 and provenance.snapshot_id == saved_source.snapshot_id
    connection = sqlite3.connect(destination)
    try:
        assert connection.execute('PRAGMA user_version').fetchone() == (3,)
        assert connection.execute('PRAGMA application_id').fetchone() == (0x50575333,)
    finally:
        connection.close()
    after = snapshot(saved_source.root)
    assert {key: value for key, value in after.items() if key != destination.name} == before
    assert destination.stat().st_ino != saved_source.legacy.stat().st_ino


@pytest.mark.parametrize('changed', ['raw', 'metadata', 'receipt', 'selection'])
def test_mismatched_original_evidence_cannot_be_rebuilt(migration, saved_source, changed):
    options = {}
    if changed in ('raw', 'metadata'):
        path = getattr(saved_source, changed)
        path.write_bytes(path.read_bytes() + b'\n')
    elif changed == 'receipt':
        receipt = json.loads(saved_source.receipt.read_text())
        receipt['raw_sha256'] = '0' * 64
        saved_source.receipt.write_text(json.dumps(receipt))
    else:
        options['limit'] = 1
    before = snapshot(saved_source.root)
    with pytest.raises((ValueError, sqlite3.Error)):
        rebuild(migration, saved_source, saved_source.root / 'must-not-exist.sqlite', **options)
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('sql', [
    "UPDATE entities SET display_name='Forged display' WHERE entity_id='fixture-001'",
    "UPDATE entities SET source_schema='ForgedSchema' WHERE entity_id='fixture-001'",
    "UPDATE entities SET referents_json='[\"forged\"]' WHERE entity_id='fixture-001'",
    "UPDATE entities SET raw_records_json='[]' WHERE entity_id='fixture-001'",
    "UPDATE entities SET group_id='forged' WHERE entity_id='fixture-001'",
    "UPDATE aliases SET original_name='Forged weak alias' WHERE property_name='weakAlias'",
    "UPDATE aliases SET normalized_name='forged' WHERE property_name='weakAlias'",
    "UPDATE aliases SET unsearchable_reason='forged reason' WHERE property_name='weakAlias'",
    "UPDATE sources SET receipt_json='{}'",
    "UPDATE sources SET report_json='{}'",
    "UPDATE sources SET selection_json='{}'",
    "UPDATE sources SET provenance_json='{}'",
])
def test_corrupt_legacy_logical_fields_are_rejected_before_output(migration, saved_source, sql):
    connection = sqlite3.connect(saved_source.legacy)
    try:
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()
    before = snapshot(saved_source.root)
    with pytest.raises((ValueError, sqlite3.Error)):
        rebuild(migration, saved_source, saved_source.root / 'must-not-exist.sqlite')
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('sql', ['CREATE TABLE foreign_table (id TEXT)', 'DROP INDEX alias_entity',
                                 'PRAGMA user_version=999', 'PRAGMA application_id=123'])
def test_forged_or_unrecognized_legacy_schema_is_rejected(migration, saved_source, sql):
    connection = sqlite3.connect(saved_source.legacy)
    try:
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()
    before = snapshot(saved_source.root)
    with pytest.raises((ValueError, sqlite3.Error)):
        verify(migration, saved_source)
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('kind', ['existing_file', 'legacy_itself', 'hardlink', 'symlink'])
def test_rebuild_never_overwrites_existing_or_linked_destination(migration, saved_source, kind):
    destination = saved_source.root / 'existing.sqlite'
    if kind == 'existing_file':
        destination.write_text('Existing owner data')
    elif kind == 'legacy_itself':
        destination = saved_source.legacy
    elif kind == 'hardlink':
        os.link(saved_source.legacy, destination)
    else:
        destination.symlink_to(saved_source.root / 'absent-target.sqlite')
    before = snapshot(saved_source.root)
    with pytest.raises((ValueError, OSError)):
        rebuild(migration, saved_source, destination)
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('failure', ['writer', 'verification'])
def test_rebuild_failure_cleans_only_private_staging(migration, saved_source, monkeypatch, failure):
    before = snapshot(saved_source.root)

    def fail_writer(path, *_args, **_kwargs):
        path.write_bytes(b'partial fictional output')
        raise OSError('Fictional write failure')

    def fail_verification(_path):
        raise ValueError('Fictional derivative verification failure')

    monkeypatch.setattr(migration, 'write_snapshot' if failure == 'writer' else 'verify_snapshot',
                        fail_writer if failure == 'writer' else fail_verification)
    with pytest.raises((OSError, ValueError)):
        rebuild(migration, saved_source, saved_source.root / 'must-not-exist.sqlite')
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('kind', ['missing_parent', 'file_parent', 'symlink_parent', 'parent_traversal',
                                 'wal', 'shm', 'journal'])
def test_invalid_output_ancestry_or_sidecars_create_nothing(migration, saved_source, kind):
    root = saved_source.root
    destination = root / 'output.sqlite'
    if kind == 'missing_parent':
        destination = root / 'missing' / 'output.sqlite'
    elif kind == 'file_parent':
        parent = root / 'parent-file'
        parent.write_text('Unrelated owner data')
        destination = parent / 'output.sqlite'
    elif kind == 'symlink_parent':
        (root / 'linked-parent').symlink_to(root, target_is_directory=True)
        destination = root / 'linked-parent' / 'output.sqlite'
    elif kind == 'parent_traversal':
        (root / 'parent').mkdir()
        destination = root / 'parent' / '..' / 'output.sqlite'
    else:
        Path(f'{destination}-{kind}').write_bytes(b'Unrelated sidecar bytes')
    before = snapshot(root)
    with pytest.raises((ValueError, OSError)):
        rebuild(migration, saved_source, destination)
    assert snapshot(root) == before


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_legacy_sidecar_is_rejected_without_recovery_or_output(migration, saved_source, suffix):
    Path(f'{saved_source.legacy}{suffix}').write_bytes(b'Fictional unresolved journal')
    before = snapshot(saved_source.root)
    with pytest.raises(ValueError, match='sidecar'):
        verify(migration, saved_source)
    with pytest.raises(ValueError, match='sidecar'):
        rebuild(migration, saved_source, saved_source.root / 'must-not-exist.sqlite')
    assert snapshot(saved_source.root) == before


@pytest.mark.parametrize('failure', ['before_link', 'after_link', 'competing_file'])
def test_publication_failure_preserves_competing_owner_and_cleans_stage(
    migration, saved_source, monkeypatch, failure,
):
    destination = saved_source.root / 'publication.sqlite'
    before = snapshot(saved_source.root)
    original_link = os.link

    def interrupted_link(source, target, *args, **kwargs):
        if target != destination:
            return original_link(source, target, *args, **kwargs)
        if failure == 'after_link':
            original_link(source, target, *args, **kwargs)
        elif failure == 'competing_file':
            destination.write_bytes(b'Concurrent owner data')
        raise OSError('Fictional publication interruption')

    monkeypatch.setattr(migration.os, 'link', interrupted_link)
    with pytest.raises(OSError, match='publication interruption'):
        rebuild(migration, saved_source, destination)
    after = snapshot(saved_source.root)
    if failure == 'competing_file':
        assert destination.read_bytes() == b'Concurrent owner data'
        del after[destination.name]
    assert after == before


def test_explicit_fictional_migration_needs_no_public_receipt(migration, tmp_path):
    fixture = make_legacy(tmp_path, sample=True)
    assert verify(migration, fixture)['status'] == 'verified'
    assert rebuild(migration, fixture, tmp_path / 'sample-v3.sqlite')['status'] == 'rebuilt'
    with pytest.raises(ValueError):
        verify(migration, fixture, sample=False, receipt_path=None)


def test_preparation_hashes_and_parses_each_supplied_buffer_once(saved_source, monkeypatch):
    from watchlist.ingest import import_source

    original = import_source._read_saved_bytes
    counts = {}

    def counted(path, *args, **kwargs):
        counts[path] = counts.get(path, 0) + 1
        return original(path, *args, **kwargs)

    monkeypatch.setattr(import_source, '_read_saved_bytes', counted)
    prepared = import_source.prepare_snapshot(saved_source.raw, saved_source.metadata, receipt_path=saved_source.receipt)
    assert prepared.provenance.snapshot_id == saved_source.snapshot_id
    assert counts == {saved_source.raw: 1, saved_source.metadata: 1, saved_source.receipt: 1}


def test_migration_cli_verifies_and_rebuilds_only_explicit_local_inputs(migration, saved_source):
    destination = saved_source.root / 'cli-v3.sqlite'
    base = [sys.executable, '-B', '-m', 'watchlist.ingest.migrate_source']
    options = ['--legacy', str(saved_source.legacy), '--input', str(saved_source.raw),
               '--metadata', str(saved_source.metadata), '--receipt', str(saved_source.receipt)]
    for action, extra in [('verify', []), ('rebuild', ['--output', str(destination)])]:
        result = subprocess.run([*base, action, *options, *extra], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['status'] == ('verified' if action == 'verify' else 'rebuilt')
