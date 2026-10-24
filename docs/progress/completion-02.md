# Completion Step 02 — input validation and nonmutating inspection

Date: 2026-10-24, Asia/Kolkata. Status: **completed within the approved R1/R2 scope**. The user explicitly approved Step 02 of the [completion plan](../project-completion-plan.md). This does not replace the original Phase 2 data-ingestion report.

The coordinator and five existing Astra/max workers split implementation, test-first regression work and independent review. We changed only the three approved application files and four approved test files, and added this report. No dependencies, data, models, original review stores, archive-reader code, preservation scripts or historical reports were changed. No network access, inference, download, Git initialization, commit, push or deployment occurred.

## Outcome

Invalid CLI syntax, configuration and review forms now produce one finite JSON error with exit code 2 **before writable workspace access**. Status/list/audit inspection uses a separate `ReviewReader` and leaves original files unchanged. Starting a case explicitly permits initialization; review and recovery require an existing workspace.

For existing workspaces, inspection obtains a coherent copy under the established writer lock. SQLite handles journal recovery only on private temporary copies. The copies are normalized, checked by the frozen Step 01 decoder and removed before the reader returns. This preserves committed data in WAL without letting SQLite create or alter original WAL/SHM files.

The existing exact execution-fingerprint guard remains in place. As expected, the three source edits changed today's fingerprint. The preserved old case still verifies and can be inspected through `watchlist.review`; its stored fingerprint has not been rewritten to permit execution.

## Acceptance and observed results

| Requirement | Evidence |
| --- | --- |
| Scalar/array/wrong-shape JSON becomes a controlled error | Config/form tests cover null, booleans, numbers, strings, arrays including nested arrays, missing/extra fields, duplicate keys and nonfinite values. Exact types prevent `5.0` from passing as approved integer `5`. |
| Missing/stray/wrong-path arguments fail before preparation | Tests forbid service, reader, recipe and retriever construction on invalid input. Workspace symlinks, traversal and non-directory ancestors are rejected before start preparation. Syntax errors now also use JSON; `--help` retains exit 0. |
| Missing inspection storage is not created | Status/audit/list reject a missing workspace, lock or database member with no initialization. |
| Existing inspection does not mutate source | Tests compare bytes, permissions, inode, modification/change times and membership, including journal sidecars. Access time is deliberately excluded. |
| WAL contents remain visible | A fixture holds a read transaction so committed data remains in WAL. Main-file-only immutable reading misses the case; the new reader sees it while all original files remain unchanged. |
| Readers do not initialize a runtime | Tests forbid original SQLite connections, graph construction, saver setup and model/retriever work during inspection. Scratch space is cleaned on success and failure. |
| Existing writer opening does not initialize | Schema recognition happens on copies; an idle existing writer context preserves original bytes and metadata. Tests forbid schema scripts/DDL, schema/journal-changing PRAGMAs and `SqliteSaver.setup()` on this path. |
| Rejected review input does not create an error-audit entry | Static, stale, cross-case, unknown and duplicate forms are checked before writable access. A reused submission ID from another case is checked across the workspace and rechecked under the writer lock. |
| Valid behavior remains supported | Existing pause/restart/review/recovery/concurrency tests pass. Supplied blank/whitespace or 201-character names still become audited invalid-query cases within the 1000-character transport envelope, without retrieval. |
| Archival compatibility survives source fixes | Both real archive CLI commands passed. Historical fingerprint match is true; current fingerprint match is false; archive execution remains disabled. |

**Final offline suite: 672 passed, 3 deselected, 13 subtests passed in 33.67 seconds.** The three deselected checks are the previously discussed real E5/MiniLM integration tests. No inference result is claimed. They remain required at the planned local-model integration and final-completion stages; this phase used deterministic fictional tests.

## Files and function walkthrough

### `src/watchlist/agent/cli.py`

The CLI now has a validation stage followed by a clearly chosen read or write path.

- Line 17, `_Parser.error`: turns argparse syntax failures into the same JSON error path used for domain/input errors. Help remains argparse's successful exit.
- Lines 24–64, `_unique_object`, `_nonfinite`, `_path`, `_file`, `_json_object`: reject duplicate JSON keys, nonfinite values, invalid path primitives, nonregular files and oversized data. Reads are bounded to limit plus one byte, so a growing input cannot bypass a preliminary size check. Excessive JSON nesting becomes a controlled input error. Parsed objects receive finite UTF-8 JSON validation.
- Line 67, `load_config`: enforces exact approved fields, values and types. Workspace path validation shares storage's no-symlink/no-traversal/ancestor checks. It validates the embedding path's text without requiring its file during status/review/recovery.
- Line 82, `make_recipe`: preflights the start-only embedding configuration, model policy, path types, receipt shape and ten required artifact paths. It then calls the existing recipe builder and checks that configuration and receipt fingerprints have not changed. This checks metadata and file presence; it does **not** hash all weights or run inference. Model inference still uses the existing encoder's verification path.
- Line 137, `_arguments`: applies an explicit option matrix. `start` requires a supplied name and rejects thread/review-file options; other actions reject query/dataset replacement; only review accepts a form; non-list actions require a thread ID. IDs must parse as UUIDs. The distinction between missing and supplied-invalid names is preserved.
- Line 165, `_review_template`: retains the existing explicit human-review template for pending cases.
- Line 173, `main`: validates arguments/config/form before storage dispatch. Status/list/audit use `ReviewReader`. Start prepares its recipe before `ReviewService(..., mode='auto')`. Review/recovery first check copied state, then use `mode='existing'`; service-level validation repeats under the writer lock to address races. Expected `OSError`, `ValueError` and SQLite failures return JSON/2. Unexpected programming `TypeError` and `RuntimeError` are not broadly swallowed. Success returns escaped finite JSON/0.

The existing recipe/data fingerprint definition is unchanged; its builder in `agent/retrieval.py` was not edited.

### `src/watchlist/agent/state.py`

A form's **shape** means its allowed fields and types. Its **state-dependent validity** means whether those fields still refer to the current saved packet and checkpoint. These need separate checks because the first can happen before opening storage.

- Line 106, `text`: retains nonblank/length rules and rejects invalid Unicode before durable JSON encoding.
- Line 116, `validate_query_envelope`: requires text of at most 1000 characters, but deliberately allows blank or normalizer-invalid names so the workflow can audit those supplied inputs.
- Line 132, `validate_recipe`: accepts only a finite primitive JSON object with string keys. It detects container cycles, invalid UTF-8 and serialization-depth failures, and returns a detached copy so later caller mutation does not alter the accepted object.
- Line 173, `validate_start_inputs`: combines the query and recipe checks without mutation. The CLI performs its preflight before opening; the service repeats validation before writing a case.
- Line 178, `validate_review_form`: validates exactly the seven caller-owned fields. It checks UUID, exact integer revision, lowercase SHA-256 syntax, checkpoint/reason text, supported outcome and candidate/null relationship. The caller cannot set local reviewer identity or submission time.
- Line 208, `validate_packet`: adds shape checks before dictionary/set/lookup operations on candidates, evidence and evidence references. Invalid huge integer scores are rejected without overflowing float conversion. Existing evidence-link and score rules remain intact.
- Line 257, `validate_review`: reuses standalone form validation, validates service-owned actor/time fields, then checks revision, saved evidence hash, checkpoint and candidate membership against saved state.

`workflow_hash()` at line 90 is unchanged. Its result changes naturally because the approved fingerprinted source bytes changed; no compatibility bypass or stored-hash rewrite was added.

### `src/watchlist/agent/storage.py`

A **WAL** is SQLite's write-ahead log: committed data may still live there rather than in the main database file. **SHM** is its shared-memory coordination file. A normal read-only SQLite connection may create or update SHM, while `immutable=1` on an unprocessed original can ignore WAL. The implementation therefore opens originals as ordinary files, not as SQLite databases, during inspection.

- Line 30, `_checked_path`: checks each existing path component before use, rejecting symlinks, parent traversal and non-directory ancestors. Missing destinations are permitted only for explicit creation preflight.
- Lines 49–78, `_file_state`, `_workspace_files`, `_file_digest`: require an established lock and both regular database files, inventory present WAL/SHM/journal files and retain the 100 MB pilot storage budget. Metadata and hashes detect changes during copying.
- Line 81, `_existing_lock`: opens the already existing lock read-only, acquires shared/exclusive locking as appropriate and checks lock identity. It never creates or chmods a lock for inspection.
- Line 96, `_require_tables`: recognizes the expected table names and database version without DDL. This is deliberately not the complete ownership/content-manifest work assigned to Step 03.
- Line 107, `_copied_databases`: copies the complete present database/sidecar set while holding the lock, checks source metadata/hashes, then recovers/backups only those copies. Normalized destinations use DELETE journal mode and can safely be read as immutable copies. The private temporary directory is cleaned on every exit path. A writer already holding the exclusive lock reuses this routine without reacquiring its own lock.
- Line 146, `ReviewReader`: holds decoded, verified evidence in memory after scratch cleanup. `__enter__` calls the frozen primitive Step 01 decoder and computes current code compatibility without graph/model setup. `_case` rejects unknown or incompatible cases. `list_cases` omits query/notes; `status` preserves the existing response shape. `validate_review` checks pending state, stale references, target-case duplicates and workspace-wide submission-ID reuse before writable access.
- Line 230, `Ledger`: its constructor now separates initialization from existing access. Existing access does not replay the schema script; the service passes copy-based recognition and enables only the connection's foreign-key flag. Other ledger operations keep their existing transaction and evidence behavior.
- Line 350, `ReviewService`: adds explicit `create` and `existing` modes, retaining `auto` for existing Python callers and the start command. Auto initializes only a missing/empty directory; existing mode requires the established pair and lock. Creation initializes both schemas once, including checkpoint tables before the first graph request.
- Line 366, writer `__enter__`: schema recognition for existing stores runs on scratch copies under the exclusive lock. Original writable connections remain idle until a requested operation. For the pinned `langgraph-checkpoint-sqlite==3.1.2`, a recognized existing saver is marked set up so its normal lazy setup cannot run DDL. Other saver versions fail explicitly rather than relying on an undocumented cross-version assumption.
- Line 422, `__exit__`: closes connections and releases the correct lock context even after failures.
- Line 469, `start`: repeats input validation before ledger creation.
- Line 480, `review`: validates caller shape before inspection, checks stored-state semantics and global submission-ID uniqueness before the operational-error logging block, then submits/resumes under the writer lock. Expected rejected input no longer becomes an attempt-audit event. Actual operational failures retain error logging/recovery behavior.
- `inspect`, writer-internal `status`, `invoke` and `recover` retain their execution guard and workflow semantics. **Use `ReviewReader` for nonmutating inspection**; methods inside an explicitly writable `ReviewService` context are not a substitute for the reader.

### Tests and this report

| File | Final test count | Main added coverage |
| --- | ---: | --- |
| `tests/test_agent_cli.py` | 164 | Input/config/form/path/syntax rejection before access; metadata-only recipe validation; unchanged workspace on inspections/rejected reviews; programmer exceptions; valid CLI flow. |
| `tests/test_agent_state.py` | 100 | Standalone form/query/recipe contracts, malformed nested packet shapes, finite values, cycles, detached data and Unicode. |
| `tests/test_review_audit.py` and `tests/test_review_resume.py` | 37 combined | Existing 17 tests plus 20 regressions for no mutation, WAL visibility, missing members, scratch cleanup, forbidden runtime/setup/DDL and fingerprint/archive behavior. |
| `docs/progress/completion-02.md` | — | This implementation, evidence, explanation and next-step preflight. |

The final focused files contain **301 tests**. The earlier combined focused run had 300; the cross-case submission-ID regression was added afterward and included in the final full suite.

## Defects reproduced and resolved

Tests were added before fixes. The first CLI baseline had **87 failures and 26 passes**. The state-contract subset had **71 failures, 2 passes and 23 deselected**. Four initial storage regressions failed because status/list created storage or changed permissions.

The first existing-writer preservation test then revealed a less obvious side effect: schema queries briefly created/deleted journal files, leaving file bytes unchanged but changing the directory's timestamps. Moving schema recognition to copies fixed that regression. A WAL fixture also needed a held read transaction so its committed record genuinely remained in WAL; the corrected fixture demonstrates why main-file-only inspection is insufficient.

After the first 300-test combined pass, independent review identified cross-case submission-ID reuse. The new test failed because it reached the writer constructor. The reader now rejects it globally before writable access; the writer repeats the uniqueness check under its lock, before error logging. The test passed after the fix and was included in the final 672-test run.

No known Step 02 test remains failing. This phase did not silently turn off assertions, relax execution compatibility or replace original history.

## Commands actually run

All project commands ran from `/Users/odin/Desktop/polyglot-watchlist-starter`; fixtures used temporary fictional stores.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q \
  tests/test_agent_cli.py tests/test_agent_state.py \
  tests/test_review_audit.py tests/test_review_resume.py
```

Observed initial combined result: **300 passed in 11.61 s**. This preceded the final extra regression.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q -m 'not integration'
```

Final result: **672 passed, 3 deselected, 13 subtests passed in 33.67 s**. This includes all final source changes and all 301 focused tests, plus the existing preservation, archive compatibility and other offline suites.

Other observed focused results: CLI 158 passed before the last path/syntax/ID additions; final path/syntax subset 27 passed; final cross-case ID test 1 passed; state 100 passed; audit/resume 37 passed in 10.12 s. These overlapping runs are not added together as independent test counts.

```sh
.venv/bin/python -B -m watchlist.review archive verify \
  --archive data/review-archives/v1

.venv/bin/python -B -m watchlist.review archive inspect \
  --archive data/review-archives/v1 \
  --case-id e449b466-466d-4b81-9a29-cb3c9d957823
```

Both returned **exit 0** after the source edits, with offline variables as above. Each checked the full archive; verification reported **37,357 files, four databases and one case**. Outputs were redirected with `umask 077` to private receipts outside the fixed archive.

A separate temporary demonstration invoked the actual `python -B -m watchlist.agent` entry point through subprocesses for missing workspace, incomplete `--name`, and a saved fictional pending case. It asserted byte/mode/metadata preservation and removed its temporary workspace afterward. No real model generated that example.

## Example input/output

With a valid configuration pointing to a nonexistent workspace:

```sh
.venv/bin/python -B -m watchlist.agent status --config TEMP_AGENT_CONFIG
```

Actual output, exit **2**, empty stderr, no new workspace:

```json
{
  "error": "existing review workspace is missing",
  "recovery_notes": [],
  "completed": false
}
```

For `python -B -m watchlist.agent start --name`, actual output was the same error envelope with `"error": "argument --name: expected one argument"`, exit **2**, empty stderr and no workspace mutation.

For an isolated case created using the fictional `FakeRetriever`, status returned exit **0**, `pending_interrupt: true`, `completed: false`, audit count **2**, and query `"Fictional Luma Vesper"`. Its workspace bytes and metadata remained unchanged. This is an interface/storage example, not an inference score or an identity conclusion.

## Preservation and compatibility evidence

The before/after inventory covered **196 existing files**: the original 187 captured project files plus nine Step 01 deliverables. Exactly the seven approved code/test paths changed; there were **zero unexpected changes**. The **180 original capture files outside that approved edit set** still match their preserved hashes and modes. Original review stores, source data, model artifacts, archive code, preservation utility and previous reports remain intact.

Archive manifest SHA-256, unchanged:

```text
ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d
```

Saved/captured workflow fingerprint, unchanged:

```text
545944411abe85d270737fe708de8e75e67e1516698d7b54df4e7313dc9960b9
```

Current workflow fingerprint after Step 02:

```text
552470cbdf26fff10b5a50337951aeb03ee9ab40d70e5ba2c2ca38fd4f4cd713
```

Real archive output confirms `captured_execution_match: true`, `current_execution_match: false`, and `execution_allowed: false`. The preserved case remains externally attributed as `simulated_demo`.

Private evidence lives at `data/review-archives/step02-checks/`: `before-files.json`, `final-file-comparison.json`, `archive-verify-after-edits.json`, `archive-inspect-after-edits.json` and `cli-examples.json`. Detailed case evidence remains private. There is still no Git repository; no commit or Git diff check is claimed.

## Boundaries and limitations

- **No writes to the inspected workspace is not no writes anywhere.** Live inspection creates private temporary copies and cleans them before returning. Filesystem access times may change. The established advisory lock coordinates cooperating project writers; it is not protection against an unrelated process deliberately bypassing that lock.
- **Use the right interface.** CLI status/list/audit and `ReviewReader` provide the nonmutating path. A `ReviewService` context explicitly allows workflow writes; its internal status assembly is used after those operations. Invalid CLI review requests receive copy-based preflight and writer-locked revalidation.
- **Pinned runtime boundary.** Skipping existing saver setup is checked against version 3.1.2. A package upgrade needs a separately validated adapter. A source fingerprint mismatch is not repaired by replacing historical hashes.
- **Storage identity/content work remains Step 03.** Existing opening now recognizes basic schema/version on copies; it does not establish a complete application identity or repair the demonstrated source-provenance defect. Full schema constraints, logical content manifests and verified rebuilds retain their planned phase.
- **Broader recovery work remains Step 04.** Required-member rejection prevents implicit recreation here, but this phase does not claim the complete reconciliation matrix, lost-history recovery rules or bounded lock timeout. No later phase was started under Step 02 approval.
- **Model scope.** Recipe preflight checks structure, approved settings and file presence, not actual inference quality. The three local-model integration tests were not run and are not counted as passes.

## 5W1H recap

| Question | Explanation |
| --- | --- |
| What? | Validate input before writable access and give inspection its own nonmutating reader. |
| Why? | A typo or status request must not create/chmod stores or append an error event; committed journal data must still be visible. |
| When? | Every CLI command checks syntax first. Review also checks saved-state relationships before writing, then repeats them under the writer lock. |
| Where? | Validation lives in `agent/cli.py` and `agent/state.py`; copy-based inspection and explicit writer modes live in `agent/storage.py`. |
| Who? | CLI users and Python callers use the reader for observation, and explicitly writable service operations for approved workflow changes. Reviewer labels remain local attribution, not authentication. |
| How? | Enforce typed finite JSON, copy a locked complete store set, recover only copies, decode primitive saved evidence, preserve the strict fingerprint guard, and test byte/permission/metadata invariants. |

## Next phase — Step 03 preflight, not started

**Goal / why:** establish database ownership and source-content integrity so foreign databases cannot be modified and altered rows cannot retain apparently valid source provenance. This follows the completed archive/read and input/opening boundaries.

**Work sequence:** reproduce R3/R4 with fictional databases; recognize complete legacy schema/constraints before any DDL; define application identity and explicit new versions; bind every retained entity/alias/exclusion/group/provenance item to a versioned logical content manifest and receipt-verified source bytes; verify no-op reimports and loads; implement a rebuild into a new destination only after independently rebuilding/comparing expected content from original input receipts. A digest of current possibly corrupted rows alone is not a valid migration.

**Files proposed:** edit `src/watchlist/database.py`, `src/watchlist/ingest/import_source.py`, `src/watchlist/ingest/schema.sql`, `src/watchlist/agent/storage.py`, `src/watchlist/agent/schema.sql`; extend `tests/test_database.py`, `tests/test_ingest.py`, `tests/test_review_audit.py`, `tests/test_review_resume.py`. Add a narrowly scoped `src/watchlist/ingest/migrate_source.py` and `tests/test_source_migration.py`, `docs/maintenance/source-database-migration.md`, and `docs/progress/completion-03.md`. The separate migration module keeps legacy recognition and rebuild logic reviewable; CLI wiring can expose the completion plan's proposed verify/rebuild operations. These interfaces do not exist merely because they are listed here.

**Dependencies and commands:** use already saved fictional/source receipts; no new network or dataset/model acquisition. No new dependency is expected. Run focused database/ingestion/migration and store-recognition pytest, then the relevant offline regression suite. Proposed verify/rebuild commands must use distinct source and output paths and must never overwrite original stores. Exact flags and the versioned data contract will be explained from the inspected implementation before that approved phase's edits.

**Risks / acceptance:** test unrelated versions 0/1/2/99, forged table names and malformed constraints; rejected databases must retain bytes, permissions and version. Detect changed/deleted names, aliases, normalized strings, exclusions, grouping, raw evidence and metadata even when SQLite integrity passes. Valid repeated imports must remain no-ops. Original legacy databases remain preserved; newly rebuilt outputs must verify against independently checked input receipts. Keep the distinction between local integrity and independent authentication explicit.

Step 03 has not begun. `AGENTS.md` requires: “AFTER every phase … STOP until user approves the next phase.” Step 02 is complete; its approval does not start Step 03.
