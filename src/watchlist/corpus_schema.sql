-- Candidate preparation evidence only; this is not a reviewed corpus schema.
PRAGMA application_id = 1347896113;
PRAGMA user_version = 2;
PRAGMA foreign_keys = ON;

CREATE TABLE candidate_manifest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    manifest_json BLOB NOT NULL,
    logical_sha256 TEXT NOT NULL CHECK (length(logical_sha256) = 64)
) STRICT;

CREATE TABLE candidate_sources (
    snapshot_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    selection_sha256 TEXT NOT NULL,
    receipt_sha256 TEXT NOT NULL,
    permission_sha256 TEXT NOT NULL,
    selection_bytes BLOB NOT NULL,
    receipt_bytes BLOB NOT NULL,
    permission_bytes BLOB NOT NULL,
    receipt_format TEXT NOT NULL CHECK (receipt_format IN ('source-acquisition-v1', 'fictional-full-acquisition-v1', 'real-full-acquisition-v1'))
) STRICT;

CREATE TABLE candidate_permission_evidence (
    snapshot_id TEXT NOT NULL REFERENCES candidate_sources(snapshot_id),
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY (snapshot_id, path)
) STRICT;

CREATE TABLE candidate_observations (
    observation_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES candidate_sources(snapshot_id),
    source_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('organization', 'vessel')),
    primary_name TEXT NOT NULL,
    provider_schema TEXT NOT NULL,
    classification_basis TEXT,
    referents_json BLOB NOT NULL,
    provider_datasets_json BLOB NOT NULL,
    provider_topics_json BLOB NOT NULL,
    source_role TEXT NOT NULL CHECK (source_role IN ('sanctions_reference', 'supplemental_unlabelled')),
    UNIQUE (snapshot_id, source_id, provider_id)
) STRICT;

CREATE TABLE candidate_names (
    evidence_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES candidate_observations(observation_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    value TEXT NOT NULL,
    field TEXT NOT NULL,
    language TEXT,
    attributes_json BLOB NOT NULL,
    UNIQUE (observation_id, ordinal)
) STRICT;
