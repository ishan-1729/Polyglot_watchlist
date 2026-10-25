# Step 08B-C3 — adjudication application and absence-validation mechanics

2026-10-25. Implementation authorized by the user's C3 request and the exact [C2 next-package proposal](completion-08b-c2.md#next-executable-packages-and-separate-approval-gates). This report supplements historical evidence; it does not revise C1/C2, acquisition receipts or the original [Step 08 requirements](../project-completion-plan.md).

**Decision: C3 COMPLETE. Full Step 08 remains incomplete.** The scoped tests, supervised preparation/independent regeneration and preservation checks passed. This package implements offline mechanics; it does not supply human judgments or an accepted corpus. No known reproducible in-scope defect remains from these checks; passing tests do not prove the absence of every possible defect.

## Scope and scientific meaning

A family graph records which observations have a supported identity relationship, which are explicitly distinct, which share dependence that could leak information between evaluation sets, and which remain uncertain. These are different relations. A C2 `supported_same` identity adjudication does not automatically prove canonical record equivalence: C3 keeps record-equivalence groups as singletons because C2 has no separate authority to declare canonical equivalence. Source-record continuity across snapshots establishes conservative dependence, not identity. Distinction is not transitive. Similar names never merge identities.

An absent query is relative to an explicitly declared, complete reference view. A low retrieval score or exclusion from a top-k result does not establish absence. The checks consider every equivalent/dependent record, original alias and declared descendant in normalized indexes, display metadata, embedding caches and reviewer memory. Unknown links, restricted names, unsupported identity/linguistic evidence, name collisions and ambiguous distinct target families block a supported dry-run absence. Holding out one alias for a positive query is a separate operation.

The real run uses **all 13,658 existing observations as provisional reference membership and zero absent targets**. It neither silently selects a 5,000/2,000 cohort nor treats missing review decisions as approval. Successful fictional absence tests demonstrate software behavior only. All real observations remain development-exposed and ineligible as fresh final material.

## Files and functions

| File | Explanation |
| --- | --- |
| [corpus_adjudication.py](../../src/watchlist/corpus_adjudication.py) | New isolated C3 module. `build_family_graph` admits pinned C1 evidence, rebuilds C2 packet bindings and replays the persisted ledger against an externally supplied head. `_derive_graph` separates identity, distinction, dependence and uncertainty, rejects contradictory closure, and propagates quarantine. `FamilyGraph` returns detached copies and refuses ordinary rehashed dictionaries as admitted graphs. |
| Same module: view/query APIs | `build_reference_view` binds complete membership and modeled descendants; `_representations` bounds and validates their ancestry DAG, including unknown ancestors and cycles. `build_absent_candidates` constructs evidence-bound requests and checks all-copy exclusion; `validate_absent_candidates` regenerates results rather than trusting editable labels. `validate_held_alias_query` separately checks positive-query withholding and reviewed directional adequacy. |
| Same module: filesystem APIs | `_load_config` and `_account_inputs` enforce exact policy, inherited roots, pins and budgets. `prepare_adjudication` writes private files without replacement, publishing the completion manifest last. `validate_adjudication` independently regenerates every output from original evidence and rechecks it. `deny_network`/`main` provide offline CLI operation and aggregate errors. |
| [test_corpus_adjudication.py](../../tests/test_corpus_adjudication.py) | Fictional persisted C2 ledgers exercise identity closure, distinctions, quarantine, absent/held-alias membership, stale/tampered artifacts, bounded resources and filesystem failure handling. No test submission is placed in the actual C2 ledger. |
| [corpus-adjudication-v1.json](../../config/corpus-adjudication-v1.json) | Exact C2 configuration/packet/head pins, 19 normalized input references, all six historical/current artifact roots, zero real actors/targets and unchanged prohibitions. New C3 artifact ceiling is 16,000,000 bytes. |
| [C3 evidence directory](../../data/eval-comparisons/completion-08b-c3/) | Private preparation, test logs, execution receipts and preservation evidence. `execute_supervised.py` permits one explicit run; `run_adjudication.py` installs network denial and serially prepares and validates using the same resource session. |
| [data-card.md](../data-card.md) | Appended C3 status and limitations. Earlier historical sections remain intact. |

C1/C2 schemas, modules, source snapshots, original models, review stores, dependency files and historical progress reports are not edited. No Git publication is performed.

## Validation evidence

Existing C1/C2 logs remain evidence for their completed work; the unchanged 2,606-test suite and secret scan were not repeated. Only the new module and fixture tests changed application behavior. No dependencies changed.

Commands actually run from the project root (stdout retained in the private C3 evidence directory):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_adjudication.py tests/test_readiness_review.py tests/test_label_review.py tests/test_corpus_readiness.py tests/test_record_links.py tests/test_resource_guard.py -p no:cacheprovider
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus_adjudication.py -p no:cacheprovider
.tools/qa/bin/python -I -B -m ruff check --isolated --target-version py314 src/watchlist/corpus_adjudication.py tests/test_corpus_adjudication.py data/eval-comparisons/completion-08b-c3/run_adjudication.py data/eval-comparisons/completion-08b-c3/execute_supervised.py
.tools/qa/bin/python -I -B -m ruff format --check --isolated --target-version py314 src/watchlist/corpus_adjudication.py tests/test_corpus_adjudication.py data/eval-comparisons/completion-08b-c3/run_adjudication.py data/eval-comparisons/completion-08b-c3/execute_supervised.py
.venv/bin/python -B data/eval-comparisons/completion-08b-c3/execute_supervised.py
```

- [Combined integration](../../data/eval-comparisons/completion-08b-c3/integration-tests.log): **416 passed in 9.50 seconds**, covering C3 and C2/C1 review, links and resource contracts.
- A subsequent narrow held-alias historical-dependence fix justified rerunning the affected C3 module: [final C3 suite](../../data/eval-comparisons/completion-08b-c3/final-c3-tests.log), **112 passed in 7.22 seconds**. The unchanged 306 companion cases reuse the combined evidence. These are overlapping runs, not 528 distinct tests or a claim that the entire repository ran on the final code.
- Final scoped [Ruff check](../../data/eval-comparisons/completion-08b-c3/ruff-final-check.log) and [format check](../../data/eval-comparisons/completion-08b-c3/ruff-final-format.log) passed for four files.
- Intermediate development runs found a fixture row-index mismatch and the final-publication race; both were fixed. Focused regression evidence: [9 passed / 101 deselected](../../data/eval-comparisons/completion-08b-c3/focused-tests.log), then [3 passed / 109 deselected](../../data/eval-comparisons/completion-08b-c3/focused-postintegration.log). These overlap the final suite and do not add to its count. The latter used `-k held_alias`; the former selected guard mutation, incoming references, propagated quarantine, expansion and restricted-alias tests. No failure was hidden by disabling or weakening a test.

The wrapper invoked preparation and independent regeneration serially, using the same resource session and a process-local socket-denial hook. The [supervisor receipt](../../data/eval-comparisons/completion-08b-c3/supervision.json) records exit 0, no stop reason, **26.714 seconds** and peak aggregate sampled RSS **372,080,640 bytes** (~355 MiB). The [worker receipt](../../data/eval-comparisons/completion-08b-c3/worker-outcome.json) records `passed`, **zero network transactions**, and identical prepared/validated summaries. One run was made; no resource-stop retry occurred.

Host free-memory fraction was **50% → 49%**, with no pressure warning. Free disk was **35,653,300,224 → 35,648,143,360 bytes**. Conservative normalized reservation was **54,672,451 / 100,000,000 bytes**; combined artifact reservation was **77,770,922 / 2,147,483,648 bytes**. Existing 1.5/2 GiB RSS, 25%/20% host-memory thresholds, 10 GiB disk floor and 60-minute session limit remained active. Sampling is not continuous measurement; the socket audit hook is process-local, not an OS isolation boundary.

The five preparation files occupy **3,964,952 bytes**. The actual graph retains 13,658 provisional record/identity/dependence groups, **1,259 uncertain equality pairs**, zero resolved identity edges and zero adjudications. It quarantines **1,638 observations** for unresolved graph evidence, including incoming-link concerns; source name restrictions remain separately attached. No literal retained-target referent pair was resolved (`unresolved_referent_pairs: 0`); raw referent assertions still block their source observations. These counts do not establish 13,658 independent families. They do not replace the broader C1 total of 2,864 flagged observations.

The [preparation manifest](../../data/eval-comparisons/completion-08b-c3/preparation/manifest.json) has file SHA-256 **`cc13c34381d187c7469df8828fe180459975e51f1129e56a4fc48f698ba6eda4`**. Logical graph commitment: `1de4e2d2a63b088e0351d4bbd3226620d221e56c408efb4bb39cd866eae7d165`; logical reference-view commitment: `76bb52d9689eaa49733a59219e969960aeb111c7a686ce4b02d6651f0f910bb6`. The worker receipt separately records hashes of the complete serialized files, which include those logical commitment fields.

[Preservation verification](../../data/eval-comparisons/completion-08b-c3/preservation-check.json) checked **99 protected files and 11 executed code/configuration files**, with zero changes. Verification used SHA-256 reads against the saved pre-run pins and supervisor execution pins; no restoration or overwrite was needed. [The completion record](../../data/eval-comparisons/completion-08b-c3/completion.json) binds the final documentation, tests and execution evidence and records the total new C3 directory size against its 16,000,000-byte ceiling.

| C3 acceptance criterion | Evidence / decision |
| --- | --- |
| Deterministic reconstruction from external ledger head | Passed: C2 packets regenerated against C1; persisted events replayed under lock; stale/rehashed/tampered inputs rejected; real prepared and independently validated summaries agree. |
| Distinct relationship types and contradictions | Passed: identity, singleton record-equivalence, dependence, distinction and uncertain edges stay separate; transitive contradiction tests reject; uncertainty propagates quarantine. |
| Complete-view absence and alias lineage | Passed in fictional tests: remaining source copies, original aliases, descendants, homonyms and unresolved links block supported absence; invalid/query-specific membership and stale views fail. Real absent requests remain empty. |
| Failure-safe output | Passed: exclusive private writes, manifest last, no replacement; interrupted/partial/corrupted output cannot validate as complete; final-callback mutation regression passes. |
| Resource and approval bounds | Passed: one offline supervised run within all stated limits; no acquisition, genuine submissions, publication, accepted release, training or Step 09. |
| Preserve original evidence and zero fabricated labels | Passed: 99 protected pins unchanged; actual ledger remains empty, actors empty; accepted labels/families/merges all zero. |

The single parent security/scientific review and fictional regressions identified and corrected these issues before real preparation:

- A resource probe could modify an output after its first byte check. Final resource callbacks now finish before complete upstream and output checks; the completion manifest follows those checks without another callback. The regression reproduced the old failure.
- A reviewed distinct homonym still present in a view could permit an unqualified absent claim. Explicit normalized-name collision checks now cover original and derived evidence; distinction alone does not resolve an ambiguous query.
- Multiple distinct target identities could receive a supported result from one matching identity. All targets are retained, but multiple distinct identities require additional query review rather than inflated accepted-family counts.
- A raw incoming provider reference could flag its source but leave a differently named plausible endpoint clear. Literal possible endpoints across namespaces now receive conservative quarantine; no namespace/identity assertion is invented.
- Large repeated family memberships/derived ancestry could multiply memory consumption. Memberships are shared, and cumulative input, ancestry, query and output expansion is bounded.
- Positive held-alias withholding must also remove equal-text dependent historical copies; identity support and leakage dependence remain separate tests.

Fictional example: an adjudicated identity family containing `fictional-a`, `fictional-b` and `fictional-c` can produce `supported_absence_dry_run` only when all its copies and descendants are absent from the declared view and other eligibility checks pass. Retaining any member returns `supported_presence`; `a=b`, `b=c`, `a≠c` fails with `transitive_identity_contradiction`. Every result still has `accepted_label: false`. These identifiers come from isolated fixtures, not human judgments about retained source organizations.

## Limitations and remaining Step 08 gates

| Work | What software can do | What cannot be supplied by offline automation |
| --- | --- | --- |
| Candidate assembly | Build immutable candidate inventories, original-evidence lineage and completeness checks; mechanically apply eligible recorded decisions. | Declare unreviewed observations independently correct or silently choose accepted cohorts. |
| Duplicate/name review | Prepare neutral packets and validate authenticated, authorized human submissions, conflicts and adjudication history. | Produce genuine judgments, verify competence from a JSON actor name, or infer identity from similarity. |
| Reference/absence population | Validate selected whole families, all-copy membership and counted denominators. | Establish approximately 5,000 usable reference and 2,000 independent absent families without sufficient evidence and review. |
| Multilingual supply | Audit known scripts/unknown languages and prepare bounded acquisition requests using existing metadata. | Create legitimate Han aliases by translation, claim unreviewed groups as final positives, or acquire additional sources without approval. |
| Permissions | Preserve exact grants, attribution and retention evidence; enforce approved paths and purposes. | Grant new legal rights, resolve direct UN permission independently, or authorize data redistribution. |
| Protected custody | Implement fictional access-policy/export checks and exposure inventories. | Appoint independent people or make this developer-accessible filesystem secret from this agent. |

The existing source-local counts are OpenSanctions UN **269 records / 918 names**, OFAC **11,610 / 25,323**, EU **1,779 / 14,327**. Combined: **12,090 organizations, 1,568 vessels and 40,568 names**. The existing 1,259 duplicate pairs form 657 review components; 2,864 records have the C1 union of flags. C3 graph quarantine and evidence-specific name restrictions are separate diagnostics and must not replace this C1 flag denominator.

C2 has **12,238 blank task entries**: 1,259 duplicate, 2,864 flagged, 6,856 proposed-positive and 1,259 negative hypotheses. Duplicate and negative queues reuse the same pairs; they are not extra independent cases or confirmed negatives. Human decisions, accepted labels, accepted reference/absent families, actual identity merges and protected final families remain **zero**.

Previously measured Latin–Arabic/Cyrillic/Han source-local candidate counts are **169 / 1,070 / 27**, before review and independence screening; 118/255/7 respectively belong to equality components. These measurements are reused from [readiness planning](completion-08b-03-plan.md), not a new acquisition or claim of independent coverage. **27,858 name entries lack language tags.** Script does not determine language. The original ≥100 independent final positive groups per claimed direction remains unchanged. Current development exposure prevents counting these as fresh final families.

The original gates still require ≥200 distinct positive-candidate and ≥200 distinct negative-candidate reviews, adjudication of every used hard negative, complete family eligibility/lineage and approximately 5,000/2,000 usable independent reference/absence groups. The 400-case minimum does not certify the rest of the corpus. Supersession/correction of genuine decisions needs an explicit append-only human workflow; C3 rejects stale inputs rather than rewriting history. Derived representations are validated against their declared ancestry, not discovered in arbitrary external caches. Hashes and file modes do not authenticate people or prove independent custody.

## Next executable package — H1-I, human-review intake and pilot handoff

**Proposed for approval, not started.** C3 is the end of the currently authorized implementation. Existing approvals do not authorize genuine human ingestion, a new acquisition batch, accepted release, training or Step 09. The next useful implementation should enable actual review progress, rather than repeat a broad corpus-planning exercise.

**Goal:** implement a separate versioned human intake path and prepare a private neutral development pilot handoff, with actual submission/execution still locked until the owner verifies the required people and protocol. Preserve C2's historical fictional-only ledger and all C3 pins. C4 remains the later application to actual cohorts; this proposal does not redefine that gate.

**Exact proposed files:** new `src/watchlist/corpus_human_review.py`, `tests/test_corpus_human_review.py`, `config/corpus-human-review-v1.json`, `docs/progress/completion-08b-h1-i.md`, and private `data/eval-comparisons/completion-08b-h1-i/`; append only to `docs/data-card.md`. Reuse existing C1/C2 evidence resolvers and C3 scientific checks through their current contracts. Do not mutate the old ledger or accepted-source contracts. If a shared contract truly needs changing, document the concrete dependency before expanding scope.

**Implementation:** create a candidate-inventory commitment bound to the verified C1/C2 evidence; support neutral reviewer-facing packet exports with source names treated as inert text; implement owner-authorized actor/access declarations plus independent submission receipts; record actual identity verification as an external prerequisite, not a boolean invented by software; validate two independent initial submissions, separate adjudication, explicit uncertainty and append-only correction/supersession; build deterministic pilot selection with family reuse/source/script/type shortfalls reported. Store separate reviewer exports so the second reviewer does not see the first answer. Keep population scope and all answers unaccepted until the required gates pass.

**Tests/commands:** fictional-only `pytest tests/test_corpus_human_review.py`; one integration with the C2 and C3 tests after connection; scoped Ruff. Test unauthorized/duplicate identities and reviewer overlap, stale packets/heads, evidence changes, competing submissions, neutral escaping, independence, append-only correction, quarantine, resource stops and interrupted writes. No real submission is synthesized or replayed as fictional.

**Proposed resource limits:** zero network, paid services, models or dependencies; ≤16,000,000 new artifact bytes, one serial supervised local run ≤60 minutes; inherited normalized inputs ≤100,000,000 bytes, combined artifact roots ≤2 GiB; existing RSS soft/hard 1.5/2 GiB, host free-memory admission/stop 25%/20%, no pressure warning, and free disk ≥10 GiB. Account for C3 outputs before admission. Stop if the package cannot fit; no implicit budget carryover or increase.

**Acceptance:** immutable candidate commitment and reproducible neutral packet IDs; all actual decisions still blank; only fictional authorized submissions accepted in isolated tests; real execution requires explicit verified access/protocol authorization; conflicts/supersession retain original events; no accepted cohort, release, final data or Step 09. Packet-size and stratum insufficiency are reported honestly; no silent substitution or alias multiplication.

### Separate owner/human gates that can be arranged in parallel

1. **S1 — appointments and scope:** name two genuinely independent competent reviewers and a separate adjudicator; confirm relevant language/domain skills, conflicts, authorization, local access, retention, time/payment budget and whether vessels remain a separate stratum. Use [the existing review protocol](../planning/step-08b-review-and-custody.md). Do not send credentials or private personal documents into this chat.
2. **H1 execution — pilot:** after H1-I and S1 pass, separately approve the **40-case development pilot, 20 proposed positives and 20 negative candidates**. Open the private [C2 packet directory](../../data/eval-comparisons/completion-08b-c2/packets/) through the validated resolver/export, not by treating raw queue names as answers. Inspect original names, source-qualified identifiers, provenance, qualifiers and permitted identity evidence. Each reviewer independently records supported-same, supported-distinct, insufficient-evidence or ineligible, with evidence citations, uncertainty, duration and directional relationship evidence. The adjudicator resolves disagreements without overwriting either submission. Missing evidence stays missing. Measure disagreement, insufficiency, family reuse and time before expanding to ≥200+200. No reviewer contact or execution is authorized by this report.
3. **S2 — supplementation and custody:** appoint an independent custodian and establish a genuinely separate environment unavailable to developers/this agent before protected acquisition. The custodian must privately screen all development exposure. Approve a source package with exact seeds, permitted fields/endpoints, revision/type/redirect policies, response/transaction/time/storage limits and expected yield. Existing official Wikidata Action API metadata can inform that package, but no entity/search calls or new rights are implied; a supplemental organization population cannot replace sanctions-domain evaluation. Direct UN stays permission-blocked. No additional acquisition quantity is authorized here.
4. **H2/C4/C5:** expand genuine review after the pilot, apply eligible decisions to actual reference/absence cohorts, meet multilingual/independence gates, then request immutable accepted-release authorization and close Step 08. Step 09 follows only after those prerequisites and separate approval.

## Beginner-friendly 5W1H

- **What:** software that builds a traceable family graph and checks whether an intended absent target really has no remaining copy in a declared reference view.
- **Why:** duplicate source records, old aliases and cached copies can otherwise make experiments look better than they are.
- **When:** after blank review infrastructure and before applying genuine reviews or accepting the corpus.
- **Where:** new private local C3 artifacts, linked to preserved C1/C2 evidence.
- **Who:** Codex implements and tests mechanics; authorized independent humans supply actual judgments, and a separate custodian protects final material.
- **How:** pinned versions, ledger replay, separate relationship types, quarantine, bounded ancestry checks, complete-view validation and private no-overwrite writes.

**Next decision:** approve the bounded H1-I implementation above, and begin S1 reviewer/custodian appointments. Genuine review execution and supplementary acquisition remain separate decisions. No new approval is needed for any remaining in-scope C3 defect fix.
