# Step 08 offline corpus-readiness planning — completed

2026-10-25. **Approved planning package: COMPLETE. Actual reviewed Step 08 corpus: INCOMPLETE. Next implementation requires approval.** No additional acquisition, reviewer execution, corpus publication, training or Step 09 occurred.

## What was done and what was reused

Read the original [completion plan](../project-completion-plan.md), `AGENTS.md`, Step 08A's corpus/source/review/custody requirements, the successful continuation report and verified aggregate evidence. Inspected `corpus.py`, `corpus_schema.sql`, `ingest/link_records.py` and `label_review.py` to distinguish existing functionality from proposed work. The Project 1 research scope and engineering/agent guidance in the reference remain unchanged; Project 2 is excluded.

The successful acquisition is not reopened. Its saved 64 focused tests, 64 audit checks and completion evidence remain historical verified results, not new tests in this phase. No full suite, acquisition retry, TLS diagnosis, model load, new dependency or repeated independent review was needed.

Created a single offline analysis for **new overlap/workload questions**, using the exact verified receipt, aggregate report and three retained selections. It hashes the five inputs, computes intersections and candidate connected-component sizes, checks the 1,259-pair/1,607-record result against the existing audit and verifies the same input hashes afterward. It outputs aggregates only: no names, IDs, pair-level packets or human labels.

## Actual findings

- **12,090 organizations + 1,568 vessels**, 13,658 source-local groups and 40,568 name-evidence entries. Organization-only entries: 38,717. None is yet a reviewed independent family.
- **1,259 normalized-name equality candidate pairs**, comprising the 663 exact pairs plus 596 additional pairs; 1,078 cross-source, 181 within-source. They form **657 candidate review components** involving 1,607 records, of which 1,561 are organizations. These components are review units, not identity merges.
- Weak-name flags affect 1,476 groups; 17 overlength entries affect four EU groups. Duplicate/weak flags overlap in 223 groups. The union of all three flags affects **2,864 groups**, including 2,790 organizations. There are **9,300 organizations with none of these listed flags**, but that is not verified independent usable yield.
- **6,711 organizations** have at least two distinct normalized nonweak application-compatible names. Only **4,751** also have none of the three flags. This helps plan review; it is not a new requirement that every reference/absence family have two names. Blanket disposal of flagged groups would unnecessarily lose potentially usable evidence.
- **169 Arabic / 1,070 Cyrillic / 27 Han** source-local cross-script candidate groups remain unchanged. Of these, 118/255/7 are in equality review components. No current candidate is fresh-final eligible; there are zero real labels or independently protected final families.
- **27,858 entries lack language tags**. Scripts are not languages; normalization or an LLM does not fill that evidence gap. Latin–Han and protected sanctions-domain final supply are explicit unresolved requirements.
- Source assertions and minimal name fields may be insufficient for cross-source legal-identity decisions. Some cases will need a separately permitted evidence request or exclusion. Human-review and custody capacity are not established.

## Deliverables and file/function explanations

| New file | Purpose and contents |
| --- | --- |
| [step-08b-corpus-readiness.md](../planning/step-08b-corpus-readiness.md) | Measured supply/intersections; implemented-versus-missing code contracts; immutable release layout, identifiers/provenance/versioning; duplicate/weak/length quarantine; 5,000-reference and 2,000-independent controlled-absence construction and acceptance checks. |
| [step-08b-review-and-custody.md](../planning/step-08b-review-and-custody.md) | Human roles; proposed 200-positive/200-negative strata; packet/submission/adjudication fields; all-used-hard-negative rules; workload assumptions; Han-source options and evidence gaps; independently controlled final-label/exposure workflow. |
| [analyze_readiness.py](../../data/eval-comparisons/completion-08b-03-plan/analyze_readiness.py) | Disposable planning-analysis script, not application implementation. `deny_network` rejects socket operations. `read` binds each input's whole-file digest. `key` uses the existing audit's NFKC→casefold→NFKC→whitespace normalization without truncation. `counts` emits source/type aggregates only. The top-level bounded pass computes candidate graph components, weak/length/alias intersections and arithmetic workload scenarios without calling review or release APIs. |
| [analysis.json](../../data/eval-comparisons/completion-08b-03-plan/analysis.json) | Exact inputs/hashes, measured aggregate intersections, review-time assumptions, zero-network/zero-human-decision counters, elapsed time and sampled peak RSS. |
| This progress report | Dependency-ordered remaining work, current acceptance decision, exact next implementation package, human/owner responsibilities and 5W1H. |

The proposed application's changes remain **unimplemented**. No existing application, test, model, source selection, review store, historical report or release was edited in this phase. Living links added to README/access ledger, if present, are status pointers only; they do not change historical outcomes or permissions.

## Commands and validation actually performed

Read-only `rg`, `sed` and `cat` inspection targeted the plan, existing code/contracts and saved evidence. The additional analysis command was:

```sh
.venv/bin/python -B data/eval-comparisons/completion-08b-03-plan/analyze_readiness.py
```

It exited **0**, completed in **0.7203655 seconds**, peaked at **142,147,584 sampled RSS bytes**, and preserved all five input hashes. It used the existing memory/disk guard and a socket-denial audit hook. It reproduced 13,658 groups, 40,568 entries, 1,259 candidate pairs and the saved component histogram. Resource checks were for this analysis, not repeated acquisition preflights. No pytest was run because application/test code did not change; the new work is documentation and a read-only aggregate analysis. Documentation link/requirements checks and the final output manifest are recorded in the planning evidence directory.

Fictional example: `source_a:42` and `source_b:42` are distinct qualified keys. Equal names nominate a pair; no merge follows. If reviewers support equivalence, both source observations remain and a new graph version links them. If one belongs to a proposed absence family, **both copies and their derivatives** must be excluded from the fixed reference universe before an absence decision is valid. If evidence is insufficient, the component stays quarantined; missing evidence never becomes a negative.

## Remaining Step 08 packages, in dependency order

These are new bounded subpackages inside Step 08, not replacements for the original step numbering. Each implementation, acquisition, human-execution and publication boundary requires its own approval. Fresh-source/custody work can be organized in parallel with exposed-data software work, but no named task is silently dropped.

| Package | Dependencies / work | Acceptance evidence and stop boundary |
| --- | --- | --- |
| **08B-C1: continuation admission and readiness queues** — recommended next | Successful acquisition; implement strict in-memory continuation preparation, normalized nomination, evidence/name quarantine and a private deterministic preparation manifest | Exact unchanged source counts; 1,259 equality pairs with evidence/method witnesses; weak/length totals; zero human decisions/merges/labels; source/claim/reservation validation; preserved historical formats; focused failure tests. Stop before accepted corpus or real review execution. |
| **08B-C2: real-review preparation and ledger mechanics** | C1; owner-selected review protocol and role model. Add explicit real-development packet mode, scoped actor authorization, append-only submission/adjudication persistence and replay/stale/conflict checks. Use fictional submissions for tests; do not fabricate humans | Separate fictional/real/protected gates; blank actual review queues only with specific packet-preparation approval; zero real decisions until human execution approved. Existing fictional review API stays strict. |
| **08B-C3: graph/cohort/absence and reviewed-release mechanics** | C1 contracts; C2 schema. Implement reviewed equivalence/dependence closure, quarantine/exposure propagation, corpus-level reference/absence universe validation and new reviewed-release format using fictional fixtures | All-copy/derived/cache membership tests; view-bound absence and target-set handling; no unresolved family accepted; immutable failure-safe writer; no actual partitions, real labels or accepted release yet. Scope can be split into graph/absence and writer changes if too large for independent review. |
| **08B-S1: owner roles, evidence and protected custody readiness** | Start alongside C1–C3 planning, before protected collection. Name qualified reviewers/adjudicator/custodian, approve rates/capacity/type mixture, establish actual separate access. Resolve minimal identity-support field/permission needs and select exact candidate Han/fresh-sanctions routes | Verified access boundary and responsibilities; approved evidence fields and source/seed/resource proposal; public proof without protected examples. Local declarations alone do not pass. Official documentation calls only under a separately approved bounded preflight. |
| **08B-H1: 40-case human development pilot** | C2; S1 reviewer authorization and explicit execution approval | 20 positive proposals +20 negative candidates, actual independent reviews/adjudication, time/uncertainty/disagreement/evidence-request measurements. Pilot is a subset of later 400 only if the frozen protocol applies. No final cases. Return measured staffing/cost plan before bulk review. |
| **08B-S2: approved supplementary/fresh acquisition and review** | S1, usable packet/ledger tools and separate exact acquisition approval | Permitted typed organizations and genuine original-script/Latin evidence; complete provenance; natural relation/direction judgments; exposure overlap screened privately. Supplementary learning and sanctions-domain evaluation remain distinct. Fresh required counts and 100-per-claimed-direction gate met, or explicit shortfall stays open. No automatic source expansion. |
| **08B-H2: full eligibility, duplicate and label review** | H1 protocol/cost decision; S2 for fresh labels. Review proposed accepted families and all relevant duplicate edges; ≥200 positive and ≥200 negative distinct candidates; adjudicate every hard negative actually used | Evidence-backed decisions/label ledger, disagreement/exclusion rates, no unresolved incoming links to accepted cohorts, per-source/type/script/family denominators. Initial 400 does not certify the rest. Protected reviews remain with custodian. |
| **08B-C4: actual reviewed corpus assembly and validation** | C3, H2 and S2 with adequate supply/custody. Apply real approved decisions; build proposed ~5,000-reference/~2,000-independent-absence cohorts and fixed corpus reference universe, validate actual memberships inside appropriate custody | Actual independent counts, actual all-copy absence checks, label/graph/permissions/withholding validation, explicit excluded components, review minima, eligible final direction capacity and independent access attestations. A tested function/planning estimate is insufficient. No Step 09 partition assignment. |
| **08B-C5: immutable release and Step 08 closure** | C4 passes all gates and owner explicitly approves private release creation | New non-overwriting reviewed release plus protected companion, logical/file hashes, attribution, versioned review and exclusion ledgers, human sign-offs and complete acceptance report. All targets pass or owner approves a named scope revision. Only then request Step 09 authorization. |

C3 can be implemented while humans are being organized; that does not authorize calling reviewers or sourcing evidence. Software completion is not human/scientific completion. No mandatory data/review/custody shortfall is deferred to training or hidden in a “complete” flag.

## Exact next implementation proposal: 08B-C1

**Goal:** turn the successfully retained selections into auditable, unreviewed readiness queues using the existing contracts. **Why:** this directly prepares the 1,259 duplicate candidates and the name-level restrictions for human work; it does not repeat downloads or prematurely release a corpus.

**Inputs/dependencies:** pinned continuation receipt `dff2ef1c…`, source-selection hashes from that receipt, the inherited permission evidence and original/failed/continuation lineage; existing source-record, resource, identifier and link APIs; unchanged environment and dependencies. Do not change the consumed policies/claims, increase permissions or rewrite `release_authorized=false`.

**Exact proposed file scope:**

- Edit `src/watchlist/corpus.py`: explicit continuation preparation/validation entry point that binds complete sources, exact new/prior accounting, reuse origin and source-purpose evidence. Keep original direct/recovery admission APIs strict. Return verified preparation objects; do not call candidate/accepted release publication.
- Edit `src/watchlist/ingest/link_records.py`: add versioned conservative normalized-name nominations alongside existing methods, with stable pair identities and original evidence witnesses; no new auto-merge relation or human origin.
- Create `src/watchlist/corpus_readiness.py`: offline-only CLI to build/validate private **readiness preparation** artifacts, evidence identifiers, duplicate-component queue and evidence-level quarantine. Distinguish its input/preparation hash from any corpus-release hash; integrate typed boundaries rather than misusing existing candidate-release fields.
- Create `config/corpus-readiness-v1.json`: exact pinned input references, normalization/nomination versions, type strata, non-use restrictions, counts/byte/time caps and no-network mode. It grants no source access, human decision, training or release eligibility.
- Extend `tests/test_corpus.py` and `tests/test_record_links.py`; create `tests/test_corpus_readiness.py` with fictional inputs and purpose-bound failure tests.
- Create a new private `data/eval-comparisons/completion-08b-c1/` preparation directory and `docs/progress/completion-08b-c1.md`. Update `docs/data-card.md` only with the measured preparation state and limits.

No SQL/schema migration, real `label_review.py` mode change, network-client edit, new library, model load or old-artifact mutation is included in C1. If implementation reveals an indispensable scope change, specify it before proceeding beyond this scope.

**Proposed commands, not run now:**

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_corpus.py tests/test_record_links.py tests/test_corpus_readiness.py -k 'continuation or readiness or normalized or quarantine' -p no:cacheprovider
.venv/bin/python -B -m watchlist.corpus_readiness prepare --config config/corpus-readiness-v1.json --output data/eval-comparisons/completion-08b-c1/preparation
.venv/bin/python -B -m watchlist.corpus_readiness validate --input data/eval-comparisons/completion-08b-c1/preparation
```

The new CLI must first be implemented and tested; current commands do not exist. Run scoped Ruff and only the relevant existing regression tests for touched contracts. No whole suite unless a concrete shared-contract change justifies it.

**Bounds:** zero network, no extra dependencies, one serial offline worker, ≤60 minutes, ≤64 MiB new preparation artifacts, within existing 100,000,000 normalized-byte/2 GiB combined artifact ceilings; preserve ≥10 GiB free disk and existing 1.5/2 GiB RSS and host-memory admission/stop guards. No automatic rerun after a resource failure. Evidence should be deduplicated/referenced in packets so duplicated long alias lists do not silently grow the output. Stop if current corpus buffer limits are insufficient; do not raise them silently.

**Required C1 acceptance:**

1. Complete continuation receipt accepted only by the explicit new preparation path; missing/failed/stale/cross-session evidence, altered reservations, wrong source selection and original-API misuse fail before output acceptance. All history remains traceable.
2. Preserve 13,658 observations, 40,568 complete name-evidence entries, original fields/types/language/weak qualifiers and stable source-qualified identifiers. No raw source reacquisition or extra retained fields.
3. Reproduce the equality subset of 1,259 unique unordered pairs, 663 exact and 596 normalized-only, 657 components and 1,607 involved observations. Retain all nomination witnesses without turning components into identities. Additional referent/continuity nominations, if the existing contract can validly qualify them, are separately reported and must not overwrite this equality denominator or infer namespaces.
4. Mark 2,153 explicitly weak entries and 17 overlength entries with evidence-level restrictions. Preserve valid sibling names and original text; unresolved duplicate components stay group-level quarantined. Unknown language stays unknown. Reproduce aggregate intersections; unflagged is not accepted.
5. New private artifact has preparation-only status, no real review submissions, zero accepted labels/identity merges/final eligibility and no corpus publication. Current real-review prohibition remains active.
6. Tests cover deterministic reorder/ties, duplicate witness accumulation, namespace collisions, changed originals, normalization collisions without identity, weak/length masking, contradictory relations, partial writes, symlink/overwrite attempts, corrupt hashes, resource stops and no-network enforcement. Preserve original formats and datasets; do not weaken tests to accept the new envelope accidentally.
7. Real preparation run emits only aggregate developer logs, private case/evidence artifacts, manifest hashes and a phase report. Stop for C2/S1 decisions; no reviewer message, review execution, accepted release or partition.

**Risks:** scope-confusion between a receipt and a candidate release; treating a nomination as a label; minimal evidence insufficient for human identity decisions; falsely treating no flags as clearance. Explicit artifact kinds, stable provenance, false eligibility flags, private evidence and human decision gates address these risks.

**Owner approval requested next:** authorize only 08B-C1 as specified. Source choice, organization/vessel population, reviewers/custodian, review budget, acquisitions and release publication remain separate decisions; none is inferred from approving C1.

## What Codex can do versus what people must supply

| Task | Codex can automate after the corresponding approval | Human/owner dependency |
| --- | --- | --- |
| Provenance/IDs/immutable preparation/release machinery | Implement and test validators, manifests, deterministic writers and failure recovery | Owner permits the exact purpose and eventual release; publishers/legal review determine rights |
| Duplicate and name quarantine | Nominate edges, preserve witnesses, propagate recorded uncertainty and approved decisions | Qualified reviewers determine equivalence/distinction; evidence gaps may require owner-approved sourcing |
| Review packets and ledger | Deterministic sampling, blank packets, authenticated-workflow mechanics, replay checks, counts | Real authorized humans supply judgments, competencies and adjudications; owner chooses staffing/rates |
| 5,000 reference /2,000 absent construction | Apply reviewed graph, exclude all known equivalent/dependent copies and derivatives, validate actual fixed-view membership | Humans support identity/non-equivalence and eligibility; owner approves population/type policy; software cannot prove unknown real-world equivalence absent |
| Han/source planning | Compare saved contracts, draft bounded source/seed/resource proposals | Owner authorizes exact new source/fields/budgets; provider terms and qualified language review remain necessary |
| Final data protection | Build network-disabled evaluator, generic integrity checks, exposure inheritance and aggregate output controls | Independent custodian establishes real separate access, obtains fresh material and protects labels/examples |
| Acceptance report | Count actual eligible families/directions/reviews, report failed gates, prepare new versions | Owner explicitly approves release and Step 09 only after all prerequisites pass |

Unfilled roles are genuine blockers to human execution and full Step 08 completion, not reasons to stop authorized software implementation. Codex cannot supply independent final custody in its own accessible workspace or certify human judgments by creating actor entries.

## Planning acceptance and 5W1H

All ten requested planning topics are covered by the two specifications and this report: measured pool; immutable release; duplicate quarantine; human review; independent absence; Han supplementation; protected final custody; dependency-ordered packages; no redundant infrastructure/full-suite work; findings/limitations/next action. The **planning** phase closes; the **corpus** phase does not.

- **What:** mapped the retained candidates into specific software, human-review, evidence and custody tasks; measured overlap to avoid double-counting workload.
- **Why:** downloaded names are not yet independently correct labels or a leakage-free corpus.
- **When:** now that three-source acquisition has succeeded, before any new collection, real labeling, release or training.
- **Where:** two planning specifications and a new private aggregate-analysis folder; source files and historical artifacts stay unchanged.
- **Who:** Codex builds/validates mechanics; the owner chooses scope/budgets/roles; qualified reviewers establish judgments; the independent custodian protects final cases.
- **How:** prepare traceable queues, collect real evidence-backed human decisions, resolve/quarantine families, validate a fixed reference/absence universe and protected fresh coverage, then seal a versioned release after explicit approval.

**Stop here. Recommended next action: approve 08B-C1, continuation admission and readiness queues.**
