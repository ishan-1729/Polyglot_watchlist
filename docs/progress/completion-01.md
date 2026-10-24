# Completion Step 01 — historical reading without workflow execution

Date: 2026-10-24, Asia/Kolkata. Status: **completed within the approved archive-reader scope**. This is Step 01 of the [completion plan](../project-completion-plan.md), not a replacement for the original Phase 1 report. Step 02 has not started.

The user approved this phase after asking why three inference tests were excluded from Step 00. The coordinator and the five existing Astra/max workers completed the archive reader, independent protocol tests, interface tests, recipe checks and design review. No dependencies were added. No original workflow source, stores, models, historical reports, preservation utility, or fixed archive artifacts were modified. No network access, model download, inference, Git initialization, commit, push or deployment was performed.

## Result and acceptance evidence

The new commands verify a preserved v1 archive and inspect one saved case without creating a review service or executing its graph. Historical reading succeeds even when current workflow source differs; the existing service still rejects execution under an incompatible fingerprint. Every reader response explicitly disables execution.

| Approved acceptance criterion | Actual evidence |
| --- | --- |
| Completed, pending and interrupted cases remain readable | Fictional fixtures cover completed/pending cases and real `os._exit(77)` stops after case creation, after packet creation, after submission, during explanation and after final audit. |
| Current source changes do not redefine old evidence | Tests alter a temporary source copy, confirm its fingerprint changes, read historical evidence, and confirm the existing service rejects incompatible execution. No real application source is edited by this test. |
| Evidence checks go beyond hashes | Tests rehash deliberately invalid packet, submission and initial records. The reader still rejects their broken semantic relationships. Mixed stores, lost checkpoint history, invalid scheduler state and malformed control records fail. |
| Safe decoding and unsupported-format rejection | Unknown schema/serializer/control extensions, pickle and constructor-revival payloads are rejected. Fresh-process tests run the compatibility reader without third-party packages. |
| No mutation or inference during reads | Subprocess audit checks forbid file writes, temporary extraction, chmod, deletion, child processes, network activity and workflow/model imports. SQLite connections must target normalized archive copies using `mode=ro&immutable=1`. |
| Real preserved archive can be read | Both CLI commands returned exit 0. Verification checked **37,357 files and four normalized databases**. The saved case remained `simulated_demo`, with four audit events, recorded review and committed audit. |
| Existing code/store/model evidence stays intact | All **187 captured project files** still match capture hashes and modes. Final comparison also found no changes in size, inode, modification time or change time since the pre-verification snapshot. |

The real archive fingerprint reconstructed from **15 historical source files and four captured workflow-package versions** is:

```text
545944411abe85d270737fe708de8e75e67e1516698d7b54df4e7313dc9960b9
```

It matches the saved case and the current execution fingerprint. Matching is informational: `execution_allowed` remains `false`. The archive manifest remains:

```text
ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d
```

## Why the three inference tests were excluded

They were excluded from Step 00 because that phase established preservation and restoration, not model execution. The reason was **scope**, not a failed inference test or a missing paid API. These tests use already acquired local weights and do not intentionally download models:

- `tests/integration/test_embedding_model.py`: real E5 output dimensions, unit-length vectors and repeatability.
- `tests/integration/test_agent_e5.py`: real E5 retrieval parity and completion of a temporary review after restarting the service.
- `tests/integration/test_reranker_model.py`: finite and repeatable real MiniLM scores.

The `integration` marker and environment opt-ins make those tests optional for the default developer command. They are **not optional evidence for an overall project-completion claim**. File hashes, receipt checks and successful imports do not prove inference works. Step 01 also has no model execution requirement: its read-only guarantee specifically excludes loading a model. The completion plan places local integration checks alongside the Step 04 workflow/recovery repairs; final reproducibility and release must also account for them. None of these three is reported as passed in this phase.

## File-by-file changes

| New file | Responsibility and reason |
| --- | --- |
| `src/watchlist/review/__init__.py` | Documentation-only package entry; no eager workflow/model imports or global bytecode-setting changes. |
| `src/watchlist/review/__main__.py` | Runs the new CLI through `python -B -m watchlist.review`. |
| `src/watchlist/review/cli.py` | Defines only `archive verify` and `archive inspect`, validates syntax before reader import, and produces finite, ASCII-escaped JSON. |
| `src/watchlist/review/archive.py` | Verifies archive membership/bytes, calls the inert compatibility reader, reconstructs execution fingerprints, checks captured recipe artifacts and exposes a private-detail inspection API. |
| `src/watchlist/review/compat_v1.py` | Freezes the supported v1 case/checkpoint protocol and decodes its saved primitive data without importing LangGraph, old Python code or model libraries. |
| `tests/test_review_archive.py` | **67 tests**, plus 13 passing unittest subtests in the observed run: archive/API/CLI/privacy, fingerprints, mutation/import audits and small fictional recipe artifacts. |
| `tests/test_review_compatibility.py` | **43 tests** in the final file: actual crash windows, strict execution rejection, semantic corruption, decoder/control safety and the asynchronous-write regression. |
| `docs/adr/0006-review-versioning.md` | Records the five separate contracts, read versus execute boundary, migration policy and limitations. An ADR is a short explanation of an engineering decision and its consequences. |
| `docs/progress/completion-01.md` | This phase's implementation, verification and teaching record. |

Private receipts are outside the fixed archive at `data/review-archives/step01-checks/`: `original-files-before-final-checks.json`, `archive-verify.json`, `archive-inspect.json` and `final-original-comparison.json`. They are stored privately and ignored through the existing archive-directory rule. The explicit inspection receipt contains saved case detail and is not copied into this report.

## Function and statement walkthrough

Line numbers below identify the final files at the time of this report. The functions are grouped by the responsibility of their statements; old workflow functions are not rewritten.

### Entry point and CLI

- `__init__.py:1` explains the import boundary. It deliberately contains no execution imports.
- `__main__.py:3` imports `main`; the module guard passes its return value to `SystemExit`, preserving success/error exit codes.
- `cli.py:12`, `_parser`: defines the nested commands, required archive path and required case identifier. Disabling abbreviation prevents ambiguous command options.
- `cli.py:39`, `_error`: serializes an expected error to stderr and returns 1. Escaped JSON preserves text without displaying raw terminal-control characters.
- `cli.py:45`, `main`: parses first, imports the reader afterward, dispatches the selected operation and prints only a fully serialized finite result. Syntax errors use argparse's exit 2; successful reads use exit 0. Unexpected programming errors are not blanket-swallowed by the CLI.

### Archive boundary and five contracts

- `archive.py:38`, `_reader_errors`: translates expected malformed-input/filesystem/SQLite failures into the reader's domain error at the public API boundary.
- `archive.py:51` through `_json_read`: canonical JSON preserves the old digest definition; duplicate keys, nonfinite constants and oversized manifests fail. Expected digest comparison binds the JSON bytes to their completion receipt.
- `archive.py:81` through `_hash`: reject traversal and symlink components, require regular files, hash through a read-only descriptor and detect replacement or observed metadata changes while reading.
- `archive.py:142`, `_all_disk_members`: inventories actual files/directories, rejects special files, links, hardlinks and nonprivate modes, and propagates directory-walk errors instead of silently skipping unreadable content.
- `_fields`, `_sha256`, `_register_member` validate exact object fields, digest syntax and nonconflicting member paths.
- `archive.py:182` through `_validate_runtime_links`: interpret the archive's recorded runtime links lexically. They check the preserved link contract; they do not create links, execute runtime code or follow them to original locations.
- `archive.py:263`, `_validate_manifest`: validates the preservation-v1 schema, runtime declaration, paths, file entries, raw/normalized database membership and sidecar receipts. Declared complete runtime metadata must satisfy the pinned execution-package contract; an excluded runtime is reported as not captured.
- `archive.py:373`, `_check_payload`: checks every recorded file's size/hash and compares exact on-disk membership. `_restore_relative` is a pure mapping retained for manifest collision checks; this reader does not restore or extract anything.
- `archive.py:411`, `_snapshot`: captures identity and metadata before/after inspection. Access time is intentionally excluded because reading may update it.
- `archive.py:417`, `_execution_sources`: mirrors v1's complete immediate `agent/*.py` and `agent/*.sql` glob plus its five shared modules. This also catches future added workflow files.
- `archive.py:427`, `_current_execution_manifest`: separately hashes current files and reads current package metadata, without importing the application. An unavailable comparison is reported separately from archived evidence validity.
- `archive.py:439`, `_captured_execution_manifest`: reads historical files and direct captured `.dist-info/METADATA` headers. Duplicate/malformed versions, folder/header disagreement and nested vendor substitution fail. Current versions never fill missing historical metadata.
- `archive.py:483`, `_read_archive`: validates completion/manifest/verification receipts, verifies full membership, reads normalized databases once, checks the old logical receipt and external simulation attribution, then builds the catalogue and detailed case views. Recipe checks are memoized by both recipe and retrieval evidence so identical evidence is not repeatedly hashed for every case.
- `archive.py:561`, `verify_archive`: exposes a catalogue without query text or reviewer reasons. `archive.py:567`, `inspect_case`: deliberately returns one matching case's primitive evidence after verifying the entire archive. An unknown/ambiguous identifier fails. Neither API offers a resume operation.

### Source and model recipe checks

A recipe describes the configuration and input fingerprints used for an experiment; it is not executable instructions.

- `archive.py:595`, `_finite_json`, and its digest/text/path helpers bound the recipe's primitive structure and canonical bytes. `_relative` maps a historical path lexically beneath the recorded source root; it does not use the current working directory, expand variables or follow original paths.
- `archive.py:671`, `_CapturedFiles`: allows only manifest-listed captured files. Directory-relative descriptors, no-follow flags, size/hash checks and fixed budgets prevent arbitrary path access. JSON is parsed with duplicate-key checks; model bytes are hashed without loading them.
- `archive.py:767`, `_normalized`, and `archive.py:776`, `_fictional_entities`: reproduce the frozen fictional data representation with entity/alias order and `provenance: null`. They do not import the current entity loader. This reconstructs the real demo's reference digest.
- `archive.py:813`, `recipe_contract`: separates opaque recipes, missing inputs and present contradictions. It links saved retrieval configuration, package labels and reference digest to the recipe, then binds the acquisition receipt's canonical digest and file list to captured artifacts. For the actual case, all **10 E5 recipe files**, including weight bytes, verified. This is distinct from Step 00's broader 18-entry inventory across models.

The five recorded retrieval-package versions remain `recorded_only`. They are not the four workflow-package versions used for the execution guard. Database-backed source recipes also remain `recorded_only` when their bytes exist: this phase does not reconstruct their reference digest or repair source provenance. `original_recipe_database_opened: false` means original paths were not opened; normalized archived database copies still undergo structural checks.

### Frozen protocol decoder

- `compat_v1.py:24`, `ArchiveError`, gives callers one explicit unsupported/corrupt-evidence error type. The path/hash helpers beginning at line 44 reject unsafe paths and sidecars before database access.
- `compat_v1.py:116`, `_PV1MessagePack`, is a bounded primitive decoder. `_pv1_inert_shape` and `_pv1_decode` allow only the specific pinned interrupt-control representation where required. They never import a class named by stored data, call a constructor or enable pickle.
- `compat_v1.py:278`, `_pv1_initial`: validates the exact frozen initial envelope, including empty/pending values and input types. This prevents a forged initial-only case from claiming it already contains a review.
- `compat_v1.py:323`, `_pv1_schedule`: interprets the supported checkpoint version, channel versions, seen versions and runnable branch. An audit event alone cannot claim workflow completion.
- `compat_v1.py:376`, `_pv1_history`: validates sequential history, node outputs, task paths, interrupt/resume controls and durable submission agreement. It also handles the proven asynchronous-write window described below.
- `_pv1_packet` and `_pv1_submission` validate candidate/evidence identity, rank, finite scores, packet digests and permitted annotation relationships. `_pv1_rows` bounds reads; `_pv1_quote` quotes SQLite identifiers.
- `compat_v1.py:625`, `_pv1_database`: opens only an already normalized copy with `mode=ro&immutable=1`, then enables query-only/trusted-schema restrictions and checks integrity, foreign keys and schema. It performs no journal recovery or setup.
- `_pv1_expect_schema` and `_pv1_constraints` validate tables, columns, keys and uniqueness rather than accepting a matching version number alone.
- `compat_v1.py:713`, `_pv1_review_pair`: cross-checks the ledger, audit chain, packet, submission, checkpoint states and controls. The audit hash retains the original literal `payload_json` string. A genuinely initial-only empty checkpoint store is allowed; missing pending history is not.
- `compat_v1.py:962`, `_pv1_saved_demo`: verifies the known saved demonstration and its external `simulated_demo` attribution. Nonobject transcript JSON fails with a controlled error; no original audit row is relabeled.
- `compat_v1.py:1035`, `_verify_archive`: opens normalized archive derivatives, closes all connections and checks database bytes again. `read_v1` at line 1103 returns receipt and private details in one pass. `verify_v1` at line 1131 returns only the receipt; `inspect_v1` at line 1137 selects one detailed record.

### What the tests teach

The archive tests begin with real temporary fictional workflows, preserve them, and then test the public APIs/CLI. Mutation tests change archived data and, where appropriate, recompute its hashes: that proves the reader checks meaning as well as checksum agreement. A separate small fixture constructs captured package metadata without loading it. `TestRecipeContract` uses tiny fictional bytes named like model files; it does not perform ML inference.

The compatibility tests generate actual crash states in subprocesses, normalize temporary store copies, and compare decoded detail with saved rows. They prove changed current code still blocks active execution. The final deterministic pair at `tests/test_review_compatibility.py:540` models a missing asynchronous output batch and rejects an inconsistent successor checkpoint.

## Bugs found and fixed during this phase

Initial test runs exposed missing scheduler/control checks, legitimate creation-only handling, malformed transcript shapes and invalid initial envelopes. Independent review also found directory-walk error suppression and overly permissive package-metadata selection. Each received a focused implementation fix and regression coverage.

A combined run then failed a genuine `during_explanation` crash fixture, even though a preceding run had passed. Inspection of the pinned runtime showed why: ordinary task-output batches and the successor checkpoint are written by independent background operations. A crash may preserve the checkpoint first. The reader now checks the successor's exact node transition, updated channels, unchanged unrelated state, version/step sequence and durable submission. It validates every present output batch but does not invent a requirement that the preceding asynchronous batch must exist. Detail output exposes affected checkpoint IDs in `checkpoints_without_preceding_write_batch`. The real preserved case has no such gaps.

The first combined test run also exposed a missing `copy` import in the newly integrated recipe tests. This was a test integration error, fixed before the passing runs below. No known failing Step 01 test remains.

## Commands actually run and results

Commands ran from `/Users/odin/Desktop/polyglot-watchlist-starter`. Test outputs below describe observed runs, not invented totals or inferred passes.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q -m 'not integration'
```

**405 passed, 3 deselected, 13 subtests passed in 32.40 s.** This includes the existing tests, 87 preservation tests, 67 archive tests and the then-current 41 compatibility tests. The last two deterministic regression tests were added afterward; the full suite is not mislabeled as a 407-test run.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q tests/test_review_archive.py
```

**67 passed, 13 subtests passed in 2.06 s.** A final run after removing unnecessary imports from test subprocess snippets also passed **67 tests and 13 subtests in 2.12 s**. The full offline run includes the final application field-name integration.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  tests/test_review_compatibility.py -q -p no:cacheprovider --tb=short
```

**41 passed in 4.72 s**, after the asynchronous-write fix. Five additional fresh-process runs of this command with `-k actual_historical` each passed seven cases: **35 fresh historical fixtures**, with per-run times 4.32 / 4.42 / 4.30 / 4.34 / 4.26 seconds. These repetitions address the observed timing issue; they are not 35 additional distinct test definitions.

The same command with `-k missing_async_write_batch` passed the last **2 tests**, with 41 deselected, in **1.61 s**. This completes coverage of the final 43-test compatibility file without claiming an unrun full-suite total.

```sh
.venv/bin/python -B -m watchlist.review archive verify \
  --archive data/review-archives/v1

.venv/bin/python -B -m watchlist.review archive inspect \
  --archive data/review-archives/v1 \
  --case-id e449b466-466d-4b81-9a29-cb3c9d957823
```

Both returned **exit 0**, using the offline environment variables above. Stdout was redirected to private files outside `v1/` with `umask 077`. The final standard-library comparison checked the 187 original files and found zero changes. The archive's own before/after snapshot checks passed in both reads. All seven new Python source/test files also passed AST syntax and trailing-whitespace checks; report code fences were checked. No Git directory exists; no Git validation is claimed.

## Example input and output

`archive verify` produced the following selected fields from the real archive:

```json
{
  "status": "verified",
  "archive_format": "polyglot-preservation-v1",
  "execution_allowed": false,
  "verification": {
    "scope": "historical_integrity_and_v1_protocol",
    "files_verified": 37357,
    "databases_verified": 4,
    "case_count": 1,
    "independent_authentication": false
  }
}
```

Explicit inspection returned `annotation_origin: "simulated_demo"`, `review_status: "recorded"`, `audit_status: "committed"`, and four audit events. Captured/current fingerprint comparisons were both true, while execution remained false. Query text and reviewer notes are omitted here and from the catalogue operation.

## Limits and retained boundaries

1. **Integrity is not authentication.** A locally stored hash chain and receipts cannot stop an attacker who can replace every unanchored artifact. Reviewer labels do not establish a human's identity. Evidence still represents possible research matches, not wrongdoing or confirmed identity.
2. **Private, quiescent archive assumption.** Hashes and metadata comparisons detect observed changes; they are not an OS snapshot or locking protocol against concurrent hostile path replacement. Access times may change. Current compatibility is a point-in-time observation.
3. **Frozen supported format.** This adapter supports preservation-v1, review-v1 and the pinned checkpoint/control format. Unknown versions fail instead of guessing or reviving objects. Task identifiers are treated as opaque and checked for consistency; runtime-specific task UUID derivation is not recomputed.
4. **Source/runtime claim limits.** The actual fictional source digest is reconstructed. Public-source database reference/provenance reconstruction belongs to Step 03's repair. Retrieval-package labels remain recorded evidence. Weight-byte verification is not inference validation, a licensing determination or a model-quality measurement.
5. **No execution/migration shortcut.** The reader cannot resume, repair or migrate. The original execution guard remains strict. Any later approved migration or fresh review must create linked new records while retaining original history.
6. **Interpreter bytecode.** Use `-B` or `PYTHONDONTWRITEBYTECODE=1` for a process with no import-cache writes. The library does not change global Python settings. Reading a file can update filesystem access time.

These are explicit product/format boundaries, not hidden incomplete Step 01 implementation tasks. The unrelated R1–R5/E1–E2 defects and broader project deliverables remain assigned in the completion plan; none was silently repaired or claimed finished here.

## 5W1H recap

| Question | Plain-English answer |
| --- | --- |
| What? | A separate reader checks and displays preserved research evidence. A schema describes record shape; a fingerprint is a checksum of the exact code/dependency inputs. |
| Why? | Necessary source fixes must not make old evidence unreadable, and old cases must not execute under changed behavior by accident. |
| When? | After preservation, particularly once workflow source changes. Use verification before explicit detailed inspection. |
| Where? | The new `watchlist.review` package reads the chosen archive's captured files and normalized database copies. A normalized copy has already consolidated journal content during preservation. |
| Who? | Researchers and reviewers inspect evidence; an explicitly approved future migration/re-review process governs new cases. No reader output establishes authenticated review or identity. |
| How? | Check inventory, bytes and supported relationships; decode primitive data; report compatibility and evidence status separately; never run the workflow. |

## Next phase preflight — Step 02, not started

**Goal and reason:** repair R1/R2 so malformed commands and read-only inspection cannot initialize, chmod or mutate a workspace. This depends on the completed archive-reader boundary, because fixes to existing agent files will change their execution fingerprint.

**Files:** edit `src/watchlist/agent/cli.py`, `src/watchlist/agent/storage.py`, `src/watchlist/agent/state.py`; extend `tests/test_agent_cli.py`, `tests/test_agent_state.py`, `tests/test_review_audit.py`, `tests/test_review_resume.py`; create `docs/progress/completion-02.md`. No new library is expected. Shared application files need one editor per file.

**Sequence:** first reproduce R1/R2 with failing tests; validate JSON object/type/field/path and command contracts before storage access; separate explicit initialization, existing writable open and nonmutating inspection; avoid saver setup in reads; return structured expected errors while preserving unexpected programming errors. Preserve the existing distinction between a missing CLI argument and a supplied invalid name that may legitimately become an audited invalid-query case.

**Expected command:** `.venv/bin/python -B -m pytest -q tests/test_agent_cli.py tests/test_agent_state.py tests/test_review_audit.py tests/test_review_resume.py`, followed by the appropriate offline regression suite and archive-compatibility checks.

**Risks:** accidentally creating or changing stores during status, masking programming defects, breaking permitted invalid-query auditing, or weakening strict compatibility. Tests must use temporary fictional stores, not the original preserved case.

**Acceptance:** null/boolean/number/string/array/wrong-path/missing-argument inputs produce the documented error/exit behavior before mutation or retrieval; missing storage is reported, not created; existing-store reads do not change bytes, modes or schema; valid start/review and strict historical execution rejection remain covered.

Stop here. `AGENTS.md` requires: “AFTER every phase … STOP until user approves the next phase.” Step 01 approval has been fulfilled; Step 02 requires its own approval.
