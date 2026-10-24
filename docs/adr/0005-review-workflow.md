# Decision 0005 — proposed E5-only, human-reviewed local workflow

Date: 2026-10-22. **Planning approved; implementation and dependencies await explicit approval.** Full specification: [Phase 7A plan](../phase-07-plan.md). This deliberately advances the roadmap's review orchestration while Phase 5B/5C and Phase 6 remain deferred, not completed.

## Context

The user selected E5-small as the default and excluded automatic match/clear decisions without validated thresholds. Saved Phase 5A primary test-challenge top-1 counts were E5→MiniLM: fictional 26/27→25/27, public 141/141→139/141, multilingual 25/30→21/30. Preserve that negative experiment. It provides no justification for default reranking or immediate fine-tuning.

The existing matcher is a normal Python pipeline. It remains appropriate for one-shot retrieval. This milestone's new requirement is a human pause that survives process exit, with the same evidence when resumed.

## Proposed decision

Use a small sequential LangGraph StateGraph with existing normalization/E5 retrieval, deterministic candidate formatting, durable review preparation, one human interrupt, deterministic explanation and idempotent audit finalization. Use a local CLI and file-backed SqliteSaver. No LLM is needed. Return candidate suggestions and a human annotation; never output an automatic identity finding or clearance.

Keep top five E5 IDs/order/scores/aliases/provenance unchanged. No reranker node. The old RapidFuzz CLI and all baseline/evaluation artifacts stay intact. Default dataset is fictional; an existing SQLite snapshot is explicit and read-only.

Typed state contains original/normalized query, candidates, evidence, model/reference versions, review status, reviewer decision and audit identifier. Runtime validation supplements type hints. The scorer/model/DB connection are runtime dependencies, never checkpoint values. A frozen evidence packet is bound to each review by digest, revision and checkpoint.

Review outcomes: `candidate_for_follow_up`, `none_selected`, `unresolved`, always with a reason. None of these establishes identity or absence. All valid retrievals, including empty results, pause for review; errors remain errors.

## Persistence and recovery

Use separate local checkpoint and case/audit SQLite files; keep the source database unchanged. They are not a shared atomic transaction. A durable submission before resume, unique event/submission keys, a local writer lock and explicit reconciliation handle the crash windows. Replayed nodes may execute again; effects must be idempotent. Resume uses the same thread and frozen packet. Version mismatch or conflicting duplicates block progression.

A per-case hash chain plus integrity checks supplies limited tamper evidence, not tamper-proof storage. No claim of verified reviewer identity in this single-OS-user CLI. No cross-case memory, automatic training-label export, remote trace service or automatic retention deletion.

## Alternatives and consequences

- A custom Python/SQLite state machine could implement this; LangGraph is chosen for explicit resumable-workflow learning and standard pause/checkpoint mechanisms, not accuracy.
- In-memory checkpointing is useful for unit tests but cannot meet restart acceptance.
- Streamlit adds UI/session complexity; defer until CLI semantics are proven and separately approved.
- A LangGraph Store, Postgres, external audit anchors and multi-user authentication are unnecessary for this bounded local pilot.

Proposed direct pins: LangGraph 1.2.16, checkpoint 4.3.0, SQLite saver 3.1.2. MIT declarations and compatible checkpoint requirement ranges were verified in official metadata; runtime compatibility with Python 3.14 and complete transitive resolution are untested. Optional temporary uv 0.13.5 bootstrap, package budget and commands are in the full plan. No packages were installed.

## Acceptance and stop gate

Require offline mocked tests, actual SQLite subprocess pause/resume, failure-injection recovery, duplicate/stale/cross-case rejection, audit integrity checks, no-MiniLM assertions, opt-in local E5 adapter parity and prior-file hash preservation. Record actual counts and a fictional walkthrough only after implementation. Improvement in Recall/MRR is not expected from unchanged retrieval.

**Await approval for the bounded Phase 7A implementation and dependency setup. No training, calibration, automatic decision routes, new model/data, UI service or wider Phase 8 scope is approved.**

## Implementation outcome — 2026-10-22

The user approved Phase 7A and the bounded dependency setup. The [implementation report](../progress/phase-07a.md) is the current execution record; the proposed text above remains history. Installed the exact three approved pins on existing Python 3.14 after compatible-wheel resolution and a real strict-serializer/SQLite/recovery smoke test. Existing runtime versions and baseline code/results remain unchanged.

Implemented E5 top-five, immutable evidence, unconditional human pause, explicit validated form, deterministic explanation, separate SQLite stores, local writer lock and replay-safe audit. New user submissions reject duplicates; `recover` alone reuses an accepted persisted submission. This follows the latest user instruction rather than the older plan's identical-submission response. A JSON review file replaces the illustrative long argument list. Status can list saved case IDs. No migration, thresholds, LLM, memory reuse, service or UI framework. Remaining operational limitations and actual acceptance checks are in the report.
