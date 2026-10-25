# Completion Step 07 — approved revision and formal closure

Date: 2026-10-25, Asia/Kolkata. **Status: COMPLETE under the explicitly approved three-source feasibility scope.** This is a new approval record; the earlier Step 07 implementation and pending-decision reports remain unchanged historical evidence. It does not claim completion of the original five successful acquisitions or of Step 08.

## Approval applied

The user stated in DECISION 1: “I approve the proposed Step 07 scope revision: OpenSanctions UN, OFAC and EU are the three required successful feasibility acquisitions.” They also required direct UN and Wikidata to remain investigated but not acquired, with traceable failures and separate review/authorization for future use. This is the approval reference; no approval is inferred from elapsed time or a tool result.

The living completion plan now records that amendment. `config/corpus-requirements.json` retains all five investigated source IDs and adds the three required successful IDs, the two investigated-not-acquired dispositions and the approval reference. Original Step 08 requirements and all numeric acquisition limits are unchanged. The source registry still records all five routes and histories: UN remains blocked; Wikidata becomes pending project acquisition authorization while retaining the captured CC0 structured-data terms. This prevents the old successful-permission decision from being mistaken for permission to retry or use a new API.

## Revised acceptance evidence

| Requirement | Verified result |
| --- | --- |
| Source-specific permission investigation and provenance | Reviewed terms/conditions remain recorded for all five; the successful sources' 15 permission-evidence file hashes match their receipts. Direct UN's missing transformation grant remains explicit. |
| Required successful bounded acquisitions | OpenSanctions UN acquisition 03, OFAC acquisition 01 and EU acquisition 02: 200 retained groups each, 600 distinct source-qualified IDs in total, 3,293 name/alias-evidence entries. Selection hashes and standalone/manifest receipts match. |
| Honest unsuccessful-source disposition | No new direct-UN selection; Wikidata attempts 01–06 retained none, with confirmed HTTP 504 in 04–06. User-approved investigated-not-acquired status closes the revised Step 07 requirement; it does not resolve permission or availability. |
| Malformed/redirect/interrupted/oversized/overwrite controls and legacy ingestion | Fresh offline policy/parser suite: **520 passed**. Scoped lint and formatting passed; current policy preflight passed. No application code or tests changed for this revision. |
| Measured feasibility and workload | Existing verified 600-group analysis supplies script/alias/duplicate counts and qualified acquisition/review estimates. No entity merges, human labels, corpus release or new model result was fabricated. |
| Budget and retention | Historical dataset reads 40,006,347/50,000,000 bytes; terms reads 3,290,827/5,000,000. No new network request in this closure. Current retained selection hashes and private modes preserved; mixed bodies were not retained. |
| Explicit approval for excluded required sources | DECISION 1 supplies the previously missing scope approval. Both excluded sources remain visible and require separate authorization/review before future use. |
| Historical preservation and downstream scope | All pre-existing progress-report hashes and the exact original Step 08 section match the pre-revision snapshot. Numerical limits are unchanged. No push, hosted CI rerun, dependency change, training or acquisition occurred. |

The [independent evidence verification](../../data/eval-comparisons/completion-07/approved-closure/evidence-verification.json) and [fresh local validation receipt](../../data/eval-comparisons/completion-07/approved-closure/local-validation.json) support this decision. The [before-revision snapshot](../../data/eval-comparisons/completion-07/approved-closure/before-revision.json) binds the unchanged historical reports and Step 08 text. Final documentation scanning is retained with this continuation's final validation evidence.

## What changed, file by file

- `docs/project-completion-plan.md`: adds the dated Step 07 scope amendment; preserves the original Step 08 requirements verbatim.
- `config/corpus-requirements.json`: adds `required_successful_source_ids`, `investigated_not_acquired` and `scope_revision`; the original `sources` list remains the investigation inventory. These policy fields are documentation for acceptance, not a newly implemented full-corpus acquisition profile.
- `config/data-sources.json`: keeps UN blocked; changes Wikidata's execution permission status to pending and explains the separate future authorization requirement. Its recorded CC0 evidence and prior query are preserved.
- `docs/source-permissions.md`, `docs/access-and-resource-ledger.md`, `README.md`: point to the current approved disposition and distinguish it from dated earlier reports.
- This new report: records approval and formal acceptance without rewriting history. No new application functions, schema migration or library was introduced.

## Commands actually run and example

```sh
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv source-tests lint
.venv/bin/python -B -m watchlist.ingest.acquire preflight \
  --profile feasibility --registry config/data-sources.json \
  --project-root /Users/odin/Desktop/polyglot-watchlist-starter
```

Both commands exited zero. The first passed 520 tests and scoped lint/format; the second performed no network access. Existing receipt/hash comparisons verified real saved selections, not a new acquisition. Example policy input: source `wikidata_orgs` now has `permission.status="pending"`; preflight can describe its recorded route/evidence, but that status does not authorize fetching. The three required selections still total 600 groups, not five successful sources.

## Limits, next phase and 5W1H

Closure establishes a permitted and reproducible feasibility exercise. It does not establish 600 independent identities, validated labels, representative script coverage, evaluation eligibility, training rights, calibrated probabilities or operational suitability. Direct UN's rights/access and Wikidata's service issues remain traceable in their preserved receipts. Later source use needs its own review.

**What:** formally close the revised Step 07. **Why:** proceed using verified permitted evidence without misrepresenting failed sources. **When:** after explicit user scope approval and fresh offline policy verification. **Where:** local source policy and evidence; no remote changes. **Who:** the user approved scope, publishers control reuse rights, and code/evidence checks establish mechanical acceptance. **How:** verify the three successful selections, preserve all histories, record the amended acceptance set, and leave excluded routes gated.

The user separately authorized **Step 08A planning and offline analysis after this closure**. That planning may inspect the existing 600 groups, design a corpus/review process and propose Step 08B resources; it may not acquire data, fabricate labels, train, use paid resources or execute Step 08B. The original targets of approximately 5,000 usable reference groups, 2,000 independent absent-query groups, at least 200 positive and 200 negative candidate reviews, and at least 100 independent final positive groups per claimed script direction remain intact.
