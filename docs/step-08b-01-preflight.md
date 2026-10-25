# Step 08B-0/1 — approved implementation and metadata preflight

Date: 2026-10-25, Asia/Kolkata. The user explicitly approved offline implementation and official metadata preflight only, following the Step 08A plan. This is the phase preflight record, not a dataset acquisition grant.

## Goal, boundaries and acceptance

Implement candidate corpus provenance, separate immutable storage, reviewed-link/quarantine contracts, fictional review-support, full-profile offline parsing, resource guards and provisional Wikidata response validation. Prove with fictional tests that failures cannot accept incomplete releases or overwrite old data. Verify official metadata within the limits below; record failures and unresolved permission/contract questions honestly. No real corpus build, human review, training, partitions, direct UN request, model/store alteration, paid resource, publication or GitHub run.

Files: src/watchlist/corpus.py, corpus_schema.sql, label_review.py; src/watchlist/ingest/link_records.py, full_acquire.py, resource_guard.py, wikidata_api.py, metadata_preflight.py; corresponding test_corpus.py, test_record_links.py, test_label_review.py, test_full_acquisition.py, test_resource_guard.py, test_wikidata_api.py, test_metadata_preflight.py; config/data-sources-step08.json; new completion-08b-01 evidence and progress report. Integrate these files into existing quality checks and verify package schema inclusion when ready. Existing dependency versions remain unchanged.

Dependencies: existing standard-library Python/SQLite, existing parsers and pinned local pytest/Ruff tools. Commands: focused pytest suites, all non-integration offline tests, scoped Ruff check/format, offline packaging check, existing secret scan, metadata module offline policy validation then explicit --execute-approved-metadata. Any explicit later metadata batch must carry the preceding completed receipt, original start time and cumulative counters; no route can be retried.

Risks: source drift, oversized documentation, redirects/challenges, undocumented API semantics, parser truncation, corrupt provenance, invented labels, ambiguous identity links and process-monitor limitations. Acceptance requires meaningful failure-path tests, recorded limits/counters, preserved historical evidence and an honest remaining acquisition/review gate. Passing code tests does not supply correct human labels or legal permission.

## Exact metadata boundary

5,000,000 total received body bytes; at most16 HTTP transactions including redirects and unsuccessful responses; at most512,000 received bytes per response; at most30 seconds/request and60 minutes across the complete metadata session. Serial requests only; no automatic retries. Failed reads and partial/error bodies count. Redirects are recorded but not automatically followed. No data bytes may be hidden in the metadata category. The extra54 MB and41 MB unallocated balance remain inactive.

The following15 routes are the initial finite metadata policy. They are grounded in config/data-sources.json, docs/source-permissions.md and the source-feasibility plan. The pinned OpenSanctions index is historical metadata and will not be called current unless the latest pointer agrees. The OFAC POST is the already documented read-only SdnList metadata operation with an empty body. The Wikidata paraminfo request asks only for module definitions, not entities, seeds, names or claims; it is the official module-metadata check explicitly proposed in Step08A. The copyright section fragment is omitted from the HTTP URL because fragments are browser-only. The EU public token is the existing catalog routing value, not an account secret.

One remaining transaction is reserved, not promised, for a current official documentation link discovered in these responses and explicitly reviewed before use. Any second batch must use the same cumulative5 MB/16-transaction/60-minute allowance, and its exact route must be added to the finite reviewed catalog with saved-link evidence. No fallback data API or arbitrary host-wide route is authorized.

| Source | Method | Exact metadata URL | Format |
| --- | --- | --- | --- |
| wikidata_orgs | GET | `https://www.wikidata.org/wiki/Wikidata:Data_access` | html |
| eu_consolidated | GET | `https://commission.europa.eu/legal-notice_en` | html |
| eu_consolidated | GET | `https://data.europa.eu/api/hub/search/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions` | json |
| eu_consolidated | GET | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xsdFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | xml |
| ofac_sdn | GET | `https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/tutorial-on-the-use-of-list-related-legacy-flat-files` | html |
| ofac_sdn | POST | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/SdnList` | json |
| ofac_sdn | GET | `https://www.copyright.gov/title17/92chap1.html` | html |
| opensanctions_un | GET | `https://creativecommons.org/licenses/by-nc/4.0/legalcode.en` | html |
| opensanctions_un | GET | `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261024160105-nsw/index.json` | json |
| opensanctions_un | GET | `https://data.opensanctions.org/datasets/latest/un_sc_sanctions/index.json` | json |
| opensanctions_un | GET | `https://www.opensanctions.org/docs/commercial/exemption/` | html |
| wikidata_orgs | GET | `https://foundation.wikimedia.org/wiki/Special:MyLanguage/User-Agent_policy` | html |
| wikidata_orgs | GET | `https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format` | html |
| wikidata_orgs | GET | `https://www.wikidata.org/w/api.php?action=paraminfo&modules=wbgetentities%7Cwbsearchentities&format=json&formatversion=2` | json |
| wikidata_orgs | GET | `https://www.wikidata.org/wiki/Wikidata:Copyright` | html |

## Source roles and rights

OpenSanctions remains a noncommercial permitted distribution; OFAC uses narrow factual names/aliases; EU uses the recorded distribution grant and notices. Metadata verification must distinguish source rights, field/type purpose scope, endpoint availability and project authorization. All four remain unauthorized for new dataset acquisition in this package. Direct UN stays outside all requests. Wikidata remains provisional until exact API contracts, appropriate non-person/type semantics, seeds, limits and the later acquisition approval are satisfied. REST is documentation comparison only; no automatic data fallback.

## Beginner 5W1H

What: build and test local preparation components, then inspect official metadata. Why: prevent bad evidence or incomplete transfers from becoming trusted corpus inputs. When: now under explicit08B-0/1 approval, before new datasets. Where: local code and new private evidence; only the listed official metadata routes are contacted. Who: software enforces mechanical checks; publishers determine rights; the owner approves acquisition and actual people provide later reviews. How: finite request and byte counters, retained receipts, fictional failure tests, immutable candidate artifacts and separate next-step approval.
