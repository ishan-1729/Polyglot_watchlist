# Phase 2 completion report — public ingestion and SQLite

Date: 2026-10-21 local (Asia/Kolkata). Phase 2 Step B was explicitly approved. Phase 3 has not begun.

## Outcome and acceptance evidence

Phase 1 supplied 12 fictional entities and 24 aliases, normalization, a RapidFuzz character-similarity baseline, and a CLI. Phase 2 gives that same matcher a second data source: a frozen, traceable SQLite snapshot. The fictional default is retained. No libraries, models, training, API keys or services were added. No Git initialization, commits, or publishing were performed.

| Acceptance criterion | Actual evidence |
|---|---|
| One approved small source | UN-only OpenSanctions export: 3,026,171 bytes; metadata: 6,523 bytes, within approved caps |
| Small reproducible selection | 20 of 269 eligible non-person records from 2,918 input objects; 79 searchable names |
| Preserve scripts/source | All 20 selected records' name/property sets matched the stored originals; provenance accompanies results |
| Database integrity | SQLite `integrity_check`: `ok`; foreign-key violations: 0 |
| Repeat import | `created: false`, same snapshot, still 20 entities and 79 aliases |
| Original mode works | Fictional `Luma Vespr` retrieved `syn-001` at 90.9090909090909 with top-k 1 |
| Offline fixture mode | 3 entities, 8 stored aliases, 7 searchable aliases; one weak alias retained but excluded |
| Tests | Baseline 68 passed in 0.44s; intermediate 105 passed in 0.57s; final suite 110 passed in 0.85s |
| Packaging | Offline uv wheel build succeeded; inspected wheel contains schema.sql and original fictional JSON |
| Group partitions | Seed 42: train 7, development 3, calibration_fit 2, threshold_selection 2, test 6 |

These are software behavior checks and row counts, not retrieval-quality metrics. No Recall@k, false-positive performance, calibration or runtime benchmarks were computed.

## 5W1H: the whole phase

- **What:** a bounded download command, offline parser, conservative deduplication, three-table database, stable group partitions, and a database-backed version of the existing CLI.
- **Why:** a suggested record is useful only if we can trace its names to a known source version and reproduce the selection. Related aliases must not later leak into different evaluation partitions.
- **Who:** OpenSanctions supplies standardized records sourced from the UN; the learner runs the prototype; a human reviews its suggestions. Neither the code nor the provider ID independently establishes identity or criminality.
- **When:** acquire only after source/network approval; import and query locally afterward; prepare splits before future evaluation. A source date, export date and retrieval date are different facts.
- **Where:** code under `src/watchlist/`, authored fixtures/tests under `tests/`, documentation under `docs/`, local ignored source/database/manifests under `data/`.
- **How:** preserve frozen bytes and hashes → parse/validate → resolve same IDs and explicit referents → select ≤20 records → commit SQLite → load names into the unchanged RapidFuzz scorer → show ranked records and provenance for human review.

See the [data card](../data-card.md) for terms and exact dates/hashes; the [decision record](../adr/0001-data-and-splits.md) explains SQLite keys, the Mermaid DAG and why feedback across runs differs from a request-level DAG.

## Every changed application file, with important statements explained

### `src/watchlist/ingest/__init__.py`

Declares the ingestion package. Its docstring describes the package; importing it performs no downloads.

### `src/watchlist/ingest/fetch_source.py`

`DATASET`, `BASE_URL` and byte-limit constants constrain the single approved source. `read_bounded` creates an HTTPS request with a descriptive user agent and 30-second timeout; it checks the final destination, optional Content-Length, and actual bytes read. Reading at most the remaining allowance plus one byte lets it detect oversized responses even without a length header. `fetch_snapshot` refuses existing outputs, fetches metadata and export, checks the provider SHA-1 when supplied, and computes local SHA-256 hashes. The receipt records source, retrieval time, license and attribution before files are saved. `main` parses the explicit download command and turns expected failures into readable CLI errors. SHA-1 here checks agreement with provider metadata; SHA-256 records our local frozen bytes. Neither validates identity. The redirect destination check occurs after urllib follows a redirect; this is not a general outbound-network sandbox. The three acquisition files are not one atomic filesystem transaction; a disk-write failure could require inspecting/removing incomplete outputs before an approved retry.

Navigation: `read_bounded` (line 18), `fetch_snapshot` (line 38), `main` (line 93). Line numbers refer to this completed version.

### `src/watchlist/ingest/deduplicate.py`

`NAME_PROPERTIES` lists the three fields handled as names. `deduplicate_records` validates IDs, schema and property types; `deepcopy` avoids changing the input objects. `by_id` indexes records by provider ID. For a repeated ID it removes name fields from temporary copies, compares the remaining metadata, rejects disagreement, and otherwise unions names with a set. Sorting IDs and name unions makes ordering predictable. `reference_groups` tracks connected ID/referent links with a parent dictionary; nested `root` follows and shortens those links. Choosing the smaller root gives a stable label. No comparison of names enters this grouping.

Navigation: `deduplicate_records` (line 8), `reference_groups` (line 50). Line numbers refer to this completed version.

### `src/watchlist/ingest/parse_opensanctions.py`

`StoredAlias` is an immutable container for original text, property, normalized text and an exclusion reason. `ParsedEntity` keeps both the matcher view and original evidence. `read_records` reads one JSON object per line and reports malformed line numbers. `parse_records` rejects limits outside 1–20 (including booleans), consolidates IDs, and resolves provider groups before selection. It serializes original record content without discarding Unicode. Schema, sanction-topic and dataset-membership checks choose the supported records. The nested property/name loops preserve each distinct original value; hashing ID/property/text creates a stable alias key. The existing normalizer is called in a try/except: unsuitable strings get a reason rather than disappearing. `weakAlias` always gets an exclusion reason. A collision is recorded when two original spellings normalize alike. `usable` contains only searchable aliases, ordered by ID. Missing captions use a usable name; no usable names means exclusion. `eligible[:limit]` selects the first IDs after sorting, and the report records exclusions and counts. `LegalEntity` remains a broad type. Original raw records remain available even when names are consolidated.

Navigation: `StoredAlias` (line 17), `ParsedEntity` (line 28), `read_records` (line 39), `parse_records` (line 56). Line numbers refer to this completed version.

### `src/watchlist/ingest/schema.sql`

`CREATE TABLE IF NOT EXISTS` defines sources, entities and aliases. `PRIMARY KEY` makes row identities unique; composite keys include snapshot identity. `FOREIGN KEY` prevents aliases without an entity and entities without a source. `CHECK` constrains synthetic flags and requires either normalized text or an exclusion reason. `UNIQUE` prevents duplicate original values for one entity/property. The alias index speeds fetching one entity's spellings. `PRAGMA user_version = 2` marks this schema so the loader can reject incompatible databases. Original text and normalized text are separate columns: display evidence is never overwritten by normalization.

### `src/watchlist/ingest/import_source.py`

`import_snapshot` reads frozen files and hashes their bytes. Sample mode requires an explicitly fictional metadata marker; public mode checks dataset, license link, and both hashes against the acquisition receipt. `parse_records` supplies validated records and diagnostics. A JSON fingerprint combines raw hash, parser version, selection, sample flag and metadata hash into the snapshot ID. `Provenance` packages source fields, preserving absent dates as null. `write_snapshot` handles the database transaction. Public sample/report files are readable exports written afterward; the authoritative report is already inside SQLite. `main` prevents mixing sample and public arguments, requires public input/metadata, and catches expected I/O, validation and SQLite errors. `--organisations-only` documents an always-enforced restriction; omitting the flag does not enable people. The sample CLI expects fixtures relative to the checkout, whereas the Python function accepts explicit paths.

Navigation: `import_snapshot` (line 16), `main` (line 96). Line numbers refer to this completed version.

### `src/watchlist/database.py`

`connect_database` uses a read-only URI for queries, so a typo cannot silently create an empty database; writable mode creates its parent directory. `sqlite3.Row` allows readable column-name access. Every connection enables foreign keys. `check_integrity` runs both database and foreign-key checks. `write_snapshot` loads packaged SQL, begins an immediate transaction, checks for a previously imported snapshot, and refuses mixed or conflicting metadata. Identical imports roll back the empty transaction and return False. New imports use SQL placeholders (`?`) to pass data safely, insert source before entities before aliases, check integrity, and commit. Any exception rolls back; `finally` closes the connection. `load_database` checks schema version and the single-source rule, loads searchable aliases, and reconstructs the same Entity/Alias objects used by Phase 1, now with provenance. Retrieval still happens in Python, not fuzzy SQL.

Navigation: `connect_database` (line 13), `check_integrity` (line 25), `write_snapshot` (line 33), `load_database` (line 91). Line numbers refer to this completed version.

### `src/watchlist/splits.py`

`PARTITIONS` defines cumulative boundaries 50, 65, 75, 85 and 100 for five future uses. `assign_groups` rejects unresolved duplicate IDs, groups explicit links, hashes seed plus group, and uses modulo 100 to select a bucket. One group receives one partition regardless of input order. `create_manifest` validates the database, carries forward the group labels resolved before selection, assigns partitions, and flags normalized names shared across different IDs without merging them. It includes the snapshot/hash so the assignments cannot be mistaken for another dataset. `main` writes JSON and prints actual counts. These labels prepare for future evaluation; they do not train models or measure accuracy.

Navigation: `assign_groups` (line 16), `create_manifest` (line 34), `main` (line 63). Line numbers refer to this completed version.

### `src/watchlist/entities.py`

Added immutable `Provenance`: source IDs/URLs, provider/publisher, retrieval/source dates, version, raw hash and license link. `Entity.provenance` defaults to None so existing fictional records still load. The strict fictional JSON loader and its validation remain unchanged. Existing Alias and Entity objects remain the common interface between storage and matching.

Navigation: `Alias` (line 14), `Provenance` (line 22), `Entity` (line 39), `_text` (line 51), `load_entities` (line 59). Line numbers refer to this completed version.

### `src/watchlist/matching.py`

`Candidate.provenance` defaults to None. Candidate construction copies provenance from its Entity. The normalization, Levenshtein similarity, per-entity best alias, ordering and tie breaks are unchanged. A storage change therefore does not silently become a new scoring experiment.

Navigation: `Candidate` (line 15), `rank_candidates` (line 29). Line numbers refer to this completed version.

### `src/watchlist/cli.py`

Added `--db` as an optional path. Without it, the original fictional loader runs. With it, `load_database` supplies records, snapshot provenance and the synthetic flag. The CLI catches expected database/file/validation errors and prints a clear argparse error. Candidate serialization omits None provenance to preserve the original fictional JSON shape; database results include snapshot/source details. The notice describes public data as a limited snapshot when appropriate. Query text is not stored in SQLite.

Navigation: `main` (line 22). Line numbers refer to this completed version.

## Test and supporting files

| File | What changed and why |
|---|---|
| `tests/fixtures/opensanctions_synthetic.ftm.json` | Seven authored input objects exercise repeated spellings, Arabic/Cyrillic, weak aliases, a shared name, a person, an address, missing names and an untagged target. These are not downloaded records. |
| `tests/fixtures/opensanctions_synthetic.metadata.json` | Explicit fictional marker/version; no invented source observation date. |
| `tests/test_ingest.py` | Validates filtering, original scripts, name collisions, same-ID union/conflict, missing/malformed data, limit bounds, links through unselected records, malformed JSON lines, mocked HTTP byte caps/checksums and receipt tampering. |
| `tests/test_database.py` | Tests no-op repeat imports, retrieval parity, foreign-key/unique rules, conflicting snapshots, transaction rollback, read-only missing paths and evidence preservation. |
| `tests/test_splits.py` | Tests linked groups, order independence, duplicate rejection, coverage and shared-name flags. |
| `tests/test_matching.py` | Added provenance propagation check with unchanged score. |
| `tests/test_cli.py` | Added fictional/public database output checks using authored data, operation outside the checkout, and invalid/missing database errors. No live download. |
| `.gitignore` | Ignores downloaded raw data, selected samples, manifests, SQLite files and sidecars. |
| `README.md` | Corrected current status and added offline Phase 2 commands, limits and links. Historical Phase 1 results remain labeled. |
| `docs/design.md` | Added current implementation status and Phase 2 architecture links; preserved original design as historical context. |
| `docs/implementation-phases.md` | Added actual Phase 2 completion evidence and current Phase 3 approval gate; preserved later proposed phases. |
| `docs/data-card.md` | Source/permission attribution, precise dates/hashes, format, selection, diagnostics, reproducibility and limitations. |
| `docs/adr/0001-data-and-splits.md` | Explains tables/keys, transaction behavior, grouping/split choices, DAG, libraries and tradeoffs. ADR means architecture decision record: why we chose a design. |
| `docs/progress/phase-02.md` | This completion and learning report. |

`normalize.py`, original fictional JSON, dependency configuration/lock, original normalization/entity tests, AGENTS.md, the reference HTML, Phase 0/1 reports and evaluation plan were not intentionally changed. No additional package install was needed. Python's `sqlite3`, `json`, `hashlib`, `pathlib`, `urllib`, `argparse`, `dataclasses`, `datetime` and `importlib.resources` cover storage, parsing, hashes, files, download, CLI, typed records, times and packaged SQL. Existing RapidFuzz/pytest/Hatchling/uv retain their Phase 1 roles.

A test's `assert` checks an expected fact; pytest reports a failure if it is false. `tmp_path` gives each test an isolated directory, and mocked HTTP responses stand in for downloads. Exception assertions verify that invalid data fails for the expected reason. Tests do not depend on a changing public snapshot.

## Historical public-source example — omitted from publication copy

Publication note: the original local Phase 2 report includes a real provider-record excerpt, its retrieved candidate fields, and a query command using that record name. Those source-derived details are omitted from this public copy because the hosted CI publication includes fictional fixtures only. The original report remains preserved locally. This omission does not change the recorded code or test results.

The fictional database query `Moonberry Loom` returned `fixture-001` and `fixture-003`, both 100.0, then `fixture-002` at 17.647058823529417. The tie is intentional: separate IDs remain separate even for identical text. The original default query `Luma Vespr` with top-k 1 returned `syn-001` at 90.9090909090909. None of these examples measures generalization.

## Commands actually run and why

Commands below ran from the project root unless stated otherwise. Inspection used `cat`, `rg`/`rg --files`, and local Python snippets to read instructions/reference/plans/source/tests, inspect source schema counts, SSL paths, hashes and generated results. Edits used file-writing scripts/patches, not Git. Temporary scripts and diagnostic output live under `/tmp` and are not project runtime dependencies.

```sh
# Establish existing behavior before changes; rerun after test additions.
.venv/bin/python -m pytest -q

# Approved bounded acquisition: first attempt failed certificate verification.
.venv/bin/python -m watchlist.ingest.fetch_source --dataset un_sc_sanctions --max-bytes 10485760

# Successful retry used the existing system CA bundle, keeping TLS verification enabled.
SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/python -m watchlist.ingest.fetch_source --dataset un_sc_sanctions --max-bytes 10485760

# Author-created fixture import; initially exposed the alias INSERT bug, then passed.
.venv/bin/python -m watchlist.ingest.import_source --sample --db data/sample.sqlite

# Import frozen approved public bytes; no networking in this command.
.venv/bin/python -m watchlist.ingest.import_source --input data/raw/un_sc_sanctions/entities.ftm.json --metadata data/raw/un_sc_sanctions/index.json --organisations-only --limit 20 --db data/watchlist.sqlite

# Prepare group assignments only.
.venv/bin/python -m watchlist.splits --db data/watchlist.sqlite --seed 42 --output data/manifests/splits.json

# Inspect CLI arguments.
.venv/bin/python -m watchlist --help

# These three CLI commands were executed through Python subprocess.check_output.
.venv/bin/python -m watchlist --name "Luma Vespr" --top-k 1
.venv/bin/python -m watchlist --db data/sample.sqlite --name "Moonberry Loom" --top-k 3
# The historical command containing a real provider-record name is omitted from this publication copy.

# First build failed on the default cache's sandbox permissions.
/tmp/polyglot-phase1-tools/bin/uv build --offline --no-build-isolation --wheel --out-dir /tmp/polyglot-phase2-dist

# Successful offline build with the already approved temporary cache.
UV_CACHE_DIR=/tmp/polyglot-phase1-uv-cache /tmp/polyglot-phase1-tools/bin/uv build --offline --no-build-isolation --wheel --out-dir /tmp/polyglot-phase2-dist
```

A local Python audit called `import_snapshot` again on the same public paths (result `created: false`), called `check_integrity`, ran SQL counts/schema and foreign-key checks, and compared every selected original name/property pair against the stored alias rows. It saved the observed diagnostics to `/tmp/polyglot-phase2-results.json` for writing this report. Another local Python check opened the built wheel with `zipfile` and asserted it contained both the SQL schema and original fictional JSON. The wheel was built and inspected; it was not installed into a second clean environment in Phase 2. Existing tests exercise database CLI use outside the checkout.

The fetch command refuses existing source outputs. Do not rerun it for ordinary reproduction. The temporary uv path/cache may disappear after cleanup; the existing `.venv` and saved source files are sufficient for these offline commands. The public source files are deliberately not included in the package wheel.

## Errors and fixes

1. **TLS certificate error:** the first download failed because this Python's expected certificate file was unavailable. The existing `/etc/ssl/cert.pem` bundle worked via `SSL_CERT_FILE`; certificate verification was never disabled.
2. **Unexpected source schema:** the initial Organization/Company-only filter found no eligible targets. Inspection showed 269 `LegalEntity` objects. The supported non-person types were expanded to include that actual schema, keeping its broad type rather than inventing a narrower classification. No Person records entered SQLite.
3. **SQL placeholder mismatch:** the first sample import had eight placeholders for seven alias columns. Fixed to seven. A rollback test verifies that failed writes leave no partially committed schema/rows.
4. **uv cache sandbox error:** the first offline wheel build could not create its default cache. Reusing the Phase 1 temporary cache solved it without extra downloads or permissions.

## Limits, uncertainties and next gate

The 20-record ID-sorted subset is deliberately small and unrepresentative. It is not the full or current list; absence is not clearance. All imported source types are `LegalEntity`, whose meaning is broader than a confirmed company. The raw export includes people and other records even though the imported subset excludes them. The metadata is retained locally to make that distinction auditable.

Provider IDs/referents and source aliases are not independently verified identity labels. Unknown duplicates and missing aliases remain possible. No extra source was joined; cross-source leakage remains unresolved. Future additions can change connected groups, so split stability applies to these frozen inputs. Hash-based percentages are unsuitable for drawing conclusions from tiny partitions. The shared-name diagnostic does not adjudicate identity.

Malformed required input stops the import; optional missing evidence is not invented. Weak aliases and overlong/blank strings remain unsearchable under this baseline. Unicode preservation does not solve cross-script retrieval or deceptive characters. The scorer still performs a full scan, has no abstention threshold, and returns low-scoring candidates. Database integrity checks are structural, not proof that every fact is true. Receipt checking is local consistency, not digital-signature verification.

SQLite commits atomically, but readable sample/report exports are separate filesystem writes. A failure there can be repaired by rerunning the identical import. Tests and builds ran on the existing Python 3.14.0 environment; other declared Python versions were not tested. No performance numbers or operational guarantees are claimed.

If explicitly approved, Phase 3 will first propose a precise evaluation protocol: leakage checks, labeled query/perturbation design, Recall@10/@50 and clearly defined false-positive measures with denominators and limitations. It must address the tiny corpus before interpreting any numbers. No Phase 3 code or evaluation has been started.

**Approval request:** Review this phase and its limitations. Approve Phase 3 explicitly only when ready; otherwise request corrections to Phase 2.

## Final documentation and scope check

Local Markdown links in all six changed/new documentation files resolved. A SHA-256 comparison against the pre-change file inventory found exactly these nine modified existing files; no original files were missing:

- `.gitignore`
- `README.md`
- `docs/design.md`
- `docs/implementation-phases.md`
- `src/watchlist/cli.py`
- `src/watchlist/entities.py`
- `src/watchlist/matching.py`
- `tests/test_cli.py`
- `tests/test_matching.py`

New source-controlled-intent files (local data and caches excluded):

- `docs/adr/0001-data-and-splits.md`
- `docs/data-card.md`
- `docs/progress/phase-02.md`
- `src/watchlist/database.py`
- `src/watchlist/ingest/__init__.py`
- `src/watchlist/ingest/deduplicate.py`
- `src/watchlist/ingest/fetch_source.py`
- `src/watchlist/ingest/import_source.py`
- `src/watchlist/ingest/parse_opensanctions.py`
- `src/watchlist/ingest/schema.sql`
- `src/watchlist/splits.py`
- `tests/fixtures/opensanctions_synthetic.ftm.json`
- `tests/fixtures/opensanctions_synthetic.metadata.json`
- `tests/test_database.py`
- `tests/test_ingest.py`
- `tests/test_splits.py`

The dependency lock/configuration, original normalizer and fictional fixture, prior reports, reference, instructions and evaluation plan retained their original hashes. The final changes after the 110-test run were documentation only; no redundant test rerun was claimed.
