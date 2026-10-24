# Review-store reconciliation and recovery

This guide describes Completion Step 04 for the existing, local `review-v1`
workflow. It is a research prototype: a saved annotation is a reviewer opinion
about possible record matches, not an identity finding or evidence of wrongdoing.
The reference proposal's broader agent features do not authorize additional
models, services, data acquisition, or Project 2.

## What is being reconciled?

The workspace contains two SQLite databases and one coordination file:

| File | Purpose |
| --- | --- |
| `cases.sqlite` | The original request, immutable candidate packet, accepted review submission, and hash-linked audit events. This is the case ledger. |
| `checkpoints.sqlite` | LangGraph's saved state, next node, complete checkpoint history, and pending task outputs or interrupt/resume controls. A checkpoint is a saved position from which the graph can continue. |
| `writer.lock` | An operating-system advisory lock used by cooperating readers and writers to keep the pair stable while it is copied or changed. The file's continued existence does not mean a process still holds its lock. |

Reconciliation means checking that these records describe the same case and a
possible point on the approved graph. A valid SQLite file and an intact local
hash chain alone do not establish that the two databases belong together.

A schema is the database's required table and constraint layout. A digest is a
hash of saved content used to detect inconsistencies; it is not authentication.
The audit chain links each event to the previous event's hash. SQLite's
write-ahead log (`-wal`) can contain committed changes that have not yet moved
into the main database file, which is why recovery must preserve the sidecars.

The graph is sequential:

```text
request envelope -> normalize -> retrieve_e5 -> format_candidates
                 -> prepare_review -> human_review -> explain -> audit_record

normalize validation error -------------------------> explain -> audit_record
```

`prepare_review` commits the packet and `suggestions_ready` event before its
checkpoint advances. `review` commits the submission and `review_submitted`
event before resuming the graph. `audit_record` commits `case_finalized` before
its checkpoint records the final receipt. These separate commits create valid
crash windows; recovery must recognize them without inventing new evidence.

## Reading and validating the pair

Existing workspaces must contain both recognized database schemas and the
existing lock. Neither reader nor writer creates a missing companion, runs
schema setup against an existing store, or silently upgrades historical stores.

Before operational access, storage copies the pair and any present SQLite
`-wal`, `-shm`, and `-journal` sidecars while holding the workspace lock. SQLite
recovery and backup run against those private copies. The resulting normalized
copies contain committed WAL records and are decoded without executing graph
nodes. Validation covers the whole workspace, including cases other than the
one requested; an inconsistent peer case also blocks access.

There are two distinct checks. Opening an existing `ReviewService` context
validates the owned schemas and complete saved protocol, including the live
task/receipt links, on copies before opening original writable SQLite handles.
A structurally valid historical pair can pass this check even when its saved
execution fingerprint differs from the current code. Before every service
operation, `_admit` rechecks the whole pair and requires its workflow/schema
and execution fingerprints to match. Incompatible execution is rejected before
graph work or original-store mutation. Opening a context is therefore not
permission to resume a historical workflow. Current reader status/list
operations also enforce their fingerprint check; the frozen archive reader
remains the historical evidence-inspection interface.

The frozen `watchlist.review.compat_v1.read_v1` decoder validates the historical
format, field shapes, audit chain, packet hashes, checkpoint lineage, scheduler
transitions, and control-write associations. The live storage checks add the
requirements in this matrix, including durable packet/submission links. The
frozen archive decoder remains unchanged. Successfully inspecting an archive
does not authorize running its workflow with changed code.

The live execution checks additionally require the first full application
checkpoint to equal the original request defaults, verify normalization and
its error branch, and bind saved task and interrupt IDs to the deterministic
identities used by pinned LangGraph `1.2.16`. A syntactically valid UUID alone
does not prove the runtime will consume a saved task output. Pending format
outputs must carry the packet's digest, and pending audit outputs must carry the
exact existing final event's receipt. The SQLite saver
contract remains pinned to `langgraph-checkpoint-sqlite` `3.1.2`; dependency
upgrades require a reviewed compatibility change.

All surviving checkpoints must form the one supported, consecutive history
from the initial input envelope. A full child checkpoint can legitimately
survive without its preceding node's output-write batch: the pinned LangGraph
runtime saves them separately. The decoder validates that surviving full
transition. Complete saved pending task outputs and controls must also match
their scheduled node. Arbitrary missing parents, skipped stages, orphan writes,
foreign threads, or partial application states are not equivalent to this valid
missing-batch window.

The service asks the runtime for the explicitly admitted latest checkpoint ID,
then compares its state and next node with the inertly decoded copy. This reads
the saved step before applying pending outputs; the runtime's ordinary live
view can hide a task whose output was saved before the next checkpoint.
Recovery consumes a complete saved task result by continuing with a `None`
input before considering an interrupt. This ordering matters when the
human-review result already survived: it avoids issuing a second resume for
work that was already accepted.

## Allowed state matrix

Every row assumes matching request identity, workflow/schema fingerprints,
recipe, packet revision, hashes, and any required parent checkpoints. An absent
record at a stage does not authorize creating a missing database. `R` means the
`request_created` event; `P` means the packet plus `suggestions_ready`; `S`
means the accepted submission plus `review_submitted`; `F` means
`case_finalized`. Events and their corresponding ledger rows must agree.
With an existing valid checkpoint history, diagnostic `attempt:*` events may be
interleaved without changing the semantic stage; they do not replace packet,
submission, or final receipts. The no-checkpoint exception is narrower: the
ledger must contain exactly the original `request_created` event for this case.
If graph invocation fails before saving its first checkpoint, the service
returns that exception and leaves the creation event alone. It does not claim
that this failure was durably logged or append an event that would invalidate
the narrow fresh-start exception.

| Saved stage | Latest checkpoint / next node | Durable ledger | Allowed recovery |
| --- | --- | --- | --- |
| Request committed before graph invocation | No checkpoint row or pending write for this thread | Exactly `R`; no `attempt:*`, `P`, `S`, or `F` | Submit the exact saved initial envelope once. Normalization and retrieval may run because no retrieval evidence survives. |
| Input envelope saved | Checkpoint exists with only `__start__` carrying the original envelope; next `__start__`; no full application state yet | `R`; no `P`, `S`, or `F` | Resume the existing checkpoint with `None`. Do not submit a second initial envelope. |
| Initial application state | Full original defaults; next `normalize` | `R`; no `P`, `S`, or `F` | Resume normalization from the saved request. |
| Normalized request | Normalized name; no retrieved packet or digest; next `retrieve_e5` | `R`; no `P`, `S`, or `F` | Continue retrieval, or consume a verified complete saved retrieval-output batch if the runtime already persisted it. A past attempt without surviving output is not durable evidence. |
| Retrieval output saved | Candidates, evidence, and retrieval metadata; digest not yet set; next `format_candidates` | `R`; no `P`, `S`, or `F` | Validate and hash the saved evidence. Do not call the retriever again. Empty candidate lists are valid retrieval results and still require review. |
| Formatted packet, before ledger prepare | Matching nonnull `evidence_sha256`; `review_status=not_requested`; next `prepare_review` | `R`; no `P`, `S`, or `F` | Commit this exact packet and its event, then continue to review. No retrieval. |
| Packet committed, checkpoint not advanced | Same formatted packet and digest; `review_status=not_requested`; next `prepare_review` | `R + P`; no `S` or `F` | Replay `prepare_review` idempotently: the same packet/event is accepted without another logical event. This is `after_packet`. No retrieval. |
| Prepared, before first human interrupt | Matching packet; `review_status=pending`; next `human_review`; no interrupt yet | `R + P`; no `S` or `F` | Run the human-review node until it saves its interrupt. No reviewer outcome is selected. No retrieval. |
| Awaiting review | Matching pending packet; next `human_review`; matching saved interrupt | `R + P`; no `S` or `F` | Return pending status. `recover` does not invent a submission. A new explicit review must bind the exact checkpoint ID, packet digest, and revision. |
| Submission accepted before checkpoint review transition | Same pending checkpoint and its interrupt; optional matching resume/task-output records | `R + P + S`; no `F` | Resume using the exact durable submission. Keep its submission ID, actor label, timestamp, outcome, candidate, and reason. A second `review` is rejected; use `recover`. |
| Review transition saved | `review_status=recorded`; `reviewer_decision` equals `S`; next `explain` | `R + P + S`; no `F` | Produce the deterministic explanation from saved packet and annotation. No retrieval. |
| Explanation saved | Exact saved packet, accepted annotation, and explanation; next `audit_record`; audit pending | `R + P + S`; no `F` | Commit the final event from this saved state. No retrieval. |
| Final event committed before final checkpoint | Same explanation and final payload; next `audit_record`; audit pending | `R + P + S + F`; `F` equals checkpoint evidence, decision, explanation, and error | Replay finalization idempotently and save its existing receipt. No second logical final event and no retrieval. |
| Completed | No next node; `audit_status=committed`; event ID and audit-head digest identify `F` | `R + P + S + F`, all matching | Return saved completion. Repeated recovery keeps the same packet, submission, final event, and receipt. |

An accepted submission must retain the actual interrupted pending checkpoint
named by `expected_checkpoint_id`, even after later checkpoints exist. That
checkpoint must be an ancestor of the latest one and carry the same packet.
A pending-looking state without its interrupt is not enough to justify an
already accepted review.

The invalid-query branch has its own legitimate shorter path. A blank or
overlong query within the stored request envelope can reach `normalize`, save
an `invalid_query` error, proceed to `explain`, and finalize that error. It has
`R`, optionally then `F`, but no packet, no submission, and no retrieval. Its
explanation states that no review conclusion was recorded. The final-event
before-final-checkpoint window and idempotent receipt rules apply to this
branch as well. Operational retrieval/storage failures do not become an empty
result, an invalid-query conclusion, or an automatic clearance.

## Forbidden combinations

These are rejections before graph execution, retrieval, or mutation of the
original workspace. Protocol damage is rejected on copies before original
writable SQLite access. A structurally valid pair with an incompatible
execution fingerprint can enter a context, but its workflow operation is
rejected. These failures are not instructions to delete or regenerate records.

| Observation | Why it is rejected |
| --- | --- |
| Missing directory, lock, ledger, or checkpoint database; truncated/unrecognized database | An existing workspace is incomplete or is not an owned format. Reopening must not initialize a replacement. |
| `P`, `S`, or `F` survives but this thread's checkpoint history is absent | Later durable progress cannot be treated as a fresh request. |
| No checkpoint survives and this case has an `attempt:*` event or any event beyond `request_created` | The narrow before-invocation exception requires the exact initial envelope and its sole creation event. |
| `P` survives but the latest checkpoint is only the input envelope, initial defaults, normalized request, or unhashed retrieval stage | Prepare could only have committed after a complete matching formatted checkpoint. This surviving combination indicates rollback or mixed generations. |
| Checkpoint is pending or recorded but the ledger packet/event is absent | The checkpoint has advanced beyond durable prepare without its required receipt. |
| Checkpoint packet, digest, original header, query, or recipe differs from the ledger | Recovery must not change evidence or retarget a request. |
| Submission or submission event exists without its counterpart, packet, matching pending ancestor, or actual saved interrupt | An accepted opinion must remain tied to the evidence and checkpoint that the reviewer saw. |
| Checkpoint review decision differs from the accepted submission; unexplained second submission or revision | Recovery cannot overwrite or substitute the accepted opinion. |
| Final event differs from the latest explanation/evidence/decision/error; committed state lacks its exact final receipt | Ledger and graph disagree about completion. A local hash alone does not repair that disagreement. |
| Extra namespace, orphan/foreign thread, branched/skipped/missing-parent history, impossible scheduler state, or mismatched pending outputs/controls | The saved graph cannot be explained by the supported sequential workflow. |
| Requested case is coherent but another case in the same pair has conflicting surviving progress | The databases are a workspace pair. Selecting one healthy case does not make a mixed-generation pair safe. |
| Stored execution fingerprint differs from the executing implementation | Context opening may succeed for a valid protocol, but every workflow operation must reject the mismatch. Read historical evidence through the compatible archive reader; do not rewrite its fingerprint. |

“Replaced checkpoint database” is detectable when its contents conflict with
surviving ledger progress or case/checkpoint identity. It is not universally
detectable from the filename or SQLite schema. The v1 format has no independently
stored workspace generation counter or external trusted history anchor. In
particular:

- A request-only ledger and an empty, correctly owned checkpoint database are
  indistinguishable from the legitimate crash before the first checkpoint.
- A coherent rollback of the entire ledger, checkpoint history, audit tail, and
  every other surviving local record to an earlier valid point is
  indistinguishable from that earlier point.

Structural checks reject conflicting surviving progress. They do not certify
that erased history never existed, authenticate a local actor label, prove
backup freshness, or defeat an attacker who can replace every record and hash.
An independently retained trusted receipt or backup history would be a separate
design and is not introduced by this change.

## The five explicit crash windows

These names are injected test failpoints. Tests terminate a separate process
with `os._exit(77)` after the indicated durable action; they do not merely throw
an exception that lets context managers close the databases normally.

| Failpoint | Last durable action | Required result after reopening |
| --- | --- | --- |
| `after_case` | Initial case and `request_created` committed, before graph invocation | Recover the saved envelope. Exactly one first retrieval may occur for a valid query. Finish at the real human interrupt. |
| `after_packet` | Packet and `suggestions_ready` committed; latest checkpoint still formatted and scheduled for prepare | Reuse packet bytes/digest, replay prepare, and reach the interrupt with zero retriever calls. |
| `after_submission` | Submission and `review_submitted` committed, before resume | Consume the saved submission with zero retriever calls; preserve its complete contents. |
| `during_explanation` | Review transition checkpoint saved; explanation node has started but not returned its output | Produce the explanation from the saved review, with zero retriever calls. |
| `after_final_audit` | `case_finalized` committed; final checkpoint not saved yet | Reuse the existing final event and save its receipt, with zero retriever calls. |

Each successful recovery must end with one logical final event. On the normal
path without diagnostic attempt events, the four semantic audit events are
`request_created`, `suggestions_ready`, `review_submitted`, and `case_finalized`.
Tests also repeat `recover` and race separate reviewers; only one submission
and one final event may win. These checks establish the tested process-crash
behavior on the local pinned runtime, not a general power-loss or distributed
transaction guarantee.

## Lock ordering and bounded waits

`ReviewReader(root, lock_timeout=5.0)` and
`ReviewService(root, retriever, mode='existing', lock_timeout=5.0)` use seconds.
The accepted value is a finite, nonnegative `numbers.Real` value that converts
to a finite float; this includes integers, floats, and `fractions.Fraction`. Booleans,
strings, `None`, negative numbers, NaN, infinity, and numbers that cannot be
represented as a finite timeout are rejected before filesystem effects.
`0` makes one immediate nonblocking attempt. The default is **5 seconds**.
Contention raises `TimeoutError` with
`review workspace is busy; lock wait timed out`; it does not create an audit
attempt or run retrieval. The CLI uses the default; there is no new
`--lock-timeout` option.

The ordering is:

1. Validate arguments and existing paths; acquire `writer.lock` before copying
   the databases or beginning any database transaction.
2. A reader takes a shared lock for its stable copy. Readers can coexist. After
   copying, it validates and reads private normalized copies. It does not open
   the originals through SQLite.
3. A writer takes an exclusive lock, checks the entire copied pair's saved
   protocol, and only then opens original SQLite handles. Each requested
   operation rechecks the pair and its current execution fingerprint under that
   same lock. Its copied validation path reuses the held lock instead of
   acquiring a second lock.
4. On writer exit, close checkpoint and ledger connections before unlocking and
   closing the lock descriptor. Error paths release held resources too.

There is no shared-to-exclusive lock upgrade. A CLI review preflight releases
its reader context before opening the writer context, which checks again under
the exclusive lock. A competing review can therefore win between checks;
the later writer must reject its stale or duplicate submission safely.

The deadline bounds waiting for the cooperating workspace lock, not total
validation, SQLite I/O, inference, or command duration. It is an advisory local
lock: a process that ignores it can still edit files. Never delete or replace
`writer.lock` to bypass a busy workspace; different lock inodes would stop the
processes from coordinating. Reopen after the holder exits or releases its lock.

## Commands and safe restoration

These are supported command examples, not claims that they were run while this
guide was written. Run from the project root with the existing pinned `.venv`.
Use fictional temporary workspaces for tests. The completion report records
actual commands, measured results, and preservation evidence separately.

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_review_resume.py tests/test_review_audit.py tests/test_agent.py

env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m pytest -q -m 'not integration' -p no:cacheprovider
```

The focused tests use authored mock retrieval output and disposable directories.
They cover process crashes, lost/rolled-back/mixed checkpoint histories,
nonmutation on rejection, contention deadlines, lock release, and review races.
These commands do not run opt-in model integration; successful model inference
and its timing must be reported from separately authorized measured checks.

For an already prepared, compatible **disposable recovery workspace**, write a
separate agent configuration that points `workspace` at that directory. Keep the
existing policy fields and leave the original configuration unchanged. Replace
the capitalized placeholders with this scratch configuration and its saved
thread ID:

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist.agent status \
  --config /ABSOLUTE/PATH/TO/recovery-agent.json --thread-id SAVED_THREAD_UUID

env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist.agent recover \
  --config /ABSOLUTE/PATH/TO/recovery-agent.json --thread-id SAVED_THREAD_UUID

env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist.agent audit-verify \
  --config /ABSOLUTE/PATH/TO/recovery-agent.json --thread-id SAVED_THREAD_UUID
```

Status and audit verification read copied evidence. Recovery is a write
operation in the selected scratch workspace. From a saved retrieval stage
onward it reuses saved evidence. A genuine pre-retrieval request can need its
original retriever and recipe; offline flags prevent network acquisition but
do not themselves prohibit local model inference. Do not use that path as a
model-free inspection command.

If reconciliation fails, preserve the entire failed workspace unchanged. Do
not delete rows, remove WAL files, regenerate a companion database, reseal
hashes, or replace one database with a convenient older copy. Stop cooperating
writers before capturing a new backup. A valid backup must bind the pair from
the same stable capture and include committed sidecar contents, rather than
copying two live main database files at unrelated times.

The existing preservation tool verifies and restores an already captured
coherent archive into a **new, absent destination**. For the preserved v1
baseline, the supported commands are:

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist.review archive verify \
  --archive data/review-archives/v1

env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B scripts/preserve_v1.py \
  --output data/review-archives/v1 --restore \
  --restore-to data/review-archives/recovery-drill-new
```

Do not point `--restore-to` at the live project or an existing recovery tree.
The restore tool validates archive membership and receipts, restores raw
database/sidecar sets and captured code/runtime assets together, re-derives
normalized copies, and writes `RESTORE-COMPLETE.json` only after verification.
Inspect the restored result before any separately approved execution. Read
[baseline-and-backup.md](baseline-and-backup.md) for the exact archive layout,
same-host runtime limitations, disk requirements, and import-only smoke check.

Restoring the v1 archive does not make its historical workflow fingerprint
current. Its historical evidence remains available through the archive reader;
current recovery must reject incompatible fingerprints. Never edit original
cases, stored recipes, historical reports, archive contents, or fingerprints to
make a recovery attempt appear compatible. Restoration provides a separate
reviewable candidate; it does not prove the chosen backup contains the newest
accepted review.

## 5W1H recap

| Question | Answer |
| --- | --- |
| What? | Check that the case ledger and checkpoint history describe one allowed point in the same workflow, then resume that point. |
| Why? | A crash can commit one store before the other; a missing or older companion must not cause fresh retrieval or lose an accepted review. |
| When? | Before existing-workspace operations and after interruption, before any resumed graph work or original-store mutation. |
| Where? | The local review workspace, with validation performed on private normalized copies and restoration performed in a separate new directory. |
| Who? | The researcher chooses a compatible workspace and, when needed, a coherent backup. A human supplies the review; local usernames are attribution labels, not authentication. |
| How? | Check schemas, complete checkpoint lineage, stage-specific packet/submission/final links, and saved controls under bounded cooperative locks; replay only the legitimate pending step. |

Step 04 changes recovery correctness, not matching quality, calibration,
licensing, model capabilities, or operational screening guarantees. Its actual
validation results belong in `docs/progress/completion-04.md`.
