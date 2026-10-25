# Step 08B-2R continuation — acquisition verified

Date: 2026-10-25. **Approved bounded package: PASS. Full Step 08: INCOMPLETE. Stop before corpus release, human review, further acquisition, training, Step 09 or publication.**

The separately approved continuation successfully acquired OFAC and EU, and reused OpenSanctions without downloading it. This is a new successful session, not a correction of the earlier failed/interrupted sessions. Their claims, receipts, uncertainties and reports remain unchanged.

## Authorization and preflight

The [continuation policy](../../config/data-sources-step08-continuation.json), SHA-256 `9a1eede5d5088841c1f30e9aef716cbaa74258b903cf458014caa5dd9ab0c8a0`, binds the [new approval](../../data/eval-comparisons/completion-08b-02rc/permissions/user-approval.json), the failed recovery policy/claim/receipt and its unresolved 4,000,000-byte reservation. It permits only 30,000,000 new received body bytes and three new charged transactions. Four is the cumulative recovery transaction ceiling, including the previous failed attempt. No original claim was reset.

The [final pre-network gate](../../data/eval-comparisons/completion-08b-02rc/pre-network-gate-final.json) binds the exact executed code and 49 verified evidence references. Current permission assessment uses the saved same-day official evidence and unchanged narrow grants; no extra metadata request was made. OpenSanctions CC BY-NC, OFAC factual non-person list use supported by complete saved section 105 and official import/export guidance, and EU XML COM_REUSE remain the basis. This does not claim worldwide/third-party clearance, permission for direct UN, Wikidata, training or public redistribution. Attribution, original fields, change notices and no raw retention remain required.

The worker explicitly selected the existing certifi bundle through process-local `SSL_CERT_FILE`:

```text
.venv/lib/python3.14/site-packages/certifi/cacert.pem
SHA-256: 50f79f98dac192b20dbf73f35c56f0b0c557ab267ff5199d1117cc1180b70785
```

The exact bundle hash, 120 loaded CAs, `CERT_REQUIRED`, and hostname verification were checked before a network claim. An offline probe exercised the real `HTTPTransport.open → _PinnedHTTPSConnection.connect → SSLContext.wrap_socket` path with DNS/socket replacements; it verified the actual SSL context and OFAC server hostname, then stopped before a handshake. The live worker uses the unchanged native transport with that verified configuration. Its successful HTTPS responses subsequently established connectivity. No verification was disabled, fallback introduced, dependency downloaded or global configuration changed.

Code review found that an initially added null continuation field would alter the original recovery claim schema. This was corrected before execution: the field is present only for continuation claims. The initial offline gate remains historical; the final gate binds the corrected code. Focused original-recovery corpus tests were added to the validation command for this concrete compatibility concern.

Historical expected bodies were 28,481,721 bytes, leaving 1,518,279 bytes for margin. Current GET headers then confirmed both dataset lengths before their bodies were read. OFAC ZIP/decoded XML size and decoded digest pins were enforced. These gates used the authorized requests, not additional HEAD or metadata calls.

## Actual requests, endpoints and bytes

| Transaction | Endpoint | HTTP / outcome | Received body bytes |
| --- | --- | --- | ---: |
| 1 | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP` | 302, approved exact redirect; complete empty body | 0 |
| 2 | Exact approved OFAC object below | 200, complete ZIP, publisher pins passed | 2,582,121 |
| 3 | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw` | 200, complete XML | 25,899,600 |

Approved and observed OFAC object, without ephemeral signing values:

```text
https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/c855675f-4385-4bb5-b89a-59ccb73a83e6/2026-10-20/4166a9f5-d268-432a-a70b-65bd16bcd16a/SDN_XML.ZIP
```

The finite signing-query validator remained active. No other redirect, retry, parallel request, additional source or discovery request occurred. The redirect had no Content-Length and a completely read empty body; the two dataset responses had exact positive Content-Length values matching their completed bodies.

The [acquisition receipt](../../data/eval-comparisons/completion-08b-02rc/acquisition/receipt.json) has SHA-256 `dff2ef1c3f0584f19e32630e37008b1bd007fb3fc01187267f700249d2172c85`. It records transfer-time raw hashes, decoded OFAC hash, parser versions, source-qualified provenance, selection hashes, grants and all transaction outcomes. Raw mixed-person source files were processed transiently and were not persisted. Consequently their hashes cannot be independently recomputed afterward; selection hashes were recomputed from the retained files.

| Accounting quantity | Value |
| --- | ---: |
| New received body bytes, measured | **28,481,721** |
| New unresolved response reservations | **0** |
| New body limit / remaining numerical allowance | 30,000,000 / **1,518,279** |
| New charged transactions / remaining | **3 / 0** |
| Earlier failed recovery reservation, preserved | **4,000,000** |
| Cumulative recovery accounted bytes / ceiling | **32,481,721 / 34,000,000** |
| Cumulative recovery charged transactions / ceiling | **4 / 4** |
| Original interrupted-session conservative accounting | **33,015,245** |
| Original + recovery + continuation conservative accounting | **65,496,966** |
| Original + recovery maximum previously authorized | **67,015,245** |

The original 33,015,245 consists of a 15,824,381-byte durable received lower bound plus a 17,190,864-byte unresolved reservation. Neither that reservation nor the failed recovery's 4 MB is claimed as measured transfer. Remaining numerical bytes do not authorize another batch; all new transaction slots are consumed.

## Resource and retention evidence

The [acquisition supervision record](../../data/eval-comparisons/completion-08b-02rc/supervision.json) shows 56% host-free memory, no pressure warning, 35,852,591,104 bytes free disk and 6,320,832 existing artifact bytes at admission. Acquisition took **125.247051 seconds**, peak sampled RSS **531,628,032 bytes**, exit zero and no resource stop. In this session the complete receipt also reports `passed`; process exit alone is not the success criterion.

Existing protections were retained: 60-minute session; OFAC 30 seconds/request and 120 seconds/source; EU 180/240 seconds; 1.5/2 GiB soft/hard RSS; ≥25% free memory at admission, stop below 20% or on pressure warning; ≥10 GiB free disk; ≤2 GiB combined artifacts; ≤100,000,000 normalized bytes. Both prior directories and the new directory were included in artifact monitoring. The worker reserved both existing 512,403-byte OpenSanctions copies before adding its new copy. Current normalized selection files across these directories total **14,498,377 bytes**. Existing bounded monitor-race handling was not relaxed.

The [offline audit supervision](../../data/eval-comparisons/completion-08b-02rc/audit-supervision.json) used the remaining original session deadline: **2.198597 seconds**, peak sampled RSS **148,209,664 bytes**, no resource stop. Its network-denial hook prevented socket access.

## Retained evidence and limitations

These are **source-local candidates**, not confirmed identities, independent families, approved labels or final-test data.

| Source | Organizations | Vessels | Total groups | Name-evidence entries including primary | Distinct source strings |
| --- | ---: | ---: | ---: | ---: | ---: |
| OpenSanctions UN, reused | 269 | 0 | 269 | 918 | 913 |
| OFAC | 10,042 | 1,568 | 11,610 | 25,323 | 24,957 |
| EU | 1,779 | 0 | 1,779 | 14,327 | 14,166 |
| Combined | **12,090** | **1,568** | **13,658** | **40,568** | **39,173 across all sources** |

Organization-only name entries total **38,717**. Vessel records are a separately counted, already permitted non-person type; they must not be described as organizations. No new type was authorized. All candidates are development-exposed, with **zero final eligibility, zero human labels and zero confirmed identity merges**.

Input disposition:

| Source | Input records | Persons excluded | Other records excluded | Retained | Excluded by cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reused OpenSanctions historical evidence | 2,905 | 732 | 1,904 | 269 | 0 |
| OFAC | 19,471 | 7,519 | 342 | 11,610 | 0 |
| EU | 6,269 | 4,490 | 0 | 1,779 | 0 |

OFAC contributes 11,610 primary-name entries and 13,713 aka entries. OpenSanctions retains 274 primary property occurrences, 627 alias-property occurrences and 17 previous-name occurrences. EU's 14,327 entries retain the provider's `nameAlias@wholeName` evidence. These field counts are not independent aliases or labels. Overall, 7,423 groups contain at least two distinct original names; 6,235 have one. There are 2,153 explicitly weak entries across 1,476 groups, and no group entirely without nonweak entries.

**Language:** 27,858 entries (68.67%) have no supplied language tag. All 12,710 supplied tags come from EU and are retained as provider evidence, not independently certified language judgments. Script detection does not infer missing language tags. The full supplied-tag distribution is in the audit. Unknown/unsupported script occurrences are also retained, not forced into one of the four target scripts.

| Candidate script pair | OpenSanctions | OFAC | EU | Total source-local groups | Strict single-script, nonweak pair |
| --- | ---: | ---: | ---: | ---: | ---: |
| Latin–Arabic | 39 | 0 | 130 | **169** | 169 |
| Latin–Cyrillic | 2 | 0 | 1,068 | **1,070** | 970 |
| Latin–Han | 4 | 0 | 23 | **27** | 26 |

These counts overlap across sources and scripts. They establish neither directionally correct transliteration nor identity equivalence. The OFAC legacy ZIP supplies substantial population/name evidence but no measured Arabic/Cyrillic/Han alias pairs. Latin–Han remains a major shortfall; 27 unreviewed source-local groups cannot meet the 100 independent final-positive target. Because this entire pool is development-exposed, none of these counts establishes fresh final cases in any direction.

**Duplicates:** exact-name equality nominates 663 group pairs (487 cross-source); conservative normalization nominates **1,259 pairs** (1,078 cross-source), involving 1,607 groups. The normalized total includes the exact pairs; it is not an additional 1,259. There are 596 newly nominated pairs beyond exact equality. These are review candidates, not accepted equivalence edges; no union or deduplication was applied to retained data. Equality discovery does not find all real-world duplicates.

**Application compatibility:** 17 EU name entries in four groups exceed the existing 200-codepoint normalization limit. All original evidence remains retained; nothing was truncated or the limit weakened. Each affected group has some accepted names. Those entries require explicit quarantine or a separately approved compatibility design before application corpus admission. All mechanically audited source provenance checks passed.

## Code, functions and validation

| File | Change / purpose |
| --- | --- |
| [full_acquire.py](../../src/watchlist/ingest/full_acquire.py) | `load_recovery_execution_policy` (893) recognizes a distinct, fixed continuation scope. `_validate_continuation` (1238) binds the prior failed policy/claim/receipt, unchanged source contract, CA hash, fixed reservation and cumulative ceilings; a prior continuation cannot be chained automatically. `continuation_tls_preflight` (1341) requires the exact selected bundle and matching default/explicit CA inventories with full verification. `_claim_recovery_session` (1370) creates an exclusive continuation claim while preserving the original claim schema. `acquire_recovery` (1609) applies the new 30 MB limit, records cumulative accounting and TLS proof, and suppresses completed-purpose grants for this acquisition-only continuation. |
| [test_full_acquisition.py](../../tests/test_full_acquisition.py) | `continuation_fixture` and focused tests cover successful three-request acquisition, reservation/history preservation, replay rejection, invalid ceiling/transaction/release/history/redirect/CA bindings, combined-cap EU rejection before body reads, and native TLS selection failure before a claim. Existing assertions were retained. |
| [continuation policy](../../config/data-sources-step08-continuation.json), private `permissions/` | Exact endpoint/publisher pins, new approval, inherited narrow source permissions and old history hashes. Historical policies/grants were not edited. |
| [tls_client_probe.py](../../data/eval-comparisons/completion-08b-02rc/tls_client_probe.py) | Tests the actual client's context and hostname without network. No monkeypatch is installed in the live worker. |
| [execute_supervised.py](../../data/eval-comparisons/completion-08b-02rc/execute_supervised.py), [run_continuation.py](../../data/eval-comparisons/completion-08b-02rc/run_continuation.py) | Process-local CA configuration, immutable preflight/code pins, one-use supervisor/worker claims, prior normalized-byte reservation and all-directory resource monitoring. Consumed scripts must not be rerun. |
| [audit_continuation.py](../../data/eval-comparisons/completion-08b-02rc/audit_continuation.py), [supervise_audit.py](../../data/eval-comparisons/completion-08b-02rc/supervise_audit.py) | Verify receipt/claim/framing/accounting/selection hashes and provenance, then reuse the existing counting helpers for per-source and combined aggregates. No release/admission API is called. OpenSanctions source aggregates are reused; records are read for cross-source duplicate comparisons. No old whole-journal audit or historical main routine is rerun. |
| README, source permissions, access/resource ledger, this report | Record successful continuation alongside unchanged historical failures and the remaining approval boundary. |

Actual commands and outcomes:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_full_acquisition.py -k 'continuation or recovery or native_tls' -p no:cacheprovider
# 45 passed, 54 deselected in 0.79s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_full_acquisition.py tests/test_corpus.py -k 'continuation or recovery or recovered or native_tls' -p no:cacheprovider
# Final focused run: 64 passed, 258 deselected in 1.55s

.venv/bin/python -B data/eval-comparisons/completion-08b-02rc/execute_supervised.py preflight
# Offline actual-client TLS proof: 120 CAs, both verification checks true, zero requests
.venv/bin/python -B data/eval-comparisons/completion-08b-02rc/execute_supervised.py execute
# One execution only; successful receipt, no resource stop
.venv/bin/python -B data/eval-comparisons/completion-08b-02rc/supervise_audit.py
# Exit 0; 64 named audit checks passed
```

The test runs overlap; do not add their counts as unique tests. The separate 64 audit checks are data/evidence assertions, not 64 more pytest cases. Scoped Ruff format/check passed for changed application/test code and the execution/audit scripts. The one-shot audit supervisor initially had two style-only semicolon diagnostics; its executed source was preserved as `supervise_audit.executed.py`, then formatting and the scoped check passed without rerunning the audit. No full regression suite, secret scan, model rehash, dependency acquisition, duplicate independent review or GitHub CI run was repeated.

[Fictional test log](../../data/eval-comparisons/completion-08b-02rc/focused-final-tests.log), [aggregate audit](../../data/eval-comparisons/completion-08b-02rc/audit-results.json), and [preservation comparison](../../data/eval-comparisons/completion-08b-02rc/preserved-inputs-after.json) supply the evidence. **49 bounded historical/input files were verified unchanged**; this is not a claim to have rehashed the entire workspace or original models. Application changes were limited to the acquisition module and focused tests. No review stores, source snapshots, models, historical experiment outputs or corpus schema were changed.

Fictional example: OFAC consumes some of the new allowance; an EU header then declares 30,000,000 bytes. The combined-budget test rejects EU before reading its body, consumes its request slot, preserves accounting and does not publish a release. A successful download likewise creates candidates and receipts, not human labels.

## Closure and next decision

| Requirement | Result |
| --- | --- |
| Existing certifi bundle used by actual native client, full TLS verification | PASS, offline call-path proof plus verified live HTTPS responses |
| Exact source contracts, narrow permissions, redirect and publisher pins | PASS for the acquired objects; no source substitution |
| Three new transactions / ≤30 MB new bodies / prior 4 MB reservation | PASS; exactly three, 28,481,721 measured bytes, reservation intact |
| Reuse OpenSanctions, preserve history and safeguards | PASS; no OpenSanctions request; bounded preservation comparison |
| Receipt, retained records, hashes, provenance and measured aggregates | PASS, with disclosed language, duplicate and overlength limitations |
| No corpus release, review execution, training, Step 09 or publication | PASS; zero new bound completion grants and no release API invocation |
| Full Step 08 reviewed independent corpus | NOT COMPLETE |

The original targets remain approximately **5,000 usable reference families plus 2,000 independent absent-query families**, at least **200 positive and 200 negative human reviews**, adjudication of every used hard negative, and **100 independent final positives for each claimed direction**. The 13,658 source-local pool is not a count of accepted independent families. Using organizations only would require about 57.9% of the 12,090 candidates to survive as 7,000 distinct usable families; this is a planning break-even ratio, not a measured yield or a guarantee. Vessels must remain a separately declared stratum if used.

**Recommended next bounded package, approval required: offline corpus-readiness and review preparation.** No more acquisition is needed merely to re-obtain these same files. The package should:

1. Freeze an acquisition-evidence inventory and design the explicit continuation admission contract for a later release; do not publish a corpus yet.
2. Prepare deterministic candidate-only review/quarantine packets for the 1,259 nominated equality pairs, the four overlength-affected groups, weak names and missing language evidence. Preserve all source-qualified IDs and provenance; make no identity merges or human decisions.
3. Define organization/vessel strata and reference/absent-family screening rules. Estimate actual reviewer capacity, disagreement adjudication and costs with explicit assumptions; name qualified reviewers before review execution.
4. Produce a concrete legally permitted Latin–Han supplementation proposal and an independently operated final-data custody/access plan. Direct UN remains pending permission and Wikidata remains provisional; neither can be accessed under this continuation. Require future acquisition approval for exact sources, endpoints, seeds, byte/request/time budgets and retention before any call.
5. Keep all development-exposed candidates out of a fresh final claim. Document the later leakage-family and protected-label gates; do not generate Step 09 partitions now.

Proposed planning outputs are `docs/planning/step-08b-corpus-readiness.md`, `docs/planning/step-08b-review-and-custody.md` and `docs/progress/completion-08b-03-plan.md`, with private aggregate packet specifications under a new evidence directory. Reuse the existing corpus/review contracts; any necessary implementation or release change must be specified and approved before execution. Planning needs no new network, paid resource or human-label execution. Acceptance is a reviewable file/field/quarantine plan, explicit human roles and approval costs, and a bounded coverage/custody proposal that preserves all original corpus targets.

**Owner's next decision:** approve that offline readiness/review-preparation planning package. No further acquisition, real labeling, release, training or publication is included or initiated.

## Beginner-friendly 5W1H

- **What:** safely downloaded the two missing sources and measured the resulting candidate pool.
- **Why:** reliable ML experiments need traceable, permitted data; a successful download is only the first step toward correct labels.
- **When:** after recovery/TLS tests, before corpus release, human review and any model experiment.
- **Where:** the new private `completion-08b-02rc` evidence directory; older sessions remain unchanged.
- **Who:** software verifies transfer and structure; publishers set permissions; qualified humans must decide identity and language correctness; an independent custodian must protect final data.
- **How:** exact URLs, one permitted redirect, verified TLS, strict budgets, active resource guards, immutable receipts, focused tests and offline aggregate checks. Next we need a concrete review/custody plan, especially for the Han coverage gap.
