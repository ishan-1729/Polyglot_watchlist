# Step 08A — offline source feasibility and Wikidata access options

Date: 2026-10-25, Asia/Kolkata. Status: **planning only; no new acquisition or adapter authorized by this document**. The user approved Step 08A offline planning after the [formal Step 07 closure](../progress/completion-07-approved.md). The [central Step 08A plan](../step-08a-plan.md) owns the final proposed quantities and approval gates. This document supplies the source reasoning; it does not amend executable configuration.

The provisional Wikidata candidate is the **Action API**, using `wbgetentities` to retrieve already identified items and a separately reviewed search process to nominate candidate IDs. This preference follows the expected shape of the work: bounded item batches with original multilingual names and classification evidence. It is not a finding that the API is currently available, complete, permitted at a particular rate, or capable of delivering the full corpus. **Wikibase REST is a comparison candidate, not an automatic fallback.**

A **QID** is Wikidata's identifier for an item, written as `Q` followed by digits. We would use it before retaining names to keep source records and redirects traceable. Wikidata supplies the identifier; the project must still check the item's type and evidence. A QID alone neither identifies a real-world entity conclusively nor supplies a match label.

## Evidence available offline

The distinction below is deliberate: a saved official page can support a historical source fact; architectural knowledge can motivate a proposal but cannot establish today's endpoint contract.

| Locally established fact | Saved evidence | Consequence and limit |
| --- | --- | --- |
| Wikidata's captured copyright page says structured data in the main, Property, Lexeme and EntitySchema namespaces is available under CC0; other namespace text has different terms. | [Saved copyright page](../../data/eval-comparisons/completion-07/permissions/wikidata-copyright.html), recorded in [source permissions](../source-permissions.md). | Supports the recorded structured-data reuse assessment. Does not verify a current API, unrestricted service use, rights in unrelated content, or project approval to train or publish. |
| The captured Wikimedia User-Agent policy asks scripts to identify themselves and provide contact information. | [Saved User-Agent policy](../../data/eval-comparisons/completion-07/permissions/wikimedia-user-agent.html), particularly its informative-header guidance. | Any future request needs a reviewed informative User-Agent. No personal contact, account or API key is introduced by this plan. |
| The captured query-service manual documents SPARQL and a MediaWiki API service callable from SPARQL. It describes public WDQS query limits. | [Saved WDQS manual](../../data/eval-comparisons/completion-07/permissions/wikidata-query-manual.html), “MediaWiki API” and “Query limits”. | These are not documentation of standalone `wbgetentities`, `wbsearchentities` or Wikibase REST. WDQS timeout/concurrency values must not be copied into an Action API rate claim. |
| The six Step 07 Wikidata invocations retained no selection; attempts 04–06 explicitly recorded HTTP 504 with zero received body bytes. Attempt 03 did not record its HTTP status. | [Approved closure](../progress/completion-07-approved.md) and [attempt 06 receipt](../../data/eval-comparisons/completion-07/acquisition-wikidata-06/wikidata_orgs.receipt.json). | Establishes what failed. It does not diagnose the server's internal plan or establish failure/success of a different API. |
| The three successful retained selections contain 600 source-local groups and 3,293 name-evidence entries. They are not 600 independently adjudicated identities. | [Verified closure evidence](../../data/eval-comparisons/completion-07/approved-closure/evidence-verification.json) and [aggregate workload](../../data/eval-comparisons/completion-07/closure-review/feasibility-workload.md). | A useful existing sanctions-domain candidate pool, with duplicate and label review still required. |
| A new read-only scan verified the three selection hashes and found zero values that were exactly a bare QID or a Wikidata `/entity/Q…` or `/wiki/Q…` URI anywhere in those 600 JSON records. | Local JSONL selections named by the successful OpenSanctions-03, OFAC-01 and EU-02 receipts; command and method below. | No explicit Wikidata seed inventory is established by those patterns. This is not proof that another kind of cross-reference could never support a reviewed link. No QID was inferred from a name. |
| No saved Action API module documentation or Wikibase REST contract was found in the inspected `docs/` and Step 07 permission captures. | Offline filename/content search; the older [Phase 05 plan](../phase-05-plan.md) describes a proposed API pilot, not a completed capability check. | Module parameters, limits, response shapes, redirects, revisions and language completeness remain Step 08B questions. An HTML navigation link to `/w/rest.php/v1/search` is not evidence for the Wikibase REST item API. |

These findings use local captures only. No official page was refreshed for Step 08A, no new endpoint was probed, and no service availability claim follows from this review.

## Candidate comparison and official verification gates

The following endpoint families and behaviors are **architectural candidates requiring official verification in Step 08B**. They are not an enabled allowlist or executable request specification.

| Candidate | Expected role, subject to verification | Main unresolved questions | Provisional decision |
| --- | --- | --- | --- |
| Wikidata Action API at the candidate route `https://www.wikidata.org/w/api.php`, module `wbgetentities` | Fetch a small known-QID batch; request labels, aliases, classification claims and item revision information while avoiding unrelated fields when the API permits. | Supported property selection, all-language behavior, batch ceiling, response completeness, errors, missing IDs, redirects, revision semantics and current access rules. Claims may be broader than P31/P279 and need transient filtering. | First candidate for a small pilot if all mandatory gates pass. It does not discover the required QIDs by itself. |
| Action API `wbsearchentities` | Nominate item IDs from predeclared search strings and languages. | Search language/fallback behavior, continuation, result ceilings, ranking, response fields, current limits and any restrictions. An `item` search type distinguishes item records; it does **not** mean organization or non-person. | Candidate discovery only. Returned names/descriptions are not the complete multilingual record or a reviewed label. |
| Action API `action=query` search, potentially with Wikibase-specific indexed filters | Possible alternate way to discover class-constrained IDs. | Whether the current Wikidata deployment supports the intended indexed syntax and how complete/fresh its results are. No ability to filter organizations is assumed. | Optional documentation comparison only. Do not enable or fall back to it without an exact reviewed query and approved scope. |
| Wikibase REST, candidate family `https://www.wikidata.org/w/rest.php/wikibase/v1/…` | Potential item/statement retrieval with an explicit HTTP resource contract. | Current route/version, available collection/search features, field projection, all-language labels/aliases, statement ranks, missing/redirect semantics, revision/ETag meaning, request multiplication and access limits. | Keep as a separately reviewed alternative. A nicer resource shape would not solve QID discovery or type-graph expansion. |

The proposed first official review should capture the current Wikidata data-access guidance, Wikibase Action API module help for `wbgetentities` and `wbsearchentities`, the Wikibase REST documentation, the RDF statement-rank/direct-property semantics, current usage/rate guidance, copyright terms and User-Agent rules. Official module metadata can be checked only within the approved metadata stage. Confirm final canonical documentation URLs before requesting them; a plausible route name is not proof of current support.

Required evidence before selecting a data route:

1. Dated official terms and module/route documentation, with final URLs, status, received bytes and complete-body hashes. A challenge page, error page or incomplete capture is not a verified contract.
2. A precise parameter and field allowlist, including all-language behavior and complete type-claim retrieval. Do not rely on defaults that silently return one language or only a display label.
3. Current anonymous/public access, rate, batch, continuation, timeout and load-shedding rules. The plan does not assume anonymous access still works, that an account is necessary, or that any proposed rate is provider-approved. If authentication, payment or broader access is required, stop and return the requirement for a separate decision.
4. Confirmed item ID, missing-item, redirect/merge and revision semantics. Confirm whether a revision can be requested or only observed; do not advertise historic replay without support.
5. An offline fictional fixture contract and cap-enforcement checks before the first data request. No real-person response should become a test fixture.

## QID discovery is a separate feasibility problem

Known-ID retrieval can reduce server-side query work, but it moves selection and classification work to the client. It does not provide a complete organization inventory. The current selections supply no explicit QID seed inventory under the scan described above.

Proposed candidate path, conditional on Step 08B approval:

1. An owner or curator reviews the **exact seed plan before the pilot**. It may contain provenance-backed organization QIDs or a fixed set of organization search strings, languages, and page limits. No new seed IDs or search terms are invented in Step 08A. Do not send private names or unrelated personal data.
2. Use at most 60 predeclared, language-balanced search strings under the central plan. Record the language allocation and selection rationale before retrieval. English, Arabic, Russian and Chinese would be possible language cells, but the final choices and exact strings require review; one language does not represent every language written in its script. Search expansion, continuation and every result page consume the same request/byte budgets.
3. Examine at most 500 unique candidate QIDs, including subsequently rejected candidates; retain at most 200 accepted organizations. A result that is a person, vessel, aircraft, ambiguous item or missing item does not free its examined-QID slot. Alias strings and repeated search hits are not additional entities.
4. Obtain the complete required item fields and classification graph before considering retention. Prefer reviewed known-ID batches of at most 10, subject to any tighter official limit. Search result rank, a returned description, or a familiar name is not non-person evidence.
5. Freeze a private, permitted selection manifest for accepted items with seed provenance, candidate-selection version and coverage/exclusion counts. Review duplicate/redirect relationships before any later split. The candidate pool remains supplemental and unlabelled.

Search results are ranked and depend on term choice, language, index state and popular/notable coverage. Balanced search-term counts do not make a representative sample. Organization-category or regional stratification would require separately approved supporting fields and verified taxonomy; it is not inferred from a name or language tag. Record missing language/script coverage and the actual acceptance yield.

Searching only the retained sanctions names could help propose cross-source links, but would deliberately favor overlap and well-described entities. It cannot supply an independent absent-query population. General organization search also cannot establish absence from sanctions lists. Do not select candidates by a matcher's score, by easy bilingual names, or by later final-test performance. Record whether pilot material is exposed during design and keep the later final population independently governed.

If the reviewed seeds, current search contract or eligible yield cannot produce enough candidates, report that bottleneck. Do not resume WDQS, scrape individuals, obtain a whole dump, substitute another publisher or broaden the type rule automatically.

## Non-person classification and complete multilingual fields

The Step 07 Wikidata query required **direct `P31 Q43229`** (an explicit instance-of organization statement), and excluded any item with a `P31/P279* Q5` path to human. The provisional Action API pilot preserves that scope. Accepting an item merely because its class is a subclass of organization would be a **new eligibility rule needing separate explicit approval**; this document does not introduce it. A sparse direct-organization yield is a measured limitation, not a reason to relax the rule.

API item statements and the SPARQL direct-property view may differ. Before implementing equivalence, verify Wikidata's documented statement-rank rules: preferred statements can take precedence over normal statements, and deprecated statements are treated differently. “Take every P31 value” or “drop deprecated values” alone must not be assumed to reproduce the old query. Unknown-value, no-value, missing, malformed and contradictory classification evidence need explicit conservative handling and fictional tests.

The proposed classification procedure is:

1. Verify the requested/canonical item and complete relevant statement collections using the reviewed API contract. Require direct organization evidence under the agreed rank semantics.
2. Inspect every relevant P31 type. Exclude direct human classification immediately. For other types, traverse the relevant P279 parent-class statements until all reachable branches are resolved or a bound is hit. This is a **type-graph closure**: following every required parent-class link so an unfinished branch cannot be mistaken for evidence of no human ancestry.
3. Any path reaching Q5 excludes the candidate, including a zero-edge class path when P31 itself is Q5. Multiple classifications require checking all relevant types, not only the organization-valued statement.
4. Share a revision-aware class-evidence cache within the pilot; visit at most 800 distinct type-graph nodes and at most 20 P279 edges along a path. Handle cycles with a visited set and verify every required outgoing branch. A cycle alone is not an exclusion, but incomplete outgoing evidence is unresolved.
5. Quarantine/exclude the candidate from the accepted selection when any relevant frontier remains unexpanded, a type request is missing or malformed, ranks cannot be interpreted, or a byte/request/time/depth/node bound is reached. A bounded traversal with unfinished branches cannot establish the exclusion test. Record aggregate reasons without retaining personal records.

“Organization with no known human path in the completely retrieved relevant graph” is a source classification result, not proof of real-world identity or that the knowledge graph is correct or complete. Review remains necessary.

For accepted groups, retrieve **all available labels and aliases across languages** under a documented complete-field contract. Preserve the exact original string, language tag, label-versus-alias distinction, source field path and item revision evidence. Do not normalize the original field in place, convert translation into transliteration, infer missing language tags, or treat every alias as a positive match. Missing aliases can be a valid empty collection; a missing/partial required field must be distinguished from an explicitly empty one. Require at least one complete original label for compatibility with the current retained-group contract.

If an API returns paginated or filtered fields, collect and validate the whole approved group within the bounds before retention. Do not silently truncate aliases or languages to fit a byte cap or treat search display text as the item's full name set. A group exceeding a safety bound is unresolved for this pilot; counts must disclose the exclusion bias.

## Missing IDs, redirects, versions and minimal provenance

| Case | Proposed handling before corpus eligibility |
| --- | --- |
| Missing, deleted or inaccessible item | Explicit missing/unresolved outcome. No empty positive record, inferred identity, or absence label. The attempt consumes its counters. |
| Returned ID differs from the requested ID | Accept a mapping only through the API's documented redirect/merge semantics. Bound chains, reject loops and unexpected targets, then recheck the canonical item and complete classification. Redirects may collapse candidates; do not count them twice. |
| Cross-source identity candidate | Keep source-qualified IDs and a proposed relation. A name match, common parent or subsidiary relationship does not authorize a merge. |
| Revision information supplied | Retain item revision ID, source-provided modified time and documented HTTP validators where present. Record each classification node's own revision evidence and acquisition time. Do not call an ETag a revision ID without the official definition. |
| Revision or coherent snapshot unavailable | Record the missing evidence and acquisition interval honestly. A collection fetched across many live requests is not an atomic historical snapshot. A frozen local projection can be reproducible even when the live endpoint cannot recreate its raw responses. |
| Complete versus interrupted response | Record a complete-body hash only on a complete bounded transfer; label partial-body hashes separately. Count actually read bytes from failed attempts too. Invalid or partial JSON yields no accepted partial entity. |

Retain only accepted non-person IDs, original names/aliases and their language/field distinctions, minimal P31/P279 classification evidence including relevant ranks/versions, the accepted redirect map, source/terms references, parser/selection version, response/selection hashes and aggregate exclusions. Type-graph nodes support classification; they are not additional name-corpus groups.

The API may return people or unnecessary claims, descriptions, sitelinks, references and other fields **transiently** even when the request is narrow. Apply the approved [retention principle](../data-retention.md): bounded in-memory processing, filter before serialization, and no mixed raw body, biography, address, contact field, photograph, unrelated statement or debug dump retained. No source strings go to external model prompts or public demos.

The future receipt design must also prevent discovery and error logs from becoming a person-ID/name inventory. Use aggregate rejection reasons, a route/parameter template and a batch receipt identifier/hash where retaining a full request would preserve rejected-person identifiers or unwanted search text. Preserve requested-to-canonical QID provenance for accepted organizations. This proposed receipt rule needs explicit review and tests alongside the exact new endpoint policy; it is not a silent change to the current acquisition contract. Do not promise secure memory erasure or exact reconstruction of deliberately unretained rejected records.

## Proposed Step 08B preflight and pilot bounds

These are **new proposals for future approval**, not execution authority. Step 07's unused allowance is not carried forward. The central plan proposes a first active tranche of **59,000,000 received response-body bytes** within the original **100,000,000-byte planning ceiling**:

| Proposed allocation | Received response-body ceiling |
| --- | ---: |
| Official source terms, format and API metadata | 5,000,000 |
| OpenSanctions UN | 5,000,000 |
| OFAC | 4,000,000 |
| EU | 30,000,000 |
| Wikidata pilot | 15,000,000 |
| **First tranche total** | **59,000,000** |
| Unallocated part of the 100 MB planning ceiling | **41,000,000 — not automatic retry or expansion capacity** |

The initial tranche concerns an approved investigation/pilot, not guaranteed completion of Step 08. Bytes include actual read response bodies from successful, failed, redirected and mixed-field responses wherever those bodies are read. They do not represent wire-level HTTP/TLS/DNS overhead. Decode/structural bounds are additional controls. All intersections apply; satisfying one ceiling does not waive another.

**Stage B1 — official documentation and access preflight.** At most 16 serial HTTP transactions, including redirects, at most 512,000 received body bytes each, and at most 5,000,000 combined metadata bytes across the sources. Capture only official source/API documentation and permitted metadata. No entity-data request, account setup, publisher message, paid resource or new model download. If a required capture is incomplete, challenged, unavailable or inconsistent, stop and record the missing fact. The current official rules may tighten these project bounds or prevent the pilot.

**Gate before B2.** Present the exact supported endpoint/module, allowed parameters and redirects, current terms/access decision, complete multilingual/type contract, reviewed seed plan and retention/receipt design. Any new adapter or policy implementation belongs to separately approved Step 08B work and must pass fictional offline checks before data access. The current registry remains unchanged and Wikidata remains pending. A general approval to plan does not pass this gate.

**Stage B2 — small smoke sample.** Within the same Wikidata totals, first inspect at most 20 of the reviewed candidate QIDs. Validate actual schemas, multilingual completeness, missing/redirect handling, type-graph completion, byte counters and filtering. Save only approved selected projections and minimal receipts. Stop for the coordinator's stated acceptance check before proceeding to the remaining pilot; do not switch endpoints or relax fields when a check fails.

**Stage B3 — bounded pilot, only if specifically approved and B2 passes.** Apply these cumulative Wikidata limits across discovery, item, class and verification reads:

| Control | Proposed bound or behavior |
| --- | --- |
| Received API bodies, including failed attempts | 15,000,000 bytes total; 2,000,000 bytes per response |
| Decoded JSON | 4,000,000 bytes per response; also enforce finite parser structure limits in the reviewed implementation |
| Retained organization groups | At most 200; all must pass the unchanged direct-organization rule and complete human-path check |
| Candidate discovery | At most 60 predeclared language-balanced search strings; at most 500 examined candidate QIDs including rejected ones |
| Type graph | At most 800 distinct nodes; path depth at most 20 P279 edges; unresolved frontiers excluded |
| API requests | At most 250 data API HTTP transactions, including discovery, continuation, type lookups, redirects and failures; no hidden secondary requests |
| Pace and batching | One in-flight request; no more than one request start per second; at most 10 known IDs per batch and any tighter official bound |
| Deadlines | 30-second absolute request deadline; 30-minute pilot wall-clock deadline including pacing and checks |
| Attempts | One attempt per logical request; stop on HTTP 429, 5xx, timeout, access challenge, unexpected redirect, malformed response or exceeded bound; no automatic retry |
| Money, identity and external exposure | No paid resources, account/API-key use, publisher messaging, public hosting or uploading selections |

Exhausting any bound stops the relevant acquisition. An unresolved item is not accepted to improve the yield. Unused metadata or other-source allowance does not enlarge the Wikidata allocation. The 41 MB unallocated portion is available only for a later explicit reviewed allocation. A REST, SPARQL or alternate search route requires a separate route/permission decision; it is not failure recovery authorized by this table.

The other first-tranche sources need their own exact endpoint, current metadata/size, permission, parser and retention gates. The proposed allocations do not declare old routes current or authorize replay of unretained bodies. Direct UN remains outside acquisition: its applicable compilation/transformation grant and working permitted endpoint remain unresolved. An OpenSanctions UN distribution remains a different acquisition and cannot be counted as direct UN.

## What the pilot can contribute to the unchanged Step 08 targets

The [original Step 08 requirements](../project-completion-plan.md) remain approximately **5,000 usable reference groups**, **2,000 independent absent-query groups**, **at least 200 proposed positive and 200 negative candidate reviews**, and **at least 100 independent final positive groups per claimed Latin↔Arabic, Latin↔Cyrillic and Latin↔Han direction**. None is reduced by a source-access workaround.

| Population or work target | Realistic candidate path and unresolved work |
| --- | --- |
| Reference groups and fresh sanctions-domain cases | Review existing permitted selections and separately approve larger/fresh selections from the three successful publishers after current terms, sizes and measured yield are checked. The 600 source-local groups are not guaranteed independent or usable. Supplemental Wikidata groups cannot silently replace the sanctions-domain study. The population allocation within the 5,000 target must be explicit. |
| Supplemental multilingual learning material | A Wikidata pilot can measure discovery cost, type exclusions, names per group, complete script-pair availability and duplicate candidates. At most 200 retained groups cannot deliver a 5,000-group corpus. Later learning eligibility needs provenance, label review and its own approved purpose. |
| 2,000 independent absent-query groups | Define the fixed reference index and equivalent-record exclusion rules first. Obtain independently reviewed candidate groups and establish absence **relative to that fixed view**, with ambiguous links quarantined. Neither a Wikidata origin nor no hit in a sampled sanctions list is an absence label; no claim of global non-sanctioned status follows. Search cannot manufacture independent evidence. |
| 200 positive and 200 negative candidate reviews | Select and review distinct candidate sets across sources/scripts/types; do not call an alias, a search hit, a duplicate-name pair or a retrieved neighbor an adjudicated label. Record disagreements and exclusions, and adjudicate any hard negative actually used. This source plan performs zero label reviews. |
| 100 independent final positives per claimed direction | Existing aggregate presence candidates are 35 Latin–Arabic, 96 Latin–Cyrillic and 4 Latin–Han, before independent identity/label review. No final-positive gate is established by those counts. One group can support two directions; two directions or many alias pairs do not create two independent identities. Reviewers with the relevant language competence and separately governed final partitions remain necessary. |

More requests, more aliases or a broader search are not evidence that these targets will be met. Measure accepted independent groups, actual reviewed script pairs, duplicates, byte/request cost and reviewer yield before proposing expansion. Insufficient yield is unfinished corpus work requiring a concrete revision or more separately approved work, not a completed training prerequisite.

## Source rights, training rights and acceptance

The saved CC0 assessment supports reuse of the specified Wikidata structured data; it is not a current service-access guarantee or an approval to use other Wikimedia text, logos or third-party works. OpenSanctions' noncommercial terms, OFAC factual-data basis and the EU distribution's reuse conditions retain their source-specific scope and notice requirements. Direct UN remains blocked pending an applicable grant. Recheck current terms before new acquisitions.

Source permission, factual correctness, a usable label and project authorization are separate decisions. A source license can permit a class of reuse without proving identity, evaluation eligibility or leakage safety. This plan does not assert that CC0 inherently prohibits training; it records that later training, sharing a corpus, releasing a model and any operational use still need their own project approval and an assessment of the selected content and applicable rights. Do not use a successful API response as a substitute for those decisions.

Step 08A source-plan acceptance is an inspectable proposal with cited cached facts, explicitly unverified API claims, a bounded discovery/type/field design, current acquisition gates left closed and unchanged downstream targets. Step 08B pilot acceptance would require actual official preflight evidence, successful offline contract/cap tests and measured retained selection/provenance/exclusion results. No availability, yield, label quality or speed result is invented here.

**Offline checks actually performed for this plan:** read the local Project 1 reference, engineering/AI-agent guidance, Step 07 approved closure, completion plan, corpus requirements, retention/source-permission records, cached Wikidata documentation and the existing workload report. Used `rg` to find local API references; used standard-library Python to parse saved HTML/JSON, verify the three retained selection SHA-256 values and recursively count exact QID/Wikidata-URI values. All three selection hashes matched; each contained 200 groups; the exact-pattern QID scan found zero matches. The scan emitted counts/field names only, not names or IDs. No application test suite was rerun for this Markdown-only task, no dependency was added and no network request was made.

**5W1H recap:** What: choose a provisional way to investigate supplemental Wikidata names. Why: the SPARQL feasibility attempts produced no usable selection, and known-item retrieval may have a different bounded workload. When: official verification and any data pilot occur only after the next explicit approval. Where: approved official endpoints and private local selected evidence, with no public service. Who: the project owner approves resources/scope, publishers define access/rights, a curator reviews seeds, code enforces bounds and human reviewers establish labels. How: verify contracts, discover bounded QIDs, prove the required classification graph as far as the source supports, preserve complete multilingual names and provenance, measure yield and stop at unresolved gates.
