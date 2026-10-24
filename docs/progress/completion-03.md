# Completion Step 03 — database ownership and source-content integrity

Date: 2026-10-24, Asia/Kolkata. Status: **complete within the approved R3/R4 scope**. The user approved Step 03 of the [completion plan](../project-completion-plan.md). This report supplements the historical Phase 3 evaluation report; it does not replace it.

The coordinator and five existing Astra/max workers divided source storage, importer/migration, review storage, source tests/independent review, and review regression tests. The work adds no dependency and does not change the parser, normalizer, frozen archive reader, preservation utility, historical reports, original databases or saved inputs. No network access, acquisition, model inference, API use, Git initialization, commit, push or deployment occurred.

## Outcome and acceptance

Source imports no longer overlay unrelated databases. New source databases use schema **v3** and application ID **`0x50575333`**. Loading checks the complete schema and a versioned logical content manifest before constructing matcher records. Repeated imports additionally compare every retained value against independently reconstructed input, and leave existing readable exports untouched.

Review readers and writers recognize complete known schemas on private copies. New ledgers receive application ID `0x50575231`; new checkpoint stores receive `0x50574331`. Their table layouts and schema versions remain ledger v1/checkpoint v0 so the frozen historical decoder stays compatible. Exact legacy zero-ID stores are recognized through explicit fixed schema contracts without header upgrades or historical fingerprint rewrites.

Both saved source databases were actually verified and rebuilt into separate destinations:

| Preserved original | New verified output | Entities | Stored/searchable/excluded aliases |
| --- | --- | ---: | --- |
| `data/sample.sqlite` | `data/source-v3/sample.sqlite` | 3 | 8 / 7 / 1 |
| `data/watchlist.sqlite` | `data/source-v3/watchlist.sqlite` | 20 | 79 / 79 / 0 |

Both new files have mode `0600` under a `0700` output directory. Both load successfully and accept verified repeat imports with `created: false`, unchanged file bytes, permissions, modification time and change time. The public rebuild uses only the already saved, approved noncommercial subset and acquisition receipt. No new data or license entitlement is claimed.

| Acceptance criterion | Actual evidence |
| --- | --- |
| Reject unrelated, partial, malformed and unsupported databases before DDL | Foreign versions 0/1/2/99, forged table names, wrong identities, missing keys/constraints/columns and extra objects are tested; rejection preserves original storage. |
| Do not recreate missing review companions | Reader/writer tests cover missing, empty and partial ledgers/checkpoints. |
| Detect semantic changes even when SQLite integrity passes | Tests change/delete entity and alias values, normalized text, exclusion status, groups, referents, raw evidence, receipt, provenance, source metadata, selection and reports. Loads and repeat imports reject them. |
| Check more than a locally resealed checksum on reimport | A test changes stored content and recomputes its local manifest; reimport still rejects the disagreement with supplied original input. |
| Genuine repeat is a no-op | File bytes/modes/inodes/timestamps are checked. Public exports remain untouched even if missing or independently altered; repeat import does not repair them. |
| Legacy migration reconstructs the expected data | Independently authored v2 fixtures and both actual saved originals are compared to parsed original inputs before v3 publication. |
| Output publication cannot overwrite existing files | Existing files/directories, links, sidecars, competing publications and injected failures are tested. Cleanup removes only the operation's own output inode. |
| Preserve prior behavior and history | Final offline suite passed; the full v1 archive verifies and its historical case remains inspectable, with execution disabled. |

**Final offline suite: 1,069 passed, 3 deselected, 13 subtests passed in 36.06 seconds.** The three real-model integration tests are outside this storage step; they were not run or declared passed. They remain required at the approved model-integration/final-completion stages. This is completion of Step 03, not a claim that the entire project is complete.

## Defects reproduced before fixes

The coordinator used temporary fictional stores to reproduce both reported defects. After SQL changed a display name, `PRAGMA integrity_check` returned `ok`, loading returned the changed name, and repeat import returned `created: false`. Import into an unrelated version-99 database modified its bytes and reset its version to 2. The reproduction receipt is saved outside the fixed archive.

The source test worker's initial selection produced **9 failures, 34 deselected**: changed content accepted by load/reimport, foreign versions overlaid, and public repeat exports rewritten. The review test worker's initial ownership selection produced **51 failures, 54 passes, 37 deselected**. It demonstrated direct ledger initialization over nonempty/claimed stores and incomplete reader/writer schema checks.

Later tests expanded the full field/schema matrices and failure boundaries. These later additions are validation evidence, not all claimed as pre-fix reproductions. Twenty review cases were specifically added after implementation started. A late source review tightened SQL JSON columns to require TEXT and added inode-specific publication cleanup. The final full suite ran after application code and tests were frozen.

## Files and function walkthrough

### `src/watchlist/database.py`

- `APPLICATION_ID`, `SCHEMA_VERSION`, `MANIFEST_VERSION`, `SELECTION_VERSION` name the owned file format and the logical/selection contracts. Selection is explicitly versioned as `opensanctions-non-person-provider-id-v1`; historical snapshot IDs are unchanged.
- `_LEGACY_SCHEMA` is a fixed v2 recognition template. It is compiled only in an in-memory database, never executed against an original.
- `_sql_tokens`, `_schema_signature`, `_expected_schema` compare every SQLite schema object plus column declarations, foreign keys and index definitions. SQL tokenization preserves quoted literals so different CHECK values cannot be mistaken for formatting differences.
- `_recognize_schema` checks the application identifier, version and full signature. Normal loading of a genuine v2 file gives migration guidance; foreign files with version 2 are not mislabeled as valid legacy stores.
- `_reject_sidecars` and `connect_database(readonly=True)` prevent SQLite from silently ignoring WAL or recovering original journal files. Reads use immutable mode only after sidecar refusal. The low-level writable connection helper remains for explicit construction/tests; it is not an ownership-verifying application loader.
- `_canonical`, `_object_pairs`, `_invalid_constant`, `_decode_json` define finite, UTF-8 canonical JSON and reject ambiguous duplicate keys, invalid values and excessive recursion.
- `_manifest` binds versions, counts and logical tables. `_logical_content` reads every source/entity/alias column, validates SQL value types and decodes retained JSON. `_expected_content` independently constructs the same representation from parser output, provenance, receipt, selection, report and metadata.
- `_validate_content` checks that source/provenance/receipt fields agree, report counts and selected IDs match the stored rows, every row belongs to the one snapshot, and each retained entity has searchable aliases. v3 also requires retained source metadata to agree with provenance.
- `_verified_content` performs full schema/integrity checks and compares the recomputed canonical content and SHA-256 with the saved manifest. No missing manifest is silently recreated.
- `_read_content` returns the already verified logical rows and checks file identity/size/timestamps before and after reading. Source files must be regular single-link files without sidecars. `_compare_content` distinguishes a different snapshot from different contents under the same snapshot ID.
- `verify_snapshot` exposes v3 validation. `compare_legacy_snapshot` explicitly compares every historical v2 column to independently prepared input; it never upgrades the original or certifies a digest of arbitrary surviving rows.
- `_insert_rows` retains real SQL constraints and rollback behavior. `write_snapshot` creates an absent destination through a private sibling transaction, verifies it, and publishes using a hardlink that cannot overwrite an existing path. Existing v3 files take the read-only comparison path. Failure cleanup removes only this operation's own inode. The optional `source_metadata` argument retains the old low-level call shape, but successful v3 publication requires metadata.
- `load_database` builds `Entity`, `Alias` and `Provenance` objects exclusively from the verified content already read. Existing retrieval/index entry points call this loader, so they inherit the check without a separate matching implementation change.

### `src/watchlist/ingest/schema.sql`

The v3 schema retains the original source/entity/alias relationships and constraints, adds `sources.source_metadata_json`, and adds `snapshot_manifests` with snapshot foreign key, manifest version, canonical content and a constrained SHA-256 value. Initialization sets the source application ID and version 3. Removing `IF NOT EXISTS` avoids treating partial schemas as destinations to repair implicitly.

### `src/watchlist/ingest/import_source.py`

- `PreparedSnapshot` groups the independently prepared provenance, parsed records, receipt, selection, report and complete metadata object.
- `_read_saved_bytes` reads one bounded regular-file buffer and checks identity and metadata across the read. The raw export is limited to 10 MiB; metadata/receipt to 1 MiB each.
- `_json_object` rejects wrong top-level shapes, duplicate keys, nonfinite values, numeric overflow and nesting failures. `_records_from_bytes` preserves the existing JSON-lines reader behavior while parsing the exact buffer whose hash was checked.
- `prepare_snapshot` validates explicit fictional/public modes, checks receipt hashes and supplied byte counts, validates metadata/provenance primitives, calls the unchanged parser and computes the original snapshot-ID formula. Parser nesting failures become controlled input errors. This prevents hashing one file version and then reparsing a replacement from the same path.
- `import_snapshot` passes full metadata to storage. It writes public readable exports only after a new successful import; a verified repeat makes no export writes.
- The existing importer CLI flags remain compatible. Migration has its own explicit command rather than changing ordinary import into an implicit upgrade.

### `src/watchlist/ingest/migrate_source.py` — new

- `_compare` passes prepared original evidence to the strict v2 adapter.
- `_new_output_path` requires an absent destination under existing real directory ancestors, rejects traversal, links and sidecars, and refuses every existing output type.
- `verify_legacy` checks the supplied evidence and compares every retained legacy value without creating files or changing database headers.
- `rebuild_legacy` performs that comparison first, builds v3 in private staging, verifies the new file and publishes without overwrite. Injected failure cleanup checks inode ownership so a competing process's file is not removed.
- `main` exposes `verify` and `rebuild`, with explicit legacy/input/metadata/receipt/output paths. Fictional mode is explicit and reconstructs its historical fixture receipt; public mode requires the saved acquisition receipt. Results include an explicit trust limitation.

### `src/watchlist/agent/storage.py` and `src/watchlist/agent/schema.sql`

Storage now contains fixed ledger and pinned-checkpointer schema contracts. `_sql_tokens`, `_schema_signature` and `_expected_schema` cover all main-schema objects, complete columns, primary/foreign/unique keys, CHECK clauses, collations and index definitions. `_require_owned_schema` accepts only the correct tagged ID or the exact known zero-ID legacy format at the expected version.

`_require_owned_pair` checks both normalized private copies. `ReviewReader.__enter__` performs it before frozen decoding; `ReviewService.__enter__` performs it under the existing writer lock before opening originals for operations. The Step 02 copy/WAL/nonmutation behavior is preserved.

`_require_empty_database` prevents direct `Ledger` initialization unless the database is unclaimed, version zero and has no schema objects. Existing direct ledger access also validates ownership; passing `schema_checked=True` cannot bypass it. Only the service's private sentinel skips a redundant original-file schema read after the copied-pair preflight.

The ledger schema stamps its application ID only during new initialization. The service stamps the checkpoint application ID only after new saver setup. No existing store is retagged and no historical case hash is rewritten. Workflow execution compatibility remains strict.

### Tests and documentation

| File | Explanation |
| --- | --- |
| `tests/test_database.py` | Full logical-content mutation matrix; complete schema/identity rejection; manifest deletion/corruption; independent reimport comparison after resealing; no-op storage invariants; source sidecar/hardlink refusal before SQLite access. |
| `tests/test_ingest.py` | Public export no-op preservation, malformed/ambiguous evidence, receipt sizes, numerical overflow and parser/JSON recursion boundaries; prior parser/deduplication cases retained. |
| `tests/test_source_migration.py` — new | 43 cases using independently authored fictional v2 databases: valid migration, changed evidence/legacy content/schema, output links/ancestors/sidecars, publication failures, competing output preservation, single-buffer preparation and real CLI behavior. |
| `tests/test_review_audit.py` | Direct ledger ownership/initialization regressions plus preserved audit tests. |
| `tests/test_review_resume.py` | Reader/writer schema matrices, missing companions, exact legacy acceptance without upgrade, new IDs, rejection preservation, plus previous restart/WAL tests. |
| `docs/maintenance/source-database-migration.md` — new | Operating instructions, exact commands, compatibility and trust boundaries, source quiescence/single-link requirements and 5W1H explanation. |
| `docs/progress/completion-03.md` — new | This report and the next-step preflight. |

Final focused counts: database/ingestion **263**, migration **43**, audit/resume **162**, totaling **468** focused cases. These overlap the full suite and must not be added to it.

## Commands actually run and observed results

Project executions used the existing `.venv`, Python `-B`, and disabled bytecode. Coordinator project runs additionally set `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`; worker focused runs used no models/network. All tests use fictional data and temporary stores; the separate migration commands below deliberately read the saved originals.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q -m 'not integration' -p no:cacheprovider
```

Final: **1,069 passed, 3 deselected, 13 subtests passed in 36.06 s**. An earlier full run before the last boundary-test expansion passed 1,022 tests; it is superseded by the final run. Source-focused runs progressed from 43 to 259 to the final worker run of **306 passed in 1.33 s**. Review-focused final run: **162 passed in 12.72 s**. AST parsing and trailing-whitespace checks passed for the edited/new Python and SQL files.

The following actual commands also ran with the offline environment above and returned exit 0. Outputs were retained in `data/review-archives/step03-checks/`.

```sh
.venv/bin/python -B -m watchlist.ingest.migrate_source verify \
  --sample --legacy data/sample.sqlite \
  --input tests/fixtures/opensanctions_synthetic.ftm.json \
  --metadata tests/fixtures/opensanctions_synthetic.metadata.json --limit 20

.venv/bin/python -B -m watchlist.ingest.migrate_source verify \
  --legacy data/watchlist.sqlite \
  --input data/raw/un_sc_sanctions/entities.ftm.json \
  --metadata data/raw/un_sc_sanctions/index.json \
  --receipt data/manifests/source.json --limit 20

mkdir -m 700 data/source-v3

.venv/bin/python -B -m watchlist.ingest.migrate_source rebuild \
  --sample --legacy data/sample.sqlite \
  --input tests/fixtures/opensanctions_synthetic.ftm.json \
  --metadata tests/fixtures/opensanctions_synthetic.metadata.json --limit 20 \
  --output data/source-v3/sample.sqlite

.venv/bin/python -B -m watchlist.ingest.migrate_source rebuild \
  --legacy data/watchlist.sqlite \
  --input data/raw/un_sc_sanctions/entities.ftm.json \
  --metadata data/raw/un_sc_sanctions/index.json \
  --receipt data/manifests/source.json --limit 20 \
  --output data/source-v3/watchlist.sqlite

.venv/bin/python -B -m watchlist.review archive verify \
  --archive data/review-archives/v1
.venv/bin/python -B -m watchlist.review archive inspect \
  --archive data/review-archives/v1 \
  --case-id e449b466-466d-4b81-9a29-cb3c9d957823

.venv/bin/python -B -m watchlist \
  --db data/source-v3/sample.sqlite --name 'Moonberry Loom' --top-k 1
```

A separate actual Python check called `verify_snapshot`, `load_database` and `import_snapshot` for both rebuilt outputs, asserted no-op bytes/modes/timestamps and recorded their receipts. There is no Git repository; no Git diff/commit result is claimed.

## Example input/output

The actual fictional CLI command above returned this subset of its JSON:

```json
{
  "query": "Moonberry Loom",
  "normalized_query": "moonberry loom",
  "entity_id": "fixture-001",
  "display_name": "Moonberry Loom",
  "similarity_score": 100.0
}
```

`entity_id`, `display_name` and `similarity_score` come from the first candidate. This is a RapidFuzz character-similarity score for an authored fixture, **not a probability or identity finding**. The actual output includes that research notice and source provenance. No embedding model produced it.

Actual rebuild snapshot IDs remained unchanged:

- Fictional: `e9fd8e473adf17362721a30984e7f8f691b578c619604cb0283286c12220c334`; v3 logical digest `c95118637f5f01108da6fe817816aa1afe4e38d515e492b5bbbef11940b9c531`.
- Public subset: `19de20acd5f0e9e0f0d81d8083d68156aa66f44b4a73489c89b314cc41f018cc`; v3 logical digest `76e690a8f509b2276f6873b3195c569d8aa151d7d7184a521c472826c6391edd`.

## Preservation and compatibility

The before/after inventory covers **202 existing project/protected files**. Exactly the **nine approved existing files** changed; **193 remained unchanged**, with zero missing files and zero unexpected changes. This includes original source/review databases, saved raw data/metadata/receipts, historical evaluation artifacts, tracked model receipts/artifacts in that inventory, configuration, frozen archive code and the preservation script. New deliverables comprise four code/test/document files plus the two generated v3 outputs and private verification receipts.

Full archive verification independently checked **37,357 files, four normalized databases and one case**. Its manifest hash remains `ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d`. The case remains attributed as `simulated_demo`.

The current workflow hash is `2c27af8f7a81d822f68962d66d14c721e0007c3c74652621fb85e9623615609a`. The preserved workflow hash remains `545944411abe85d270737fe708de8e75e67e1516698d7b54df4e7313dc9960b9`. Archive output confirms captured execution match **true**, current execution match **false**, and execution allowed **false**. Source changes naturally alter the current fingerprint; no stored history was rewritten to hide that.

Private evidence: `before-files.json`, `initial-defect-reproduction.json`, `final-file-comparison.json`, `sample-legacy-verify.json`, `public-legacy-verify.json`, `sample-rebuild.json`, `public-rebuild.json`, `rebuilt-load-repeat-examples.json`, `fictional-cli-example.json`, `archive-verify-after-edits.json` and `archive-inspect-after-edits.json` under `data/review-archives/step03-checks/`.

## Limitations and boundaries

- A local manifest detects changes not reconciled with that manifest. Application IDs are structural markers, not authentication. Someone able to replace all rows, hashes, original inputs and receipts can produce another internally consistent set. Independent custody/authentication remains distinct from this local integrity guarantee.
- Source verification requires stable single-link files with no journal/WAL sidecars. It detects ordinary replacement/modification through metadata checks; it is not an adversarial filesystem lock, online migration, OS snapshot or power-loss durability guarantee. Recovery, if needed, must operate on a separate copy. Review inspection continues to support WAL through its established locked-copy path.
- Exact schema adapters intentionally reject extra indexes/objects and alternative definitions, even when they might be semantically harmless. Such changes require a reviewed schema version rather than automatic acceptance.
- Original v2 source databases now fail normal loading with explicit migration guidance. Use the new `data/source-v3/` paths for new source-backed work. Historical configs, recipes, evaluation reports and review cases retain their original paths/fingerprints; this source migration does not automatically authorize changing their contracts.
- No new model-quality, calibration, recovery-protocol or operational screening guarantee is established. No known Step 03 acceptance failure remains. Later approved steps and the three model-integration tests remain project-completion requirements.

## 5W1H recap

| Question | Answer |
| --- | --- |
| What? | Recognize owned database formats and bind every retained source value to a versioned manifest. |
| Why? | Ordinary SQL edits can keep SQLite structurally valid while making evidence false; running DDL before ownership checks can alter unrelated databases. |
| When? | Before source loading/reimport/migration and before existing review-store access. |
| Where? | Source database/import/migration modules, review storage, their tests and the maintenance guide. |
| Who? | A researcher explicitly selects saved inputs and a new destination; human review remains responsible for interpreting possible record matches. |
| How? | Compare complete schema contracts, hash canonical logical contents, reconstruct originals independently, verify private staging and publish without overwrite while preserving history. |

## Next: Step 04 preflight — checkpoint reconciliation and crash recovery

**Goal / why:** a missing, replaced or rolled-back checkpoint must not turn a progressed case into a fresh query. Step 03 establishes recognized store formats; Step 04 checks whether the two stores describe the same legitimate workflow progress.

**Exact files:** edit `src/watchlist/agent/storage.py`; extend `tests/test_review_resume.py`, `tests/test_review_audit.py`, `tests/test_agent.py`; create `docs/maintenance/recovery-state-matrix.md` and `docs/progress/completion-04.md`. Preserve original stores, archives and historical reports.

**Work:** first document each allowed request/packet/submission/explanation/final-event/checkpoint state and crash window. Add regressions for missing/replaced/truncated/rolled-back checkpoint state and mixed generations. Permit the genuine initial-envelope-only crash, where no checkpoint exists yet; retain `after_packet` recovery from saved evidence. Preserve accepted submissions and one logical final event. Add a bounded lock timeout with documented lock ordering, then test real subprocess termination and concurrent review in isolated fictional workspaces.

**Dependencies / expected commands:** existing pinned LangGraph/saver/runtime and completed Steps 01–03; no new dependency, network, data or model acquisition expected. Run the focused audit/resume/agent pytest files, then the offline full suite and archive compatibility checks. The completion plan also calls for opt-in already-local model integration when the repaired workflow behavior requires it; define those exact checks in the Step 04 execution preflight and do not misreport their current status.

**Risks / acceptance:** overstrict reconciliation can reject a legitimate crash window, while permissive recovery can reretrieve or lose a recorded review. Every allowed crash state must recover with unchanged durable evidence and one logical final event. After evidence exists, assert zero retriever calls. Missing/mixed stores or missing checkpoint threads after progress must fail before mutation. Original stores and archives remain unchanged; no automatic historical-hash rewrite.

Step 04 has **not** begun. `AGENTS.md` requires stopping after each phase until explicit approval for the next one.
