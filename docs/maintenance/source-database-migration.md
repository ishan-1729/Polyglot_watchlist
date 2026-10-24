# Verify and rebuild a saved source database

The source loader now accepts only the owned **v3** format. A historical v2
database must first be compared with its original saved input, metadata and
receipt. A rebuild creates a separate v3 database; it never upgrades the original
in place. These operations are offline and load no model.

This is a research prototype for possible record matches and human review.
Verification establishes consistency of the supplied evidence, not identity,
wrongdoing, model accuracy, or permission for a new use of public data.

## What the checks mean

| Question | Explanation |
| --- | --- |
| What? | A **logical content manifest** is a deterministic description and SHA-256 fingerprint of every retained source, entity and alias value. v3 stores it beside the rows. |
| Why? | SQLite's own integrity checks can pass after a valid SQL edit changes a name or evidence field. Comparing all rows with the manifest detects an unreconciled edit. |
| When? | v3 loads and repeated imports verify the manifest. A v2 rebuild additionally reconstructs expected rows from the original supplied inputs before creating a new file. |
| Where? | All input, staging and output files remain on the local filesystem. Private staging is created below the already existing output parent. |
| Who? | A researcher runs an explicitly chosen verification or rebuild. A successful check does not replace human review. |
| How? | Check bounded input buffers and receipt hashes, reproduce the original parser and selection, recognize the exact v2 schema, compare every retained logical value, then write and verify a new v3 file. |

v3 has `PRAGMA user_version = 3`, application ID `0x50575333`, and a
`watchlist-logical-content-v1` manifest with selection contract
`opensanctions-non-person-provider-id-v1`. Complete schema recognition checks tables,
columns, indexes, constraints and other schema objects before application data is
accepted. Neither a familiar table name nor a familiar version number is enough.
v2 verification requires the exact historical schema, version 2 and application
ID 0. The original snapshot ID, selected records and parser semantics stay the
same during a successful rebuild.

The manifest covers source provenance, receipt, selection and import report;
all entity fields, retained raw records, referents and grouping; all alias fields,
including normalization and reasons a name is excluded from retrieval; and the
complete parsed metadata object retained by v3. The legacy format did not retain
that complete metadata object. Its supplied metadata is instead checked against
the original receipt hash and its retained provenance fields before v3 stores it.

## Before running

- Stop all writers to the selected source database and keep the supplied inputs
  stable throughout the operation. Read-only checks may update filesystem access
  times, but they do not change original bytes, modes or SQLite versions.
- Source databases must be regular files with exactly one hardlink. A hardlinked
  database can have SQLite sidecars under another filename, so it is rejected
  instead of assuming those hidden changes do not exist. Source symlinks are
  rejected too.
- Supply the original raw export and metadata, plus the acquisition receipt for
  public-source mode. Keep the original selection limit; its default is 20.
- `-wal`, `-shm` and `-journal` sidecars cause rejection, including empty sidecars.
  They can contain unresolved state. Do not delete them to bypass a check. Any
  needed recovery or consolidation must be an explicit operation on a separate
  copy; this command does not perform recovery.
- Choose a completely absent output file below an existing real directory. The
  output cannot be an existing file, directory, hardlink or dangling symlink.
  Symlink ancestors, parent traversal and pre-existing output sidecars are also
  rejected. The command does not create missing parent directories.
- Use the existing environment. No installation, acquisition, network access,
  API key or model inference is needed. The raw export is bounded to 10 MiB;
  metadata and receipt are each bounded to 1 MiB.

## Public-source format: explicit saved local evidence

Run these commands from the repository root. They refer only to the saved local
subset and its original receipt; they do not fetch a newer source or establish
current license permission. Use public data only within its applicable terms and
the already approved purpose.

First verify the preserved original:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m watchlist.ingest.migrate_source verify \
  --legacy data/watchlist.sqlite \
  --input data/raw/un_sc_sanctions/entities.ftm.json \
  --metadata data/raw/un_sc_sanctions/index.json \
  --receipt data/manifests/source.json \
  --limit 20
```

Create a dedicated parent directory once, if it does not already exist:

```sh
mkdir -m 700 data/source-v3
```

Then request a distinct output:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m watchlist.ingest.migrate_source rebuild \
  --legacy data/watchlist.sqlite \
  --input data/raw/un_sc_sanctions/entities.ftm.json \
  --metadata data/raw/un_sc_sanctions/index.json \
  --receipt data/manifests/source.json \
  --limit 20 \
  --output data/source-v3/watchlist.sqlite
```

`rebuild` repeats all verification itself, so the preceding `verify` is a useful
inspection step rather than a prerequisite token or approval. A second rebuild
to the same output fails instead of overwriting it. If a verification mismatch
occurs, keep the evidence and investigate it; the command cannot repair or bless
changed v2 content by hashing whatever rows happen to remain.

## Explicit fictional mode

For the historical authored fixture database, pass `--sample` and the original
fictional input and metadata. Unlike the importer shortcut, migration always
requires explicit `--input` and `--metadata` paths. Sample mode reconstructs the
historical fictional receipt, so the CLI rejects a supplied `--receipt`.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m watchlist.ingest.migrate_source verify \
  --sample \
  --legacy data/sample.sqlite \
  --input tests/fixtures/opensanctions_synthetic.ftm.json \
  --metadata tests/fixtures/opensanctions_synthetic.metadata.json \
  --limit 20

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m watchlist.ingest.migrate_source rebuild \
  --sample \
  --legacy data/sample.sqlite \
  --input tests/fixtures/opensanctions_synthetic.ftm.json \
  --metadata tests/fixtures/opensanctions_synthetic.metadata.json \
  --limit 20 \
  --output data/source-v3/sample.sqlite
```

Success prints JSON with `status` (`verified` or `rebuilt`), the unchanged
`snapshot_id`, manifest version, logical content digest, counts and an explicit
trust limitation. `verified` here means the **legacy content matched supplied
inputs**; it does not add a manifest to v2 or make it loadable by the normal v3
loader. `source_metadata_retained` is false for the legacy comparison and true
for the rebuilt v3 output. The logical digest changes between legacy and v3
because v3 includes its schema version and full metadata object.

For Python callers, the corresponding entry points are:

```python
from pathlib import Path
from watchlist.ingest.migrate_source import rebuild_legacy, verify_legacy

options = {
    "limit": 20,
    "sample": True,
}
checked = verify_legacy(
    Path("data/sample.sqlite"),
    Path("tests/fixtures/opensanctions_synthetic.ftm.json"),
    Path("tests/fixtures/opensanctions_synthetic.metadata.json"),
    **options,
)
```

`rebuild_legacy` accepts the same first three paths, followed by the new output
path; public mode also requires `receipt_path=Path(...)`.

## Publication, repeated imports and compatibility

Rebuilding first compares v2 against independently reconstructed input. Only then
does it create private staging, write v3 and verify its contents. The final
publication uses a hardlink that fails if the destination already exists,
including if another process creates that path after preflight. Staging is
removed on failure. If publication succeeds and a subsequent cleanup step fails,
the command removes the output only when its inode is still the one it created;
an independently created destination is preserved. This assumes a quiescent
local workspace, not hostile concurrent filesystem manipulation. It is not an
OS snapshot or a power-loss durability guarantee.

The rebuilt file is a different inode from every supplied original. No readable
sample/report side exports are created by migration. The ordinary importer
creates those exports only for a successful new public import. A fully verified
identical v3 reimport is a no-op: it does not touch the database, exports or their
permissions/timestamps, and it does not repair missing or altered exports.
Existing empty, foreign, malformed or legacy destinations are rejected by that
import path before schema changes.

Selecting a new source database for later matching is explicit. This migration
does not rewrite review archives, pending cases, model recipes, evaluation
results or historical source/workflow fingerprints. Those stores retain their
own compatibility rules; no successful source rebuild authorizes their migration.

## Trust limits and verification tests

Receipt hashes bind raw and metadata bytes to a **supplied local receipt**.
They are not signatures or independent provider authentication. A person able to
replace the database, receipt and original inputs together can produce another
consistent set. A v3 manifest detects edits that have not also been reconciled
with its stored manifest; independently supplied input is still needed to check
against the original acquisition evidence. No current licensing or operational
screening guarantee follows from a matching hash.

The tests construct their own historical v2 databases from fictional records;
they do not mutate saved original databases. Run the focused checks with:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q \
  tests/test_source_migration.py tests/test_ingest.py tests/test_database.py
```

The phase progress report records the actual test results and any separately
approved saved-source verification. Commands in this guide are usage examples,
not evidence that a particular saved source has passed.
