PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cases (
 audit_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL UNIQUE,
 initial_json TEXT NOT NULL, parent_audit_id TEXT REFERENCES cases(audit_id)
);
CREATE TABLE IF NOT EXISTS review_packets (
 audit_id TEXT NOT NULL REFERENCES cases(audit_id), revision INTEGER NOT NULL CHECK(revision=1),
 packet_json TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(audit_id, revision)
);
CREATE TABLE IF NOT EXISTS review_submissions (
 submission_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL, revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL, sha256 TEXT NOT NULL,
 UNIQUE(audit_id, revision),
 FOREIGN KEY(audit_id, revision) REFERENCES review_packets(audit_id, revision)
);
CREATE TABLE IF NOT EXISTS audit_events (
 audit_id TEXT NOT NULL REFERENCES cases(audit_id), sequence INTEGER NOT NULL,
 event_key TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
 previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL,
 PRIMARY KEY(audit_id, sequence), UNIQUE(audit_id, event_key)
);
PRAGMA user_version = 1;
PRAGMA application_id = 0x50575231;
