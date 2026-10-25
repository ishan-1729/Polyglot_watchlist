# Step 08 SOLO-I — separate solo intake and frozen pilot handoff

2026-10-25. Authorized by the owner's explicit approval of the [solo protocol](step-08-solo-protocol-proposal.md) and its exact bounded SOLO-I package. This report concerns implementation and blank preparation; it does not authorize human review ingestion or close Step 08.

**Decision: implementation, offline integration and blank preparation PASSED; SOLO-I acceptance remains BLOCKED on the required real-browser smoke test. Full Step 08 remains incomplete.** The browser security policy rejected opening the local fictional file and prohibited alternate-route workarounds. No browser rendering or browser download success is claimed. All remaining authorized software/preparation work is complete; genuine ingestion remains disabled.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| [corpus_solo_review.py](../../src/watchlist/corpus_solo_review.py) | Separate solo packet, provenance, one-owner declaration, blank form and integrity-checked ledger. Reuses frozen H1-I evidence without rerunning the selection algorithm. Genuine intake remains hard-disabled. |
| [test_corpus_solo_review.py](../../tests/test_corpus_solo_review.py) | Isolated fictional tests for evidence/identity boundaries, corrections, unsupported negatives, corruption, interruptions and old-contract preservation. |
| [corpus-solo-review-v1.json](../../config/corpus-solo-review-v1.json) | Exact H1-I configuration/manifest pins, inherited artifact roots plus the new root, fixed limits, blank owner declaration and false execution permissions. |
| [Completion plan](../project-completion-plan.md), [review/custody protocol](../planning/step-08b-review-and-custody.md), [data card](../data-card.md) | Dated append-only solo-track amendments. Historical wording remains; the separate solo evidence standard and reduced claims are explicit. |
| [Private SOLO-I evidence](../../data/eval-comparisons/completion-08-solo-i/) | Frozen-input pins, supervised preparation scripts, test/browser evidence, new blank packet and ledger, and practical owner handoff. |

The old C1/C2/C3/H1-I modules, configurations, ledgers, source receipts, dependency versions, models, historical reports and AGENTS.md remain outside the edit scope. No new library, source request or publication is authorized. Review origin does not overwrite evidence origin; neither origin grants accepted corpus eligibility.

Function guide for the new module: `_load_config` (115) binds the approved scope, H1 pins, inherited roots and false permissions; `_source_context` (204) admits/rechecks the frozen H1 bytes without running its selector; `_packet` (251) preserves case order and original evidence while adding evidence-version commitments and distinct provenance fields. `_html_export` (366) creates readable inert-text name tables, optional original evidence and blank response/correction controls. `_write_packet` (481), `prepare_solo_review` (552) and `validate_solo_review` (703) publish only a new complete packet and reproduce it from the frozen source. `_declaration` (726) binds a single fictional owner for tests and permits only a blank real declaration. `create_ledger` (786), `_event` (895), `_apply` (1010), replay (1044/1145) and `append_submission` (1178) validate evidence/competence, chronology, corrections, hashes and stale-head rejection. `_write_cli_json` (1243) confines draft exports to their monitored sibling directory and rechecks inputs after resource callbacks; `main` (1270) exposes the six offline commands. No API authorizes independent-review claims or accepted corpus export.

The HTML records evidence origin separately from review origin. Real blank cases retain `publisher_assertion` / `none`; a future authorized owner's actual response is single-human feedback, not independent ground truth. Fictional fixtures retain `synthetic_derivation` and `fictional_human` origin markers even while testing the single-human review contract. All scope/permission/evidence checks remain enforced.

## Validation and execution evidence

Commands actually run (from the project root):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_solo_review.py tests/test_corpus_human_review.py tests/test_readiness_review.py tests/test_corpus_adjudication.py -p no:cacheprovider
.tools/qa/bin/python -I -B -m ruff check --isolated --target-version py314 src/watchlist/corpus_solo_review.py tests/test_corpus_solo_review.py data/eval-comparisons/completion-08-solo-i/run_handoff.py data/eval-comparisons/completion-08-solo-i/execute_supervised.py
.tools/qa/bin/python -I -B -m ruff format --check --isolated --target-version py314 src/watchlist/corpus_solo_review.py tests/test_corpus_solo_review.py data/eval-comparisons/completion-08-solo-i/run_handoff.py data/eval-comparisons/completion-08-solo-i/execute_supervised.py
.venv/bin/python -B data/eval-comparisons/completion-08-solo-i/execute_supervised.py
```

The one final [integration run](../../data/eval-comparisons/completion-08-solo-i/integration-tests.log) passed **397 tests in 23.36 seconds**: 86 new SOLO tests, 94 H1, 105 C2 and 112 C3. Scoped [Ruff lint](../../data/eval-comparisons/completion-08-solo-i/ruff-check.log) and [format](../../data/eval-comparisons/completion-08-solo-i/ruff-format.log) passed. Focused development runs preceded that final integration and are not additional unique tests. The full 2,606-test suite, prior secret scan and unchanged infrastructure checks were not repeated.

Tests cover evidence-origin/review-origin misclassification, unauthorized independent claims, insufficient documentary support for negatives, missing competence, one-owner attribution, wrong/stale case/evidence hashes, duplicate events, corrections, contradictory context, corrupt/truncated history, concurrent writes, unsafe paths, private ownership, resource stops, interrupted publication and final resource-callback input changes. Old genuine multi-reviewer intake remains rejected. Test assumptions about derived neutral case IDs, nested result counts and CLI stderr were corrected to the actual contracts; protections were not removed.

Two implementation defects were fixed before the final integration: JSON object insertion order could make HTML reconstruction nondeterministic after persistence (canonical serialization now preserves identical output), and CLI draft export initially allowed a private destination outside the monitored sibling directory (it now confines paths, reserves bytes and rechecks pinned inputs before publication). One specialist reviewed those integrity boundaries; there was no repeated broad independent review cycle.

Fictional example: an initial owner response can record `insufficient_evidence`; a correction with a new submission ID cites the current same-case response and gives a reason. Replay retains both events, counts one inspected case and reports zero accepted labels. A source record with two name forms can support a publisher-record hypothesis; two different record IDs alone cannot support a negative. No actual response was synthesized.

### Frozen-pilot preparation

[Supervision](../../data/eval-comparisons/completion-08-solo-i/supervision.json) reports exit 0, no resource stop, **4.9137 seconds** and peak sampled aggregate RSS **134,004,736 bytes**. The [worker receipt](../../data/eval-comparisons/completion-08-solo-i/worker-outcome.json) records successful prepare/validate and empty-ledger replay. Host free memory stayed **51%**, no pressure warning; disk was **35,591,774,208 → 35,591,053,312 bytes**. Normalized reservation was **54,313,472 / 100,000,000 bytes** and combined artifact reservation **77,467,954 / 2,147,483,648 bytes**. The new real packet and ledger total **645,120 bytes**. Sampled supervision does not imply continuous measurement between samples.

[Selection preservation](../../data/eval-comparisons/completion-08-solo-i/selection-preservation.json) verifies the exact original order/case hashes, **40 cases, 60 observations and 570 original name-evidence entries**. Selection was not regenerated. The inherited 20-positive/20-negative composition and nine substitutions remain unchanged. All 40 cases are blank/unreviewed, with zero actual submissions, corrections, labels, identity merges, partitions or releases; inter-reviewer agreement is `not_measured`. Source acquisition/network transactions were zero.

- New packet manifest SHA-256: `0922533880513eefc98ce0ead4adc2abc3618d388ded2bdbdfd0cd124238862d`.
- Empty solo ledger header/genesis head: `60e3f5b7508cfd2dcdf21e6fcb12ace0ff7492c5d548ac6cea75ebbd2d2464ad`.
- Unchanged source H1-I manifest: `2f235e847e1e6b49db280f44ebe95d5f0a7783dc680babf786e741fd48cea16d`.

The [preservation check](../../data/eval-comparisons/completion-08-solo-i/preservation-check.json) records 157 unchanged protected files, 15 unchanged executed source/configuration/script pins and preservation of all original bytes in the three append-only documents. [The completion record](../../data/eval-comparisons/completion-08-solo-i/completion.json) binds final artifacts/logs/documentation and records total new artifact bytes against the 16,000,000-byte ceiling. Its status preserves the browser blocker rather than claiming full acceptance.

### Browser acceptance remains open

An isolated five-case fictional multilingual packet was generated using `make_browser_fixture` from the new test module. Its form JavaScript matches the final module. The attempted in-app-browser navigation to the local `file://` HTML was rejected by the tool's automatic URL security policy (only HTTP/HTTPS allowed), which explicitly prohibited workaround/alternate-surface execution. No local server, alternative browser route or network workaround was attempted.

The [browser receipt](../../data/eval-comparisons/completion-08-solo-i/browser-check.json) records **blocked**, not passed. HTML structure/escaping and Python intake tests passed, but these do not substitute for actual browser rendering, keyboard behavior or downloaded JSON. The owner can perform the [fictional-only smoke checklist](../../data/eval-comparisons/completion-08-solo-i/BROWSER-SMOKE.md) locally and report results; generated fictional JSON can then be checked against the validator. Do not begin the actual 40-case review while that prerequisite remains unresolved.

| Acceptance item | Result |
| --- | --- |
| Explicit dated solo amendments, original track preserved | Passed; append-only documentation, original code/configuration hashes unchanged. |
| Frozen selection and original evidence preserved | Passed; same 40 case IDs/order and source evidence. |
| Separate deterministic blank packet, ledger and provenance | Passed; new manifest/head, no actual decisions. |
| Fictional intake, corrections, integrity and compatibility | Passed; 397 tests, scoped lint/format. |
| Resource limits and preserved artifacts | Passed; single supervised blank preparation within limits. |
| Real-browser fictional smoke check | **Blocked by browser URL security policy; required before reviewer use.** |
| Actual review ingestion, accepted corpus, training/Step 09 | Not authorized; both original and solo genuine intake remain disabled. |

## Remaining scope and the next decision

Actual human reviews, accepted labels, identity merges, accepted corpus release, training and Step 09 remain unauthorized. The new solo handoff does not manufacture answers. The original independent-review track remains available and its actual intake remains disabled.

After SOLO-I, **SOLO-E** must separately authorize bounded genuine solo activation and the owner's actual 40-case review/import/corrections. It must bind an owner declaration, competencies, retention and a new execution policy/ledger without overwriting this blank preparation. No second actor or adjudicator is required for the approved solo track. No actor attestation, source alias assertion, repeated self-review or AI output may claim independent human validation. An outcome unsupported by evidence remains unresolved.

The [practical SOLO-E handoff](../../data/eval-comparisons/completion-08-solo-i/SOLO-E-START.md) gives exact opening, per-case review, private draft return/import and correction instructions. Its CLI example is explicitly gated; current real submission attempts fail closed. The immediate action is the fictional browser check, then a separate SOLO-E approval with the owner's actor ID, competencies, retention and time allowance. No broad replanning or new reviewer appointments are needed for this solo track.

The pilot can inform later expansion to at least 200 positive-candidate and 200 negative-candidate inspections, but the nine accepted workflow substitutions do not satisfy multilingual strata. Approximately 5,000 usable reference families, 2,000 independent absent families, fresh permitted sanctions-domain evidence and at least 100 eligible independent final families per claimed direction remain actual completion gates. Current retained data remains development-exposed. Actual solo-compatible family/absence application and any new acquisition remain separately approved packages.

## Beginner-friendly 5W1H

- **What:** a separate blank review form and auditable intake for one researcher.
- **Why:** progress honestly without inventing independent people or stronger ground truth.
- **When:** after the approved solo protocol, before actual owner review or corpus acceptance.
- **Where:** private local development artifacts; old evidence remains preserved.
- **Who:** Codex implements/tests mechanics; the owner later supplies real judgments under separate approval.
- **How:** reuse the committed pilot, preserve evidence versions, keep provenance classes separate, reject unsupported claims and retain append-only corrections.
