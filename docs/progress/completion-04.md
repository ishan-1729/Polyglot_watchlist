# Completion Step 04 — checkpoint reconciliation and crash recovery

Date: 2026-10-24, Asia/Kolkata. Status: **complete within the approved recovery scope**, under the user's explicit Step 04 approval. This is Completion Step 04, not the historical embedding Phase 4. Final verification passed: **1,211 non-integration tests, 13 subtests, and all 3 local model integration tests**. No known Step 04 acceptance failure remains; the broader project and Step 05 are not complete.

## Approved scope and preflight

The goal is to reject missing, replaced, inconsistent or rolled-back checkpoint state when surviving records show later progress, before retrieval or original-store mutation. Legitimate interrupted work must recover without retrieving saved evidence again, losing an accepted review or creating a second logical final event.

Approved edits: `src/watchlist/agent/storage.py`, `tests/test_review_resume.py`, `tests/test_review_audit.py`, `tests/test_agent.py`. New documents: `docs/maintenance/recovery-state-matrix.md` and this report. Dependencies remain the existing pinned LangGraph, SQLite saver and runtime. Original databases, source/model artifacts, preserved archives, frozen archive decoder, schema files and historical reports stay unchanged. No network, downloads, paid APIs, Git operations or deployment are authorized by this step.

Expected validation: focused audit/resume/agent tests, the offline non-integration suite, archive verification/inspection, and all three existing opt-in already-local E5/MiniLM integration tests with temporary cache/config paths and networking blocked. New model inference is limited to those approved local checks using authored fictional inputs.

The coordinator and five Astra/max workers divide storage implementation, subprocess recovery regressions, audit reconciliation tests and independent review, lock/concurrency tests, and the recovery-state matrix/design review. An app interruption ended the initial workers after their tests were written; replacement workers continued from those saved tests and the preserved baseline instead of restarting the work.

## Baseline evidence

- Step 03's full baseline was **1,069 passed, 3 deselected, 13 subtests**.
- The pre-Step-04 inventory records hashes, modes and sizes of **208 existing files** in `data/review-archives/step04-checks/before-files.json`.
- The initial audit test selection observed **12 failures, 28 deselected**: inconsistent accepted submissions, audit/case identities and orphan checkpoints reached original writable SQLite before reconciliation. Test guards prevented that access.
- The initial subprocess recovery selection observed **12 failures, 10 passes, 134 deselected in 27.02 s**. Eleven invalid-history cases attempted retrieval and changed storage; a prior checkpoint generation containing only a peer case was accepted when recovering that healthy peer. All five genuine crash windows already met the new retrieval-count assertions; missing/truncated-file checks also passed.
- After restart, the lock constructor/default selection observed **25 failures, 42 deselected in 0.19 s** because the timeout API was absent. This run alone does not measure the old blocking wait's duration.
- Existing saved model verification passed: ten E5 files at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` and eight MiniLM files at revision `1427fd652930e4ba29e8149678df786c240d8825`. This verifies local files; it is not yet an inference test result.

## Evidence boundary

The legacy format has no independent workspace epoch or external monotonic record. A matching-schema empty checkpoint substituted while only the initial request survives, and a coherent replacement of all evidence with an earlier valid pair, cannot be distinguished locally from that valid earlier state. The implementation rejects contradictions in surviving progress without claiming authentication or universal rollback detection. The supported states and limits are specified in `docs/maintenance/recovery-state-matrix.md`.

## What the repair changes

A checkpoint is the graph's saved position. Reconciliation checks whether that position agrees with the ledger's original request, candidate packet, reviewer submission and final audit event. It runs on private copies of the entire workspace before an existing writer opens original SQLite files, and again before each public operation. A damaged peer case therefore cannot be hidden by selecting a healthy case.

The request-only exception is deliberately narrow: a case with no checkpoint must have exactly its original `request_created` event. An input-only checkpoint is a different valid state: it resumes with `None`, which tells LangGraph to continue saved work, rather than submitting a second initial request. After durable retrieval output exists, recovery consumes that output and never calls the retriever again.

The immutable packet, accepted submission and final receipt remain linked to their actual checkpoint history. An accepted submission needs its saved human-review interruption even after completion. A second external review is rejected; internal recovery consumes the accepted submission. Finalization reuses one logical final event.

Saved task outputs require an additional execution check. The historical reader treats task IDs as opaque identifiers, whereas the running graph uses exact deterministic IDs to find reusable work. Live storage now verifies the pinned runtime's task/interrupt identities and pending audit receipts. It asks the runtime for the explicit latest durable checkpoint, then compares its state and next node to the independently decoded copy. This avoids misreading a saved task-output batch as an already completed graph.

Both reader and writer accept `lock_timeout`, defaulting to **5 seconds**. A zero timeout tries immediately; invalid, negative, infinite, NaN or boolean values fail before filesystem access. The timeout bounds lock waiting, not the duration of copying, validation, inference or a review operation. Cooperating readers share the lock; writers hold it exclusively. Database handles close before the writer lock is released.

## File and function walkthrough

### `src/watchlist/agent/storage.py`

| Function / area | Explanation |
| --- | --- |
| `_validated_lock_timeout` | Validates finite nonnegative real seconds before touching a workspace. Fractions are accepted; booleans and complex values are rejected. |
| `_acquire_lock` | Uses nonblocking `flock` attempts and a monotonic deadline, polling at most every 50 milliseconds. A clock adjustment cannot lengthen the wait. |
| `_existing_lock`, `_copied_databases` | Carry the configured timeout through existing shared/exclusive lock paths. Copy the pair and sidecars while locked; SQLite normalization happens only on private copies. |
| `_require_live_execution` | Uses the frozen inert decoder after structural validation. Checks initial defaults, deterministic normalization/error results, pinned task and interrupt identities, formatted packet output, and final audit-output receipts. It does not execute graph nodes. |
| `_read_live_pair` | Combines complete owned-schema and frozen v1 protocol checks with live recovery requirements for every case. Rejects missing history after progress, packet/checkpoint disagreements and accepted reviews without their saved interruption. |
| `ReviewReader.__init__`, `__enter__` | Apply the bounded lock wait and complete copied-pair checks. Read-only status continues to avoid opening original databases through SQLite. |
| `ReviewService.__init__`, `__enter__` | Apply the timeout and reject active-context re-entry. Validate the existing pair's integrity before writable connections or runtime construction. Preserve the existing API boundary: a structurally valid historical pair can open, but `_admit` rejects its changed execution fingerprint before any workflow operation. |
| `ReviewService.__exit__` | Close both database connections even if one cleanup fails, clear stale handles and release the OS lock. Failed entry and later retry use the same cleanup path. |
| `_admit` | Recheck the whole pair under the held writer lock before each operation. Validation at context entry alone would miss damage introduced while that context remained open. |
| `inspect`, `status` | Inspect the explicit latest checkpoint rather than the runtime's live projection, compare state/next with admitted evidence, and require the final receipt for a terminal graph. |
| `invoke` | Allow only the saved initial request for a new case, `None` for legitimate continuing work, or the exact accepted review at its original interrupted checkpoint. Arbitrary input/update/goto commands cannot reset existing work. |
| `_record_attempt_error` | Add operational diagnostics only when the pair still admits them. A rejection does not mutate an invalid pair; an error before the first checkpoint must leave the request-only recovery exception intact. |
| `start`, `review`, `recover` | Admit before writing; separate duplicate or invalid caller submissions from operational failures; distinguish absent/input-only checkpoints; consume complete saved task results before considering another interrupt resume. |

The existing `Ledger` transaction, immutable packet and idempotent final-event mechanisms remain the underlying storage contract. No schema migration, new dependency, historical decoder edit or workflow-fingerprint rewrite is introduced. XXH3 comes from the already installed LangGraph dependency `xxhash`; its use is tied explicitly to LangGraph 1.2.16, with SQLite saver 3.1.2.

### Tests and maintenance guide

| File | What it demonstrates |
| --- | --- |
| `tests/test_review_resume.py` | Real terminated subprocesses at the five existing crash windows plus input-only, retrieval-output-write and retrieval-checkpoint boundaries. Checks zero retrieval after saved evidence, unchanged accepted reviews/final events, missing/truncated/replaced/rolled-back histories, mismatched peer generations and damage after writer admission. |
| `tests/test_review_audit.py` | Rejections on copies before writable original access; coherent but wrong audit/header/submission identities; missing interruptions; controlled direct invocation; saved output batches at all eight normal task boundaries; altered task IDs, impossible initial state and forged pending final receipts; startup failure before any checkpoint. |
| `tests/test_agent.py` | Subprocess writer contention, shared readers, timeout nonmutation, retry, constructor validation, handle cleanup, process termination, re-entry and one winning concurrent review. The in-memory graph smoke test now uses a direct graph and isolated ledger rather than substituting an in-memory saver into a service that promises a durable store pair. |
| `docs/maintenance/recovery-state-matrix.md` | Defines allowed and forbidden stages, crash windows, task-output handling, lock order, recovery/restore commands and the limits of detecting wholesale rollback. Commands in this guide are examples; actual executed checks are recorded below. |

## Verification discoveries

The test-first reproductions showed why checking only SQLite schemas or the selected case was insufficient. Independent review then found three less obvious windows: an altered task ID could cause repeated retrieval; an intact complete task-output batch could look terminal in the runtime's default view; and replaying an already saved human-review output could rewrite its resume bytes. The tests retain real emitted output batches and preserve their bytes while recovering at every normal node boundary.

A final startup-error regression failed before its fix: **1 failed, 72 deselected in 0.18 s**. The old error path appended an `attempt:*` event before the first checkpoint, creating a state that its own narrow recovery rule rejected. The exception remains visible to the caller; this window now preserves the untouched request for recovery.

Test construction also needed correction. A first provisional combined run had **292 passes and 7 failures** because newly added rollback fixtures read crashed main database files using immutable mode, omitting committed WAL contents, or compared bytes only after their own writable connection closed. Those fixtures now snapshot a coherent SQLite generation and distinguish nonmutation during rejection from their own close-time WAL flush. A later resume run had **169 passes and 1 failure in 54.19 s** because the new crash hook matched the initial `retrieval=None` field; requiring a nonnull retrieval result fixes the hook. These are disclosed fixture corrections, not successful application checks or weakened rejection assertions.

The first full-suite run had **1,205 passes, 1 failure, 3 deselections and 13 passing subtests in 95.63 s**. The existing compatibility test expected a valid historical pair to open before recovery rejects the changed implementation. Moving that fingerprint rejection to context entry had changed the established API boundary. The correction preserves full protocol validation before original access and whole-workspace fingerprint validation before each operation. The compatibility test and historical reader remain unchanged.

## Final verification

Final application source SHA-256: `9d7f8f621b50494ad365fa6043d3d524d2888b28f24d53db813bc2bc56fe25c2`. Current workflow fingerprint: `39a6725f106463b59e885010e7142d65f76c48188db00ed24c43d27d09c3314a`.

| Check | Actual outcome |
| --- | --- |
| Final full non-integration suite | **1,211 passed, 3 deselected, 13 subtests passed in 89.71 s**. The three deselected integration tests all passed in the separate run below. |
| All three existing local model integration tests, final source | **3 passed in 7.21 s**; **0 network attempts**, temporary caches/configs, no model download. |
| Focused audit file | **73 passed in 6.91 s**, before the final entry-boundary correction; included again in the final full suite. |
| Focused agent/lock file | **71 passed in 8.89 s**, before the final startup-error and entry-boundary corrections; included again in the final full suite. |
| Corrected actual saved-retrieval subprocess boundaries | **2 passed in 2.54 s**, before the final entry-boundary correction; included in the final full suite. |
| Exact compatibility regression plus existing fingerprint/archive checks | **3 passed in 1.54 s** on final source. |
| New direct-operation fingerprint regression | **5 passed in 0.37 s** on final source. Status, recover, review, start and invoke reject before runtime calls, ledger writes or file changes. |
| Fictional accepted-review recovery example | Passed: zero recovery retrieval calls, identical packet/submission, one final event and stable repeated recovery. |
| Historical archive verification and inspection | Both exited 0 and returned `verified`; **37,357 files, 4 databases, 1 simulated-demo case**. |
| Baseline preservation | **208 files checked: exactly 4 approved existing files changed, 204 unchanged, 0 missing, 0 unexpected changes**. Original stores, source-v3 rebuilds, model files/configs, historical reports and frozen compatibility code are covered. |
| Changed Python syntax and whitespace | All **4** files parse; final newlines present and no trailing whitespace. No bytecode was written. |

The three integration cases cover E5 shape/unit normalization/repeatability, MiniLM finite repeatable logits, and E5 candidate/evidence parity plus review restart with a retriever that refuses to run. They are deliberately separate from the non-integration suite; none is deferred or skipped in this step.

The fixed archive manifest remains `ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d`. Its historical execution fingerprint remains `545944411abe85d270737fe708de8e75e67e1516698d7b54df4e7313dc9960b9`. Both archive commands preserve `captured_execution_match=true`, `current_execution_match=false`, and `execution_allowed=false`. The historical case is readable, not executed or silently migrated.

Saved final evidence: `full-suite-final.log`, `local-integration.log`, `local-integration-result.json`, `archive-verify.json`, `archive-inspect.json`, `preservation-result.json`, `python-source-check.json` and `recovery-example.json` in `data/review-archives/step04-checks/`. Earlier freeze outputs are retained separately with `first-freeze-` and `second-freeze-` prefixes. The complete resume file now contains **175** cases; the audit and agent files contain **73** and **71** respectively.

### Commands actually executed

All commands below ran from `/Users/odin/Desktop/polyglot-watchlist-starter` with `PYTHONDONTWRITEBYTECODE=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and the existing `.venv/bin/python -B`. No package installation or acquisition was performed.

```sh
# Focused workers, using temporary fictional stores.
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_agent.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_review_audit.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_review_resume.py

# Final complete non-integration suite.
.venv/bin/python -B -m pytest -q -m 'not integration' -p no:cacheprovider

# All three existing local model integration tests, isolated and network-blocked.
.venv/bin/python -B data/review-archives/step04-checks/run-local-integration.py

# Preserved historical evidence; these commands never execute an archived case.
.venv/bin/python -B -m watchlist.review archive verify --archive data/review-archives/v1
.venv/bin/python -B -m watchlist.review archive inspect --archive data/review-archives/v1 \
  --case-id e449b466-466d-4b81-9a29-cb3c9d957823

# Disposable fictional recovery example.
.venv/bin/python -B data/review-archives/step04-checks/run-recovery-example.py
```

Additional focused selections checked the saved retrieval-output boundaries, startup failure, saved task batches and the exact historical fingerprint compatibility failure. The first full resume-file run is the disclosed 169-pass/1-fixture-failure run; the corrected complete file is included in the final full suite. Inline Python checks compared the baseline inventory and parsed the changed Python sources without creating bytecode. Logs, private verification harnesses and JSON receipts are under `data/review-archives/step04-checks/`, outside the preserved archive.

The integration harness enables all three existing `RUN_*_INTEGRATION` opt-ins, uses temporary copies of the two model configs with absolute local model paths, and redirects alias/Hugging Face/Torch/XDG caches to temporary directories. A Python audit hook rejects socket connection, DNS and datagram-send attempts. The actual result records network attempts rather than assuming offline flags prove there were none.

### Executed fictional input/output

`run-recovery-example.py` used mock authored candidates in a temporary workspace, interrupted after the submission transaction, closed it, then reopened with a retriever that raises if called. This example uses an injected `BaseException`; actual killed-process coverage is in pytest. It is an automated simulated annotation, not an independently authenticated human review.

Input: `"  LUMA   VESPER "`. Saved normalized query: `"luma vesper"`. The submitted opinion was `candidate_for_follow_up` for fictional `syn-001`.

```json
{
  "initial_retriever_calls": 1,
  "recovery_retriever_calls": 0,
  "completed": true,
  "packet_digest_preserved": true,
  "accepted_submission_preserved": true,
  "logical_final_events": 1,
  "audit_event_count": 4,
  "repeated_recovery_preserves_receipt": true,
  "duplicate_review_error": "duplicate review; use recover for an interrupted accepted submission"
}
```

These values were produced by the executed script and saved in `recovery-example.json`. The temporary directory was removed afterward. The initial example harness correctly hit the existing symlink-path rejection because macOS exposes its temporary parent through a symlink; resolving the temporary directory before creating the disposable workspace corrected the harness without changing application validation.

## Limitations and remaining project work

- Recovery is proved for the tested process-crash windows on the local pinned runtime. This is not a distributed transaction or arbitrary power-loss guarantee.
- Locks are advisory and require cooperating processes. The implementation uses `fcntl`; this step does not establish Windows support or multi-host coordination.
- Full-pair verification adds local I/O proportional to saved history. The existing 100-case/100 MB pilot bounds remain; this work makes no throughput claim.
- Saved digests detect inconsistent surviving evidence. They do not authenticate a reviewer, prove that erased history never existed or detect a coherent replacement of every local record with an earlier valid pair.
- Changing storage changes the execution fingerprint. Historical cases remain inspectable through the preserved reader; their fingerprints are not rewritten to allow current execution.
- The model checks exercise local inference and workflow integration on fictional examples. They do not establish multilingual accuracy, calibrated probabilities or operational screening suitability.

## 5W1H recap

| Question | Answer |
| --- | --- |
| What? | Reconcile the ledger and checkpoints before recovery, preserve saved work and bound lock waits. |
| Why? | Missing or contradictory saved state must not reset a reviewed case, repeat retrieval or lose a recorded annotation. |
| When? | Before an existing writer opens originals, before public operations and when recovering an interrupted task. |
| Where? | Review storage, three focused test files, temporary fictional workspaces and the recovery guide. |
| Who? | The researcher operates the local prototype; the saved annotation remains a reviewer opinion requiring human interpretation. |
| How? | Validate locked private copies, bind saved outputs to pinned executor task identities, resume the exact durable step and reuse immutable receipts. |

## Next: Step 05 preflight — evaluation contracts

**Goal / why:** fix E1/E2 before trusting new experiments. Every query, including an absent query, needs valid ancestry, alias ownership, labels and an immutable reference view. Shortlist metrics must distinguish the index population from the number of records returned.

**Exact files:** edit `src/watchlist/evaluation_data.py`, `src/watchlist/evaluate.py`, `src/watchlist/compare_retrieval.py`, `src/watchlist/splits.py`, `tests/test_evaluation_data.py`, `tests/test_evaluation.py`, `tests/test_compare_retrieval.py` and `tests/test_splits.py`. Create `src/watchlist/evaluation_metrics.py`, `src/watchlist/scripts.py`, `tests/test_evaluation_metrics.py`, `tests/test_evaluation_protocol.py`, `tests/test_scripts.py` and `docs/progress/completion-05.md`. Save comparison outputs in a new directory; preserve historical data/results and mark their use as regression-only through the new contract/report rather than rewriting frozen artifacts.

**Work:** reproduce E1/E2 with fictional fixtures; audit original and normalized query text, ownership, generation ancestry, script sets, target groups and views; separate train/calibration/test partition from presence/ambiguity labels; separate index size, requested k, returned count and evaluated depth; define positive/absent/ambiguous/unlabelable denominators; prevent withheld-alias or gold-label access; hand-check metrics before model work; replay historical results separately and explain any difference.

**Dependencies / commands:** completed storage repairs and existing pinned offline runtime. First inspect the current evaluation tests and saved inputs, then run the relevant focused pytest files, the full offline suite and a historical metric replay into a new comparison directory. No new model/data acquisition, network, paid API, package installation, Git action or public deployment is included.

Proposed focused command after the Step 05 files exist, with the same offline/no-bytecode environment:

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_evaluation_data.py tests/test_evaluation.py \
  tests/test_compare_retrieval.py tests/test_splits.py \
  tests/test_evaluation_metrics.py tests/test_evaluation_protocol.py tests/test_scripts.py
```

The replay will read existing saved evidence and write only a new `data/eval-comparisons/completion-05/` directory. Its exact CLI is to be confirmed from the current harness before execution; this report does not invent unsupported replay flags or claim an unrun comparison.

**Risks / acceptance:** stricter audit may reveal invalid legacy rows; preserve them and document exclusions instead of silently correcting history. In a 1,000-entity index returning 50 candidates, a target at rank 30 must count correctly at 50, while rank 51 or a missing target is a miss. Truncated rankings report MRR@K without invented tail ranks. Altered ancestry, wrong ownership, absent collisions and invalid views must fail. Historical full-ranking metrics must reproduce or each change must have a documented cause.

Step 05 is **not started**. `AGENTS.md` requires explicit approval before implementing the next step.
