# Completion Step 08B-2 — bounded candidate acquisition and interruption report

Date: 2026-10-25, Asia/Kolkata. **PARTIAL acquisition; APPROVAL REQUIRED for recovery. Full Step 08 is incomplete.**

The approved live path was implemented and tested. One of three sources completed: OpenSanctions UN retained 269 organization groups. OFAC returned an unapproved redirect; EU was interrupted by the resource supervisor. All three request slots are consumed. No retry, new acquisition, real human review, training, Step 09, publication, commit or push followed the interruption.

This report supplements the historical [08B-0/1 report](completion-08b-01.md); it does not change that report or the [original Step 08 requirements](../project-completion-plan.md). The implementation work is complete for the attempted package, but its three-source acquisition outcome is not successful. No final acquisition receipt, derived purpose grant or candidate corpus release exists.

## Approved scope and permission gate

The user approved one serial direct request per source, 39,000,000 combined received response-body bytes, no redirects/retries, and the source-specific limits below. The [execution registry](../../config/data-sources-step08-full.json), [offline permission review](../../data/eval-comparisons/completion-08b-02/permissions/permission-review.md), and [pre-network policy validation](../../data/eval-comparisons/completion-08b-02/live-policy-preflight.json) bind the exact endpoints, evidence, purpose and limits. The original feasibility registry remains separate.

| Source / exact requested endpoint | Received cap | Retained cap | Request / source deadlines |
| --- | ---: | ---: | --- |
| OpenSanctions UN: `https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000105-chi/entities.ftm.json` | 5,000,000 bytes | 300 non-person groups | 30 / 120 seconds |
| OFAC: `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP` | 4,000,000 bytes | 12,000 non-person groups | 30 / 120 seconds |
| EU: `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | 30,000,000 bytes | 2,000 non-person groups | 180 / 240 seconds |

OFAC decoding is separately capped at 32,000,000 bytes. OpenSanctions has publisher size/SHA-1 pins; OFAC has compressed-size and decoded XML SHA-256 pins. EU's current complete size is not known. The 60-minute overall limit includes transfer, parsing and supervision. Resource limits remain 1.5/2 GiB aggregate RSS soft/hard, at least 25% host-free memory at admission, stop below 20% or on a pressure warning, at least 10 GiB free disk, 100,000,000 normalized bytes and 2 GiB new artifacts. No model was loaded.

Permissions were checked offline before transport:

- **OpenSanctions:** captured noncommercial bulk-use statement and CC BY-NC 4.0 support this private research purpose. Preserve source/version, attribution, license and selection/change notices. Distributor permission does not authorize direct UN access.
- **OFAC:** the older official 450,000-byte copyright capture is an incomplete chapter but contains complete section 105(a)–(d), its closing boundary and the beginning of section 106. Together with fresh OFAC database import/export guidance, it supports the unchanged narrow factual organization-name/alias purpose. The recent oversized chapter response remains unsuccessful. The assessment does not claim worldwide or third-party rights clearance; broader use requires a new review. This narrow use did not require a permission stop.
- **EU:** the exact XML distribution is bound to COM_REUSE / Commission Decision 2011/833/EU, with attribution/change notices and exclusions preserved. The separate tracker distribution's NoDerivs license is not substituted.
- **Direct UN and Wikidata:** excluded from execution; zero requests under this authorization. Their earlier permission/API issues remain traceable.

Mixed raw responses were processed only in bounded memory and not retained. Only the completed permitted non-person selection, provenance, hashes and receipts/journals were saved privately. [Retention rules](../data-retention.md) continue to apply. Source grants permit private candidate preparation, not unrestricted redistribution or automatic training/evaluation use. All resulting candidates are development-exposed and final-ineligible.

## Actual run and accounting

The saved [supervision record](../../data/eval-comparisons/completion-08b-02/supervision.json) starts at 2026-10-25 01:18:55.575152 UTC (06:48:55 Asia/Kolkata). Admission recorded normal memory pressure, 49% host-free memory and 35,913,216,000 bytes free disk. The worker was terminated after **29.546705 seconds**, return code **-15**, reason **`resource_probe_unavailable`**. Sampled peak RSS was **103,186,432 bytes**. This was a monitoring failure, not evidence of an observed memory-pressure breach or RSS excess. Sampling is not an instantaneous allocation guarantee.

| Source | Transactions / HTTP | Last durable received bytes | Result |
| --- | --- | ---: | --- |
| OpenSanctions UN | 1 / 200 | 3,015,245, complete | Passed; 269 organizations retained. |
| OFAC | 1 / 302 | 0, complete response | `redirect_not_followed`; no selection. No redirected request was made. |
| EU | 1 / 200 | 12,809,136, incomplete | External interruption; no complete selection. Its original journal still says `running`. |
| **Total** | **3 / 3 slots used** | **At least 15,824,381** | Exact final received count is unknown. |

The EU response had **17,190,864 bytes** reserved beyond its last durable count. Received lower bound plus outstanding reservation gives **33,015,245 bytes of conservative accounting**, not measured transfer. The 39,000,000-byte ceiling therefore has **5,984,755 unreserved bytes**, but **zero available request slots**. Bytes possibly read after the last journal are covered by the reservation; they cannot be reported as an exact measurement. Accounting excludes HTTP headers, DNS/TLS overhead and bytes buffered outside the worker's recorded reads.

The [interruption assessment](../../data/eval-comparisons/completion-08b-02/interruption-assessment.md) checked all **1,022** immutable journals: contiguous sequence, strict JSON, monotonic counters, source limits, exact endpoints, unchanged completed rows, policy and all **29** referenced evidence files. The original exclusive [session claim](../../data/eval-comparisons/completion-08b-02/acquisition-session.claim.json) remains consumed and disables resume. It was not reset.

OpenSanctions selection: **512,403 bytes**, SHA-256 `caade45281bc200519db0a4fc3f645cbb080f183dec781ba19f7bc3c09f23d34`. Its worker-recorded raw-input SHA-256 is `06eb0d4a1727fce1be471908d98f7ff7a35efd45ad4ba4d8d4cf19303a69dd3b`; publisher size/SHA-1 verification passed during execution. Because raw bodies were not retained, the raw-input hash cannot now be independently recomputed. The later journal manifest establishes consistency, not independent custody or a cryptographic predecessor chain.

## Implemented files and functions

| File | Function / effect |
| --- | --- |
| `src/watchlist/ingest/full_acquire.py` | `load_execution_policy` (line 935) validates the exact three-source policy and all grants/evidence before opening transport. `acquire_live` (1352) claims the session once, makes bounded serial requests, persists journals and retains only completed selections. It checks decoded/publisher hashes and parsing deadlines. A partial package does not receive complete-corpus purpose grants. Reviewed fixes bind grant bytes against reread changes and handle response-close failures. |
| `src/watchlist/ingest/resource_guard.py` | `BudgetLedger` accepts narrower total/transaction/bucket limits: live execution supplies 39 MB, three bulk requests and one/source. Existing defaults remain for other callers. `_artifact_size` (505) now restarts a scan at most three times when a listed temporary file disappears; partial totals are discarded. Persistent instability and other errors still stop. `ResourceGuard._check` (386) preserves specific stop codes. Memory/disk/time thresholds were not relaxed. |
| `src/watchlist/corpus.py` | `bind_real_full_permission` (2033) deterministically binds approved purpose evidence to a complete real receipt. `prepare_real_full_source` (2098) checks real receipt/selection/provenance integrity. `build_candidate_release` (2639) validates before exclusive immutable publication. The interrupted session is intentionally inadmissible through this complete-receipt path. |
| `src/watchlist/corpus_schema.sql` | Version 2 recognizes `real-full-acquisition-v1` while retaining exact read-only version-1 compatibility. Candidates remain ineligible for training/evaluation pending later gates. |
| `tests/test_full_acquisition.py`, `tests/test_corpus.py`, `tests/test_resource_guard.py` | Focused policy, parser, provenance, grant, failure, immutable-publication and monitoring regressions. Corpus tests include the actual fictional acquisition writer through purpose binding, admission, release and load. |
| `config/data-sources-step08-full.json` | Exact one-use live policy; hash `4a2cd2f3a34655c97637720c3f881abb2b026dba609bb3f159351fb615e79af4`. Does not activate UN or Wikidata. |
| `data/eval-comparisons/completion-08b-02/permissions/` | Explicit user-approval record, source grants, evidence review and preflight. No retrospective final-purpose grant was generated. |
| `data/eval-comparisons/completion-08b-02/run_acquisition.py` and `supervision.json` | Saved execution harness and actual supervisor outcome. The harness is historical evidence, not a command to resume. |
| `data/eval-comparisons/completion-08b-02/interruption-*` | Separate interruption assessment and journal manifest; preserve original source statuses and uncertainty. |
| `data/eval-comparisons/completion-08b-02/audit/` | `audit_candidates.py` verifies the interruption envelope and completed selection, then measures scripts, aliases, candidate links and exposure. It does not call corpus admission or reconstruct a final receipt. Aggregate outputs omit names, provider IDs and pair endpoints. |
| `README.md`, `docs/access-and-resource-ledger.md`, `docs/source-permissions.md`, this report | Living status, permission clarification, accounting, unresolved requirements and next approval boundary. Historical reports remain unchanged. |

## Focused verification and diagnosis

The [validation summary](../../data/eval-comparisons/completion-08b-02/validation-summary.json) records the final source hashes and results. No full-suite or secret-scan rerun was needed; the prior 2,606-test/scan evidence remains historical and is not claimed to cover later code unchanged.

| Focused scope | Actual result | Evidence qualification |
| --- | --- | --- |
| Full acquisition | 54 passed | Implementation-owner executed focused tests; result recorded in validation summary. Scoped Ruff passed. |
| Corpus | 204 passed | Implementation-owner executed focused tests including acquisition-writer integration; result recorded in validation summary. Scoped Ruff passed. |
| Resource guard after race fix | 38 passed in 0.21 s | [Saved log](../../data/eval-comparisons/completion-08b-02/resource-tests-after-race-fix.log); scoped Ruff passed. Earlier 35-test result predates the three new regressions. |
| Package SQL/source inclusion | 1 passed, 7 deselected in 1.44 s | [Corrected log](../../data/eval-comparisons/completion-08b-02/package-resource-tests-corrected.log). The initial invocation omitted the required local UV setting; its failed log is preserved. |
| Offline aggregate audit | 118 checks passed; 47 input/code hashes unchanged | [Verification](../../data/eval-comparisons/completion-08b-02/audit/verification.json), private file/directory modes checked, Ruff passed. These checks are not extra pytest cases. |

The focused test commands used `pytest -q tests/test_full_acquisition.py`, `pytest -q tests/test_corpus.py` and `pytest -q tests/test_resource_guard.py` under the existing `.venv` Python. The corrected package command was:

```sh
UV=/Users/odin/Desktop/polyglot-watchlist-starter/.tools/bin/uv \
UV_CACHE_DIR=/Users/odin/Desktop/polyglot-watchlist-starter/.tools/uv-cache \
WATCHLIST_WHEELHOUSE=/Users/odin/Desktop/polyglot-watchlist-starter/data/eval-comparisons/completion-06/wheelhouse \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q \
  tests/test_packaging.py -k includes_exact_package_sources
```

Actual audit command:

```sh
.venv/bin/python -B data/eval-comparisons/completion-08b-02/audit/audit_candidates.py \
  --inputs data/eval-comparisons/completion-08b-02/audit/inputs.json \
  --inputs-sha256 742d8316bfa6ae20831fa6d6aef8c1c3793052575e5d7fa8a61792acc8cb2330
```

After the documentation edits, a local Python link-existence check inspected 68 relative links across this report, README, the access/resource ledger and source permissions: zero missing targets. It made no network requests or application-code changes; no additional pytest run was needed for those prose edits.

**Monitoring bug:** the acquisition writer publishes a file by linking a private temporary path and then removing that temporary path. A concurrent artifact-size scan could list it, then fail to stat it after removal. A deterministic offline regression reproduced this failure before the bounded-rescan fix. The fixed monitor retries only that transient whole-scan inconsistency, never returns an incomplete sum and still fails closed on persistent instability or inaccessible/unsafe files. [Narrow review](../../data/eval-comparisons/completion-08b-02/preservation/resource-race-review.json) found no material issue. The old supervisor saved only a generic probe error, so this is a proven possible cause, **not a proven diagnosis of the exact live subprobe failure**. No live retry followed the fix.

Preservation evidence is deliberately limited: the derived baseline carries 1,673 historical expectations (1,667 hashes and six stat-only records) and freshly pins ten small prior metadata receipts/plans. It is not a fresh whole-tree/model comparison. Audit inputs remained hash-identical before/after analysis. New outputs use private, non-overwriting paths; original journals, source snapshots, models and review stores were not intentionally modified. No redundant whole-tree recovery scan or model rehash was performed.

## Measured candidate yield and limitations

The [aggregate report](../../data/eval-comparisons/completion-08b-02/audit/report.md) and [results](../../data/eval-comparisons/completion-08b-02/audit/results.json) contain the definitions and measurements.

| Measurement | Actual result |
| --- | ---: |
| Completed organization groups / vessels | 269 / 0 |
| Input records / excluded persons / excluded other types / cap exclusions | 2,905 / 732 / 1,904 / 0 |
| Name-evidence entries / distinct original strings | 918 / 913 |
| Groups with multiple distinct names / single-name groups | 154 / 115 |
| Missing supplied language tags | 918 of 918 |
| Explicitly weak alias entries | 0; absence of a weak marker does not prove correctness |
| Names rejected by the 200-code-point normalizer / groups without an accepted name | 0 / 0 |
| Latin–Arabic / Latin–Cyrillic / Latin–Han groups with separate nonweak single-script name candidates | 39 / 2 / 4 |
| Exact-name duplicate nominations / conservative-normalization nominations | 3 / 3 pairs, involving three groups in one candidate component |
| Actual human reviews / usable reviewed labels / final-eligible groups | 0 / 0 / 0 |

The name-evidence fields comprise **274 `properties.name`, 627 `properties.alias` and 17 `properties.previousName`** occurrences. Script occurrences are **873 Latin, 43 Arabic, two Cyrillic and four Han**; a mixed-script name may count toward more than one script, so these occurrences are not mutually exclusive. Group script presence is 269 Latin, 39 Arabic, two Cyrillic and four Han. Script is the writing system inferred from characters, not a verified language tag.

All 269 retained rows passed mechanical record/provenance validation; no malformed retained row was accepted. Persons and other record types were exclusions, not parser errors. OFAC/EU have no completed parsed input, so their excluded/rejected-record counts are **unknown**, not zero. Name evidence includes primary names and alias/property occurrences; 918 must not be called 918 independent aliases or labels.

All 200 earlier OpenSanctions provider IDs recur; there are **69 additional source-local IDs**, not 69 proven independent identities. Against all earlier 600 groups, exact-name overlap nominates 289 pairs (85 cross-source); conservative normalization nominates 308 (104 cross-source), involving 226 current and 304 prior groups. Forty-three current groups lack detected overlap; that does not establish freshness. All 269 are developer-exposed regardless of collision results.

Script co-presence nominates review material; it does not establish language, correct transliteration, independent identity or either directional evaluation claim. The rows overlap. No Han coverage gate is met. Fictional example: `  Fable　Harbor  ` normalizes to `fable harbor`; equal strings in two records nominate a link, not an identity merge. Real source names and final labels are not published in this report.

## Acceptance and remaining corpus work

| Gate | Decision |
| --- | --- |
| Exact pre-network policy, narrow permissions, no UN/Wikidata | PASS for this execution. |
| Three requests, no redirects/retries, enforced caps and guards | PASS; the guard terminated on unavailable monitoring. Exact final byte measurement is unavailable and conservatively reserved. |
| All three successful selections | NOT MET: OFAC redirect and EU interruption. |
| Immutable complete real receipt and candidate release | NOT MET; correctly withheld. Completed OpenSanctions evidence is retained, not promoted into a fabricated complete receipt. |
| Aggregate audit of the completed selection | PASS with exposure and no-label limitations. |
| Full Step 08 acceptance | NOT MET. Independent groups, reviewed equivalence, label ledger, fresh custody and script coverage remain unfinished. |
| Step 09 readiness | NOT MET; no partitions or final labels created. |

Targets stay approximately **5,000 usable reference groups + 2,000 independent absent-query groups**, at least **200 positive and 200 negative reviews**, adjudication of every used hard negative, and **100 independent final positives per claimed direction**. Sanctions-domain cases cannot be replaced silently by a general organization supplement. Reference absence must be established against all equivalent source copies, not inferred from an unmatched name. Equivalence groups, uncertainty quarantine and leakage families must precede partitioning; all aliases/copies and exposure descendants stay together. An independent final-data custodian is still needed.

## Proposed recovery package — not executed; explicit approval required

Recommend **08B-2R: offline recovery support, then one bounded OFAC/EU recovery session**. Preserve and reuse the completed OpenSanctions selection; do not redownload it.

1. **Offline first:** add explicit completed-source recovery/admission, binding the existing selection to its original completed journal, interruption assessment, policy and prospective permission. Keep the original interrupted session and absent final receipt intact. Test source failure, mismatched/cross-session evidence, stale grants, consumed claims and immutable publication with fictional fixtures. Combining independently completed sessions requires a distinct manifest, never a claim that the interrupted session completed.
2. **Monitor readiness:** add more specific failed-subprobe diagnostics and one bounded offline exercise of publication concurrent with resource monitoring. Stop if monitoring is unstable; do not start an indefinite check cycle. Existing resource thresholds remain unchanged.
3. **Only after those checks, a newly authorized session:** at most **34,000,000 additional received body bytes and three HTTP transactions**, serial, no automatic retries. OFAC gets at most two transactions (one exact export route plus at most one specifically allowed redirect), **4,000,000 bytes combined across them**, 32,000,000 decoded bytes and 12,000 retained groups. EU gets one direct transaction, 30,000,000 bytes and 2,000 groups. Redirect/error bodies count. No fourth call, extra metadata, alternate version, fallback or changed endpoint is permitted.

OFAC starts at the exact export endpoint above. The only proposed redirected object is the historically reviewed path:

```text
https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/c855675f-4385-4bb5-b89a-59ccb73a83e6/2026-10-20/4166a9f5-d268-432a-a70b-65bd16bcd16a/SDN_XML.ZIP
```

Permit only the finite provider signing-query parameters checked by the existing redirect validator; never save signing values. This historical path is **not known to be the target of the current failed 302**, whose Location was not saved. A different host/path, unsupported parameter or digest mismatch stops OFAC for review; do not improvise a new route. EU uses the same exact XML URL above. Preserve the pinned OFAC decoded digest and size constraints; changed contents need a separate metadata/contract decision.

Use a new explicit one-use approval and claim. Keep 30-second OFAC requests/120-second source, 180-second EU request/240-second source and 60-minute overall limits. Keep all existing RSS, host-memory, disk and retention safeguards. To prevent budget reset by using a new directory, count old plus new 08B-2 artifacts against the same **2 GiB** ceiling and combined normalized selections against **100,000,000 bytes**.

This requests additional authorization: prior conservative accounting 33,015,245 + proposed 34,000,000 = **67,015,245 bytes** across the original/recovery sessions. It is not spending unused original allowance or claiming all those bytes were transferred. Maximum combined transactions would be six. No further batch is included.

Historical supply suggests up to **11,610 OFAC + 1,779 EU = 13,389 source-local candidates**; this is not a forecast of independent usable families. Together with the retained 269, the historical supply scenario is 13,658 before overlap/eligibility review. Approximately 51.25% would need to survive as distinct usable families to reach 7,000; the survival rate is unmeasured. Expected remaining transfer using old size evidence is about 28.48 MB plus any redirect body, under the requested 34 MB cap. Current size, source availability and multilingual yield can differ.

The earlier storage scenario was about 17.80 MB normalized at the proposed caps, or 88.99 MB at five times that projection; it is an assumption, not measured future storage. The current retained selection is 0.512403 MB. Full-parser peak memory remains unmeasured; a 103 MB sampled partial run cannot prove the full run will fit. Stop at guard failures instead of caching mixed raw data to disk.

Coverage benefit: more OFAC/EU groups may provide Arabic/Cyrillic and additional Han evidence beyond the biased first 200 selections. No numerical script-yield promise is supportable. Even a successful recovery remains development material; it does not produce independent final cases. Report yield and gaps before proposing another permitted source/custody package. Wikidata and direct UN remain outside this request.

Review planning stays separate: 7,000 family screens at an assumed 2–5 minutes imply 233–583 reviewer-hours; the minimum 400 label items at 3–10 minutes imply 20–66.7 hours per pass. These overlapping estimates are not additive, do not price bilingual adjudication and authorize no spending or reviews. A later package must identify qualified Arabic/Cyrillic/Han reviewers, rates/capacity, disagreement handling and final custody.

**Files proposed for recovery approval:** only `src/watchlist/ingest/{full_acquire.py,resource_guard.py}`, `src/watchlist/corpus.py`, their three focused test files, a new recovery execution-policy file, new private recovery evidence/manifest directory and living status/permissions/report documentation. No label-review execution, model change, Step 09 or publication. Acceptance requires verified complete selections with traceable cross-session lineage, unchanged historical evidence, focused failure tests, bounded receipts, aggregate audit and an honest remaining-gap report. If a source fails again, record it and stop at the next decision boundary.

## Beginner 5W1H

- **What:** built the bounded downloader and collected one complete source; measured its organization/name evidence.
- **Why:** usable ML data needs complete files, permission, provenance and independent human judgments. A name collision is only a review candidate.
- **When:** during approved Step 08B, before actual human review and independent dataset splitting.
- **Where:** private local evidence under `completion-08b-02`; only the three listed source requests went online.
- **Who:** software checks structure and budgets; publishers define reuse conditions; the project owner approves recovery; qualified reviewers and a separate custodian must later establish labels and freshness.
- **How:** strict policy/grants, guarded serial transfer, immutable journals, offline failure tests and an aggregate audit. The failed monitor stopped the run instead of allowing unmonitored transfer.

**Decision requested:** approve or decline the concrete 08B-2R offline recovery changes plus the additional **34 MB / three-transaction OFAC/EU session** above. The original request ceiling is exhausted and the user explicitly required approval for another batch or expanded budget. Stop here pending that decision.
