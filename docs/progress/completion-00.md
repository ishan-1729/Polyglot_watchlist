# Completion Step 00 — preserved baseline and verified restore

**Status: complete within the approved Step 00 scope.** Report date: 24 October
2026, Asia/Kolkata. Capture time: `2026-10-23T19:12:41.195833+00:00` (UTC).

The existing research prototype now has a private verified archive and a fresh
verified restore. Application, configuration, model and data files were preserved.
Of the 184 files recorded before this phase, 183 retain their original bytes and
permissions; the only changed existing file is the explicitly approved
`.gitignore`. All 187 project files selected at capture still match their captured
hashes, permissions, identities and modification metadata after the restore.

The preserved demo contains one completed fictional case, one review packet, one
submission, four audit events, nine checkpoints and 44 checkpoint-write rows.
Its packet, submission, audit chain, pending/final checkpoint states and saved
transcripts agree. External private attribution identifies the assistant-created
annotation as `simulated_demo`; original case rows and JSON were not rewritten.

**Validation:** 87 preservation tests passed; 210 existing offline tests passed.
Three optional inference integration tests were explicitly deselected from the
existing-suite run. The actual archive, independent archive verification, fresh
restore, restored model/cache checks and restored-package smoke all passed.

## Authorization and phase boundary

This implements Step 00 of [the complete project plan](/Users/odin/Desktop/polyglot-watchlist-starter/docs/project-completion-plan.md:117)
after the user's explicit approval. The coordinator used the five requested Astra
workers for safety review, tests, database evidence, runtime recovery, and
source/model/publication review. It introduced no dependency and performed no
network access, download, installation, paid/API operation, training, inference,
application repair, migration or graph execution. Git initialization, staging,
commits and pushing were excluded from this approval; no `.git` directory exists.
Project 2 was not implemented.

This report uses the completion-plan numbering. Historical numbered phase reports
remain unchanged; this is not a replacement for the original Phase 00 report.

## Deliverables and changes, file by file

| File or directory | What changed and why |
| --- | --- |
| [scripts/preserve_v1.py](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py) | New standard-library command-line utility. Captures originals through read-only descriptors, verifies coherent copied stores, verifies archive membership, and restores to a fresh private destination. It sits outside fingerprinted application source. |
| [tests/test_preserve_v1.py](/Users/odin/Desktop/polyglot-watchlist-starter/tests/test_preserve_v1.py) | New tests using temporary fictional projects/stores and tiny fictional runtime trees. Covers recovery, source preservation, invalid paths/manifests, concurrency and publication failures. |
| [docs/maintenance/baseline-and-backup.md](/Users/odin/Desktop/polyglot-watchlist-starter/docs/maintenance/baseline-and-backup.md) | New operator guide explaining preconditions, commands, raw versus consolidated copies, permissions, recovery limits and what the runtime check proves. |
| [docs/releases/v1-manifest.json](/Users/odin/Desktop/polyglot-watchlist-starter/docs/releases/v1-manifest.json) | New allowlisted public summary with counts, source/config/dependency hashes, recorded source/model descriptors and actual verification outcomes. It excludes review identifiers, notes, queries, aliases and absolute local paths. |
| [.gitignore](/Users/odin/Desktop/polyglot-watchlist-starter/.gitignore) | Added `data/review-archives/` so private archives, restore drills and supporting receipts are excluded from normal Git staging. No Git commands were run. |
| [data/review-archives/v1](/Users/odin/Desktop/polyglot-watchlist-starter/data/review-archives/v1) | Private archive: original selected project/runtime files, inert runtime-link metadata, four consolidated database derivatives, full manifest, logical receipt and completion marker. |
| [data/review-archives/v1-restore-drill](/Users/odin/Desktop/polyglot-watchlist-starter/data/review-archives/v1-restore-drill) | Fresh extracted project/environment/framework plus derivative databases and `RESTORE-COMPLETE.json`. Retained for review. |
| [data/review-archives/step00-checks](/Users/odin/Desktop/polyglot-watchlist-starter/data/review-archives/step00-checks) | Private before-change inventory, runtime rehearsal receipt and post-restore original-file comparison. These are outside the archive’s fixed membership. |
| [docs/progress/completion-00.md](/Users/odin/Desktop/polyglot-watchlist-starter/docs/progress/completion-00.md) | This report: actual outcomes, code walkthrough, commands, examples, limitations and next boundary. |

The public summary and this report were generated after capture and are explicit
snapshot exclusions to avoid self-reference. The maintenance guide, utility and
tests are included in the archive. Historical project documents are included.

## What was captured

| Category | Regular files | Regular-file bytes | Directory entries | Recorded links |
| --- | ---: | ---: | ---: | ---: |
| Project | 187 | 1,041,397,260 | 47 | 0 |
| Installed environment | 25,306 | 808,612,344 | 2,490 | 3 |
| Python framework | 11,860 | 510,314,403 | 2,157 | 36 |
| Consolidated database derivatives | 4 | 622,592 | 0 | 0 |
| **Total** | **37,357** | **2,360,946,599** | **4,694** | **39** |

The byte total is approximately 2.36 decimal GB, before the small manifest/receipt
files and filesystem overhead. It excludes transient caches and bytecode. Both
models, source receipts/exports, frozen splits, historical evaluations and all
seven embedding-cache JSON/NumPy pairs are present. The full manifest digest is:

```text
ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d
```

The dry run found 15,138,770,944 free bytes against a 4,991,573,838-byte estimate
covering capture, restore, database working copies and overhead. After restore,
10,426,597,376 free bytes were observed. Disk availability is time-dependent.

Two existing links, in Tcl and Tk `PrivateHeaders`, have missing targets. Their
exact original link text and absence are preserved, with `target_exists=false`.
All other recorded runtime link targets are represented by the captured tree.
No original header links were repaired or omitted.

## How preservation works, step by step

1. Validate source/workspace/output paths, required existing stores and the lock.
   Refuse missing members, symlink components, project hardlinks, special files,
   overlaps and existing destinations. Inspect space before creating the archive.
2. Open the established lock read-only and acquire it without creation, truncation
   or chmod. Use `lsof` to refuse other lock/database/sidecar descriptors, including
   idle database readers. Keep other applications stopped throughout capture.
3. Inventory original file bytes, sizes, identities, permissions, relevant times
   and directory membership. Preserve every present SQLite main/WAL/SHM/rollback
   journal file. Copy independently and recheck originals and sidecar membership.
4. Keep raw archive bytes untouched. Copy complete SQLite file sets to disposable
   working directories, recover journals there, and use SQLite backup to produce
   consolidated derivatives. The original databases are never SQLite inputs.
5. Check copied SQL integrity, foreign keys, schema and review/checkpoint evidence.
   Decode the pinned checkpoint format inertly, without importing saved classes,
   pickle, `ReviewService`, `SqliteSaver` setup or graph execution.
6. Verify exact archive membership and hashes, fsync completed files/directories,
   and install the completion marker atomically without overwrite. Any failure
   before successful completion leaves no valid completion marker.
7. For the drill, restore into a newly created private destination. Check bytes,
   membership, modes and links. Rebuild derivatives from the restored raw database
   sets and compare logical receipts; do not merely trust copied derivative files.
8. Import packages from the restored source/environment under isolated Python,
   with offline settings and controlled temporary scratch. Recheck the restored
   tree after imports, verify the archive again, and publish the restore receipt.

A WAL is the file in which SQLite can retain committed changes before merging
those changes into its main database. A rollback journal records information
needed to undo an unfinished transaction. Preserving both types prevents a main
file copy from accidentally losing committed data or retaining uncommitted data.

## Code walkthrough with line/function references

| Entry point or helper | Explanation |
| --- | --- |
| [_paths](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:314) | Rejects unsafe/overlapping paths and requires the existing lock and database pair. It does not initialize an incomplete workspace. |
| [_inventory](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:263) | Walks the explicit project/runtime allowlist, records file metadata/hashes and inert link targets, and excludes transient/self-referential outputs. |
| [_locked](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:367) and [_lsof](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:342) | Establish the existing application lock and check actual open-file users. Only the utility's precise lock descriptor is exempted. |
| [_copy_file](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:207) | Reads a verified no-follow source descriptor, exclusively creates a private destination, writes/fsyncs it and checks source identity/metadata again. It never makes source/destination hardlinks. |
| [preflight](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:407) | Composes path, runtime, inventory, lock, open-user and free-space checks without creating directories or opening SQLite. |
| [_backup_databases](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:422) | Makes further disposable copies of all database sidecars, triggers recovery only there, and closes both connections after using SQLite's backup API. |
| [_resolve_runtime_member](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:515) | Resolves captured link components entirely from the manifest with bounded traversal, including `Versions/Current`, missing targets and cycle/escape rejection. |
| [_validate_manifest](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:577) | Enforces member types, canonical contained paths, restore mappings, runtime contract, database coverage and declared sidecar/link membership before extraction. |
| [_PV1MessagePack](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:1002) | Bounds byte length, nesting and item count and decodes primitive checkpoint data. Only the exact pinned interrupt representation is allowed in its specific control-write context; no dynamic class loading occurs. |
| [_pv1_review_pair](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:1351) | Checks schema constraints, canonical packet/submission hashes, ordered audit envelopes, checkpoint ancestry and links between durable records and checkpoint state. |
| [_pv1_saved_demo](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:1563) | Compares the preserved known demo with its independently saved pending/completed/recovery/audit transcripts and supplies external simulation attribution. |
| [logical_verification](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:1631) | Opens only normalized, sidecar-free copied databases read-only, combines structural/semantic receipts and confirms no inspection writes occurred. Immutable mode is used only after recovery/consolidation, never to skip original WAL data. |
| [_publish_json](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:183) | Writes a fully fsynced temporary JSON marker and installs it with no-replace link semantics; cleanup/rollback removes only the marker owned by this operation. |
| [apply_archive](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:712) | Holds the lock across capture and verification, checks originals again and publishes the complete archive last. |
| [verify_archive](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:776) | Checks completion/manifest hashes, exact private membership and actual payload bytes, then repeats logical verification on disposable copies. |
| [_check_restored_payload](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:830) | Checks the extracted inventory, file hashes/modes, independent inodes and exact link text before and after verification and imports. |
| [restored_runtime_smoke](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:1958) | Runs restored Python with `-B -I -S`, loads restored source/packages without editable `.pth` startup, checks import origins and distribution metadata, and records the original-framework dependency. |
| [restore_archive](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:871) | Requires a fresh destination, reconstructs files/links, repeats raw-data recovery and logical checks, requires successful requested smoke and confirms the archive remained unchanged. |
| [main](/Users/odin/Desktop/polyglot-watchlist-starter/scripts/preserve_v1.py:2068) | Parses mutually exclusive operations, rejects irrelevant flag combinations, prints JSON results and reports safety failures with a nonzero exit code. |

The utility is intentionally narrow to this established v1/macOS CPython 3.14
baseline. It is separate from the future product archive reader and does not add
application workflow features.

## Actual commands and test results

Commands were run from `/Users/odin/Desktop/polyglot-watchlist-starter`. No commands in this section are hypothetical.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/test_preserve_v1.py
```

Final result: **87 passed in 12.32 seconds**. The suite uses fictional temporary
stores and runtime trees. It covers dry-run invariance, missing/busy/idle-reader
failures, main/WAL/journal recovery, original bytes/modes/inodes, wrong database
pairs, invalid schemas and evidence, unsafe serialized data, permissions under a
permissive umask, tampered/re-signed manifests, path escape/cycles, source changes,
copy/fsync/space/SQLite/late-lock failures, marker rollback, fresh restore and CLI
contracts. The last ten added tests cover faithful runtime-link restoration.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -B -m pytest -q -m 'not integration' --ignore=tests/test_preserve_v1.py
```

Result: **210 passed, 3 deselected in 11.98 seconds**. The three deselected tests
are explicit local-model inference integrations. This phase verifies model bytes
and restored imports, not inference quality; no broader evaluation or training
result is claimed. The later runtime-link changes touch only the separately
retested preservation utility/tests, not the application suite.

```sh
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/preserve_v1.py --workspace data/review --output data/review-archives/v1 --dry-run
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/preserve_v1.py --workspace data/review --output data/review-archives/v1 --apply
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/preserve_v1.py --output data/review-archives/v1 --verify
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/preserve_v1.py --output data/review-archives/v1 --restore --restore-to data/review-archives/v1-restore-drill --smoke
```

Final results: dry run `ready`; apply `verified`; independent verify `verified`;
restore `verified`, all with exit code 0. The initial dry run had exited safely
with code 1 on the original dangling framework header links and created no
archive. It was retried after faithful-link support and tests passed. There was
one successful actual archive capture and one successful actual restore.

Additional actual checks used standard-library scripts to compare the original
184-file inventory and the captured 187 project files, inspect JSON receipts,
verify source/model/cache hashes and generate the public summary. Syntax checks
used `compile`/`ast.parse` without writing bytecode. The runtime rehearsal copied
only source/environment into a temporary private tree and removed that tree after
validation; its private receipt preserves failed attempts and the successful run.

### Example input/output

The real `--apply` command returned this summary (field order simplified):

```json
{
  "status": "verified",
  "database_count": 4,
  "file_count": 37357,
  "missing_runtime_link_count": 2,
  "original_bytes_and_modes_unchanged": true,
  "manifest_sha256": "ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d"
}
```

The real restore receipt reports `raw_bytes_verified=true`,
`logical_evidence_verified=true`, `archive_unchanged=true`, and
`runtime_smoke.ok=true`. Its full detail is private at
[RESTORE-COMPLETE.json](/Users/odin/Desktop/polyglot-watchlist-starter/data/review-archives/v1-restore-drill/RESTORE-COMPLETE.json).

## Actual preserved-store and runtime evidence

| Copied database | User version | Table row counts | Integrity and foreign keys |
| --- | ---: | --- | --- |
| `data/review/cases.sqlite` | 1 | audit_events: 4, cases: 1, review_packets: 1, review_submissions: 1 | Passed |
| `data/review/checkpoints.sqlite` | 0 | checkpoints: 9, writes: 44 | Passed |
| `data/sample.sqlite` | 2 | aliases: 8, entities: 3, sources: 1 | Passed |
| `data/watchlist.sqlite` | 2 | aliases: 79, entities: 20, sources: 1 | Passed |

The original live database sets had no WAL, SHM or rollback journal companions
at capture. Their absence was recorded and rechecked under the lock. Recovery of
nonempty WAL and hot rollback journals was nevertheless tested with actual
crash-left fictional SQLite file sets.

The restored smoke imported `watchlist`, `rapidfuzz`, `numpy`, `torch`,
`transformers`, `sentence_transformers`, `langgraph`, and
`langgraph.checkpoint.sqlite` from the restored trees. It found **82 installed
distributions**, checked **3,808 imported-file locations**, and verified the exact
identity/type/source of Torch's two synthetic module objects. The interpreter used
CPython 3.14.0 and SQLite 3.50.4 on this Mac. Scratch cleanup succeeded. No model,
case database or graph was loaded/executed by the smoke test.

The smoke's audit hook denied two internally attempted writes to `/dev/null`;
the imports handled those denials and succeeded. Torch emitted its existing
macOS redirect-support note. Neither changed the restored files or the successful
import result. Offline settings and Python audit checks are not an OS sandbox
against arbitrary native code.

Independent artifact checks passed on both archive and restore: **18/18 model
receipt entries**, **7/7 embedding-cache pairs**, raw source/metadata receipt hashes,
and **40/40 selected application/configuration/dependency hashes**.

## Issues found and addressed during this phase

- macOS `lsof` returned exit code 1 when the utility's lock was open but the named
  databases had no open descriptors. The initial implementation rejected that
  safe state. It now accepts the documented observed combination only when its
  own exact lock descriptor is found, no other descriptors appear and stderr is
  empty. Busy/idle-reader tests still reject actual open users.
- Runtime imports need private temporary scratch, and Torch exposes two synthetic
  modules with placeholder filenames. The smoke now permits scratch only in its
  disposable private directory and verifies those two objects narrowly against
  their defining restored source. It does not waive general origin checks.
- The installed Tcl/Tk header links are already dangling. They are captured as
  such, rather than omitted or repaired. Tests include nested link components,
  missing targets and direct/prefix-growing cycles and escapes.
- Safety review tightened manifest types/coverage, path validation, atomic marker
  installation, exception-safe SQLite closure and rollback after late failures.
  These are fixes to the new preservation utility, not application repairs.

## Acceptance evidence and limitations

Every preservation acceptance item in approved Step 00 has actual evidence:
original protected file comparison; stable coherent raw database capture; four
verified consolidated copies; case/evidence/checkpoint correspondence; fresh raw
restore and repeated logical verification; preserved model/cache assets; tested
same-host package imports; preserved historical reports and external simulation
attribution; private permissions and ignore rule. Git was separately excluded.

Recovery limitations remain explicit:

1. **Same-host runtime:** preserved `.venv` links and native binaries depend on the
   original Python framework and compatible macOS libraries. Framework bytes
   were restored and hash-checked, but independently relocating/running that
   framework or rebuilding from a complete offline wheelhouse was not proved.
   Old console-script shebangs/editable paths can point at the live project;
   use the isolated invocation in the guide.
2. **Known missing development headers:** the two original Tcl/Tk header targets
   remain absent. The validated imports do not claim those SDK headers exist.
3. **Integrity scope:** access times, generated bytecode and transient caches are
   excluded. Raw captures are byte-identical; consolidated SQLite files are
   separately verified derivatives. Root/container directories remain private;
   recorded nested regular-file/directory modes and link text are restored.
4. **Operational scope:** other database/review processes must stay stopped.
   `flock`, `lsof` and repeated checks do not defeat a hostile same-user/root
   filesystem racer. The archive verifier is for these locally created archives,
   not arbitrary downloaded archive packages.
5. **Storage/trust:** archive and drill are on one local disk, so this is not an
   off-device disaster-recovery copy. Local hashes are not independent trusted
   signatures, encryption, reviewer authentication or tamper-proof audit anchors.
6. **Licensing:** source/model descriptors are historical receipts. E5's local
   card/receipt declare MIT but no standalone LICENSE/NOTICE file was present.
   MiniLM's existing license text is preserved. No new legal validation,
   redistribution permission or missing license text is inferred.
7. **Research scope:** this is a matching research prototype and the preserved
   annotation is simulated. Successful preservation is not proof of model
   quality, identity, wrongdoing, live screening safety or application defect
   resolution. Known project issues remain assigned to their planned phases.

These are boundaries of the approved preservation result, not unperformed
Step 00 implementation tasks. No source edit for a later phase is hidden here.

## 5W1H recap

| Question | Answer |
| --- | --- |
| What? | A verified private capture and fresh restoration of the established v1 research baseline, with explicit runtime limitations. |
| Why? | Later source fixes can invalidate old execution fingerprints; preserve the original implementation and evidence before changing them. |
| When? | After explicit Step 00 approval and before Step 01 or any application repair; completed locally on 24 October 2026. |
| Where? | Ignored local archive/restore directories, plus public summary and maintenance/progress documentation. |
| Who? | The coordinator integrated work from five requested Astra workers; this does not convert the existing assistant demo into human review. |
| How? | Existing lock/open-file checks, raw byte capture, SQLite recovery on copies, bounded evidence verification, hashes, failure tests and a fresh isolated import/restore drill. |

## Next phase — not started

Step 01 will separate historical archive inspection from workflow execution. It
will add a narrow read-only v1 reader that verifies stored evidence without model
loads, graph setup, migration or source-hash rewriting, while preserving strict
compatibility checks for any pending execution. It will test completed, pending,
interrupted, corrupt and unsupported archives after current source bytes change.

Its exact files, commands and acceptance criteria are already specified in
[Step 01 of the completion plan](/Users/odin/Desktop/polyglot-watchlist-starter/docs/project-completion-plan.md:132).
No Step 01 application files were created. Work stops here under
[AGENTS.md](/Users/odin/Desktop/polyglot-watchlist-starter/AGENTS.md:10): “Do not start later phases automatically” and
“STOP until user approves the next phase.”
