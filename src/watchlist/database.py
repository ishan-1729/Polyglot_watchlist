"""Owned SQLite snapshots with complete logical-content verification.

Source databases must be quiescent: close their writers before reading them.
Any WAL, shared-memory, or rollback-journal sidecar is rejected before SQLite
opens the file. Consolidate a separate copy explicitly if recovery is needed;
this module neither recovers originals nor silently discards committed WAL rows.
"""

from dataclasses import asdict
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

from watchlist.entities import Alias, Entity, Provenance
from watchlist.ingest.parse_opensanctions import PARSER_VERSION, ParsedEntity

APPLICATION_ID = 0x50575333
SCHEMA_VERSION = 3
MANIFEST_VERSION = "watchlist-logical-content-v1"
SELECTION_VERSION = "opensanctions-non-person-provider-id-v1"

_SOURCE_COLUMNS = (
    "snapshot_id", "dataset", "synthetic", "raw_sha256", "parser_version",
    "selection_json", "provenance_json", "receipt_json", "report_json",
    "source_metadata_json",
)
_ENTITY_COLUMNS = (
    "snapshot_id", "entity_id", "display_name", "entity_type", "source_schema",
    "source", "referents_json", "raw_records_json", "group_id",
)
_ALIAS_COLUMNS = (
    "snapshot_id", "entity_id", "alias_id", "original_name", "property_name",
    "normalized_name", "unsearchable_reason",
)

# Historical DDL is a recognition template only; it never initializes a file.
_LEGACY_SCHEMA = """
CREATE TABLE sources (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    dataset TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    raw_sha256 TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    selection_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    report_json TEXT NOT NULL
);
CREATE TABLE entities (
    snapshot_id TEXT NOT NULL REFERENCES sources(snapshot_id),
    entity_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    source_schema TEXT NOT NULL,
    source TEXT NOT NULL,
    referents_json TEXT NOT NULL,
    raw_records_json TEXT NOT NULL,
    group_id TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, entity_id)
);
CREATE TABLE aliases (
    snapshot_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    alias_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    property_name TEXT NOT NULL,
    normalized_name TEXT,
    unsearchable_reason TEXT,
    PRIMARY KEY (snapshot_id, alias_id),
    UNIQUE (snapshot_id, entity_id, property_name, original_name),
    FOREIGN KEY (snapshot_id, entity_id) REFERENCES entities(snapshot_id, entity_id),
    CHECK (unsearchable_reason IS NOT NULL OR normalized_name IS NOT NULL)
);
CREATE INDEX alias_entity ON aliases(snapshot_id, entity_id);
PRAGMA user_version = 2;
"""

# Preserve quoted SQL tokens verbatim, including spaces/case in CHECK literals.
_SQL_TOKENS = re.compile(
    r"--[^\n]*(?:\n|$)|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
    r"`(?:``|[^`])*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]",
    re.DOTALL,
)


def _sql_tokens(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(
        token if token[0] in "'\"`[" else token.lower()
        for token in _SQL_TOKENS.findall(value)
        if not token.startswith(("--", "/*"))
    )


def _schema_signature(connection: sqlite3.Connection) -> tuple:
    """Describe all schema objects, columns, indexes, and foreign-key rules."""
    objects = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name"
    ).fetchall()
    signature: list[tuple] = []
    for kind, name, table, sql in objects:
        signature.append(("object", kind, name, table, _sql_tokens(sql)))
        # Table-valued PRAGMAs safely bind even untrusted object names.
        if kind == "table":
            for pragma in ("table_xinfo", "foreign_key_list", "index_list"):
                rows = connection.execute(f"SELECT * FROM pragma_{pragma}(?)", (name,))
                signature.append((pragma, name, tuple(tuple(row) for row in rows)))
        elif kind == "index":
            rows = connection.execute("SELECT * FROM pragma_index_xinfo(?)", (name,))
            signature.append(("index_xinfo", name, tuple(tuple(row) for row in rows)))
    return tuple(signature)


def _current_schema() -> str:
    return files("watchlist.ingest").joinpath("schema.sql").read_text(encoding="utf-8")


@lru_cache(maxsize=2)
def _expected_schema(version: int) -> tuple:
    """Build recognition templates in memory, never in a supplied database."""
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(_LEGACY_SCHEMA if version == 2 else _current_schema())
        return _schema_signature(connection)
    finally:
        connection.close()


def _recognize_schema(connection: sqlite3.Connection, *, legacy: bool = False) -> None:
    """Require the precise owned format before reading application rows."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    application = connection.execute("PRAGMA application_id").fetchone()[0]
    if not legacy and version == 2 and application == 0:
        if _schema_signature(connection) != _expected_schema(2):
            raise ValueError("incomplete or unrecognized legacy source database schema/constraints")
        raise ValueError(
            "legacy source database schema v2 requires explicit verified migration; "
            "use python -m watchlist.ingest.migrate_source with the original "
            "source, metadata, and receipt, and a new destination"
        )
    wanted_version, wanted_application = (2, 0) if legacy else (SCHEMA_VERSION, APPLICATION_ID)
    if version != wanted_version or application != wanted_application:
        raise ValueError("unsupported or foreign watchlist database schema/application identity")
    if _schema_signature(connection) != _expected_schema(wanted_version):
        raise ValueError("incomplete or unrecognized watchlist database schema/constraints")


def _reject_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError(
                f"source database has a SQLite sidecar ({suffix}); close writers and "
                "explicitly consolidate a separate copy before verification or migration"
            )


def connect_database(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    """Connect without schema initialization; immutable reads reject sidecars.

    The writable form is a low-level helper for private new-file transactions
    and explicit local tests. Import/load entry points recognize ownership before
    they use application data. Immutable reads require a quiescent source file.
    """
    path = Path(path)
    if readonly:
        _reject_sidecars(path)
        if path.is_symlink():
            raise ValueError("source database must be a regular file, not a symbolic link")
        if path.exists() and path.stat().st_nlink != 1:
            raise ValueError("source database must not be hard-linked; verify a separate regular copy")
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        connection.execute("PRAGMA query_only = ON")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def check_integrity(connection: sqlite3.Connection) -> None:
    """Fail on storage corruption or orphaned aliases instead of serving them."""
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    if len(rows) != 1 or rows[0][0] != "ok":
        raise ValueError("SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("SQLite foreign key check failed")


def _canonical(value: object) -> str:
    """Canonical finite JSON preserves strings while ignoring object-key order."""
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("snapshot content must contain UTF-8 finite JSON values") from exc
    return result


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("snapshot JSON contains a duplicate object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"snapshot JSON contains nonfinite number {value}")


def _decode_json(value: str) -> object:
    try:
        decoded = json.loads(value, object_pairs_hook=_object_pairs,
                             parse_constant=_invalid_constant)
        _canonical(decoded)
        return decoded
    except (TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("snapshot contains invalid JSON content") from exc


def _manifest(tables: dict[str, list[dict]], *, legacy: bool) -> dict:
    aliases = tables["aliases"]
    return {
        "manifest_version": MANIFEST_VERSION,
        "schema_version": 2 if legacy else SCHEMA_VERSION,
        "selection_version": SELECTION_VERSION,
        "counts": {
            "sources": len(tables["sources"]), "entities": len(tables["entities"]),
            "aliases": len(aliases),
            "searchable_aliases": sum(row["unsearchable_reason"] is None for row in aliases),
            "unsearchable_aliases": sum(row["unsearchable_reason"] is not None for row in aliases),
        },
        "tables": tables,
    }


def _logical_content(connection: sqlite3.Connection, *, legacy: bool = False) -> dict:
    """Read every column, decoding retained JSON into canonical logical values."""
    tables = {}
    layouts = (
        ("sources", _SOURCE_COLUMNS[:-1] if legacy else _SOURCE_COLUMNS, "snapshot_id"),
        ("entities", _ENTITY_COLUMNS, "snapshot_id, entity_id"),
        ("aliases", _ALIAS_COLUMNS, "snapshot_id, alias_id"),
    )
    for table, columns, ordering in layouts:
        rows = connection.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {ordering}")
        values = []
        for row in rows:
            item = dict(row)
            for column, value in item.items():
                if column.endswith("_json"):
                    if not isinstance(value, str):
                        raise ValueError(f"{table}.{column} must contain JSON text")
                    decoded = _decode_json(value)
                    expected = list if column in {"referents_json", "raw_records_json"} else dict
                    if not isinstance(decoded, expected):
                        raise ValueError(f"{table}.{column} has invalid logical content")
                    item[column] = decoded
                elif column == "synthetic":
                    if type(value) is not int or value not in (0, 1):
                        raise ValueError("source synthetic marker must be zero or one")
                elif value is None and column in {"normalized_name", "unsearchable_reason"}:
                    continue
                elif not isinstance(value, str):
                    raise ValueError(f"{table}.{column} must contain text")
            values.append(item)
        tables[table] = values
    return _manifest(tables, legacy=legacy)


def _expected_content(
    provenance: Provenance, records: list[ParsedEntity], *, receipt: dict,
    selection: dict, report: dict, source_metadata: dict | None, legacy: bool = False,
) -> dict:
    """Build expected logical rows directly from independently parsed inputs."""
    if type(receipt.get("synthetic")) is not bool:
        raise ValueError("source receipt synthetic marker must be a boolean")
    source = dict(zip(_SOURCE_COLUMNS, (
        provenance.snapshot_id, provenance.dataset, int(receipt["synthetic"]),
        provenance.raw_sha256, PARSER_VERSION, selection, asdict(provenance),
        receipt, report, {} if source_metadata is None else source_metadata,
    )))
    if legacy:
        del source["source_metadata_json"]
    entities, aliases = [], []
    for record in records:
        entity = record.entity
        entities.append(dict(zip(_ENTITY_COLUMNS, (
            provenance.snapshot_id, entity.entity_id, entity.name, entity.entity_type,
            record.schema, entity.source, list(record.referents),
            [_decode_json(value) for value in record.raw_records], record.group_id,
        ))))
        aliases.extend(dict(zip(_ALIAS_COLUMNS, (
            provenance.snapshot_id, entity.entity_id, alias.alias_id, alias.name,
            alias.property_name, alias.normalized, alias.unsearchable_reason,
        ))) for alias in record.aliases)
    content = _manifest({
        "sources": [source],
        "entities": sorted(entities, key=lambda row: (row["snapshot_id"], row["entity_id"])),
        "aliases": sorted(aliases, key=lambda row: (row["snapshot_id"], row["alias_id"])),
    }, legacy=legacy)
    # Detach caller-owned mappings and reject unsupported values before writing.
    return json.loads(_canonical(content))


def _validate_content(content: dict) -> None:
    """Check minimum record/provenance relationships after complete row loading."""
    tables, counts = content["tables"], content["counts"]
    if counts["sources"] != 1:
        raise ValueError("database must contain exactly one committed source snapshot")
    if not counts["entities"] or not counts["aliases"]:
        raise ValueError("database must contain nonempty entity and alias content")
    source = tables["sources"][0]
    provenance, receipt, report = (source[key] for key in
                                    ("provenance_json", "receipt_json", "report_json"))
    try:
        Provenance(**provenance)
    except TypeError as exc:
        raise ValueError("source provenance fields do not match the supported format") from exc
    if (any(source[key] != provenance.get(key) for key in ("snapshot_id", "dataset", "raw_sha256"))
        or receipt.get("dataset") != source["dataset"]
        or type(receipt.get("synthetic")) is not bool
        or int(receipt["synthetic"]) != source["synthetic"]
        or receipt.get("raw_sha256") != source["raw_sha256"]
        or source["parser_version"] != PARSER_VERSION):
        raise ValueError("source content and provenance/receipt disagree")
    if "source_metadata_json" in source:
        metadata = source["source_metadata_json"]
        if (metadata.get("name") != source["dataset"]
            or metadata.get("last_change") != provenance["source_updated_at"]
            or metadata.get("version") != provenance["export_version"]):
            raise ValueError("source metadata is missing or differs from stored provenance")
    expected_counts = {
        "selected_entities": counts["entities"], "stored_aliases": counts["aliases"],
        "searchable_aliases": counts["searchable_aliases"],
    }
    if any(type(report.get(key)) is not int or report[key] != value
           for key, value in expected_counts.items()):
        raise ValueError("source report counts differ from stored content")
    selected = [row["entity_id"] for row in tables["entities"]]
    if report.get("selected_ids") != selected:
        raise ValueError("source report selection differs from stored entities")
    if any(row["snapshot_id"] != source["snapshot_id"]
           for table in ("entities", "aliases") for row in tables[table]):
        raise ValueError("database contains rows from another source snapshot")
    searchable = {row["entity_id"] for row in tables["aliases"]
                  if row["unsearchable_reason"] is None}
    if searchable != set(selected):
        raise ValueError("each retained entity must have searchable aliases")


def _verified_content(connection: sqlite3.Connection) -> dict:
    _recognize_schema(connection)
    check_integrity(connection)
    content = _logical_content(connection)
    _validate_content(content)
    manifests = connection.execute("SELECT * FROM snapshot_manifests").fetchall()
    if len(manifests) != 1:
        raise ValueError("database must contain exactly one content manifest")
    row = manifests[0]
    encoded = _canonical(content)
    if (row["snapshot_id"] != content["tables"]["sources"][0]["snapshot_id"]
        or row["manifest_version"] != MANIFEST_VERSION
        or row["content_json"] != encoded
        or row["content_sha256"] != hashlib.sha256(encoded.encode("utf-8")).hexdigest()):
        raise ValueError("source content manifest verification failed")
    return content


def _summary(content: dict, *, legacy: bool = False) -> dict:
    return {
        "status": "legacy_compared" if legacy else "verified",
        "snapshot_id": content["tables"]["sources"][0]["snapshot_id"],
        "manifest_version": MANIFEST_VERSION,
        "content_sha256": hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest(),
        "counts": dict(content["counts"]),
        "source_metadata_retained": not legacy,
    }


def _read_content(path: Path, *, legacy: bool = False) -> dict:
    """Read once and reject ordinary concurrent replacement/modification.

    Stat checks and a second sidecar check detect normal local writer activity.
    They do not provide an adversarial filesystem lock: callers must stop all
    writers, and hashes kept beside data are not independently authenticated.
    """
    _reject_sidecars(path)
    before = path.stat() if path.exists() else None
    if before is not None and not stat.S_ISREG(before.st_mode):
        raise ValueError("source database must be a regular file")
    connection = connect_database(path, readonly=True)
    try:
        if legacy:
            _recognize_schema(connection, legacy=True)
            check_integrity(connection)
            content = _logical_content(connection, legacy=True)
            _validate_content(content)
        else:
            content = _verified_content(connection)
    finally:
        connection.close()
    _reject_sidecars(path)
    after = path.stat()
    if before is None or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                          before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                                  after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("source database changed during verification; stop writers and retry")
    return content


def _compare_content(actual: dict, expected: dict) -> None:
    actual_id = actual["tables"]["sources"][0]["snapshot_id"]
    if actual_id != expected["tables"]["sources"][0]["snapshot_id"]:
        raise ValueError("database contains another snapshot; use a new database path")
    if _canonical(actual) != _canonical(expected):
        raise ValueError("stored content differs from independently expected parsed records or metadata")


def verify_snapshot(path: Path) -> dict:
    """Verify owned v3 schema, integrity, every logical value, and saved manifest.

    The manifest detects unreconciled changes; an attacker able to replace both
    rows and manifest can rewrite it. Reimport independently compares supplied
    receipt-verified source records, and v2 requires the explicit compare adapter.
    """
    return _summary(_read_content(Path(path)))


def compare_legacy_snapshot(
    path: Path, provenance: Provenance, records: list[ParsedEntity], *,
    receipt: dict, selection: dict, report: dict, source_metadata: dict,
) -> dict:
    """Compare every v2 column to independently rebuilt receipt-verified input.

    This adapter never blesses a legacy digest or changes a legacy file. The
    caller must hash and parse the same retained input bytes before calling.
    V2 did not retain the complete metadata object: its receipt hash and the
    metadata fields represented in provenance are compared; new v3 retains it.
    """
    expected = _expected_content(provenance, records, receipt=receipt, selection=selection,
                                 report=report, source_metadata=source_metadata, legacy=True)
    if (source_metadata.get("name") != provenance.dataset
        or source_metadata.get("last_change") != provenance.source_updated_at
        or source_metadata.get("version") != provenance.export_version):
        raise ValueError("supplied source metadata differs from expected provenance")
    actual = _read_content(Path(path), legacy=True)
    _compare_content(actual, expected)
    return _summary(actual, legacy=True)


def _insert_rows(connection: sqlite3.Connection, content: dict) -> None:
    """Insert actual rows; SQL constraints remain the authority on duplicates."""
    for table, columns in (("sources", _SOURCE_COLUMNS), ("entities", _ENTITY_COLUMNS),
                           ("aliases", _ALIAS_COLUMNS)):
        for row in content["tables"][table]:
            values = tuple(_canonical(row[key]) if key.endswith("_json") else row[key]
                           for key in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(f"INSERT INTO {table} VALUES ({placeholders})", values)


def write_snapshot(
    path: Path, provenance: Provenance, records: list[ParsedEntity], *,
    receipt: dict, selection: dict, report: dict, source_metadata: dict | None = None,
) -> bool:
    """Publish a new v3 file, or verify a complete identical snapshot read-only.

    Only an absent destination can be initialized. Existing foreign, partial,
    legacy, or unsupported databases are rejected before DDL. A private sibling
    file holds the transaction; an exclusive hard-link publication cannot
    overwrite a destination created concurrently. No sidecars are accepted.
    Successful v3 writes require source_metadata. The optional default preserves
    the legacy low-level call shape; missing metadata fails before publication.
    """
    path = Path(path)
    expected = _expected_content(provenance, records, receipt=receipt, selection=selection,
                                 report=report, source_metadata=source_metadata)
    _reject_sidecars(path)
    if path.exists() or path.is_symlink():
        _compare_content(_read_content(path), expected)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    published_identity: tuple[int, int] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=".watchlist-import-", dir=path.parent) as staging:
            staged = Path(staging) / "snapshot.sqlite"
            connection = connect_database(staged)
            try:
                if (connection.execute("PRAGMA user_version").fetchone()[0] != 0
                    or connection.execute("PRAGMA application_id").fetchone()[0] != 0
                    or connection.execute("SELECT 1 FROM sqlite_schema").fetchone() is not None):
                    raise ValueError("new snapshot destination is not empty")
                connection.executescript("BEGIN IMMEDIATE;\n" + _current_schema())
                _recognize_schema(connection)
                _insert_rows(connection, expected)
                encoded = _canonical(expected)
                connection.execute("INSERT INTO snapshot_manifests VALUES (?, ?, ?, ?)", (
                    provenance.snapshot_id, MANIFEST_VERSION, encoded,
                    hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                ))
                _compare_content(_verified_content(connection), expected)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            _compare_content(_read_content(staged), expected)
            _reject_sidecars(path)
            info = staged.stat()
            published_identity = (info.st_dev, info.st_ino)
            # os.link fails if any destination entry (including a symlink) exists.
            os.link(staged, path, follow_symlinks=False)
    except BaseException:
        # Cleanup may fail after publication; remove only our own new inode.
        if published_identity is not None:
            try:
                info = path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (info.st_dev, info.st_ino) == published_identity:
                    path.unlink()
        raise
    return True


def load_database(path: Path) -> tuple[tuple[Entity, ...], Provenance, bool]:
    """Adapt only verified v3 logical rows to the matcher's typed record view."""
    content = _read_content(Path(path))
    tables = content["tables"]
    source = tables["sources"][0]
    provenance = Provenance(**source["provenance_json"])
    synthetic = bool(source["synthetic"])
    aliases: dict[str, list[Alias]] = {}
    for row in tables["aliases"]:
        if row["unsearchable_reason"] is None:
            aliases.setdefault(row["entity_id"], []).append(Alias(row["alias_id"], row["original_name"]))
    entities = tuple(Entity(
        row["entity_id"], row["display_name"], row["entity_type"],
        tuple(aliases[row["entity_id"]]), synthetic, row["source"], provenance,
    ) for row in tables["entities"])
    return entities, provenance, synthetic
