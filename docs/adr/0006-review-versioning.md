# Decision 0006 — read historical evidence separately from workflow execution

Date: 2026-10-24. Accepted for completion Step 01, after the approved v1 preservation and restore drill. See the [completion plan](../project-completion-plan.md#step-01--separate-archival-reading-from-workflow-execution) and [Step 00 report](../progress/completion-00.md).

## Context and decision

The v1 workflow fingerprints its Python/SQL source and selected installed package versions. Even a comment changes a source hash. Its existing execution guard requires the saved schema, workflow version, and workflow hash to match the running implementation. That protects a pending case from continuing under changed behavior, but the old service also applies the guard when reading completed evidence.

Add a separate, standard-library-only reader under `src/watchlist/review/`. It reads preserved archive data with a frozen v1 compatibility contract. It verifies the stored evidence and its relationships without importing archived application code, importing LangGraph, loading a model, creating a service, or resuming a graph. Keep the existing execution guard unchanged.

The reader exposes only archive verification and case inspection. A successful response has `status: "verified"` and `execution_allowed: false`. Verification says that the supported archived records and receipts passed the reader's checks. It does not establish a person's identity, wrongdoing, reviewer authentication, or permission to execute a saved workflow.

## Five separate contracts

A contract is the set of rules needed to interpret or use a record. These contracts answer different questions and must not be collapsed into one version number.

| Contract | Meaning in historical v1 | What the reader may conclude |
| --- | --- | --- |
| Case schema | Stored `schema_version: "review-v1"` defines the case fields, types, and supported states. | The record has a supported structure and valid relationships. A recognized version alone is insufficient. |
| Packet contract | The immutable evidence packet is the field selection frozen by v1's `packet()` function. V1 stores its digest but has no separate packet-version field. | The reader applies an **inferred frozen review-v1 packet shape**, checks its finite canonical JSON digest, and checks submission/checkpoint links. It must not invent a historically stored packet version. |
| Workflow execution manifest | Stored `workflow_version` and `workflow_sha256` bind the case to source-file hashes and four workflow package versions. | The original fingerprint can be reconstructed from verified archived source and archived distribution metadata without importing that source. Missing historical metadata remains unavailable; current installed versions cannot fill the gap. |
| Source snapshot | The recipe's `reference_sha256`, source identifiers, and evidence provenance describe the reference data used for retrieval. | A saved reference hash records a claim about the historical data. Independent verification requires the corresponding preserved bytes and the defined hashing procedure; the reader must state which level it checked. A historical path is not permission to open a current source database. |
| Model recipe | The recipe records configuration, `model_receipt_sha256`, and retrieval package versions. | These bind the saved case to its recorded model setup. Checking a receipt is distinct from checking all model bytes or reproducing inference. Inspection loads no weights and reports no new model result. |

Database-backed source snapshots remain `recorded_only`: captured bytes and normalized SQLite structure are checked, but the recipe reference digest is not reconstructed. The five retrieval-package versions remain `recorded_only` even when the model receipt and files verify. The four workflow-package versions are checked separately against captured distribution metadata. `model_recipe.status: verified` means captured artifact agreement, not verified inference or retrieval-runtime behavior. `original_recipe_database_opened: false` describes paths recorded in recipes; normalized archive databases still receive read-only structural checks.

V1 canonical JSON sorts object keys, uses its original separators and UTF-8 encoding, and rejects nonfinite numbers. Preserve that byte definition for old digests. New code organization or new contracts cannot retroactively change it.

## Verification and execution compatibility

The archive reader checks the preserved manifest/receipts, supported database schemas, case and checkpoint correspondence, immutable packet and submission bindings, and audit-chain relationships. It decodes primitive application state and only the narrowly supported control-record shapes required by the pinned v1 serializer. Unknown schemas or unsafe serialized objects fail; no pickle or dynamic type loading is allowed.

Archived source is data to hash, never code to execute. Reconstruct the historical workflow fingerprint from the archived file set and its own distribution metadata. A separate current-workflow comparison may be `true`, `false`, or unavailable (`null`). It describes byte/version compatibility only. **Every archive response keeps `execution_allowed: false`, even when the current hash matches.** A valid audit hash is also insufficient by itself: the saved protocol state and evidence links must agree.

The existing active service retains its exact v1 guard. This decision adds no resume, recovery, review, migration, initialization, permission change, or data repair operation. It never rewrites `workflow_sha256`, packet digests, audit events, or chain heads to make an old case match new code. A future approved migration or fresh review must create a new case explicitly linked to the retained original case and record its own versions and evidence.

## Read-only commands and outputs

Run from the project using the reviewed local Python environment:

```sh
.venv/bin/python -B -m watchlist.review archive verify --archive data/review-archives/v1
.venv/bin/python -B -m watchlist.review archive inspect --archive data/review-archives/v1 --case-id AUDIT_ID
```

Replace `AUDIT_ID` with a case identifier returned by verification. The verification catalogue omits query text and reviewer notes; explicit case inspection returns the historical detail and annotation origin. The reader preserves attribution when an annotation was supplied by an external simulation rather than an authenticated human reviewer.

The `-B` interpreter option prevents bytecode cache writes throughout the process, including before package code runs. The reader itself never writes to the archive, creates temporary files, changes permissions, or performs a migration. Ordinary Python without `-B` may write its own `__pycache__` during import; the package does not change global interpreter settings to conceal that distinction.

Both commands emit one finite, ASCII-escaped JSON object on stdout and return exit code 0 on success. Expected archive or filesystem errors produce a concise JSON error on stderr and return 1; invalid command syntax returns argparse's exit code 2. ASCII escapes keep terminal control and bidirectional characters from altering the displayed output while preserving text for JSON consumers. Argument parsing completes before importing the archive reader. No command accepts replacement evidence, a model path, or a resume instruction.

## Consequences and validation

The extra reader duplicates a small, frozen subset of the v1 format intentionally: future application changes must not redefine old evidence. Unknown formats require a separately reviewed adapter. A hash chain provides limited local tamper evidence, not independent authentication; an attacker able to replace all data and unanchored receipts may replace the chain as well.

Inspection assumes a private, quiescent archive: no other process should edit it during the read. File hashes and before/after metadata checks reject observed content, membership, or identity changes. These checks do not create an operating-system snapshot or acquire a lock, and do not promise isolation from a process that can replace filesystem paths concurrently. Filesystem access times may change when files are read; they are excluded from the mutation comparison. A current-workflow match is a point-in-time observation, and the active service must still apply its own execution guard.

Acceptance requires inspection of completed, pending, and interrupted fictional archived cases after current source bytes change; rejection of corrupt/mixed stores and unknown control objects; and process-level checks for writes, permission changes, model/graph imports, and migrations. Tests must also preserve the active service's rejection of incompatible execution. Actual commands and results belong in the Step 01 progress report, rather than being assumed from this design.

## 5W1H teaching recap

- **What:** a frozen archive reader checks and displays old evidence; an execution guard controls whether a live workflow may continue.
- **Why:** engineers need to fix source code while keeping historical research records inspectable.
- **When:** use this reader after preservation, especially when current code differs from the saved workflow fingerprint.
- **Where:** the new `watchlist.review` package reads the selected archive; the existing `watchlist.agent` execution guard stays in place.
- **Who:** a researcher or reviewer may inspect evidence, while an explicitly approved future process would govern migration or a linked fresh review.
- **How:** verify preserved bytes and supported record relationships, decode only known safe shapes, report compatibility separately, and leave historical records unchanged.
