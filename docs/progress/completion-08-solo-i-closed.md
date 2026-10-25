# SOLO-I closure — 2026-10-25

**Decision: SOLO-I COMPLETE. Full Step 08 remains incomplete. SOLO-E is not activated or authorized by this closure.**

This dated addendum closes the browser/fictional-download prerequisite in the [original SOLO-I report](completion-08-solo-i.md). That report and its [original completion receipt](../../data/eval-comparisons/completion-08-solo-i/completion.json) remain unchanged historical evidence. Their blocked status describes the earlier state, not the outcome recorded here.

## Acceptance evidence

| Requirement | Result and evidence |
| --- | --- |
| Separate solo implementation, explicit protocol amendments, preserved original track | Passed in the original report. No implementation/configuration changes during this follow-up. |
| Deterministic blank handoff and frozen H1-I selection | Passed: 40 cases, 60 observations, 570 name entries; no reselection. The 20 positive proposals / 20 negative hypotheses and nine substitutions remain unchanged. Substitutions receive no multilingual-coverage credit. |
| Regression and cross-component integration | Existing **397 tests passed in 23.36 seconds**, including 86 solo tests; scoped Ruff lint/format passed. [Test log](../../data/eval-comparisons/completion-08-solo-i/integration-tests.log). No repeated tests were needed. |
| Actual browser interaction | Owner reported Google Chrome passes for opening, Latin/Arabic/Cyrillic/Han rendering, JSON download, case switching/reset, both incomplete correction-pair rejections, missing-citation rejection and keyboard Tab navigation. This is owner-reported evidence, not agent-observed browser automation. |
| Downloaded fictional JSON validates against its pinned packet | **Passed** in the [third attempt receipt](../../data/eval-comparisons/completion-08-solo-i/browser-followup-03/validation.json), started 2026-10-25 at 13:52:34 UTC. The existing download and its preserved copy match. |
| Resource, disk and integrity safeguards | Passed during that single authorized attempt: memory pressure false, free memory 62%, peak sampled process RSS 42,631,168 bytes, final free disk 35,553,660,928 bytes, combined measured artifacts 77,191,476 bytes. Five normal guard checkpoints are not five retries. |
| Preserved evidence and disabled real execution | All 63 original completion file pins were verified unchanged before closure. Original preservation evidence covers 157 protected files, 15 executed pins and three document prefixes. Zero fictional or real ledger events were written; both genuine intake tracks remain disabled. |

The input was `fictional-solo-cc62fab8-ad29-4b62-abf6-e6ee6f7dae94.json` in the owner's Downloads directory: **1,188 bytes**, SHA-256 `c871339239f77ac2bb4fc3953b7283f28dae7352d00c571ab8c587713198625a`. It binds fictional packet SHA-256 `32948012d7ead9ea199356f50a784abd1229a0e5f8c61c00e07580f9bcca6109`.

Example validated result: actor `fictional-solo-owner`, outcome `insufficient_evidence`, one citation, initial response rather than correction; origins remain `fictional_human`, `synthetic_derivation` and `single_human`. This is a fictional validation example, not a real judgment or accepted label.

## What ran and what changed

The authorized attempt reused the existing Python validation functions, with `ResourceGuard` and real `system_snapshot` measurements across the configured roots. It validated the packet/context and declaration, replayed the empty ledger under its lock, checked the event, timestamp, in-memory application and encoded event size, then rechecked resources, input identity and ledger integrity. It did **not** call submission append or publish an event. The receipt records `validation_mode: read_only_no_append` and `automatic_retries: 0`.

Two preceding authorized attempts stopped at admission with `host_memory_pressure`; their receipts remain intact in `browser-followup-01` and `browser-followup-02`. No safeguard was bypassed. After the latest successful attempt, only evidence/documentation reads and closure-file creation were performed; validation, preparation and tests were not rerun.

New files in this closure:

- This report: records the acceptance decision, evidence limits and next authorization boundary. No application functions changed.
- [closure.json](../../data/eval-comparisons/completion-08-solo-i/closure.json): binds this report, the original completion record, the latest validation receipt, the owner-reported browser evidence and prior test log by SHA-256. Records SOLO-I complete, Step 08 incomplete and execution disabled, with artifact-size accounting against the existing 16,000,000-byte ceiling.

Closure commands used `cat`, `rg`, `sed` and `tail` to inspect the existing records; `apply_patch` created this report, and `.venv/bin/python -B` with standard-library JSON/hash/path utilities created the exclusive new receipt and checked local report links. A read-only `git status --short` returned “not a git repository”; no Git operation or publication was performed, and Git status is not an acceptance prerequisite for this local package.

## Remaining limitations and next action

**Browser external-network observation remains NOT VERIFIED.** The [smoke guide](../../data/eval-comparisons/completion-08-solo-i/BROWSER-SMOKE.md) explicitly makes the developer-tools observation optional. Content-security policy is not a measured network trace. The browser version was not supplied. Valid correction-pair download was not separately reported as a manual browser result; correction mechanics retain the existing fictional regression evidence. These evidence limits do not erase the confirmed required interaction checks or justify independent-validation claims.

No real decisions, accepted labels, identity merges, corpus release, acquisition, training, Step 09 or publication occurred. The real packet and blank ledger remain pinned. The existing [SOLO-E handoff](../../data/eval-comparisons/completion-08-solo-i/SOLO-E-START.md) remains the practical guide; its historical statement that the smoke test is open is superseded only by this addendum. All its separate activation gates still apply.

**Next decision:** separately approve bounded SOLO-E activation and genuine owner review/import/corrections for the existing 40 development cases in a new execution ledger. Supply a stable actor ID, local-account ownership attestation, actual language/domain competencies, retention choice and review-time allowance. No additional reviewer or adjudicator appointment is required for the approved solo track. Activation must bind a versioned policy and resource limits before any actual answer is accepted; changing a flag alone is insufficient.

Step 08 still requires the actual 200 positive and 200 negative candidate inspections, approximately 5,000 usable reference families and 2,000 independent absent-query families, permitted fresh sanctions evidence, group-disjoint evaluation and at least 100 eligible independent final families per claimed direction. Forty pilot cases do not satisfy those gates, and unsupported evidence remains unresolved.

## Beginner-friendly 5W1H

- **What:** closed the implementation and blank-review preparation package.
- **Why:** the final required fictional download now validates successfully.
- **When:** after the owner's Chrome checks and one additional guarded attempt.
- **Where:** existing private local evidence, with a new report and receipt.
- **Who:** the owner tested the browser; the existing validator checked the fictional response. Neither supplied genuine review labels.
- **How:** preserve versioned evidence, reuse passing tests, enforce resource checks and keep genuine intake disabled until separately approved.
