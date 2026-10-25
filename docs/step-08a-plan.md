# Step 08A — corpus design, source feasibility and resource plan

Date: 2026-10-25, Asia/Kolkata. **Planning/offline analysis only. Step 07 is closed under its approved three-source revision. Step 08B is not authorized or implemented.** The original Step 08 requirements in `docs/project-completion-plan.md` remain unchanged; this document specifies a staged way to meet them, not a reduction of their targets.

## Outcome and fixed requirements

Build two explicitly documented populations: multilingual non-person names for learning, and fresh permitted sanctions-domain cases for domain evaluation. A supplementary organization dataset must not silently replace the latter. The research output is possible record matches for human review, not findings about wrongdoing or operational compliance.

| Original requirement | Design commitment |
| --- | --- |
| Approximately 5,000 usable reference groups | Aim for at least 5,000 accepted independent families in the declared reference universe. More source records or alias pairs do not substitute for independent families. |
| Approximately 2,000 independent absent-query groups | Plan 2,000 additional accepted families absent from the fixed index, disjoint from the 5,000 reference families. Absence is index-relative, not absence from sanctions worldwide. |
| At least 100 independent final positive groups per claimed Latin↔Arabic/Cyrillic/Han direction | Preserve each direction's target. Plan fresh, reviewed, eligible families and direction-specific withheld-name views; do not multiply correlated aliases into independent groups. Han is an explicit acquisition priority. |
| At least 200 proposed positive and 200 negative candidate reviews | Human reviews across source/script/type, disagreement and exclusion logs; every hard negative actually used is adjudicated. The 400-review minimum does not validate thousands of otherwise unreviewed labels automatically. |
| Immutable releases and full lineage | Preserve source-qualified IDs, original evidence, source snapshots, terms, versions, transformations and approvals. New releases never overwrite old ones. |
| Cross-source equivalence and uncertainty | Separate confirmed equivalence, broader leakage families and uncertain candidate links; quarantine uncertainty before splitting. |
| Step 09 independence | Whole families across approximately 50/15/10/10/15 roles; training-only mining; independent calibration/threshold selection; final labels under separate custody. No partition is created in 08A. |

The [approved Step 07 closure](progress/completion-07-approved.md) is the prerequisite. Earlier progress reports and acquisition receipts remain dated evidence. Direct UN and Wikidata were investigated but not acquired; this plan does not enable either.

## Existing evidence and its limits

The three retained selections have 600 source-local groups, 3,293 name-evidence entries and 3,072 unique strings. They are 600 organizations and zero vessels under the preserved provider classifications. A provider record is a candidate, not proof of an independently usable identity.

| Source | Existing retained groups | Name evidence | Eligible in completed input before cap | Complete input body bytes |
| --- | ---: | ---: | ---: | ---: |
| OpenSanctions UN | 200 | 696 | 269 | 3,026,789 |
| OFAC | 200 | 724 | 11,610 | 2,582,121 compressed |
| EU | 200 | 1,873 | 1,779 | 25,899,600 |
| Total | 600 | 3,293 | 13,658 source-local candidates | 31,508,510 |

The existing selections occupy 1,152,233 bytes. All contain Latin evidence; 35 groups contain Arabic, 96 Cyrillic and four Han. Strict single-script alias-pair candidates are 35/88/4. Name-language tags are present on 1,469 entries and unknown on 1,824. Exact names nominate 69 candidate links, including 65 across sources; none was converted into an identity merge or human label.

The [08A offline audit](../data/eval-comparisons/completion-08a/audit/report.md) found zero mechanical required-field, primary-name membership or source-specific provenance failures. It verified 15 permission-evidence references and preserved all input hashes. Only **386 groups have at least two distinct names**; 214 have one. **482 groups have no supplied language tag**. The 49 explicitly weak OFAC name entries span 23 groups. All 3,293 names meet the current normalizer's 200-code-point admission rule; none was truncated.

Conservative NFKC/case/whitespace normalization nominates **83 candidate pairs**, including the 69 exact pairs: four within-source and 79 cross-source, involving 166 groups. Fourteen additional cross-source pairs need review. Candidate connected components have two groups each in this sample; that is a graph observation, not an identity merge. The audit also finds 5,687 distinct provider referents in the OpenSanctions selection, without resolving them; unmatched references in a capped subset are not automatically invalid. Only aggregates are saved. Candidate links remain unreviewed even if multiple algorithms agree, and missing language is not inferred from nationality.

These 600 inspected groups are conservatively **exposed development/learning candidates**, together with their equivalent copies and derived aliases. They are not a fresh calibration, threshold-selection or final-test set. This is an exposure rule, not a label or an automatic training eligibility decision. No final test labels are opened, generated or exposed in 08A.

## A credible path to 5,000 plus 2,000 families

1. Revalidate permitted scope, current artifact metadata, field policy and sizes before any new acquisition. The saved source terms support the earlier bounded local research use; larger retention and later training/release need their explicit purpose checks. Direct UN remains outside the acquisition package pending an applicable grant and separate authorization.
2. Use the three successful sanctions-source routes as the initial candidate supply. The observed complete inputs contain 13,658 source-local eligible records, but deduplication, provenance, exposure and label review can reduce that substantially. The three source totals include overlapping identities; the existing 600 are a subset of that supply, not 600 additional records.
3. Screen and review candidate families before counting them toward either population. Target at least 7,000 accepted, disjoint families overall: 5,000 reference plus 2,000 absent. This requires approximately 51.25% accepted independent yield from the observed 13,658 source-local pool if no other sources contribute. That percentage is a break-even planning calculation, not a measured yield or a guarantee. If only the 5,000 reference target is considered, its break-even fraction is approximately 36.61%.
4. The primary source-feasible absent cohort consists of independently reviewed permitted non-person families whose **every equivalent copy is excluded from the fixed index**. This is a controlled index-absence experiment expressly compatible with Step 09. These records may themselves appear on public sanctions lists; the label means only “no equivalent reference in this declared index.” Human identity/non-equivalence review and a mechanical all-copy exclusion audit are both required. The same family cannot count in both the 5,000 and 2,000 totals.
5. A natural background nonmember cohort can be added as a separately identified population after permitted acquisition and review. Wikidata membership is never evidence of index absence. Do not claim open-world screening performance from a controlled withheld-family cohort; report population-specific error and limitations. The original 2,000-group requirement does not require inventing a new public source or assuming an API pilot will supply all 2,000.
6. Preserve dedicated fresh sanctions-domain families for independent evaluation. Supplementary multilingual organization names may support learning or a separately reported transfer study, but may not be used to disguise insufficient sanctions-domain coverage.

With the optimistic assumption that all 600 existing candidates become independent accepted reference families, at least 4,400 additional reference families and 2,000 separate absent families are needed. If future accepted-independent yield is q, additional candidate demand is at least `ceil((7,000 − U) / q)`, where U is the accepted current-family count and U≤600. At U=600, q=1/0.8/0.5 gives 6,400/8,000/12,800 additional candidates. These scenarios do not justify extrapolating script yield from the biased first-200 samples.

## Script coverage and fresh final evaluation

Arabic and Cyrillic have some candidate evidence; Han is currently extremely sparse. Prioritize collection plans that can independently verify original-script names and a supported Latin counterpart, retaining translation, transliteration and spelling-variation as different relationships. No machine-generated translation is promoted to a natural positive alias.

The final target remains at least 100 independently reviewed positive families per claimed direction. The current 35/96/4 source-local candidates are not fresh final cases and cannot be subtracted from that target. Under a strict 15% final allocation within a script stratum, at least `ceil(100/0.15)=667` eligible **fresh** families are a planning lower bound; review failures and duplicates increase it. Alternatively, a predeclared stratified allocation may reserve 100 eligible families in the final role while retaining approximately the overall 50/15/10/10/15 proportions. A fixed rule is chosen before model scores; do not search split seeds for coverage or performance.

The same genuinely bidirectional family can support two separately reported directional evaluations, but it counts only once in each direction and remains in one partition. Different scripts, directions and synthetic perturbations do not create independent families. If the planned corpus cannot supply the agreed fresh coverage, Step 08 remains unfinished data work; do not lower the target silently or start training around it.

## Supplemental API feasibility — offline conclusion

**Provisional preference: evaluate Wikidata's Action API for bounded known-ID retrieval before considering REST.** It potentially supports multilingual labels/aliases and structured type information without a graph-wide SPARQL query. This is an architecture assessment, not a verified current API contract or availability claim. Saved official evidence covers CC0 structured data and prior WDQS policy, not the current Action/REST limits or schema.

The existing 600 selections contain no established Wikidata seed-ID inventory. Discovery is a distinct bottleneck. A later pilot needs a finite curator-reviewed seed/search plan, balanced across Arabic, Cyrillic and Han aims; searching only retained sanctions names is overlap enrichment, not an independent absent cohort. Search rank is biased and is not a random sampling procedure. Known-ID retrieval, organization qualification, human exclusion, complete multilingual fields and revision/redirect provenance each require verified contracts and tests.

Keep direct `P31 Q43229` organization qualification as the conservative initial rule from Step 07. Expanding qualification to subclasses is a new rule requiring explicit review/approval, a bounded complete type-evidence algorithm and uncertainty quarantine. No untraversed class frontier may be interpreted as proof that a record is not human. A REST fallback, entity-data dump, alternate host or new organization catalog requires its own reviewed endpoint/permission decision; no automatic fallback is authorized.

Details and evidence distinctions: [source feasibility](planning/step-08a-source-feasibility.md). Direct UN remains legally pending and is excluded from the proposed network package. A successful HTTP response would not supply its missing transformation permission.

## Corpus and human-review design

The [corpus design](planning/step-08a-corpus-design.md) specifies the proposed schema, functions, invariants and fictional examples. Core separation:

- Immutable source snapshots and source-qualified record IDs identify evidence, never cross-source equivalence by themselves.
- Original name-evidence rows preserve supplied text, field, language, strength and version. Derived normalization/script data references its exact inputs and transform version.
- Candidate links record how a pair was proposed. Evidence-supported equivalence decisions are versioned, reviewable and reversible in a successor release. Similar names, shared parents and parent/subsidiary relations do not imply identity.
- Leakage-family membership is conservative and separate from canonical equivalence. Reviewed dependence may justify keeping records in one leakage family without declaring identity. Unresolved identity links quarantine the affected components before splitting; they are not silently treated as positive training examples.
- Human review records evidence, proposed decision, independent decision where possible, disagreement, adjudication, exclusions and reviewer role. Unresolved or weak evidence does not receive an invented binary label.
- Release manifests bind source hashes, terms, schema/parser versions, source-qualified membership, link/review versions, exclusions and exposure status. Frozen releases are immutable; corrections create a new version and invalidate affected descendants.

At least 200 proposed positive and 200 negative candidates must be reviewed across relevant source/script/type strata. These are minima, not permission to use additional unreviewed hard negatives. All used hard negatives are adjudicated, and independently reviewed final labels are sought with an identified custodian/reviewer arrangement. If qualified language review or independent final custody is unavailable, the corresponding gate remains unmet; the assistant cannot impersonate a reviewer.

## Step 09 compatibility and custody

The [partition and approval plan](planning/step-08a-partition-and-approval-gates.md) defines the detailed rules. Later Step 09 allocates whole reviewed leakage families approximately 50% training, 15% development, 10% calibration fit, 10% threshold selection and 15% final test. For nominal 5,000 reference and 2,000 absent families, those role counts are 2,500/750/500/500/750 and 1,000/300/200/200/300, respectively, before justified predeclared stratification. These are proposed counts, not generated partitions.

All aliases, source duplicates, historical versions and descendants follow their family. Training pair endpoints and negative-mining indexes use training families only. A query's withheld alias is removed from every equivalent reference copy in that view. Absent targets have all equivalent copies excluded from their declared reference view. New duplicate evidence crossing partitions invalidates the affected release and experiment; it is not silently patched after looking at results.

An independent custodian controls final family selection, labels and query details. Developers receive aggregate counts, hashes and integrity pass/fail checks, not final example names, scores, rankings, failure cases or label diagnostics. Hashes alone do not prove secrecy. The 600 currently inspected families and overlap descendants carry exposure flags and do not enter fresh calibration/threshold/final roles. Final evaluation remains reserved for Step 28; 08A creates no final artifacts.

## Resource estimate: observations versus assumptions

The [resource report](planning/step-08a-resources.md) and [read-only host probe](../data/eval-comparisons/completion-08a/resource-probe.json) record the actual machine and arithmetic. Observed at the probe: 16 GiB physical RAM, approximately 50.03 GiB free disk, and an OS free-memory estimate of 47%. These are a momentary availability observation, not a reservation or peak-RSS benchmark.

| Quantity | Measured basis or explicit assumption |
| --- | --- |
| Existing selected files | 1,152,233 bytes for 600 groups, approximately 1,920 bytes/group on this sample. |
| Offline parsed-data measurement | Approximately 5.71 MB of reachable Python objects and 5.85 MB peak traced allocations for loading the selected JSONL. This excludes interpreter/import baseline and is not acquisition peak RSS or evidence that full mixed XML processing fits. |
| Larger retained payload scenario | 14,500 groups at that same mean would be approximately 27.85 MB of JSONL; biased-sample linear scaling is only a planning scenario, not a hard storage bound. |
| Full source transfer baseline | Three completed responses total 31.51 MB. OFAC expands from 2.58 MB ZIP to 29.25 MB XML. Future versions may differ. |
| Disk proposal | Maximum 2 GiB new artifacts for the first acquisition tranche; require at least 10 GiB free disk before starting and throughout the run. Receipt/staging/index/backup overhead must be measured; no mixed raw-body staging or model/index build is included. |
| Memory proposal | One active source/request. Pause/stop at 1.5 GiB soft and 2 GiB hard aggregate acquisition-process RSS bounds, with an implemented supervisor tested before use. Byte limits are not a proof of peak memory. |
| Time proposal | At most 60 minutes for the live acquisition window; at most 30 minutes for the Wikidata pilot. Parsing/resource supervision is included. Human review is separate. |
| Human group review scenario | 7,000 group screens at an assumed 2–5 minutes each: approximately 233–583 hours, before difficult identity work, disagreement and independent review. Current 600 screens are included, not additional. |
| Minimum label review scenario | 400 first-pass label items at assumed 3–10 minutes each: 20–66.67 hours per pass. Separate second review may add similar time. Work overlaps group/link review, so do not add rows as a project total. |
| Monetary planning | Cash cost is `review hours × agreed hourly rate` plus separately approved costs. The resource report's ₹1,000/hour example is an assumption, not a quote, commitment or requirement to hire. Owner-provided review still has a time/expertise cost. No paid service, GPU, API key or cloud instance is authorized. |

Measured review speed, accepted independent yield and disagreements are still unknown. Obtain those from an explicitly approved review pilot before making a firm staffing schedule. The machine was not stress-tested, no model loaded and no dependency downloaded for these estimates.

## Exact proposed Step 08B first work package — approval required

This is a **new** resource proposal. Step 07's unused allowance does not authorize it. Retain the original **100,000,000-byte planning ceiling**, but activate only the following **59,000,000-byte first tranche** if explicitly approved. The other 41,000,000 bytes are unallocated and cannot fund automatic retries, new sources or a larger pilot. Every cap is an intersection, not an additional allowance; headers/TLS overhead are not included in the body-byte counter.

| Activity | Maximum received body bytes across all requests | Retention or work cap |
| --- | ---: | --- |
| Official terms/schema/API/size preflight | 5,000,000 | At most 16 HTTP transactions including redirects; at most 512,000 bytes each. No dataset response is disguised as metadata. |
| OpenSanctions UN reviewed distribution | 5,000,000 | At most 300 eligible non-person source-local groups. |
| OFAC SDN reviewed compressed export | 4,000,000 | At most 12,000 eligible non-person groups; decoded XML at most 32,000,000 bytes. |
| EU reviewed XML distribution | 30,000,000 | At most 2,000 eligible non-person groups. |
| Wikidata Action API pilot, conditional on preflight and seed approval | 15,000,000 | At most 200 retained organizations, 500 examined candidate QIDs, 800 type-graph nodes, and 250 HTTP API transactions including discovery/type calls. |
| **First tranche total** | **59,000,000** | At most 14,500 retained source-local groups before deduplication; no target achievement is guaranteed. |

The source caps cover the prior complete input sizes with modest headroom, not a second full download. Record every failed/partial/error-body read against its activity and global budget. A declared length over the remaining cap fails before transfer; missing lengths still require strict streaming counters. Never silently increase a ceiling or discard alias evidence to make a response fit.

**Execution order and stop gates:**

1. **08B-0, offline implementation first.** Implement and test the approved full-profile admission rules, exact destination validation, resource/byte/deadline accounting, private immutable staging, reviewable selection and API adapter boundaries using fictional fixtures. Current `fetch --profile full` is not implemented; do not pass larger quantities to the Step 07 feasibility profile or raise its global 200-group ceiling. Resolve source-specific terms/use questions and the human/custodian plan before subsequent data use.
2. **08B-1, authorized metadata preflight.** Only reviewed official terms/schema/metadata URLs, strict TLS and one request at a time. Use 30-second absolute request deadlines and no automatic retries. Pin current artifact URLs, official storage redirects, publisher hashes/sizes where supplied, API schema/revision/redirect/rate/completeness behavior and applicable non-person field-use terms. An unexpected destination, challenge, unavailable grant, paid/key requirement or ambiguous endpoint stops that branch. No live Action/REST contract was verified in 08A. New routes must be recorded in the reviewable execution policy before any data fetch; this plan does not grant an arbitrary host-wide exception.
3. **08B-2, three-source candidate acquisition.** Before this stage or 08B-3 receives prospective protected material, establish and verify the actual independent custody/storage boundary, reviewer access and aggregate-only developer outputs. A plan or file hash alone is insufficient. Material inspected through shared developer paths is exposed and must remain development-only. One attempt per source, at most two reviewed redirects per source and nine HTTP transactions across the three sources. Preserve existing source deadlines: 30-second requests/120-second source for OpenSanctions and OFAC; 180/240 seconds for EU. One source active at a time. Retain only approved fields and types; reject or explicitly quarantine unsupported evidence, never silently truncate aliases. New artifacts go to new private paths; historical artifacts remain untouched.
4. **08B-3, conditional API discovery/retrieval pilot.** Curator approves at most 60 exact language-balanced search terms or a finite provenance-backed seed list before executing. Terms are not invented here and this unresolved input must be supplied before the pilot starts. At most one request/second and at most ten known IDs/batch, only if current documented limits permit; smaller service limits take precedence. At most 2,000,000 received and 4,000,000 decoded bytes per API response, 30-second absolute deadline, 30-minute pilot wall deadline, one attempt per logical request. Stop on 429, 5xx, timeout, schema/permission ambiguity or exhausted limits; no automatic retry or REST fallback. Type traversal uses visited IDs, depth at most 20 and the 800-node global cap; incomplete frontiers quarantine the affected candidate. Direct organization qualification is the initial rule; subclass broadening requires a separate explicit decision. Missing multilingual fields, truncated continuation or revision ambiguity cannot be treated as complete evidence.
5. **08B-4, local admission and audit.** Verify hashes, non-person evidence, receipts, schema and field completeness; compute aggregate yield, exposure overlap and duplicate candidates. Keep uncertain groups separate. Do not build final partitions or label unreviewed candidates. Produce the measured yield and any source/coverage shortfall. No model training, hosted demo or public real-data upload.
6. **08B-5, review pilot and next tranche decision.** Begin only with identified qualified human reviewers, explicit review capacity/cost approval and a final-label custody arrangement. Measure acceptance, uncertainty, script coverage, review time and disagreement; preserve at least the original 200-positive/200-negative review requirement and all-used-hard-negative adjudication. If the full 5,000+2,000 independent-family and fresh final-script gates remain unmet, propose a new specific tranche or additional permitted source for approval. Do not spend the unallocated 41 MB or mark Step 08 complete automatically.

The live acquisition window is at most 60 minutes; it excludes human review but includes metadata, parsing, supervision and API pilot time. Additionally cap normalized selections at 100,000,000 bytes within the 2 GiB total artifact ceiling, require a 25% OS free-memory reading before starting and stop below 20% or on a pressure warning. The OS reading is an operational guard, not a memory guarantee. Proposed artifact/RSS/free-space limits are enforcement requirements to implement and test, not current controls. No mixed raw source data may be saved to avoid a memory ceiling. Stop and propose a reviewed streaming/processing change instead.

## Proposed implementation files and tests — not created in 08A

The original Step 08 scope remains `src/watchlist/{corpus.py,corpus_schema.sql,label_review.py}`, `src/watchlist/ingest/link_records.py`, `tests/test_corpus.py`, `tests/test_record_links.py`, `tests/test_label_review.py`, a new private release directory and updated data/permissions cards. Future functions and schema invariants are described in the corpus design; no SQL migration or corpus command was implemented now.

The acquisition package additionally needs a narrowly reviewed full-profile path and an API-specific adapter, with rationale and approval: proposed `src/watchlist/ingest/full_acquire.py`, `wikidata_api.py`, `resource_guard.py`; corresponding fictional tests; and `config/data-sources-step08.json`. Reuse existing transport/parser boundaries where compatible without weakening the frozen Step 07 profile. An approved implementation may choose fewer files if separation stays clear, but must not silently add unrelated libraries or change old fingerprinted contracts.

Required fictional acceptance cases include mixed person/organization responses, unknown/cyclic/truncated type graphs, wrong-rank type claims, aliases in multiple scripts, missing continuation and languages, HTTP/rate-limit/error/oversized/interrupted responses, redirects outside the reviewed exact routes, cumulative retry/decompression/resource limits, no-overwrite paths, provenance mismatch, uncertain duplicate chains, parent/subsidiary distinction, cross-source alias withholding, false “absent” targets with equivalent index copies, training-mining contamination and final-label export denial. Use a separate final custodian fixture rather than real final labels in tests.

Future commands such as `ingest.acquire fetch --profile full`, `corpus build`, `label_review export/validate` and `corpus audit` are **proposed interfaces from the completion plan**, not currently working commands or actions executed in 08A. Implementation must prove those contracts with offline tests before an approved live run.

## Decisions needed before execution

Approval must cover the first-tranche byte/request/time/type/field/retention policy; official metadata review and any newly pinned API route; full-profile/API/resource-guard implementation scope; local disk/RSS bounds; a finite curated Wikidata seed/search specification if that optional pilot branch is activated; and qualified reviewer capacity/cost plus final custody. Network acquisition, paid resources, keys, source substitutions and expanded quantities are not authorized by Step 08A. A partial approval activates only its named branches.

Recommended next action: approve only 08B-0 offline implementation and 08B-1 official metadata/source preflight: at most 5,000,000 received body bytes, 16 HTTP transactions including redirects, 512,000 bytes per response, 30 seconds per request, no automatic retries, and at most 60 minutes total. This partial approval would activate only the 5 MB metadata bucket, not the other 54 MB of the proposed first tranche. Require a concrete execution-policy/seed/reviewer/custody readiness review and separate approval before live dataset branches 08B-2/3 or human review 08B-5. The API pilot can remain unactivated if its seed or contract is not ready, without being called successful or used to claim full Step 08 completion. Any changed source/type rule or larger budget returns for explicit approval. Direct UN remains outside all branches pending legal permission clarification.

## Beginner 5W1H

**What:** a design for a larger reviewed name corpus and a bounded first acquisition package. **Why:** many names and passing software tests do not by themselves produce reliable ML labels or independent evaluation. **When:** after Step 07 closure and before new data, human labels, training or final-test exposure. **Where:** local private evidence and planned immutable releases; real names stay out of public demos. **Who:** publishers grant reuse rights; the project owner approves resources; qualified people review identity/name relationships; an independent custodian protects final labels. **How:** collect within approved limits, preserve provenance, quarantine uncertainty, review families and aliases, freeze releases, then allocate whole families without leakage in Step 09.
