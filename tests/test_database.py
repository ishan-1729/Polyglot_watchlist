"""Atomic imports, relational integrity, provenance, and retrieval parity."""

from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

import pytest

from watchlist.database import connect_database, load_database, write_snapshot
from watchlist import database as database_module
from watchlist.entities import Provenance
from watchlist.ingest.import_source import import_snapshot
from watchlist.ingest.parse_opensanctions import parse_records, read_records
from watchlist.matching import rank_candidates

FIXTURE = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
METADATA = FIXTURE.with_name("opensanctions_synthetic.metadata.json")


def database_files_snapshot(path: Path) -> dict:
    """Ignore access time while detecting bytes, modes, identity, and sidecars."""
    result = {}
    for member in sorted(path.parent.glob(path.name + "*")):
        info = member.lstat()
        result[member.name] = (
            info.st_mode, info.st_ino, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
            hashlib.sha256(member.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None,
        )
    return result


def assert_sqlite_healthy(path: Path) -> None:
    """Logical evidence corruption need not violate SQLite's structural checks."""
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("statement", [
    "UPDATE entities SET display_name='Changed fictional name' WHERE entity_id='fixture-001'",
    "UPDATE aliases SET normalized_name='changed fictional normalization' WHERE entity_id='fixture-001'",
])
def test_changed_logical_content_is_rejected_despite_sqlite_integrity(tmp_path, operation, statement):
    db = tmp_path / "sample.sqlite"
    import_snapshot(FIXTURE, METADATA, db, sample=True)
    with sqlite3.connect(db) as connection:
        connection.execute(statement)
    assert_sqlite_healthy(db)
    before = database_files_snapshot(db)
    with pytest.raises(ValueError):
        if operation == "load":
            load_database(db)
        else:
            import_snapshot(FIXTURE, METADATA, db, sample=True)
    assert database_files_snapshot(db) == before


@pytest.mark.parametrize("version", [0, 1, 2, 99])
def test_foreign_database_is_rejected_before_ddl_without_mutation(tmp_path, version):
    db = tmp_path / "foreign.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE unrelated (note TEXT)")
        connection.execute("INSERT INTO unrelated VALUES ('Fictional unrelated data')")
        connection.execute(f"PRAGMA user_version={version}")
    db.chmod(0o640)
    before = database_files_snapshot(db)
    with pytest.raises(ValueError):
        import_snapshot(FIXTURE, METADATA, db, sample=True)
    assert database_files_snapshot(db) == before


def test_idempotent_import_and_matching_parity(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite"
    first = import_snapshot(FIXTURE, METADATA, db, sample=True)
    second = import_snapshot(FIXTURE, METADATA, db, sample=True)
    assert first["created"] is True and second["created"] is False
    assert first["snapshot_id"] == second["snapshot_id"]
    entities, provenance, synthetic = load_database(db)
    assert synthetic is True and len(entities) == 3
    assert provenance.source_updated_at is None
    assert provenance.dataset == "fictional-ftm-v1"
    parsed, _ = parse_records(read_records(FIXTURE), synthetic=True)
    in_memory = [replace(r.entity, provenance=provenance) for r in parsed]
    assert rank_candidates("Moonberry Loom", entities) == rank_candidates("Moonberry Loom", in_memory)
    assert any(a.name == "مونبيري لوم" for e in entities for a in e.aliases)


def test_foreign_keys_and_exact_alias_uniqueness(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite"
    import_snapshot(FIXTURE, METADATA, db, sample=True)
    connection = connect_database(db)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        row = tuple(connection.execute("SELECT * FROM aliases LIMIT 1").fetchone())
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO aliases VALUES (?, ?, ?, ?, ?, ?, ?)", row)
        orphan = list(row)
        orphan[1], orphan[2] = "missing-entity", "new-alias"
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute("INSERT INTO aliases VALUES (?, ?, ?, ?, ?, ?, ?)", orphan)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


def test_other_selection_does_not_change_existing_database(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite"
    import_snapshot(FIXTURE, METADATA, db, sample=True)
    before = db.read_bytes()
    with pytest.raises(ValueError, match="another snapshot"):
        import_snapshot(FIXTURE, METADATA, db, sample=True, limit=1)
    assert db.read_bytes() == before


def test_partial_insert_failure_rolls_back_every_table(tmp_path: Path) -> None:
    reference_db = tmp_path / "reference.sqlite"
    import_snapshot(FIXTURE, METADATA, reference_db, sample=True)
    _, provenance, _ = load_database(reference_db)
    reference = connect_database(reference_db, readonly=True)
    row = reference.execute("SELECT * FROM sources").fetchone()
    reference.close()
    parsed, _ = parse_records(read_records(FIXTURE), synthetic=True)
    db = tmp_path / "failed.sqlite"
    with pytest.raises(sqlite3.IntegrityError):
        write_snapshot(
            db, provenance, [parsed[0], parsed[0]],
            receipt=json.loads(row["receipt_json"]), selection=json.loads(row["selection_json"]),
            report=json.loads(row["report_json"]),
        )
    connection = connect_database(db)
    try:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        connection.close()


def test_missing_database_read_does_not_create_file(tmp_path: Path) -> None:
    db = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        load_database(db)
    assert not db.exists()


def test_raw_source_and_unsearchable_alias_survive_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "sample.sqlite"
    import_snapshot(FIXTURE, METADATA, db, sample=True)
    connection = connect_database(db, readonly=True)
    try:
        row = connection.execute("SELECT raw_records_json FROM entities WHERE entity_id='fixture-001'").fetchone()
        assert json.loads(row[0])[0] == read_records(FIXTURE)[0]
        weak = connection.execute("SELECT original_name, unsearchable_reason FROM aliases WHERE property_name='weakAlias'").fetchone()
        assert weak[0] == "Loom" and weak[1]
    finally:
        connection.close()


@pytest.fixture
def committed_snapshot(tmp_path):
    path = tmp_path / "committed.sqlite"
    import_snapshot(FIXTURE, METADATA, path, sample=True)
    return path


def reject_snapshot_unchanged(path: Path, operation: str) -> None:
    assert_sqlite_healthy(path)
    before = database_files_snapshot(path)
    with pytest.raises(ValueError):
        if operation == "load":
            load_database(path)
        else:
            import_snapshot(FIXTURE, METADATA, path, sample=True)
    assert database_files_snapshot(path) == before


def test_v3_identity_manifest_counts_and_true_repeat_are_verified(committed_snapshot):
    db = committed_snapshot
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == 0x50575333
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        expected_counts = {
            "sources": 1,
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "aliases": connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
            "searchable_aliases": connection.execute("SELECT COUNT(*) FROM aliases WHERE unsearchable_reason IS NULL").fetchone()[0],
            "unsearchable_aliases": connection.execute("SELECT COUNT(*) FROM aliases WHERE unsearchable_reason IS NOT NULL").fetchone()[0],
        }
        raw, saved_hash = connection.execute("SELECT content_json,content_sha256 FROM snapshot_manifests").fetchone()
        manifest = json.loads(raw)
        assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == saved_hash
        assert manifest["counts"] == expected_counts
        assert manifest["selection_version"] == "opensanctions-non-person-provider-id-v1"
        assert manifest["tables"]["sources"][0]["source_metadata_json"] == json.loads(METADATA.read_text())
    before = database_files_snapshot(db)
    receipt = database_module.verify_snapshot(db)
    assert receipt["manifest_version"] == "watchlist-logical-content-v1"
    assert receipt["content_sha256"] == saved_hash
    assert receipt["counts"] == expected_counts
    assert len(load_database(db)[0]) == expected_counts["entities"]
    assert import_snapshot(FIXTURE, METADATA, db, sample=True)["created"] is False
    assert database_files_snapshot(db) == before


CONTENT_MUTATIONS = [
    ("entity_type", "UPDATE entities SET entity_type='legal_entity' WHERE entity_id='fixture-001'"),
    ("source_schema", "UPDATE entities SET source_schema='Organization' WHERE entity_id='fixture-001'"),
    ("source", "UPDATE entities SET source='changed-fictional-source' WHERE entity_id='fixture-001'"),
    ("referents", "UPDATE entities SET referents_json='[\"changed-reference\"]' WHERE entity_id='fixture-001'"),
    ("raw_evidence", "UPDATE entities SET raw_records_json='[{\"id\":\"fixture-001\",\"caption\":\"changed evidence\"}]' WHERE entity_id='fixture-001'"),
    ("group_id", "UPDATE entities SET group_id='changed-fictional-group' WHERE entity_id='fixture-001'"),
    ("alias_text", "UPDATE aliases SET original_name='Changed fictional alias' WHERE property_name='weakAlias'"),
    ("alias_id", "UPDATE aliases SET alias_id='changed-fictional-alias-id' WHERE property_name='weakAlias'"),
    ("alias_property", "UPDATE aliases SET property_name='changedProperty' WHERE property_name='weakAlias'"),
    ("alias_parent", "UPDATE aliases SET entity_id='fixture-003' WHERE property_name='weakAlias'"),
    ("removed_exclusion", "UPDATE aliases SET unsearchable_reason=NULL WHERE property_name='weakAlias'"),
    ("changed_exclusion", "UPDATE aliases SET unsearchable_reason='changed exclusion' WHERE property_name='weakAlias'"),
    ("added_exclusion", "UPDATE aliases SET unsearchable_reason='new exclusion' WHERE alias_id=(SELECT alias_id FROM aliases WHERE property_name='alias' LIMIT 1)"),
    ("deleted_alias", "DELETE FROM aliases WHERE property_name='weakAlias'"),
    ("deleted_entity", "DELETE FROM aliases WHERE entity_id='fixture-002'; DELETE FROM entities WHERE entity_id='fixture-002'"),
    ("added_alias", "INSERT INTO aliases SELECT snapshot_id,entity_id,'extra-fictional-alias','Extra fictional alias','alias','extra fictional alias',NULL FROM entities LIMIT 1"),
    ("added_entity", "INSERT INTO entities SELECT snapshot_id,'extra-fictional-entity',display_name,entity_type,source_schema,source,referents_json,raw_records_json,group_id FROM entities LIMIT 1; INSERT INTO aliases SELECT snapshot_id,'extra-fictional-entity','extra-fictional-alias','Extra fictional alias','name','extra fictional alias',NULL FROM sources"),
]


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("label,sql", CONTENT_MUTATIONS, ids=[item[0] for item in CONTENT_MUTATIONS])
def test_every_entity_alias_and_evidence_change_is_detected(committed_snapshot, operation, label, sql):
    with sqlite3.connect(committed_snapshot) as connection:
        connection.executescript(sql)
    reject_snapshot_unchanged(committed_snapshot, operation)


SOURCE_JSON_FIELDS = (
    [("provenance_json", field) for field in Provenance.__annotations__]
    + [("receipt_json", field) for field in (
        "dataset", "provider", "publisher", "synthetic", "source_url", "download_url", "retrieved_at",
        "raw_sha256", "metadata_sha256", "license", "license_url", "attribution")]
    + [("source_metadata_json", field) for field in ("name", "synthetic", "version", "last_change", "description")]
    + [("selection_json", field) for field in ("limit", "order", "non_person_only")]
    + [("report_json", field) for field in (
        "input_records", "duplicate_id_records", "excluded", "unsearchable_names", "duplicate_alias_values",
        "normalized_collisions", "eligible_entities", "selected_entities", "excluded_by_limit",
        "selected_ids", "stored_aliases", "searchable_aliases")]
)


def altered_json_value(value):
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if isinstance(value, str):
        return value + " changed"
    if isinstance(value, list):
        return value + ["changed-fictional-evidence"]
    return "changed-fictional-metadata"


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("column,field", SOURCE_JSON_FIELDS)
def test_every_recorded_source_metadata_field_is_bound(committed_snapshot, operation, column, field):
    with sqlite3.connect(committed_snapshot) as connection:
        value = json.loads(connection.execute(f"SELECT {column} FROM sources").fetchone()[0])
        assert field in value
        value[field] = altered_json_value(value[field])
        connection.execute(f"UPDATE sources SET {column}=?", (json.dumps(value),))
    reject_snapshot_unchanged(committed_snapshot, operation)


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("column,value", [
    ("dataset", "changed-fictional-dataset"), ("synthetic", 0),
    ("raw_sha256", "0" * 64), ("parser_version", "changed-parser-v99"),
])
def test_scalar_source_columns_are_bound(committed_snapshot, operation, column, value):
    with sqlite3.connect(committed_snapshot) as connection:
        connection.execute(f"UPDATE sources SET {column}=?", (value,))
    reject_snapshot_unchanged(committed_snapshot, operation)


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("damage", ["missing", "hash", "content", "version"])
def test_missing_or_corrupt_manifest_is_not_recreated(committed_snapshot, operation, damage):
    with sqlite3.connect(committed_snapshot) as connection:
        if damage == "missing":
            connection.execute("DELETE FROM snapshot_manifests")
        else:
            column, value = {"hash": ("content_sha256", "0" * 64),
                             "content": ("content_json", "{}"),
                             "version": ("manifest_version", "unknown-v99")}[damage]
            connection.execute(f"UPDATE snapshot_manifests SET {column}=?", (value,))
    reject_snapshot_unchanged(committed_snapshot, operation)


def test_repeat_compares_independent_inputs_even_after_local_manifest_is_resigned(committed_snapshot):
    """A locally consistent digest cannot substitute for source reconstruction."""
    with sqlite3.connect(committed_snapshot) as connection:
        manifest = json.loads(connection.execute("SELECT content_json FROM snapshot_manifests").fetchone()[0])
        row = next(row for row in manifest["tables"]["entities"] if row["entity_id"] == "fixture-001")
        row["display_name"] = "Changed fictional display name"
        connection.execute("UPDATE entities SET display_name=? WHERE entity_id='fixture-001'", (row["display_name"],))
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        connection.execute("UPDATE snapshot_manifests SET content_json=?,content_sha256=?",
                           (encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()))
    reject_snapshot_unchanged(committed_snapshot, "repeat")


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("pragma,value", [
    ("user_version", 0), ("user_version", 1), ("user_version", 2), ("user_version", 99),
    ("application_id", 0), ("application_id", 0x12345678),
])
def test_recognized_shape_with_foreign_identity_is_rejected_unchanged(committed_snapshot, operation, pragma, value):
    with sqlite3.connect(committed_snapshot) as connection:
        connection.execute(f"PRAGMA {pragma}={value}")
    reject_snapshot_unchanged(committed_snapshot, operation)


@pytest.mark.parametrize("kind", ["zero_byte_file", "empty_sqlite", "directory"])
def test_existing_empty_destination_is_not_initialized(tmp_path, kind):
    db = tmp_path / "existing.sqlite"
    if kind == "directory":
        db.mkdir()
    elif kind == "zero_byte_file":
        db.touch()
    else:
        with sqlite3.connect(db) as connection:
            connection.execute("VACUUM")
    db.chmod(0o750 if kind == "directory" else 0o640)
    before = database_files_snapshot(db)
    with pytest.raises(ValueError):
        import_snapshot(FIXTURE, METADATA, db, sample=True)
    assert database_files_snapshot(db) == before


def clone_with_forged_schema(source: Path, target: Path, damage: str) -> None:
    """Keep expected table names, data, version and app ID while weakening DDL."""
    with sqlite3.connect(source) as original, sqlite3.connect(target) as forged:
        original.row_factory = sqlite3.Row
        schema = original.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY rowid").fetchall()
        changed = False
        for row in schema:
            sql = row["sql"]
            if row["name"] == "alias_entity" and damage == "missing_index":
                changed = True
                continue
            if row["type"] == "table" and damage == "all_constraints_missing":
                columns = original.execute(f'PRAGMA table_info("{row["name"]}")').fetchall()
                sql = f'CREATE TABLE "{row["name"]}" (' + ",".join(f'"{column["name"]}" {column["type"]}' for column in columns) + ")"
                changed = True
            if row["name"] == "entities" and damage == "missing_not_null":
                sql, count = re.subn(r"display_name\s+TEXT\s+NOT\s+NULL", "display_name TEXT", sql, flags=re.I)
                changed |= bool(count)
            if row["name"] == "aliases":
                patterns = {
                    "missing_unique": r"UNIQUE\s*\(snapshot_id,\s*entity_id,\s*property_name,\s*original_name\)\s*,",
                    "missing_fk": r"FOREIGN\s+KEY\s*\(snapshot_id,\s*entity_id\)\s*REFERENCES\s+entities\s*\(snapshot_id,\s*entity_id\)\s*,",
                    "missing_check": r",\s*CHECK\s*\(unsearchable_reason\s+IS\s+NOT\s+NULL\s+OR\s+normalized_name\s+IS\s+NOT\s+NULL\)",
                }
                if damage in patterns:
                    sql, count = re.subn(patterns[damage], "", sql, flags=re.I)
                    changed |= bool(count)
            forged.execute(sql)
        for row in schema:
            if row["type"] == "table":
                rows = original.execute(f'SELECT * FROM "{row["name"]}"').fetchall()
                if rows:
                    placeholders = ",".join("?" for _ in rows[0])
                    forged.executemany(f'INSERT INTO "{row["name"]}" VALUES ({placeholders})', [tuple(value) for value in rows])
        extras = {
            "extra_trigger": "CREATE TRIGGER unexpected_trigger AFTER INSERT ON entities BEGIN SELECT 1; END",
            "extra_view": "CREATE VIEW unexpected_view AS SELECT entity_id FROM entities",
            "extra_index": "CREATE INDEX unexpected_index ON entities(display_name)",
            "extra_table": "CREATE TABLE unrelated(note TEXT)",
        }
        if damage in extras:
            forged.execute(extras[damage])
            changed = True
        assert changed, "The test must actually forge the declared schema"
        forged.execute("PRAGMA user_version=3")
        forged.execute(f"PRAGMA application_id={0x50575333}")


@pytest.mark.parametrize("operation", ["load", "repeat"])
@pytest.mark.parametrize("damage", ["all_constraints_missing", "missing_not_null", "missing_unique", "missing_fk",
                                    "missing_check", "missing_index", "extra_trigger", "extra_view", "extra_index", "extra_table"])
def test_forged_expected_tables_and_constraints_are_rejected_before_ddl(committed_snapshot, operation, damage):
    db = committed_snapshot.with_name("forged.sqlite")
    clone_with_forged_schema(committed_snapshot, db, damage)
    db.chmod(0o640)
    reject_snapshot_unchanged(db, operation)


@pytest.mark.parametrize("operation", ["load", "verify", "repeat"])
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("kind", ["regular_file", "dangling_symlink"])
def test_sidecars_are_refused_before_sqlite_opens(committed_snapshot, monkeypatch, operation, suffix, kind):
    sidecar = Path(str(committed_snapshot) + suffix)
    if kind == "regular_file":
        sidecar.write_bytes(b"Fictional unresolved SQLite journal")
        sidecar.chmod(0o640)
    else:
        sidecar.symlink_to(committed_snapshot.with_name("absent-sidecar-target"))
    before = database_files_snapshot(committed_snapshot)

    def unexpected_connection(*_args, **_kwargs):
        pytest.fail("SQLite must not open a database with a sidecar")

    monkeypatch.setattr(database_module.sqlite3, "connect", unexpected_connection)
    with pytest.raises(ValueError, match="sidecar"):
        if operation == "repeat":
            import_snapshot(FIXTURE, METADATA, committed_snapshot, sample=True)
        else:
            (load_database if operation == "load" else database_module.verify_snapshot)(committed_snapshot)
    assert database_files_snapshot(committed_snapshot) == before


@pytest.mark.parametrize("operation", ["load", "verify", "repeat"])
def test_hardlinked_source_is_refused_before_sqlite_opens(committed_snapshot, monkeypatch, operation):
    alias = committed_snapshot.with_name(committed_snapshot.name + ".linked")
    os.link(committed_snapshot, alias)
    before = database_files_snapshot(committed_snapshot)

    def unexpected_connection(*_args, **_kwargs):
        pytest.fail("SQLite must not open a hard-linked database")

    monkeypatch.setattr(database_module.sqlite3, "connect", unexpected_connection)
    with pytest.raises(ValueError, match="hard-linked"):
        if operation == "repeat":
            import_snapshot(FIXTURE, METADATA, committed_snapshot, sample=True)
        else:
            (load_database if operation == "load" else database_module.verify_snapshot)(committed_snapshot)
    assert database_files_snapshot(committed_snapshot) == before


@pytest.mark.parametrize("operation", ["load", "repeat"])
def test_deeply_nested_retained_json_is_a_clean_validation_failure(committed_snapshot, operation):
    depth = sys.getrecursionlimit() + 100
    nested = '{"nested":' + "[" * depth + "0" + "]" * depth + "}"
    with sqlite3.connect(committed_snapshot) as connection:
        connection.execute("UPDATE sources SET source_metadata_json=?", (nested,))
    reject_snapshot_unchanged(committed_snapshot, operation)
