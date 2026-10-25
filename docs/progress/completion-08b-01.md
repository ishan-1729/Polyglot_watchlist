# Completion Step 08B-0/08B-1 — implementation and bounded metadata preflight

Date: 2026-10-25, Asia/Kolkata. **Approved package complete, with documented metadata limitations. Next acquisition requires approval. Full Step 08 remains incomplete.**

## Decision and scope

08B-0's offline preparation components and failure tests pass. 08B-1's authorized metadata investigation is complete: 16 transactions, 1,628,809 received response-body bytes, zero dataset bytes. Fourteen complete metadata responses were retained; two request outcomes were unsuccessful and remain in the receipts. This closes the bounded investigation, not every source's legal/API readiness. No real corpus release, human label, training run, partition, publication, commit or push was created.

The original [completion plan](../project-completion-plan.md), [08A plan](../step-08a-plan.md), its acceptance evidence, and [approved preflight](../step-08b-01-preflight.md) remain the requirements. Step 07 stays closed; its receipts and historical reports were not rewritten. All proposed 39 MB bulk and 15 MB Wikidata allocations remain inactive. The full corpus targets remain approximately 5,000 usable reference groups, 2,000 independent absent-query groups, at least 200 positive and 200 negative candidate reviews, adjudication of every used hard negative, and at least 100 independent final positives per claimed Latin↔Arabic/Cyrillic/Han direction.

“Offline” here means code, fixtures and existing local evidence were used without contacting a data service or downloading dependencies/models. It does not mean that the later explicitly approved metadata-only requests were forbidden. Those requests are separately accounted below.

## Files and functions

| File | Main entry points / explanation |
| --- | --- |
| `src/watchlist/corpus.py` | `prepare_source` (line 1377) validates legacy selections, receipts, provenance and explicit candidate-preparation purpose evidence. `prepare_fictional_full_source` (1403) admits the distinct fictional full-profile format without pretending it is live evidence. `build_candidate_release` (1910) validates the entire SQLite candidate in memory and publishes one new private file exclusively; existing destinations fail. `load_candidate_release` (1822) checks hashes, schema and invariants; `audit_candidate_release` (1933) reports candidate counts and unmet eligibility honestly. |
| `src/watchlist/corpus_schema.sql` | Separate SQLite application ID and strict source/snapshot/name/provenance/manifest tables. Source-qualified IDs distinguish records from identity claims. Original name text, languages, qualifiers, transform versions and source evidence remain attributable. This is candidate storage, not the old operational database. |
| `src/watchlist/ingest/link_records.py` | `nominate_links` (314) proposes links from names without declaring identity. `validate_link_decisions` (352) binds decisions to release/evidence/reviewer attestations. `build_record_groups` (571) separates reviewed equivalence from uncertain links; `build_leakage_families` (590) propagates dependence/exposure and quarantines conflicting components before any later split. |
| `src/watchlist/label_review.py` | `freeze_review_packet` (260), export/load (290/322), submission/adjudication validation (485/532), `PairContext` (604), `assess_pair_use` (654), and `review_summary` (706) prepare and validate fictional review workflows. Context is derived from a hash-verified grouping result. CLI supports fictional preparation/audit only; no real/final label export or persistent real adjudication store is enabled. |
| `src/watchlist/ingest/full_acquire.py` | `prepare_full_profile` (129), `parse_full_payload` (213), and `acquire_fictional` (576) exercise bounded full parsing with sealed fictional transport. Whole-input validation precedes fragment parsing; source/container/member hashes, XML inheritance and global duplicate IDs are checked. Proposed 300/12,000/2,000 retention caps are separate from the unchanged Step 07 cap of 200. No live full-fetch transport/CLI is enabled. |
| `src/watchlist/ingest/resource_guard.py` | `BudgetLedger` (82) persists cumulative limits; `ResourceLimits` (278), `ResourceGuard` (326), `system_snapshot` (527) and `supervise_command` (580) enforce admission and sampled disk/memory/time checks. The supervisor terminates its owned worker process group on a breach. Sampling is not an instantaneous OS allocation cap; trusted workers must not daemonize. |
| `src/watchlist/ingest/wikidata_api.py` | `parse_fictional_wikidata_api_batches` (476) validates supplied fictional batches, requested IDs, revisions, redirects, direct organization qualification and complete bounded type evidence. Human/unknown/incomplete candidates are excluded or quarantined. There is no search, transport or live registry connection. |
| `src/watchlist/ingest/metadata_preflight.py` | `load_policy` checks exact source/URL/method/format tuples and hash-bound rationale. `run_session` records cumulative attempts, partial/error bytes, deadlines and individual outcomes. `_validated_prior` checks chained receipts and policy/body hashes. The default CLI validates locally; explicit execution is required for networking. The final allowlist addition is only the exact new OpenSanctions index discovered in the saved redirect. |
| `config/data-sources-step08.json` | Fifteen initial official metadata routes and the exact user-approved limits. It grants no dataset acquisition. The reserved sixteenth route has a separate reviewed policy in the evidence directory, chained to the first batch. |
| Seven new test files | `test_corpus.py`, `test_record_links.py`, `test_label_review.py`, `test_full_acquisition.py`, `test_resource_guard.py`, `test_wikidata_api.py`, `test_metadata_preflight.py`: fictional schema, provenance, duplicate/quarantine, immutable-write, parser, budget, interrupted-transfer and resource-failure cases. |
| `Makefile`, `pyproject.toml` | Add the new code/tests to existing quality scope; no dependency-version changes. |
| `tests/test_packaging.py` | Requires the corpus SQL resource in the built package; wheel/source distribution checks and clean offline installation passed. |
| `scripts/project_checks.py` | Adds one exact checksum/location-bound non-secret exception for the metadata policy's rationale hash. Fictional attack literals have narrowly scoped annotations. No general scanner exclusion. |
| `README.md`, `docs/access-and-resource-ledger.md`, this report | Record current package status and the next approval boundary. The original 08A planning statements remain dated history. |

Hashes bind content; they do not authenticate a human reviewer or grant legal rights. Candidate artifacts retain reviewed/training/evaluation eligibility as false. Weak aliases and missing language are not silently upgraded.

## What was tested and fixed

The saved [final offline log](../../data/eval-comparisons/completion-08b-01/final-offline-tests.log) records **2,606 passed, 3 deselected, 13 subtests passed in 105.97 seconds**. The three deselections are the existing optional model integration cases; this package changes no model implementation and loads no model. They are not newly failing tests.

The [lint log](../../data/eval-comparisons/completion-08b-01/final-lint.log) reports all checks passed and 27 files already formatted. The [secret scan](../../data/eval-comparisons/completion-08b-01/source-scan-after-review.json) passed on 181 files: 72 reviewed non-secret findings, zero unresolved. It is a scan of those recorded inputs, not a guarantee about all future files. `.tools/bin/uv lock --check --offline` passed for the existing 113-package lock.

The final full-suite command actually run was:

```sh
UV_CACHE_DIR=/Users/odin/Desktop/polyglot-watchlist-starter/.tools/uv-cache \
WATCHLIST_WHEELHOUSE=/Users/odin/Desktop/polyglot-watchlist-starter/data/eval-comparisons/completion-06/wheelhouse \
WATCHLIST_PACKAGING_EVIDENCE=/Users/odin/Desktop/polyglot-watchlist-starter/data/eval-comparisons/completion-08b-01/final-packaging \
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv test
```

The [packaging receipt](../../data/eval-comparisons/completion-08b-01/final-packaging/receipt.json) records successful offline builds, reconstruction from the source archive, clean installation using existing wheels and installed CLI checks. These local package artifacts precede the final one-URL metadata allowlist addition; they are not published final-release artifacts.

An earlier broad run had three failures: one in-progress full-receipt field mismatch, plus two packaging checks invoked without the documented local cache/wheelhouse environment. The receipt fields were aligned, and the corrected command above passed. No dependency download or weakened assertion was needed. Other material issues fixed during focused review were forged pair facts under a genuine grouping hash, ignored raw weak-alias markers, a redirected human type in fictional Wikidata evidence, and underreported fictional Content-Length hiding trailing records. Regression tests cover the corrected behavior.

After the only later code change—the exact sixteenth metadata URL—the relevant command was:

```sh
.venv/bin/python -B -m pytest -q tests/test_metadata_preflight.py
.tools/qa/bin/ruff check src/watchlist/ingest/metadata_preflight.py
.tools/qa/bin/ruff format --check src/watchlist/ingest/metadata_preflight.py
```

Result: **46 passed in 0.12 seconds**, scoped lint/format passed. See [focused log](../../data/eval-comparisons/completion-08b-01/metadata-final-route-tests.log). The broad suite and scan were not repeated afterward; no remaining code change needs a broader retest.

The existing independent review includes 36 focused boundary tests with socket creation denied, all passing with external pytest plugin autoload disabled. The earlier strict audit failure is preserved: pytest auto-loaded LangSmith/requests/urllib3, whose local IPv6 capability probe attempted socket creation and was denied before a connection. It was not a project network request. The isolated rerun changed no application code. See [isolated receipt](../../data/eval-comparisons/completion-08b-01/preservation/independent-validation-isolated.json) and [diagnosis](../../data/eval-comparisons/completion-08b-01/preservation/socket-diagnosis.json).

Fictional end-to-end example: two supplied organization observations share a fictional name → one candidate name link → immutable candidate release → blank review packet. Actual output: **2 observations, 1 nomination, 0 human reviews, 0 usable real labels**. A nomination is a request for evidence review, not a correct-match label. Invalid receipts, changed inputs, duplicate IDs, unsafe/existing destinations and incomplete bodies fail closed. A post-publication sync failure can leave only the already fully validated artifact, never a partially accepted release.

## Actual metadata accounting

The initial memory warning blocked admission even after free-memory headroom improved. Once macOS reported normal pressure and 50% free memory, the unchanged guard admitted the run. No request occurred while the warning blocked admission. No exception was applied and no application was stopped by the agent. Disk headroom at admission was 35,579,666,432 bytes.

[Batch 01](../../data/eval-comparisons/completion-08b-01/metadata/batch-01/session.json) ran 15 serial transactions. [Batch 02](../../data/eval-comparisons/completion-08b-01/metadata/batch-02/session.json) used the reserved transaction after reviewing the exact redirect target, retaining the original session start and counters. The [review rationale](../../data/eval-comparisons/completion-08b-01/metadata-current-index-review.md) and its policy bind that decision. Verified HTTPS used the existing local certifi CA bundle; certificates were not bypassed.

| Limit | Actual | Remaining / interpretation |
| --- | ---: | --- |
| 5,000,000 response-body bytes | 1,628,809 | 3,371,191 unused; cannot be spent because transaction allowance is exhausted. |
| 16 HTTP transactions | 16 | 0. Includes the failed response and redirect. |
| 512,000 bytes/response | Maximum 512,000 | Oversized chapter stopped at this cap; no incomplete body accepted. |
| 30 seconds/request | Every receipt within limit | No retries or parallel requests. |
| 60 minutes/session | 133.516103 seconds | Original clock includes the gap for review and focused tests. Session is finished, not available for a new batch. |
| Source datasets / entities acquired | 0 bytes / 0 new groups | All successful bodies are terms, schema, index or API-module metadata. |
| Sampled aggregate process RSS | Peak 63,193,088 bytes | Below 1.5 GiB soft / 2 GiB hard stops. Sampling limitation remains. |

The [receipt validation](../../data/eval-comparisons/completion-08b-01/metadata-receipt-validation.json) passed: chain, copied policy hashes, individual receipts, saved body hashes, unique attempted URLs, cumulative totals, zero reservation and deadlines. Two [supervision](../../data/eval-comparisons/completion-08b-01/metadata-supervision.json) [receipts](../../data/eval-comparisons/completion-08b-01/metadata-second-supervision.json) record exit zero without a resource stop. Received-body accounting excludes headers, TLS and DNS overhead, as approved.

| Source | Transactions | Received body bytes | Complete / unsuccessful |
| --- | ---: | ---: | --- |
| OpenSanctions UN | 5 | 151,544 | 4 / 1 redirect |
| OFAC | 3 | 562,863 | 2 / 1 oversized chapter |
| EU | 3 | 327,531 | 3 / 0 |
| Wikidata | 5 | 586,871 | 5 / 0 |

Exact endpoint outcomes follow. IDs map to individual receipts and successful `.body` artifacts in the two batches. No failed outcome was rewritten as success.

| Receipt | Method / exact URL | HTTP | Body bytes | Outcome |
| --- | --- | ---: | ---: | --- |
| metadata-01 | GET `https://www.wikidata.org/wiki/Wikidata:Data_access` | 200 | 141,761 | Complete metadata |
| metadata-02 | GET `https://commission.europa.eu/legal-notice_en` | 200 | 154,018 | Complete metadata |
| metadata-03 | GET `https://data.europa.eu/api/hub/search/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions` | 200 | 157,397 | Complete metadata |
| metadata-04 | GET `https://webgate.ec.europa.eu/fsd/fsf/public/files/xsdFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | 200 | 16,116 | Complete metadata |
| metadata-05 | GET `https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/tutorial-on-the-use-of-list-related-legacy-flat-files` | 200 | 38,759 | Complete metadata |
| metadata-06 | POST `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/SdnList` | 200 | 12,104 | Complete metadata |
| metadata-07 | GET `https://www.copyright.gov/title17/92chap1.html` | 200 | 512,000 | response_cap_before_eof |
| metadata-08 | GET `https://creativecommons.org/licenses/by-nc/4.0/legalcode.en` | 200 | 49,995 | Complete metadata |
| metadata-09 | GET `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261024160105-nsw/index.json` | 200 | 6,523 | Complete metadata |
| metadata-10 | GET `https://data.opensanctions.org/datasets/latest/un_sc_sanctions/index.json` | 307 | 0 | redirect_not_followed |
| metadata-11 | GET `https://www.opensanctions.org/docs/commercial/exemption/` | 200 | 88,503 | Complete metadata |
| metadata-12 | GET `https://foundation.wikimedia.org/wiki/Special:MyLanguage/User-Agent_policy` | 200 | 100,048 | Complete metadata |
| metadata-13 | GET `https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format` | 200 | 203,267 | Complete metadata |
| metadata-14 | GET `https://www.wikidata.org/w/api.php?action=paraminfo&modules=wbgetentities%7Cwbsearchentities&format=json&formatversion=2` | 200 | 35,745 | Complete metadata |
| metadata-15 | GET `https://www.wikidata.org/wiki/Wikidata:Copyright` | 200 | 106,050 | Complete metadata |
| metadata-16 | GET `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000105-chi/index.json` | 200 | 6,523 | Complete metadata |

## Source conclusions and unresolved items

- **OpenSanctions:** current exemption text expressly permits noncommercial bulk use such as student/personal research without an API key; CC BY-NC 4.0 legal code was captured. Attribution, noncommercial use and modification notices remain required. The old pinned index is historical. The current index, version `20261025000105-chi`, advertises `entities.ftm.json` at 3,015,245 bytes; its counts differ from the older index. Neither advertised size nor count proves actual eligible/independent yield. No entity body was fetched. This distributor's permission does not establish direct-UN permission.
- **OFAC:** the tutorial supports importing list data, and the live SdnList metadata advertises `SDN_XML.ZIP` at 2,582,121 bytes and `SDN.XML` at 29,245,041 bytes with a decoded-content digest. The Copyright Office chapter reached 512,000 bytes before completion; no current full chapter was accepted. The previously saved section 105 evidence and narrow factual-name rationale remain available in [source permissions](../source-permissions.md); this preflight does not claim a successful fresh recapture or worldwide clearance of all third-party material. New candidate-preparation purpose approval is still needed.
- **EU:** the exact XML 1.1 distribution in the catalog retains `COM_REUSE` (Commission Decision 2011/833/EU). The legal notice requires credit/change notices and preserves third-party/excluded-right limitations. A different tracker distribution has a different NoDerivs license; that is not the selected XML grant. The 16,116-byte XSD matches the prior saved schema hash. The catalog does not establish a fresh XML size; the 25,899,600-byte full-body measurement remains historical, so the proposed 30 MB cap must stop a grown file. No dataset request was made.
- **Wikidata:** Data_access, Copyright, User-Agent policy, RDF documentation and Action API `paraminfo` completed. Module definitions show `wbgetentities` supports labels, aliases, claims and info, multiple IDs (ordinary limit 50, so the proposed 10 is conservative), and redirect handling; `wbsearchentities` requires a search/language and has pagination. Structured-data CC0 is distinct from page-text licensing. These are metadata findings, not proof that the fictional parser matches every live response. A finite curator-reviewed seed list/search protocol, exact request/field/revision/continuation contract, type/redirect policy and polite user-agent remain required before any pilot. No entity or search request was sent. REST is not activated or silently substituted; current full REST behavior is not verified by this package. The previous SPARQL 504s remain historical failures, not fixed by a successful Action API metadata call.
- **Direct UN:** no request; remains blocked pending an applicable permission for the proposed compilation/transformations and a verified authorized endpoint. The [existing permission path](../source-permissions.md) remains the practical resolution. No publisher inquiry was sent.

Successful transport receipts intentionally retain `contract_verified=false`; source interpretation is recorded here, not retroactively injected into historical receipts. This package does not turn any source into a real training/evaluation grant.

## Acceptance and remaining project work

| Requirement | Decision / evidence |
| --- | --- |
| Offline acquisition, provenance, schema and immutable candidate preparation | PASS for the approved offline scope; integrated fictional tests and packaging evidence. |
| Review/link/quarantine support without fabricated real labels | PASS for fictional preparation; actual human reviews and accepted real labels remain zero. |
| Failure does not corrupt old data or accept an incomplete release | PASS in failure-path tests; final preservation comparison is separately recorded below. |
| Bounded official metadata investigation and honest outcome accounting | PASS; validated 16 transactions / 1,628,809 bytes. Oversized copyright response and initial redirect remain unsuccessful outcomes. |
| Memory/disk/time/budget safeguards | PASS for this measured metadata session; prior memory block was respected. Full-data peak resource fit is still unmeasured. |
| Every named source ready for acquisition | NOT CLAIMED. Wikidata remains provisional; direct UN remains blocked; OFAC's fresh chapter recapture is incomplete. |
| Full Step 08 corpus, review and script targets | NOT COMPLETE. Current 600 groups remain source-local, unreviewed and exposed; no fresh final labels were generated. |
| Step 09 | NOT STARTED. Family independence, withheld aliases, all-copy absence checks and separate final custody remain prerequisites. |

The [final preservation comparison](../../data/eval-comparisons/completion-08b-01/preservation/verification-reviewed-final.json) passed: 1,839 exact-hash files unchanged, 18 stat-only large/model files unchanged, and six explicitly reviewed edits. The initial comparison flagged the known metadata module change because its allow-edit list omitted that already approved file; the failed receipt is preserved as `verification-final.json`. The corrected comparison declares that edit rather than modifying the baseline. The baseline covers 1,845 exact-hash files and 18 explicitly stat-only files; stat equality is weaker than a content hash. `scripts/project_checks.py` was outside that baseline and its narrow intentional edit is reported separately. No models were loaded or rehashed. Command: `.venv/bin/python -B data/eval-comparisons/completion-08b-01/preservation/verify_preservation.py --output verification-reviewed-final.json --allow-edit Makefile --allow-edit pyproject.toml --allow-edit tests/test_packaging.py --allow-edit README.md --allow-edit docs/access-and-resource-ledger.md --allow-edit src/watchlist/ingest/metadata_preflight.py`.

## Proposed next package — explicit approval required, not executed

Recommend **08B-2: activate the reviewed three-source full path and acquire one bounded candidate tranche**, followed by aggregate local admission/audit (08B-4). Do not bundle Wikidata collection, human-review execution or training into that approval.

| Exact selected dataset route | Body cap | Retained non-person source-local cap | Yield basis |
| --- | ---: | ---: | --- |
| `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000105-chi/entities.ftm.json` | 5,000,000 | 300 | Current advertised body 3,015,245 bytes; older complete input yielded 269 eligible groups. |
| `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP` | 4,000,000 | 12,000 | Current advertised ZIP 2,582,121 bytes; older complete input yielded 11,610 eligible groups. Decoded XML must stay ≤32,000,000 bytes and match recorded publisher digest when applicable. |
| `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | 30,000,000 | 2,000 | Last measured body 25,899,600 bytes; older complete input yielded 1,779 eligible groups. Current size/yield unmeasured. |
| **Total new dataset approval requested** | **39,000,000** | **14,300 maximum candidates** | Historical supply 13,658 source-local groups, not an independent usable total. |

The expected transfer scenario is about 31.50 MB using current OpenSanctions/OFAC advertised sizes and the historical EU size. It is not a promised byte count. One attempt per source; serial only; **three direct GET transactions**, with no automatic redirect following, retry or fallback. An unexpected redirect stops that source and returns for route review/approval rather than spending a speculative redirect allowance. This is a narrower proposed execution envelope than the 08A nine-transaction ceiling. Each source cap applies to its complete response; errors/partial reads consume it. No new metadata request is included.

Approve this as a **new explicitly bounded dataset session**, not a reset or reuse of the finished metadata allowance: ≤60 minutes overall, OpenSanctions/OFAC ≤30 seconds/request and120 seconds/source, EU ≤180 seconds/request and240 seconds/source. All decoding/parsing/supervision work counts toward that session. Retain the existing 25% host-free admission/20% stop, stop on pressure warning, 10 GiB free-disk floor, 1.5/2 GiB aggregate RSS stops, 100,000,000-byte normalized cap and2 GiB total new-artifact cap. Do not load models alongside acquisition. Mixed source bodies stay bounded in memory and are not saved; retain only permitted non-person selection/provenance and receipts. Stop rather than silently truncating aliases or publishing an incomplete accepted release.

**Implementation approval needed:** extend only `full_acquire.py`, `corpus.py`, metadata/source policy configuration and their focused tests as needed to activate a reviewed live full transport and distinct real receipt admission. Prepare explicit source/purpose/field grants for private noncommercial candidate preparation, using the captured evidence; do not reuse a feasibility-only or fictional grant. Existing parser, resource, provenance and immutable-publication invariants remain mandatory. Scope includes one new private candidate directory, updated living permissions/data documentation and the next progress report. Full-fetch commands described in the original plan are not currently live; validate the activation offline before requesting any dataset.

**Yield and coverage:** 13,658 historical source-local groups include overlaps and the existing 600, not 600 extra. At least about 51.25% would have to survive equivalence/eligibility review as distinct families to reach 7,000 combined reference/absent groups. This is a break-even assumption, not measured acceptance. The current inspected candidates have 35 Arabic, 96 Cyrillic and only4 Han groups; they cannot demonstrate fresh final coverage. Collecting beyond the biased first200 may improve coverage, but no honest numeric script-yield forecast exists. Report measured aggregate script coverage and propose further permitted acquisition if the unchanged targets remain unmet. Wikidata stays a separate optional multilingual supplement and cannot replace the sanctions population.

**Storage and review:** prior source-specific flat projection is about17.80 MB normalized at the proposed caps; a5× scenario is about88.99 MB. Both are assumptions subject to the100 MB cap. Seven thousand accepted-family screens at an assumed2–5minutes each imply233–583reviewer-hours before difficult cases or independent review. The minimum400label items at3–10minutes each imply20–66.7hours per pass; these overlap broader group work and are not additive project totals. No human review or spending is authorized by the proposed acquisition. A later review package must identify qualified Arabic/Cyrillic/Han reviewers, capacity/rates, disagreement/adjudication workflow and an independent final-label custodian. Every used hard negative requires adjudication; the minimum400reviews do not validate all other labels.

**Stop conditions and acceptance:** changed terms/schema, missing purpose permission, cap/timeout/pressure breach, malformed/truncated content or unexpected redirect stops the affected source. Record actual received bytes, eligible/retained counts, original evidence, duplicate nominations, exposure overlap, normalized size and peak resource observations; only complete validated candidate artifacts may be accepted. Source-record counts do not close Step08. All equivalent copies and aliases must later remain in the same leakage family; exposed600families and descendants cannot become fresh calibration/threshold/final cases. No split or final label is exposed here.

Exact next owner decision: approve or decline the three-source **39 MB / three-direct-request** candidate acquisition and the narrowly scoped live-path activation described above. The optional15 MB Wikidata pilot, the unallocated41 MB planning balance, direct UN, human reviews, training, Step09 and publication remain outside that decision. If Wikidata is desired next instead, it needs a separate concrete contract/seed proposal and approval; the present metadata allowance cannot fund further calls.

## Beginner 5W1H

- **What:** built and tested the machinery for trustworthy candidate data, then checked official descriptions/terms rather than collecting new entities.
- **Why:** a downloaded name is not a verified identity or label; incomplete files and uncertain duplicate links must not enter experiments unnoticed.
- **When:** after Step07/08A and before the separately approved larger collection and real human review.
- **Where:** new local code/private evidence; only the16 listed official metadata requests touched the network.
- **Who:** software verifies mechanical integrity; source publishers define reuse terms; the owner approves resources; qualified people supply later identity/label decisions.
- **How:** fictional failure tests, immutable candidate files, explicit provenance and purpose checks, independent grouping/review contracts, bounded supervised requests and saved receipts.

Recommended next action: review this concrete acquisition proposal and explicitly authorize08B-2 if its limits and purpose are acceptable. Stop here; do not start another acquisition or Step09 automatically.
