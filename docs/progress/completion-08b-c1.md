# Step 08B-C1 — continuation admission and readiness queues

**Decision: C1 COMPLETE. Full Step 08 remains incomplete.** Completed locally on 2026-10-25 under the approved [C1 scope](completion-08b-03-plan.md), [completion plan](../project-completion-plan.md) and [collaboration rules](../../AGENTS.md). The result is a private, unreviewed preparation, not an accepted corpus, identity decision or training prerequisite. No network requests, human submissions, model execution, publication or Step 09 work occurred.

## Actual result

The single supervised worker prepared new artifacts and independently regenerated/validated them from pinned source evidence. Every approved C1 denominator and all ten comparable planning diagnostics matched.

| Measure | Actual result |
| --- | ---: |
| Retained source-local observations | 13,658 |
| Organizations / vessels | 12,090 / 1,568 |
| Complete name-evidence entries | 40,568 |
| Unique equality candidate pairs | 1,259 |
| Exact / normalized-only pairs | 663 / 596 |
| Cross-source / within-source pairs | 1,078 / 181 |
| Unresolved review components / involved observations | 657 / 1,607 |
| Explicitly weak names / affected observations | 2,153 / 1,476 |
| Normalizer-rejected long names / affected observations | 17 / 4 |
| Union of flagged observations | 2,864: 2,790 organizations, 74 vessels |
| Duplicate-and-weak overlap | 223 observations |
| Duplicate-and-overlength / weak-and-overlength overlap | 0 / 0 |
| Missing-language entries, preserved as unknown | 27,858 |
| No listed flag | 10,794; **not accepted or cleared** |
| Two distinct normalized nonweak names passing the current normalizer, with no listed flag | 4,880: 4,751 organizations, 129 vessels; **not independent accepted entities** |
| Human decisions / accepted labels / identity merges | 0 / 0 / 0 |

Source counts remain OpenSanctions UN **269 observations / 918 names**, OFAC **11,610 / 25,323**, and EU **1,779 / 14,327**. No aliases were truncated or silently discarded. Weak and long names carry evidence-specific restrictions; valid sibling names remain. Long rejected names additionally carry `matcher_input` exclusion. Duplicate components remain unresolved group-level flags, not identity or leakage families.

Component-size histogram: 431 of size 2; 202 of size 3; 11 of size 4; four each of sizes 5 and 6; two of size 7; one each of sizes 11, 12 and 14. Original referent strings are preserved, but additional referent nominations were not generated: the new evidence exposes raw strings, whereas the existing link contract requires qualified `(source_id, provider_id)` endpoints and a candidate-release hash. Neither namespaces nor a release hash were invented. There is one retained snapshot per source, so there is no cross-snapshot continuity population in this package.

## Implemented files and functions

| File | Change and responsibility |
| --- | --- |
| [corpus.py](../../src/watchlist/corpus.py) | `ContinuationSource` and `ContinuationPreparation` (lines 212/229) distinguish verified readiness inputs from publishable `PreparedSource`. `_continuation_binding` and `_continuation_lineage` validate the interrupted original, failed recovery, reused OpenSanctions selection, grants, claims and unresolved reservation. `_candidate_observations` preserves source-qualified record/name identifiers. `_continuation_manifest` binds retained bytes and false eligibility. `prepare_continuation_sources` (line 3770) verifies all three sources and 50 saved evidence files; original direct/recovery APIs remain strict. |
| [link_records.py](../../src/watchlist/ingest/link_records.py) | `ReadinessLinkWitness`/`ReadinessLinkNomination` (137/163) bind complete evidence witnesses to a preparation hash. `readiness_name_key` (449) versions NFKC → casefold → NFKC → whitespace comparison. `nominate_readiness_links` (463) creates one sorted unordered pair, preserving every exact/normalized witness and original-text hash. `validate_readiness_links` (589) recomputes instead of trusting edited nominations. Limits bound records, names, characters, pairs and witnesses before expansion. |
| [corpus_readiness.py](../../src/watchlist/corpus_readiness.py) | `_load_config` (148) enforces exact pins, types, permissions and limits; `_resource_guard` (232) accounts for historical retained selections and existing new artifacts. `assemble_readiness` (277) derives deterministic observations, nominations, components, evidence restrictions and diagnostics. `_recheck_inputs` (573) detects source changes before completion. `_write_payload` (624) writes private staged files, verifies bytes, fsyncs and exclusively links without overwrite. `prepare_readiness` (680) writes the manifest last. `validate_readiness` (740) independently re-admits inputs and regenerates all content. `deny_network`/`main` (780/786) deny socket operations and keep CLI failures aggregate. |
| [corpus-readiness-v1.json](../../config/corpus-readiness-v1.json) | Pins the actual continuation receipt, five retained selections, four monitored roots, organization/vessel strata, expected counts, normalization/nomination versions and Unicode 16.0.0. Every use/publication permission remains false. |
| [test_corpus.py](../../tests/test_corpus.py), [test_record_links.py](../../tests/test_record_links.py), [test_corpus_readiness.py](../../tests/test_corpus_readiness.py) | Fictional regression and adversarial coverage for provenance, history/accounting, namespaces, witnesses, determinism, corrupted artifacts, unsafe paths, interrupted writes, resource stops and network denial. No real labels. |
| [data-card.md](../data-card.md) | Adds the current preparation status and measured limitations without rewriting its historical Step 06 account. |
| [C1 evidence directory](../../data/eval-comparisons/completion-08b-c1/) | New private evidence, test logs, supervised execution scripts/results, preservation verification and preparation artifacts. No prior destination overwritten. |

No dependency, SQL schema, acquisition client, resource-guard implementation, original review store or model artifact was changed. `label_review.py` remains fictional-only. No commit or push was made; this workspace checkout has no `.git` directory.

## Private artifact contract

[Preparation manifest](../../data/eval-comparisons/completion-08b-c1/preparation/manifest.json):
`bb84c60fd09a4ff11fb93ddb5cb37d630c18b684cbc8d0d216ec3cabc047b195`

[Input manifest](../../data/eval-comparisons/completion-08b-c1/preparation/input-manifest.json):
`70f334f28d6bcc276cff41c5f84bea1cb42b563748e91de2573da8b5a84e579c`

The externally pinned continuation receipt remains `dff2ef1c3f0584f19e32630e37008b1bd007fb3fc01187267f700249d2172c85`.

Seven preparation files total **23,640,265 bytes**: `input-manifest.json`, `observations.jsonl`, `nominations.jsonl`, `components.jsonl`, `quarantine.jsonl`, `summary.json`, and the completion `manifest.json`. The directory is mode 0700 and final files mode 0400. Repeated preparation refuses an existing destination, including a partial one. An interrupted precommit write may leave private partial evidence but no valid completion manifest; no automatic cleanup or retry erases that evidence. The validator rejects missing/extra files, changed originals, modified flags, bogus links and self-consistently rewritten output hashes by rebuilding from trusted inputs.

These controls provide local integrity checks, not protection against an administrator replacing code and every trusted pin. No independent final-test custody is claimed.

## Commands and checks actually completed

Focused worker commands used `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q <file> -p no:cacheprovider`: final results were **286 corpus**, **45 record-link**, and **42 readiness** tests passed. The initial readiness-fixture failures came from a mocked manifest missing newly required source references; the fixture was completed. The actual fictional continuation integration already passed. These focused results overlap the combined run below; they are not additive new test counts.

One final affected-contract integration/security run:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q \
  tests/test_corpus.py tests/test_record_links.py tests/test_corpus_readiness.py \
  tests/test_label_review.py tests/test_resource_guard.py tests/test_full_acquisition.py \
  -p no:cacheprovider
```

**582 passed in 6.88 seconds.** [Raw log](../../data/eval-comparisons/completion-08b-c1/integration-tests.log). This covers touched contracts and their acquisition/resource/review boundaries, not the unchanged whole project suite. No training/inference tests or network were required.

Scoped Ruff `check --isolated --target-version py314` and `format --check --isolated --target-version py314` ran through `.tools/qa/bin/python -I -B -m ruff` on the three implementation files and three test files. Both passed ([lint](../../data/eval-comparisons/completion-08b-c1/ruff-check.log), [format](../../data/eval-comparisons/completion-08b-c1/ruff-format.log)); the two execution scripts were also formatted and linted. `.venv/bin/ruff` was absent; the existing isolated QA environment supplied Ruff, with no download.

Real execution command:

```sh
.venv/bin/python -B data/eval-comparisons/completion-08b-c1/execute_supervised.py
```

The wrapper invoked `run_readiness.py`, which called `prepare_readiness(...)` and `validate_readiness(...)` serially with the same guard, installed socket denial, compared all ten planning diagnostics, and wrote aggregate outcomes. It did not run the two CLI commands as separate unsupervised sessions. [Supervisor](../../data/eval-comparisons/completion-08b-c1/supervision.json): exit 0, no stop reason, **8.663 seconds**, peak aggregate sampled RSS **279,560,192 bytes** (~267 MiB). [Worker](../../data/eval-comparisons/completion-08b-c1/worker-outcome.json): passed, **zero transactions**. No acquisition attempts or resource-stop retries occurred.

Resource evidence: host free-memory fraction **55% → 54%**, no pressure warning; free disk **35,754,627,072 → 35,731,304,448 bytes**. Conservative normalized reservation **57,282,965 / 100,000,000 bytes**, including existing retained copies and staging; combined artifact reservation **80,329,214 / 2,147,483,648 bytes**. Measured historical-plus-C1 artifact bytes at worker completion **61,193,143**. C1's new-folder ceiling **67,108,864 bytes** and 60-minute window were enforced; final evidence directory size is recorded in the completion record. Existing 1.5/2 GiB RSS, 25%/20% host-memory admission/stop and 10 GiB disk floors were unchanged. The supervisor samples resource use; the audit hook is process-local, not an OS network sandbox.

[Preservation check](../../data/eval-comparisons/completion-08b-c1/preservation-check.json): **67 pinned historical/protected files unchanged**, including original receipts/permissions, previous results, unchanged contracts and dependencies. Executed implementation/configuration hashes still match the supervision record.

## Acceptance and defects resolved

All seven C1 acceptance criteria passed: strict continuation-only admission and history; complete observations/names; deterministic equality pairs/components/witnesses; correct quarantine/intersections and unknown languages; private preparation-only status; fictional failure/security regression; supervised aggregate-only real execution with immutable history.

The implementation review found and resolved two concrete gaps before real execution: validation now enforces the new-root 64 MiB ceiling and accounts for existing artifacts against normalized storage; rejected long names explicitly prohibit matcher input. Source/config mutation before completion and rehashed output corruption have regression tests. No known reproducible in-scope failure remains from these checks. This is scoped evidence, not a claim of defect-free software.

Fictional example: source A's `Fictional Lumen Orchard` and source B's compatibility/case variant produce an unresolved normalized-name nomination with both evidence IDs. A weak, overlength alias retains its original text and receives label/mining/final-query/matcher restrictions. Its valid sibling name remains. Neither operation creates a human identity label.

## What remains and the exact next decision

Full Step 08 still needs actual human review, resolved duplicate/equivalence and leakage relationships, approximately 5,000 usable reference families and 2,000 independent absent-query families, at least 200 positive and 200 negative candidate reviews, adjudication of every used hard negative, and independently reviewed final positives meeting the original target of at least 100 groups per claimed direction. Current observations are development-exposed. The planning evidence reports only 27 Latin–Han candidate groups before review; C1 does not improve that shortage or establish independence. Direct UN and Wikidata remain outside this package. Accepted release creation, protected custody and Step 09 remain closed.

**Recommended next approval: 08B-C2 — offline review-packet and ledger implementation.** This advances the reviewed corpus directly, using the now-validated preparation rather than another acquisition/infrastructure audit.

Proposed bounded implementation:

1. Add `src/watchlist/readiness_review.py`, `tests/test_readiness_review.py`, and `config/corpus-review-v1.json`; extend `tests/test_label_review.py` only for compatibility/boundary regression. Keep the existing fictional review API and corpus SQL schema unchanged. Update `docs/data-card.md`, create `docs/progress/completion-08b-c2.md`, and use a new private `data/eval-comparisons/completion-08b-c2/` evidence directory.
2. Bind private, **blank/unreviewed development packets** to the C1 manifest, component, pair and evidence IDs. Use references to original names instead of repeated source copies. Keep duplicate-equivalence tasks distinct from positive/negative label tasks; no candidate becomes a correct label automatically.
3. Implement an append-only, integrity-checked local submission/adjudication ledger and explicit actor authorization. Test submissions with fictional actors only. Proposed protocol: two independent reviewers plus a separate adjudicator for disagreements; insufficient evidence remains unresolved. An empty real-actor registry must block real submissions. Local actor declarations cannot prove independent custody.
4. Exercise stale packets, duplicate/replayed submissions, incompatible decisions, self-adjudication, altered evidence, unsafe paths, interrupted writes and corrupt ledgers. Actual case queue preparation is allowed only if included in the next explicit approval; **actual human decision ingestion stays disabled until separately approved**.
5. Zero network, new dependencies or model calls. Retain current resource ceilings and one serial supervised real-data worker ≤60 minutes. Propose ≤16,000,000 bytes of new C2 artifacts, counting prior normalized material toward the unchanged 100,000,000-byte ceiling. Stop if a preflight reservation cannot fit; do not increase a bound. Run focused tests and one necessary compatibility check.

C2 acceptance: deterministic packets trace back to verified C1 evidence, the ledger rejects unauthorized/stale/conflicting/tampered input, interruption cannot publish accepted partial work, old fictional behavior remains strict, and real decisions/labels/merges/releases stay zero. No acquisitions, human execution, training, Step 09 or publication are included.

Codex can implement/test these mechanics and prepare approved blank packets. **The owner must authorize C2 and choose/approve the review protocol; actual named reviewers/adjudicator/custodian, their availability and real access separation belong to S1. Humans must supply evidence-backed decisions.** C3 graph/absence/release mechanics, S1/S2 supply and custody, H1/H2 actual review, and C4/C5 actual assembly/closure remain required in the existing dependency order. None is being deferred to training.

## Beginner-friendly 5W1H

- **What:** organized the retained records into trustworthy, unreviewed work queues.
- **Why:** reviewers need complete evidence and clear uncertainty flags before anyone builds learning labels.
- **When:** after acquisition and before real review, accepted corpus assembly or training.
- **Where:** private local C1 preparation files; original sources and experiments remain intact.
- **Who:** Codex validates software and evidence consistency; authorized humans decide identity/labels, and the owner approves each next package.
- **How:** verify source hashes and permissions, retain original names, nominate possible duplicates, mark restrictions, write privately, then independently reconstruct and compare the result.

**Stop at this boundary. Approve C2's bounded implementation and blank development-packet preparation to proceed; no human execution is requested yet.**
