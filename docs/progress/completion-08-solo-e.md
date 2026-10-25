# SOLO-E — activated development pilot, awaiting the owner's first response

2026-10-25. The owner explicitly approved genuine single-reviewer development execution, confirmed local-account ownership and reviewer attribution, supplied actual competencies, and approved the pilot bounds and private retention. Declaration details and live case/session identifiers are omitted from this public copy; the original report is preserved locally. This report supersedes the pending declarations in the [preflight](completion-08-solo-e-preflight.md), without modifying the original.

**Decision: preparation and corrected activation PASSED. Actual 40-case review is not complete. No owner response, accepted label, identity merge, corpus release, training, Step 09 or publication has occurred.** The first-case session has its own receipt; its machine-generated session event is not a human review. The first downloaded owner JSON and its private ledger entry still require validation before proceeding to the other cases.

## Files and functions

| File | Purpose |
| --- | --- |
| [corpus_solo_execution.py](../../src/watchlist/corpus_solo_execution.py) | Separate execution path; original SOLO-I and multi-reviewer modules remain unchanged. `_qualified` (47) enforces declared competence, distinguishes Urdu from Arabic, and compares language-tag case without changing original tags. `_policy` (87) binds approval, identity, retention, fixed budgets, source and code pins; `_context` (215) admits the original evidence through existing validators and resource guards. `_header` / `activate` (265/282) publish a new private empty ledger with its header last. |
| Same module, event/CLI functions | `_validate_response` (332) checks actual provenance, actor, citations, evidence versions, uncertainty and supported scope; `_state`, `_apply_event` and `_replay` (445/467/557) enforce time reservations, first-case gating, corrections and the hash chain. `_summary` (615) separates inspections from accepted labels. `operate` (650) serializes replay/append using the existing lock and atomic writer. `stage_download` (756) copies one selected download privately without changing the original or ingesting it. `main` (823) exposes offline pinned CLI operations and denies network. |
| [test_corpus_solo_execution.py](../../tests/test_corpus_solo_execution.py) | 52 isolated fictional tests, including the genuine-mode code route on explicitly authored fictional records. No test uses real owner responses. |
| Private `config/corpus-solo-execution-v2.json` (not published) | Current, private, pinned execution policy. References the unchanged 40-case packet, SOLO-I closure, code, declaration, retention and the separate `ledger-v2`. The initial v1 policy is preserved as history. |
| [Private SOLO-E artifacts](../../data/eval-comparisons/completion-08-solo-e/) | Owner declaration, approved retention extension, private incoming drafts directory, logs, supervision/activation receipts, initial empty ledger, corrected empty ledger, and practical handoff. No source snapshot is duplicated or reacquired. |

The genuine response validator is a separately versioned adaptation of the frozen SOLO-I response contract. It keeps the real `human` / `publisher_assertion` / `single_human` origins; it does not retag real material as fictional or monkeypatch the original gate. Shared evidence, lock, private-path, canonical serialization, atomic-publication and correction primitives are reused. No library or dependency version changed.

## Tests, commands and corrections

Commands actually run included:

```sh
.tools/qa/bin/python -I -B -m ruff check --isolated --target-version py314 src/watchlist/corpus_solo_execution.py tests/test_corpus_solo_execution.py
.tools/qa/bin/python -I -B -m ruff format --isolated --target-version py314 src/watchlist/corpus_solo_execution.py tests/test_corpus_solo_execution.py
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_checks.py focused-01
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_checks.py focused-02
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_checks.py focused-03
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_checks.py integration
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_checks.py focused-04
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_activation.py
.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/run_activation_v2.py
```

The check wrapper runs `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_solo_execution.py -p no:cacheprovider --maxfail=3` under the existing real process supervisor. Integration also includes `tests/test_corpus_solo_review.py`. Fixtures are isolated and deny network; real resource supervision remains enabled around the test process.

- Initial focused run: **38 passed, 3 failed** before stopping. It exposed incorrect capitalization of script tokens; these now match the project's `LATIN`/`ARABIC` tokens. The duplicate-response check now reports that error before cumulative-time checks. A stale test draft was refreshed so its intended first-case gate could be exercised without an earlier valid backdating rejection.
- Subsequent focused checks after the fixes/additions: **43 passed**, then **47 passed**.
- One cross-component integration: **135 passed in 11.72 seconds** (49 new execution cases and 86 unchanged SOLO-I cases), with peak sampled supervised RSS **159,629,312 bytes** and no resource stop.
- The actual packet then revealed uppercase `EN`/`RU` tags. Before reviewer use, competence comparison was corrected to be case-insensitive while preserving source tags. A separately named policy/ledger was added so the initial empty activation could remain untouched. **Final focused validation: 52 passed in 4.22 seconds**; peak sampled supervised RSS **119,144,448 bytes**, no resource stop. This focused retest covers the correction; the preceding integration log is not represented as a run of the final code.
- Final scoped Ruff check passed. Original code/dependencies and browser JavaScript are unchanged, so the full suite, previous secret scan and browser smoke were not repeated.

Tests cover missing/invalid declarations, enlarged limits, unsafe paths, incorrect actors and origins, stale packets/citations, missing identity evidence, unsupported language claims, duplicate responses, append-only corrections, time/session limits, first-case checkpoint, corrupt/truncated ledgers, interrupted activation/append, changed inputs during resource callbacks, private idempotent download staging and deterministic replay. Fictional real-mode tests are confined to temporary authored datasets and are not human validation.

## Actual activation and preservation evidence

[Corrected activation](../../data/eval-comparisons/completion-08-solo-e/activation-v2.json) and [supervision](../../data/eval-comparisons/completion-08-solo-e/activation-v2-supervision.json) passed. Worker elapsed time was **2.3324 seconds**; supervisor sampled peak aggregate RSS **146,259,968 bytes**. Free memory was **62%**, memory pressure false, final free disk **35,554,881,536 bytes**, combined measured artifacts **77,252,069 bytes**, and normalized reservation **54,154,849 / 100,000,000 bytes**. Measurement is sampled, not a continuous OS allocation guarantee.

- Current policy SHA-256: `82c039739216def08eb5e3276be5273df4855a14ced8079ea0ffbadaab4ecba7`.
- Unchanged packet manifest SHA-256: `0922533880513eefc98ce0ead4adc2abc3618d388ded2bdbdfd0cd124238862d`.
- Corrected empty-ledger genesis head: `47855e530c5f0fc5aa15bef6902387e400215d158b15be5540290d7a85df3d39`. A later session/import advances the head; use its receipt, not this historical genesis, for the next write.
- **All 63 original SOLO-I completion file pins unchanged** after activation. Original multi-reviewer code/configuration and genuine-intake rejection remain intact. The accepted 40-case composition, nine substitutions and original evidence are unchanged.
- Initial activation, policy and empty ledger remain in place; `execution-module-initial.py` preserves its executed module. Their successful receipts describe the earlier empty state. Only policy v2 / `ledger-v2` is current; no real submission occurred under v1. Its old code pin fails closed against the corrected module.
- Zero network transactions and zero automatic retries. No actual human judgment has been fabricated.

The local owner attestation and UID check establish attribution under the owner's account, not independent identity verification. Inspected private directories are 0700; the checked `ls -lde` output listed no ACL grants. New policies, declaration and ledger use private file permissions. Encryption, external backup privacy and independent custody are not claimed.

## Review schedule, first case and next handoff

Approved bounds are 40 existing cases, at most 4 hours, sessions at most 30 minutes and first case at most 20 minutes. The ledger **conservatively reserves an entire session window**, including unused/idle time; it never refunds failed/expired windows. This can stop earlier than four hours of reported active work and cannot enlarge the allowance. Start each session only when ready. The first-session receipt records its exact start/expiry; no deadline should be inferred from report creation time. Imports can be checked later if the draft's recorded review time was within its session; never backdate a draft.

The first case is preserved in its original position. Competence requirements are checked against the private declaration; unsupported language or identity judgments remain unresolved. Codex must not supply a judgment or rationale on the owner's behalf. Case identifiers, evidence and reviewer-specific restrictions remain in the private handoff.

Use [START-HERE.md](../../data/eval-comparisons/completion-08-solo-e/START-HERE.md) and the existing [field guide](completion-08-solo-e-preflight.md#first-case-field-guide--use-only-after-activation-succeeds). The unchanged form still describes SOLO-I's disabled ingestion. That statement remains true for the original module: the new, separately authorized SOLO-E policy accepts its downloaded drafts through the new private intake only. No form JavaScript or source evidence was regenerated.

The owner personally inspects Case 1, fills only their own supported observations and downloads one JSON draft. Codex then stages that exact selected download privately, checks the current packet/actor/evidence/time/session, imports a valid response into `ledger-v2`, replays its new head, and records the first-case verification checkpoint. That checkpoint means **schema/evidence/ledger verification, not validation of label truth**. Only then may a new session include the remaining cases. Failed validation retains the original draft and reports the reason. Corrections use a new submission ID and refer to the current accepted response for that case.

The command `.venv/bin/python -B data/eval-comparisons/completion-08-solo-e/start_first_case.py` subsequently passed guarded append and replay. The private first-session receipt records exact times, identifiers and the trusted head; these are omitted from this public copy. There is one machine session event and **zero human submissions** at this report's snapshot. The 1,200-second reservation leaves **13,200 seconds (3 hours 40 minutes)** unreserved. Free memory was 61%, pressure false; sampled supervisor peak RSS was 147,226,624 bytes, with no stop or retry. The local report/guide links and session-script syntax were checked; no additional test suite ran.

Example from isolated tests only: an `insufficient_evidence` response produces one inspected case and zero accepted labels; a subsequent correction produces two stored submissions but still one inspected case. No example response was inserted into the actual ledger.

## Remaining limitations and 5W1H

First actual JSON validation and the 40-case review are pending genuine owner action. Competence and minimal source evidence may leave many cases unresolved. Inter-reviewer agreement is not measured; no independent validation, identity confirmation or sanctions-screening assurance is claimed. The pilot does not satisfy the later 200+200 inspections, 5,000 reference families, 2,000 absent families, fresh sanctions evidence or multilingual final-family gates. No later acquisition, release, training, Step 09 or publication is authorized by this handoff.

**What:** activate only attributable single-owner development feedback. **Why:** collect real observations without inventing reviewers or labels. **Who:** the owner judges; Codex checks mechanical validity. **When:** within approved sessions, with Case 1 checked first. **Where:** the existing local form and new private v2 ledger. **How:** pinned policy/evidence, explicit competence, resource/time limits, immutable events and retained corrections.
