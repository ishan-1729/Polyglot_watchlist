-- A database contains one explicitly selected snapshot. Composite keys keep
-- every alias attached to the same snapshot and entity as its parent.
CREATE TABLE sources (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    dataset TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    raw_sha256 TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    selection_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    source_metadata_json TEXT NOT NULL
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

-- The manifest binds logical rows, independent of SQLite page layout. It is
-- an integrity check, not a signature against someone replacing rows and hash.
CREATE TABLE snapshot_manifests (
    snapshot_id TEXT PRIMARY KEY NOT NULL REFERENCES sources(snapshot_id),
    manifest_version TEXT NOT NULL,
    content_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    )
);

PRAGMA application_id = 0x50575333;
PRAGMA user_version = 3;
