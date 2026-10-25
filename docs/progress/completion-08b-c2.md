# Step 08B-C2 — offline review packets and ledger

**Decision: C2 COMPLETE. Full Step 08 remains incomplete.** Completed locally on 2026-10-25 under the user's C2 approval, the [C1 next-package specification](completion-08b-c1.md), [completion plan](../project-completion-plan.md), [review/custody protocol](../planning/step-08b-review-and-custody.md) and [AGENTS.md](../../AGENTS.md).

C2 implements and validates the approved offline mechanics and creates blank development packets plus an empty private ledger. It does not execute human reviews, authenticate people, establish identity, accept labels, acquire data, publish a corpus, train models or enter Step 09.

## Actual deliverables

| Queue | Blank tasks | Meaning |
| --- | ---: | --- |
| Duplicate candidates | 1,259 | Review each existing equality nomination, retaining its evidence and unresolved component. |
| Flagged records | 2,864 | Review existing record/name restrictions without discarding aliases or clearing quarantine. |
| Proposed positives | 6,856 | One deterministic pair of distinct normalized nonweak, normalizer-accepted names per qualifying source observation. A provider's alias assertion is not a human label. |
| Negative candidates | 1,259 | Ask whether independent evidence establishes distinction for the **same existing equality pairs**. These are hypotheses, not negatives. |
| Total task entries | **12,238** | All unreviewed; duplicate/negative overlap is explicitly reported. This is not a count of distinct reviewed pairs, accepted labels or independent families. |

Positive selection sorts complete normalized keys, then evidence IDs; it does not choose favorable model scores or silently truncate long names. Weak/normalizer-rejected names are excluded from proposed-positive selection but remain preserved in C1 and visible in relevant flag evidence. Component and flagged-observation references propagate into packets. Every task has a stable version-bound identifier, neutral question, original-evidence references, script competencies, unresolved status and blank outcome. The source-qualified IDs, snapshots, primary names, aliases, original fields/qualifiers and unknown languages remain in pinned C1; `resolve_evidence` retrieves that original evidence for a case. This keeps packets compact without losing provenance.

The ledger contains **zero events, zero submissions and zero adjudications**; deterministic replay returns **12,238 unreviewed states**, with **zero accepted labels and zero identity merges**. Its real actor registry is empty. Real submissions are rejected by code, independently of editable permission flags. Fictional submissions exist only in isolated tests.

## Changed files and function explanations

| File | What changed |
| --- | --- |
| [readiness_review.py](../../src/watchlist/readiness_review.py) | New single-owner C2 module; no old source module or database schema was modified. |
| [corpus-review-v1.json](../../config/corpus-review-v1.json) | Pins the C1 configuration and manifest, all five historical retained selections and seven C1 artifact files, five monitored roots, queue counts, metadata, protocol/version identifiers, exact limits, empty actors and false use permissions. |
| [test_readiness_review.py](../../tests/test_readiness_review.py) | 105 fictional packet/ledger regressions, including genuine fictional continuation→C1→C2 integration. |
| [test_label_review.py](../../tests/test_label_review.py) | Four new cross-contract compatibility cases; old fictional APIs remain strict. |
| [data-card.md](../data-card.md) | Appends the measured C2 status and limitations; historical accounts remain intact. |
| [C2 evidence directory](../../data/eval-comparisons/completion-08b-c2/) | New private packets, empty ledger, test logs, supervision scripts/results, preservation evidence and completion record. |

Main functions in the new module:

- `_c1_payloads` (line 180) checks complete C1 byte pins and reconstructs its derived queues. `assemble_review_packets` (272) builds deterministic versioned tasks, bounds case expansion before appending, retains references and keeps queue hypotheses separate from labels.
- `_load_config` (457), `_account_inputs` (563) and `_admit_c1` (597) enforce the external configuration, existing normalized-byte accounting and strict C1 validation. `prepare_review` (733) writes only a new destination; `validate_review` (777) independently regenerates the packets from trusted sources.
- `_write_packet` (660) uses private staging, exact-byte checks, exclusive publication and a manifest written last. `_recheck_c1` (711) rejects changed upstream evidence before completion. Partial or existing output is never silently replaced.
- `_validate_packet_content` (839), `_load_packet` (954) and `_verify_packet_saved` (1022) reject malformed, changed, stale or cross-bound packet content. `write_fictional_packet` (814) requires the explicit fictional contract and namespaces; changing only a real packet's mode cannot make it a fixture.
- `_actors` (1047) records role, competencies, authorization reference, actor ID, principal ID and independence group for fictional tests. Shared authorization documents are permitted; two accounts for one principal/group cannot satisfy independent review.
- `_ledger_context` (1091) enforces pinned packet/configuration paths and inherited resource accounting even when callers do not supply a guard. `create_ledger` (1138) creates a private immutable header and empty event directory, returning a genesis hash to retain separately.
- `_locked` (1200) serializes verification and publication with an OS file lock and directory/lock-identity checks. `_event_payload` (1244) validates evidence, actor, timestamp, outcome, uncertainty/conflict declarations, rationale, relationship annotation and direction. Direction endpoints must be original name evidence, not identity-support references.
- `_apply_event` (1370) requires two independent initial reviewers and a separate adjudicator, retains disagreement, rejects replay/duplicate reviews and contradictory adjudications for the same pair, and never clears corpus eligibility. Definitive cross-record outcomes require identity-support evidence; current real packets contain none invented by Codex.
- `_replay` (1439) reconstructs state from immutable numbered events and validates hash ancestry against the caller's separately retained expected head. `replay_ledger` (1590), `_append` (1622), `append_submission` (1702) and `append_adjudication` (1727) reject stale heads, truncation, tampering and changed packets. Append execution remains fictional-only.
- `resolve_evidence` (1752) validates the packet/source bindings and returns original observations, nomination and quarantine context. Source text is untrusted data; no UI, shell, model or external service interprets it. `deny_network`/`main` (1822/1828) enforce the offline CLI boundary and aggregate failure output.

No new dependency, acquisition-client change, schema migration, legacy review-store mutation, model artifact change, commit or GitHub publication occurred. This workspace has no `.git` directory.

## Private artifacts and reproduction evidence

[Packet manifest](../../data/eval-comparisons/completion-08b-c2/packets/manifest.json):
`64d7b9d7ff120b0363d1cfae6ccee324cb61df8a8a44d3d836e4e70fec2868a3`

[Empty ledger header](../../data/eval-comparisons/completion-08b-c2/ledger/header.json), also its initial externally retained head:
`cd9b8e4f7d320d8a29368d9b8618a03fa8595b5e96532a030bdd05f4c238d7e3`

The packet binds C1 manifest `bb84c60fd09a4ff11fb93ddb5cb37d630c18b684cbc8d0d216ec3cabc047b195` and input manifest `70f334f28d6bcc276cff41c5f84bea1cb42b563748e91de2573da8b5a84e579c`. The parent source receipt and source files were not changed.

Packets plus empty ledger consume **9,478,867 bytes**. Data directories are private; completed packet/header/event files are read-only to normal writes. Ledger locking uses a separate private lock file. A hash chain detects corruption only against an independently retained expected head; it does not authenticate humans or defeat an administrator who replaces code and every trusted pin. Local private directories are not independent final-test custody.

If a write is interrupted before publication, it cannot become an accepted event. If interruption occurs after an event is fully published but before its new head is acknowledged, the old expected head fails closed. The persisted event must be inspected before an explicitly authorized head update; no automatic deletion, silent retry or history rewrite occurs. Tests exercise both sides of this boundary and competing writers.

## Tests and commands actually run

Focused tests initially passed 87 of 88 cases. The remaining test incorrectly assumed authorization references must be unique; one authorization document can legitimately cover multiple people. It was replaced with a shared-document positive test and stronger principal/independence-group checks. The subsequent focused run passed **101 tests in 1.92 seconds**. Four final direction-reference cases passed in **0.16 seconds**. Four compatibility tests passed with 47 deselected. These counts overlap the combined result; they are not additive independent test totals.

One final integration command:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q \
  tests/test_readiness_review.py tests/test_label_review.py \
  tests/test_corpus_readiness.py tests/test_record_links.py \
  tests/test_resource_guard.py -p no:cacheprovider
```

**306 passed in 2.74 seconds.** [Raw integration log](../../data/eval-comparisons/completion-08b-c2/integration-tests.log). Coverage includes deterministic replay/reordering; duplicate submissions; invalid or insufficiently competent reviewers; two accounts for one person; self-adjudication; uncertain/conflicting outcomes; wrong identity/name references; stale packets and ledger heads; rehashed corruption; valid-prefix truncation; interrupted publication; concurrent writers; unsafe paths/private modes; resource stops; offline enforcement; and old/new contract separation. The unchanged 2,606-test suite was not rerun.

Scoped Ruff `check --isolated --target-version py314` and `format --check --isolated --target-version py314` ran through `.tools/qa/bin/python -I -B -m ruff` on the new module, both changed test files and the two execution scripts. [Lint](../../data/eval-comparisons/completion-08b-c2/ruff-check.log) and [format](../../data/eval-comparisons/completion-08b-c2/ruff-format.log) passed. No tools were installed.

Real execution command:

```sh
.venv/bin/python -B data/eval-comparisons/completion-08b-c2/execute_supervised.py
```

The wrapper ran one serial `run_review.py` worker. It admitted resources, called `prepare_review`, created the empty ledger, independently called `validate_review`, and replayed the ledger against the external packet/head pins. It emitted only aggregates and artifact hashes. [Worker outcome](../../data/eval-comparisons/completion-08b-c2/worker-outcome.json): passed. [Supervision](../../data/eval-comparisons/completion-08b-c2/supervision.json): exit 0, no stop reason, **20.852 seconds**, peak sampled aggregate RSS **308,297,728 bytes (294.016 MiB)**. **Zero HTTP/network transactions**, no retries and no real review events.

Resource measurements: host free-memory fraction **46% → 45%**, no memory-pressure warning; free disk **35,678,134,272 → 35,672,924,160 bytes**. Conservative normalized reservation **51,669,797 / 100,000,000 bytes**; combined artifact reservation **74,733,977 / 2,147,483,648 bytes**. Existing source/C1 normalized inputs total **38,138,642 bytes**. The new C2 root plus staging remained within **16,000,000 bytes**; its final size including evidence is recorded in completion.json. Existing 1.5/2 GiB RSS limits, 25%/20% memory floors, 10 GiB disk floor and 60-minute limit remained active. Resource enforcement is sampled/cooperative with supervised process-group termination; the socket audit hook is not an OS network sandbox.

[Preservation check](../../data/eval-comparisons/completion-08b-c2/preservation-check.json): **85 historical/protected files unchanged**, and executed source/configuration hashes still match the supervision record. Source names, old experiments, receipts and legacy review/model artifacts were not edited.

## Defects resolved and acceptance decision

Before actual preparation, the implementation/security review found and fixed:

1. A fictional packet writer could initially accept a real packet after a mode-only edit. Explicit fictional namespaces and content validation now reject that path.
2. A packet loaded before a ledger operation could change before commit. Packet bytes, saved ledger bytes, lock inode and directory identity are now checked immediately before publication/return.
3. Standalone ledger calls initially accounted for only the C2 root. They now load the pinned configuration and preserve historical roots and normalized reservations.
4. Actor account IDs alone did not express reviewer independence. Principal and independence-group checks now prevent repeated accounts from satisfying the protocol.
5. Direction annotations initially allowed identity-support references in place of names. Name-only direction references are now enforced and regression-tested.

Case count and encoded-byte limits also stop expansion before unbounded queue construction. One editor owned the implementation/config contracts; independent workers owned the primary tests, legacy compatibility tests and read-only security review. A separate read-only worker clarified next gates without rerunning acquisition investigations.

C2 acceptance passes: deterministic versioned packets trace to C1; the empty real ledger stays blank; fictional append/replay validates actors, provenance and disagreements; invalid/stale/conflicting/corrupt/partial work fails safely; legacy APIs remain strict; one supervised real run stayed within limits; historical artifacts remain unchanged. No known reproducible in-scope failure remains from these checks. Passing tests are scoped evidence, not a claim that software has no possible defects.

Fictional example: two distinct authorized fictional principals disagree about a case. Replay marks `disagreement_pending_adjudication`. A third independent fictional principal may adjudicate with valid cited evidence; the original reviews remain. The result remains fixture-only, with release blocked and accepted labels zero. Against an actual development packet, the same append call is rejected regardless of the actor names supplied.

## Remaining limitations

These packets organize work, but no person has reviewed them. Reviewers, adjudicator, real submission access, competence and independence have not been established. The actual source evidence is minimal; a same-name pair is often insufficient to establish legal identity or distinction. Obtaining extra identity-support fields requires separately approved permissions and scope. No inference is used to fill missing evidence.

Script incidence across the retained name entries is Latin 38,579, Arabic 188, Cyrillic 1,822, Han 27 and unknown 389. These are **nonexclusive name-entry script counts**, not languages, reviewed groups or coverage claims. Mixed-script entries may contribute more than once. The earlier **27 Latin–Han source-local candidate groups** remain development-exposed and unreviewed; C2 creates no new multilingual supply or fresh final cases.

The original Step 08 requirements remain: approximately 5,000 usable reference families and 2,000 independent absent-query families; at least 200 positive and 200 negative distinct candidate reviews; adjudication of every used hard negative; duplicate/equivalence/dependence resolution; and at least 100 independently reviewed final positive groups per claimed direction. Review minima do not certify every other corpus record. No task/alias/source copy multiplication satisfies independence. Accepted corpus assembly/publication and Step 09 remain closed.

## Next executable packages and separate approval gates

**Recommended next decision: approve 08B-C3 — offline adjudication application, family-graph and absence-validation mechanics.** This is implementation, not another broad planning cycle.

Proposed files: new `src/watchlist/corpus_adjudication.py`, `tests/test_corpus_adjudication.py`, and `config/corpus-adjudication-v1.json`; update `docs/data-card.md`; create `docs/progress/completion-08b-c3.md` and a new private C3 evidence directory. Keep C1/C2 formats, old stores and dependency/schema files unchanged unless a concrete unavoidable change is separately identified.

C3 implementation work:

- Consume hash-bound validated **fictional** C2 adjudications and mechanically derive versioned dry-run eligibility. Keep equivalence, dependence/leakage families and uncertain nominations distinct; propagate quarantine and development exposure.
- Detect contradictory transitive paths, unresolved incoming links, stale/superseded decisions and wrong evidence/purpose bindings. No real identity merge or label acceptance is authorized by implementing the mechanics.
- Validate absent-query declarations against a fixed reference-view hash. Every equivalent copy and alias of an absent target must be excluded; unresolved possible equivalents block eligibility. Absence is relative to that view, not a declaration about all sanctions lists.
- Produce deterministic, failure-safe **dry-run** manifests and regression tests for all-copy membership, contradictions, uncertainty, source copies, held-out aliases, changed views, stale ledgers, tampering and interrupted writes. Actual Step 09 partitions remain absent.
- Proposed bounds for explicit approval: zero network/new dependencies/model calls, ≤16,000,000 new C3 artifact bytes, one serial supervised worker ≤60 minutes, unchanged 100,000,000 normalized-byte/2 GiB artifact ceilings and existing disk/memory guards. Run focused tests plus one necessary C2 compatibility integration. Stop rather than expand a bound.

C3 acceptance: deterministic reconstruction from externally pinned ledger heads; rejected unresolved/contradictory families; absent validation fails if any equivalent target remains; real decisions/merges/labels/releases remain zero; preserved historical data and focused evidence. This completes machinery, not the actual 2,000-family population.

**Separate human gate — S1 then H1.** The owner must name and verify two competent independent reviewers plus an independent adjudicator, approve population/type scope, protocol, allowed evidence/purposes, time/budget, retention and actual submission access. Actor JSON rows alone are insufficient. A separate implementation/execution authorization then enables genuine human ingestion and the 40-case development pilot (20 positive proposals, 20 negative candidates), with independent first-pass review and adjudication. Measure real time, evidence insufficiency and disagreement before expanding to ≥200+200 distinct cases. C2 does not authorize contacting people or fabricate their decisions. C3 may proceed while people are organized; applying real decisions remains gated.

**Separate data/custody gate — S1 then S2.** Select a permitted, bounded multilingual source package and establish genuinely separate custodian access **before protected acquisition**. Reuse existing official metadata evidence when valid. Wikidata Action API is a possible supplementary organization route, not an acquired corpus or replacement for sanctions-domain evaluation. Direct UN remains pending permission clarification. The acquisition proposal must specify exact endpoints/parameters, seeds, fields/types, current rights, transactions/bytes/time, expected yield and storage/custody. No prior network allowance is renewed here. Fresh final families must be screened privately against all development exposure. Han shortages cannot be filled with invented translations or repeated aliases.

After these gates, H2 supplies the real reviewed decisions; C4 applies them to actual reference/absent cohorts and verifies counts/coverage; C5 requires explicit approval for the immutable accepted release and Step 08 closure. None of these requirements is moved into training.

## Beginner-friendly 5W1H

- **What:** built blank review work packets and a secure local record of future review events.
- **Why:** people need complete source evidence, and their decisions must remain traceable without being confused with automatic guesses.
- **When:** now, after verified acquisition/preparation and before real review, accepted corpus assembly or training.
- **Where:** private local C2 artifacts referring to unchanged C1 evidence.
- **Who:** Codex implements/tests the mechanics; verified humans must make actual judgments, and the owner approves the next gates.
- **How:** deterministic references and versions, independent reviewer checks, private atomic writes, a hash-linked event history, external head verification, resource limits and fictional failure tests.

**Stop here. The immediate decision is whether to approve the bounded C3 implementation above. Human execution and new acquisition remain separate approvals.**
