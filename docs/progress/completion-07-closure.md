# Completion Step 07 — closure decision

Date: 2026-10-25, Asia/Kolkata. **Decision: APPROVAL REQUIRED. Step 07 is not marked complete. Step 08 has not started.**

The engineering, permission investigation and measured feasibility work are complete for the evidence available. The unchanged completion plan names five sources and explicitly requires either permitted acquisition or an approved scope revision for a source that cannot be used. Direct UN and Wikidata still lack successful permitted acquisitions. Recording those failures honestly does not turn them into successful deliverables.

## What this continuation did

The user authorized a focused Step 07 continuation, including current official UN permission/access review and one justified bounded Wikidata query. The five workers divided permission review, query review, feasibility/workload analysis, acceptance audit and budget/retention reconciliation. Existing successful acquisitions, models, databases and CI were reused rather than repeated. No scope revision has been applied and no publisher message was sent.

1. Reviewed Step 07/08 in the completion plan, the source registry, corpus requirements, existing tests, acquisition receipts, permissions and progress report.
2. Captured the official UN rights guidance and followed one reviewed official information redirect, stopping at its access-verification challenge.
3. Removed global sorting from the Wikidata query, reduced its candidate sample to 20, retained the organization/human/field constraints, ran local checks and made exactly one new acquisition attempt.
4. Completed the existing 600-group feasibility and workload analysis without creating labels, merging identities or acquiring a larger corpus.
5. Audited acceptance criteria and prepared the explicit scope decision below.

## Direct UN: the precise missing approval

The official [UN Rights & Permissions page](https://shop.un.org/rights-permissions) returned HTTP 200. Under **Databases**, it states:

> Permission is required to reuse content from any and all United Nations’ online platforms and databases (namely, bibliographic, legal and statistical databases).

The previously captured general terms also reserve compilation and derivative rights. The credited publication-excerpt exception was reviewed; it does not establish permission for the proposed compiled and transformed database. No applicable list-specific override or written grant was established. This is a conservative project permission decision, not a claim that no grant could exist elsewhere.

The missing grant must explicitly cover retaining up to 200 non-person groups with IDs, original names/aliases, type evidence and provenance; compiling them locally; normalizing and indexing names; and evaluating possible record matches for noncommercial research. Attribution, change notices, retention and other conditions must be known. Public redistribution, training, model release and operational screening remain outside that request. Your authorization to investigate does not replace the publisher's grant.

The official sanctions-information URL redirected to `main.un.org`, which returned HTTP 202 with an access-verification challenge. The review stopped without bypassing it. No currently working primary XML endpoint was established. The configured XML candidate's earlier HEAD 404 remains historical evidence; it does not prove every UN endpoint is unavailable. A working URL would still not resolve the separate rights question.

Practical route if this source stays mandatory: provide an existing applicable grant, or separately authorize a narrow inquiry through the official rights route; obtain and review the publisher's answer and conditions; establish an official endpoint; then perform an approved bounded acquisition. The existing inquiry draft remains unsent. The separately permitted OpenSanctions UN distribution is not a completed direct-UN acquisition.

Evidence: [UN re-review](../../data/eval-comparisons/completion-07/closure-review/un-permission-review/report.md), [HTTP receipts](../../data/eval-comparisons/completion-07/closure-review/un-permission-review/http-receipts.json). Three serial requests read 39,923 bytes. There was no UN dataset GET or new XML HEAD.

## Wikidata: justified attempt and observed result

Earlier attempts 01/02 recorded generic transport failure/timeout; attempt 03 recorded an HTTP error without a status; attempts 04/05 explicitly recorded HTTP 504. No missing status was retroactively inferred. The previous query's global sort and 200-candidate expansion were avoidable work, but the receipts do not identify which internal server operation timed out.

The revised query:

- Selects at most 20 direct `P31 Q43229` organization candidates, without global sorting or DISTINCT.
- Excludes any candidate with a `P31` type linked through zero or more `P279` steps to human `Q5`. This preserves direct-human and human-subclass exclusion.
- Does not refill excluded candidates, broaden types, filter languages or impose an outer row limit on names.
- Returns all label/alias rows and language tags for surviving candidates using the unchanged parser projection.
- Uses no vendor optimizer hint and makes no claim about physical server join order.

This is a service-order feasibility sample, not a representative or stable live sampling procedure. Removing sort work and reducing the candidate count justify a bounded attempt; they do not guarantee success. The exact query remains pinned by the registry, so the change does not authorize arbitrary SPARQL.

**Attempt 06 returned HTTP 504**, read zero response-body bytes and retained no selection. It used one attempt, a 90-second request limit, a 120-second source deadline and the unchanged remaining combined byte allowance. No retry followed. Zero bytes read means the error body was not consumed; it does not mean the request generated zero network traffic.

Evidence: [query](../../data/eval-comparisons/completion-07/closure-review/wikidata-query-06.sparql), [actual command and remaining limits](../../data/eval-comparisons/completion-07/acquisition-wikidata-06-command.json), [receipt](../../data/eval-comparisons/completion-07/acquisition-wikidata-06/wikidata_orgs.receipt.json). A service-side timeout cannot be repaired or diagnosed conclusively from these client receipts. A future request needs a new evidence-based plan; unused byte allowance alone is not a reason to repeat this query.

## Measured feasibility using the existing 600 groups

A **source-local group** is one provider's record and its names. It is not yet an independently verified real-world identity. **Alias evidence** preserves a name together with its source field and qualifiers, so equal text can occur more than once without being duplicate evidence.

| Source | Complete downloaded body | Eligible records before retention cap | Retained groups | Name/alias evidence | Unique strings within source |
| --- | ---: | ---: | ---: | ---: | ---: |
| OpenSanctions UN | 3,026,789 bytes | 269 | 200 | 696 | 693 |
| OFAC | 2,582,121 bytes, compressed | 11,610 | 200 | 724 | 720 |
| EU | 25,899,600 bytes | 1,779 | 200 | 1,873 | 1,845 |
| Direct UN | No new acquisition | Not measured | 0 | 0 | 0 |
| Wikidata | No successful response | Not measured | 0 | 0 | 0 |

Combined retained evidence: **600 organizations, zero vessels, 3,293 name-evidence entries and 3,072 globally unique strings**. Names shared between sources explain why source-level unique counts do not add to the global count. All 600 groups contain Latin evidence; 35 contain Arabic, 96 Cyrillic and four Han. Script is a writing-system observation, not a validated language tag or translation relationship. Language tags are supplied on 1,469 entries and missing on 1,824; 65 entries have UNKNOWN script evidence.

| Script pair | OpenSanctions candidates | OFAC candidates | EU candidates | Total presence candidates | Strict single-script pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Latin–Arabic | 29 | 0 | 6 | 35 | 35 |
| Latin–Cyrillic | 0 | 0 | 96 | 96 | 88 |
| Latin–Han | 3 | 0 | 1 | 4 | 4 |

The same group may support several pairs or directions; these counts are not independent reviewed positives. The eight mixed-script Cyrillic cases need review, not automatic rejection. OFAC contributes 49 explicitly weak name entries; EU's non-main-name flag is not treated as a weak-alias label.

Exact original-name equality nominates **69 candidate group pairs** involving 138 source-local groups: four within a source and 65 across sources (51 EU/OpenSanctions and 14 OFAC/OpenSanctions). These are a triage queue, not confirmed duplicates. No merge, positive label or negative label was made. Different spellings may reveal additional candidate links later.

The [complete measured feasibility/workload report](../../data/eval-comparisons/completion-07/closure-review/feasibility-workload.md) includes source input counts, all script/language counts, alias repetition arithmetic, evidence hashes and limits. Its 600-group measurements remain unchanged by the unsuccessful sixth Wikidata attempt.

## Estimated Step 08 acquisition and human review — planning only

The existing plan proposes approximately 5,000 usable reference groups, 2,000 independently established absent-query groups and at least 100 independent final positive groups for each claimed script direction. These are Step 08 requirements, not hidden Step 07 minimums.

- Even if every current group is usable and independent, at least **4,400 additional reference groups** are needed. With that optimistic current base, future candidate demand would be 4,400 at 100% usable yield, 5,500 at 80%, or 8,800 at 50%. The latter percentages are illustrative assumptions, not measured yields.
- **All 2,000 absent-query groups remain unestablished.** Absence must be defined against the fixed reference index and supported by review. Neither a Wikidata record nor absence from a small sample proves it.
- The optimistic candidate gaps against 100 are **65 Arabic, four Cyrillic and 96 Han** groups. All 100 independently reviewed final groups per direction remain unestablished; deduplication, review and partition allocation can increase acquisition needs.
- The three complete source bodies already observed total **31,508,510 bytes** and contained 13,658 source-local parser-eligible records before capping. Those counts suggest a pool to assess, but cannot establish independent yield, unretained script coverage or future response sizes. Mixed raw bodies were not saved, so larger retention would require an approved fresh acquisition. The plan's 100 MB Step 08 proposal is not approved by this report and cannot yet be guaranteed sufficient, especially for the absent-query population.
- Human work includes **600 group screens**, inspection of up to **3,293 name-evidence entries**, triage of **69 observed candidate links**, and at least **200 proposed positive plus 200 negative candidate reviews**, followed by disagreement resolution and independent checks where possible. These overlapping work units must not be summed as if they were identical tasks.
- Illustrative staffing ranges: 600 group screens at 2–5 minutes each take 20–50 hours; 69 link reviews at 5–15 minutes take 5.75–17.25 hours; 400 label reviews at 3–10 minutes take 20–66.67 hours per review pass. These are explicit assumptions, not measured speeds or a total project estimate. A later approved pilot must measure acceptance, review speed and disagreement before staffing and download quantities are committed.

Insufficient reviewed Han coverage, uncertain duplicate independence and the absent-query population are important Step 08 design risks. They are not repaired by dropping a source requirement or by calling the current sample representative.

## Acceptance decision, criterion by criterion

| Step 07 requirement | Evidence/status |
| --- | --- |
| Review current primary terms separately for five named sources | **Satisfied as an investigation.** Four have narrow local-use permission decisions; direct UN remains blocked with exact missing permission documented. No direct-UN use is authorized. |
| Freeze requirements and a bounded source registry | **Satisfied.** Five sources remain listed; types/fields, exact URLs, redirect rules and numeric caps remain controlled. Query sampling narrowed; numeric budgets did not increase. |
| Source adapters, receipts and legacy-contract preservation | **Satisfied for implementation.** Five adapters and fictional fixtures; current focused tests include the legacy contract. A parser is not evidence of real acquisition. |
| Real permitted bounded acquisitions, with hashes and bytes | **Partially satisfied.** Three verified retained selections; no successful direct UN/Wikidata selection. Under the unchanged plan these two are mandatory unresolved deliverables. |
| Malformed/redirect/interrupted/oversized/overwrite controls | **Satisfied locally.** All 520 acquisition/parser tests passed after the query change, with scoped lint/format and offline preflight. Existing full-suite evidence remains a prior snapshot, not a claim it was rerun. |
| Measured scripts, aliases, duplicate candidates and workload | **Satisfied for feasibility.** Verified 600-group aggregates and explicitly qualified workload estimates; no invented labels or extrapolated representative yield. |
| No unapproved access, overwrites or expanded budgets | **Satisfied for this continuation.** Three bounded UN metadata requests, one Wikidata attempt, no UN dataset GET, no new retained real data, old selections/evidence preserved. See final accounting. |
| Prevented named source resolved by access or approved revision | **Not satisfied.** Neither required acquisition succeeded and the proposed revision below has not been approved. This determines the closure decision. |

Wikidata's “supplementary” role is not an optional-source exemption. Conversely, 200 groups is a cap, not a minimum; there is no Step 07 minimum vessel count, trained model, reviewed-label target or 5,000-record release. The [independent acceptance audit](../../data/eval-comparisons/completion-07/closure-review/acceptance-audit.md) records the original criteria and evidence before this final request outcome; this closure report supplies the current result.

## Exact decision requested — no revision applied yet

**Recommended: explicitly approve this source-scope revision:**

> For Step 07, require successful retained feasibility acquisitions from OpenSanctions UN, OFAC and EU. Remove successful direct-UN and Wikidata acquisition from the mandatory Step 07 acceptance requirements, and record those two named candidates as investigated but not acquired: direct UN lacks an applicable reuse grant and verified current endpoint; Wikidata repeatedly returned HTTP 504, including the smaller bounded query. Preserve their blocked/failed records, code, receipts and restrictions; do not mark them acquired, treat OpenSanctions as the direct UN source, or enable them implicitly. Any future use requires its own reviewed access/permission and acquisition approval. This revision does not waive Step 08 population, independent-identity, multilingual-coverage, absent-query or label-review requirements, expand any budget, or authorize Step 08.

This is an explicit narrowing of the feasibility source requirement, not evidence that five-source acquisition succeeded. If approved, the plan, registry/requirements scope notes and closure status must be updated consistently, with the approval recorded. The current five-source requirements remain in force until then.

**Alternative: retain the original five-source requirement.** Step 07 remains BLOCKED. Resolve UN permission through an existing applicable grant or an authorized inquiry and answer; establish official access. For Wikidata, obtain evidence of service recovery or a separately reviewed access/query approach and approve a concrete bounded attempt. No repeated request, substitute endpoint, larger budget or publisher contact is implied by choosing to retain the requirement.

Recommendation rationale: three permitted sources already support the measured sanctions-domain feasibility exercise, while the two unresolved services currently provide no usable retained data. A transparent, expressly approved scope change is preferable to misrepresenting unsuccessful acquisitions. If five-source coverage is itself essential to your project, retain the stricter requirement and follow its resolution path instead.

## Files, commands, limits and beginner recap

- `src/watchlist/ingest/source_registry.py`: only `WIKIDATA_QUERY` changed. The inner selection caps service-order candidates at 20; the middle human-type exclusion preserves the non-person rule; the outer label/alias union stays complete. No transport/parser logic changed.
- `config/data-sources.json`: pins that exact query and documents its sampling limits; UN stays blocked with the newly captured official permission evidence. Other source policies and numeric limits remain unchanged.
- `config/corpus-requirements.json`: clarifies the one-attempt, 20-candidate investigation inside the unchanged 200-group ceiling; all numeric caps and all five named sources remain unchanged.
- `docs/source-permissions.md`, `docs/access-and-resource-ledger.md`, `docs/progress/completion-07.md` and this closure report: record current findings and the pending decision. Historical acquisition, coverage and CI receipts are preserved.
- New private evidence is under `data/eval-comparisons/completion-07/closure-review/` plus `acquisition-wikidata-06*`. It contains aggregate analysis, request/validation receipts and public rights pages; no new real-data selection was saved.

Actual command families were focused `make source-tests lint`, offline acquisition `preflight`, the existing serialized `run_bounded_source.py wikidata_orgs acquisition-wikidata-06`, and the real source scanner. Exact arguments, exits and logs are retained in [query validation](../../data/eval-comparisons/completion-07/closure-review/query06-local-validation.json) and the [closure validation receipt](../../data/eval-comparisons/completion-07/closure-review/closure-validation.json). Final policy checks passed all **520 tests**, scoped lint/format and offline preflight. The [final source scan](../../data/eval-comparisons/completion-07/closure-review/secret-scan-final.json) covers **157 files, 71 individually reviewed non-secret findings and zero unresolved findings**. No detector or test was disabled. A passed preflight means the local policy/evidence validates; it does not mean the endpoint is reachable. The live example outcome is `status=failed`, `http_status=504`, `bytes_received=0`, `records_path=null`; the single attempt took approximately 66.16 seconds.

Dataset reads remain **40,006,347 / 50,000,000 bytes**, leaving **9,993,653**. Terms/metadata reads are **3,290,827 / 5,000,000**, leaving **1,709,173**. Failed and superseded downloads remain charged. These counters measure bytes actually read from response bodies, not HTTP/TLS overhead. The [final budget/retention receipt](../../data/eval-comparisons/completion-07/closure-review/final-budget-and-retention.json) reconciles the new and prior evidence. No additional CI run, push, dependency install or model test was needed for this query/policy/documentation continuation.

**What:** investigated the two missing source outcomes and completed measured feasibility. **Why:** later matching experiments need permitted, traceable data and honest coverage. **When:** before Step 07 closure and any Step 08 approval. **Where:** local private evidence, with bounded official read-only requests. **Who:** publishers control reuse permission; you control project scope and resources; future reviewers adjudicate identity and labels. **How:** reuse receipts, enforce limits, test the narrowed query locally, attempt it once, measure retained data and record failure without hiding it.

**Next action:** approve the quoted scope revision, or retain the five-source requirement and choose its permission/access resolution path. Step 08 remains unopened in either case until its scope, corpus strategy, review resources and acquisition budget are approved separately.
