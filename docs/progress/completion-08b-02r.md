# Completion Step 08B-2R — recovery implementation and stopped acquisition

Date: 2026-10-25, Asia/Kolkata. **Implementation and partial-evidence validation completed; acquisition incomplete. APPROVAL REQUIRED for another attempt. Full Step 08 remains incomplete.**

The completed OpenSanctions selection was reused byte-for-byte: **269 organizations and 918 name-evidence entries**, with no new OpenSanctions request. The first OFAC attempt failed before an HTTP response was obtained. The package stopped immediately; EU was not attempted. No automatic retry, direct UN/Wikidata access, human-label review, training, Step 09 or GitHub publication occurred.

The resource monitor was healthy. Offline diagnosis after the failure found a definite local prerequisite missing from the initial preflight: this Python installation's default TLS trust store contained **zero trusted CA certificates**. The installed `certifi` bundle contains **120** and works with certificate verification and hostname checking enabled. The coordinator should have checked this before the attempt. The saved failure code was generic, so the exact failure's underlying exception cannot now be proved. No historical receipt was rewritten to claim a TLS diagnosis it did not record.

## Decisions, limits and source readiness

The user approved the [08B-2R proposal](completion-08b-02.md), with stronger preflight/failure requirements. The [new registry](../../config/data-sources-step08-recovery.json) has SHA-256 `63264e256c20506ede558b9ab533bab207b72f42f0b2483511b0d5219478f91e`. It authorizes only a separate one-use OFAC/EU recovery session, with **34,000,000 additional response-body bytes and at most three charged HTTP attempts**, including failures/redirects. It does not resume or reset the original interrupted session.

| Source | Exact approved route / behavior | Limits and size evidence |
| --- | --- | --- |
| OpenSanctions UN | Reuse the pinned selection from `completion-08b-02/acquisition/opensanctions_un.jsonl`; no request | 512,403 retained bytes, SHA-256 `caade45281bc200519db0a4fc3f645cbb080f183dec781ba19f7bc3c09f23d34` |
| OFAC | `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP`; at most one specifically reviewed redirect below | 4,000,000 bytes combined across at most two requests; 12,000 retained groups; decoded XML ≤32,000,000 bytes; 30 seconds/request, 120 seconds/source. Saved ZIP size 2,582,121; decoded size 29,245,041 and publisher SHA-256 pinned. |
| EU | `https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw`; one direct request, no redirect | 30,000,000 bytes; 2,000 retained groups; 180 seconds/request, 240 seconds/source. Last complete measurement 25,899,600 bytes is historical, not current size proof. |

Only this OFAC storage object may be followed:

```text
https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/c855675f-4385-4bb5-b89a-59ccb73a83e6/2026-10-20/4166a9f5-d268-432a-a70b-65bd16bcd16a/SDN_XML.ZIP
```

The finite existing signing-query validator still applies; signing values are never persisted. A different valid official object may now be recorded **unsigned and rejected**, enabling precise review without another discovery request. Arbitrary hosts/paths or malformed signing parameters are rejected without saving their raw text. No redirect was actually observed in this attempt.

The saved expected OFAC+EU body sizes total **28,481,721 bytes**, within the authorized cap, but do not guarantee current sizes. The implemented runtime gate requires a positive, valid HTTP 200 `Content-Length` within the remaining limits **before reading a dataset body**, with exact OFAC size matching. Complete framing, parsing and publisher pins remain necessary afterward. This uses the approved GETs, not additional HEAD/metadata requests. Neither current size nor current redirect was established by the failed attempt.

The [permission preflight](../../data/eval-comparisons/completion-08b-02r/permissions/preflight.md) validates saved same-day evidence and **41 local evidence references**. OpenSanctions CC BY-NC, narrow OFAC factual-name reuse supported by complete saved section 105 plus import/export guidance, and the exact EU COM_REUSE XML grant remain the basis. The earlier failed full copyright-chapter recapture remains failed. No worldwide or third-party clearance is inferred. New prospective recovery grants permit private, noncommercial, non-person candidate preparation, preserving attribution, original fields and change notices; they are not human labels or completed-acquisition grants. Direct UN remains permission-blocked and Wikidata remains outside authorization.

Resource limits were unchanged: serial requests, no automatic retries; 60-minute session; 1.5/2 GiB RSS soft/hard; ≥25% free host memory at admission, stop below 20% or on pressure warning; ≥10 GiB free disk; ≤100,000,000 normalized bytes and ≤2 GiB total artifacts across the original and recovery directories. Original normalized bytes and their new copy are counted separately. Mixed raw source bodies are not saved.

## Actual execution and accounting

The [supervision record](../../data/eval-comparisons/completion-08b-02r/supervision.json) records normal pressure, **56% host-free memory**, **35,840,155,648 bytes free disk**, and **5,490,690 existing artifact bytes** at admission. The worker exited normally in **1.1235319169936702 seconds**, sampled peak RSS **84,918,272 bytes**, with no resource stop. A normal process exit does not mean acquisition success: the worker correctly saved a partial receipt.

| Source | New charged attempts | HTTP / body outcome | Retained result |
| --- | ---: | --- | --- |
| OpenSanctions | 0 | No transfer; historical completed row preserved separately | 269 reused groups; identical local copy |
| OFAC | 1 | No HTTP status or body obtained; `transport_or_framing_error`; 0 body bytes recorded | Failed; no selection |
| EU | 0 | Not attempted after OFAC failure | No selection |

The new [acquisition receipt](../../data/eval-comparisons/completion-08b-02r/acquisition/receipt.json) has SHA-256 `49cc2b211f3993529ab5ba42fb319f92c4d0c9ccd8bda1b15ae6b793a37e1265`. Its `partial` status counts reused OpenSanctions evidence, **not a successful new source download**. A charged attempt is counted before opening transport, including failure before an HTTP response. The new claim is consumed and cannot be reset or resumed.

| Accounting quantity | Bytes / attempts |
| --- | ---: |
| New response-body bytes returned to the reader | **0** |
| New unresolved OFAC reservation retained conservatively | **4,000,000** |
| New received-plus-reserved accounting | **4,000,000** |
| Unreserved portion of the approved 34 MB recovery allowance | **30,000,000** |
| Recovery attempts charged / authorized | **1 / 3** |
| Original session persisted received lower bound | **15,824,381** |
| Original outstanding EU reservation | **17,190,864** |
| Original conservative accounting | **33,015,245** |
| Combined original + recovery conservative accounting | **37,015,245** |

Reservations are not claims of bytes actually received. The original session's exact final total remains unknown. The new failed attempt preserves its reservation even after closing transport; no speculative refund is taken. Accounting concerns body bytes returned to the reader, excluding headers/TLS/DNS overhead. Two unused request slots do not authorize retrying a consumed source attempt or resetting the claim. All earlier receipts, statuses and uncertainty remain intact.

## Code and evidence changes

| File / function | Explanation |
| --- | --- |
| `src/watchlist/ingest/full_acquire.py`: `load_recovery_execution_policy` (890) | Validates exact recovery scope, limits, permissions and old completed-source anchors before transport. Keeps original completed and interrupted journals distinct; verifies received/reserved accounting without inventing an original final receipt. |
| Same file: `_recovery_redirect` (1263), `_transfer_recovery` (1282) | At most one exact OFAC redirect; combined source/global budgets; per-transaction journals; current size admission; charged partial/error bytes and conservative unresolved reservations. A source failure stops the package. |
| Same file: `acquire_recovery` (1459) | Uses a new exclusive claim, copies verified OpenSanctions bytes, attempts only OFAC/EU, and produces an explicit separate-session envelope. Bound completion grants require all three completed sources. |
| Same file: `_native_tls_preflight` (90), safe transport-error classification | Added **after the failed attempt**. Native requests require a real SSL context, `CERT_REQUIRED`, hostname checking and a nonempty loaded CA store before output/claim/request creation. Covers default and explicitly supplied native transports; sealed fictional transports remain usable offline. TLS certificate, TLS protocol, DNS, connection and framing failures now receive distinct safe codes without exception text/signing values. |
| `src/watchlist/ingest/resource_guard.py`: `_artifact_size` (516), `system_snapshot` (614), `ResourceGuard` | Preserves at most three complete rescans on disappearing temporary entries; persistent failure still stops. Adds fixed subprobe diagnostics, explicit combined artifact roots and initial normalized-byte reservations. It does not reset disk limits by using a new directory. |
| `src/watchlist/corpus.py`: `bind_recovered_full_permission` (3067), `prepare_recovered_full_source` (3118), `_recovery_manifest` (3246) | Admits only a complete, explicitly scoped recovery assembly with exactly three sources from one new receipt. Stores separate-session lineage and verifies old interrupted history. Original admission API remains restricted to its original scope. All training/evaluation eligibility stays false. SQL schema unchanged. |
| `tests/test_full_acquisition.py`, `tests/test_resource_guard.py`, `tests/test_corpus.py` | Fictional recovery, stale/cross-session evidence, incomplete receipt/body, reservations, exact redirects, no signing-value leaks, monitor races, empty TLS trust, immutable publication and end-to-end admission regressions. |
| `config/data-sources-step08-recovery.json`, new private `permissions/` | Exact approved policy, source grants, old evidence anchors and reviewed redirect contract. These executed files were not rewritten after the failure. |
| New `run_recovery.py`, `execute_supervised.py` | Actual one-use worker/supervisor scripts. Preserve them as execution history; do not rerun a consumed session. |
| New `audit/audit_recovery.py`, `audit/run_recovery_completion.py` | Validate the new envelope, reuse unchanged old aggregates when no new selection exists, and prevent candidate publication from partial receipts. Complete packages can reuse prepared source objects for publication without duplicate parsing. |
| `transport-trust-diagnosis.json`, validation logs, supervision/audit receipts | Record the local TLS defect, offline configured-bundle proof, actual test outcomes and the distinction between tested code and code executed before the fix. |
| README, access/resource ledger, source permissions, this report | Update living status without rewriting historical reports or original corpus targets. |

The [pre-network gate](../../data/eval-comparisons/completion-08b-02r/pre-network-gate.json) correctly records the checks then performed and the execution code hash, but omitted TLS trust readiness. It is not proof of a complete preflight. Acquisition executed `full_acquire.py` hash `b855178293c91797d2b96f0e5f3bab80daca1903690dd88400fe2c1dcee1512f`; the later TLS fix is hash `033d7480a112d3b5c732f6eff6042fce012d2e283c64a454ae9e627e19bee6b1`. **No live attempt used the later fix.**

## Tests, commands and limitations

| Focused validation | Actual result / evidence |
| --- | --- |
| Initial acquisition implementation | 72 passed in 1.87 s; [log](../../data/eval-comparisons/completion-08b-02r/storage-validation.json) |
| Redirect-evidence fix / historical fixture correction | 19 recovery tests passed, 54 deselected in 0.37 s; [incremental log](../../data/eval-comparisons/completion-08b-02r/storage-incremental-validation.json) |
| Native TLS preflight and failure diagnostics | 35 passed, 54 deselected in 0.61 s; [final focused log](../../data/eval-comparisons/completion-08b-02r/storage-tls-validation.json) |
| Resource guard | 63 passed in 0.21 s; [review and commands](../../data/eval-comparisons/completion-08b-02r/resource-audit/resource-review.json) |
| Corpus | 223 passed in 1.24 s; [validation](../../data/eval-comparisons/completion-08b-02r/corpus-focused-validation.json). Whole corpus-file run was justified by shared receipt/manifest changes. |
| Concurrent publication workload | 200 actual fictional journal publications, 102 concurrent measurements plus final, 1.661211 s; final 10,800 bytes exact. Fifteen measurements needed two scans; none failed. |
| Actual partial-receipt audit | 72 checks passed; [completion evidence](../../data/eval-comparisons/completion-08b-02r/audit/completion.json). Separate from pytest counts. |

These runs overlap; do not add their counts as unique tests. Scoped Ruff/format checks passed. No project-wide suite, secret scan, dependency/model download or model rehash was repeated. The earlier 2,606-test result remains historical.

The first corpus integration reached successful writer → binding → admission → build/load, then its overwrite test expected the wrong exception class. The immutable publisher correctly raised `FileExistsError`; the test expectation was corrected. The historical fictional fixture was also corrected to represent the real OS-completed journal separately from the later EU-running journal. Runtime acceptance assertions were not weakened.

Representative commands actually run (full logs linked above):

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q tests/test_resource_guard.py --junitxml=data/eval-comparisons/completion-08b-02r/resource-audit/resource-tests.xml
.venv/bin/python -B -m pytest -q tests/test_full_acquisition.py -p no:cacheprovider
.venv/bin/python -B -m pytest -q tests/test_full_acquisition.py -k 'recovery or native_tls' -p no:cacheprovider
.venv/bin/python -B data/eval-comparisons/completion-08b-02r/execute_supervised.py 63264e256c20506ede558b9ab533bab207b72f42f0b2483511b0d5219478f91e
```

The real audit command, input hashes and results are in its [report](../../data/eval-comparisons/completion-08b-02r/audit/report.md). It ran under [resource supervision](../../data/eval-comparisons/completion-08b-02r/audit-supervision.json), using the remaining original session time rather than resetting the 60-minute window; exit zero, no resource stop, sampled peak RSS 32,718,848 bytes. It created **no candidate database**, because all three sources were not complete.

The [TLS diagnosis](../../data/eval-comparisons/completion-08b-02r/transport-trust-diagnosis.json) records absent default CA paths and zero loaded roots. An isolated subprocess set only:

```text
SSL_CERT_FILE=/Users/odin/Desktop/polyglot-watchlist-starter/.venv/lib/python3.14/site-packages/certifi/cacert.pem
```

That existing bundle's path/hash is recorded; the subprocess loaded 120 CAs with `CERT_REQUIRED` and hostname verification, with socket access denied. No global environment/configuration, dependency or verification requirement changed. This demonstrates local readiness with that setting, **not a successful TLS handshake with OFAC**. Future authorized worker execution must explicitly select and verify this existing bundle; the unconfigured empty-store path now fails before spending a request or claim.

## Measured yield, preservation and remaining Step 08 requirements

No new source selection was completed. The [new aggregate audit](../../data/eval-comparisons/completion-08b-02r/audit/report.md) verified the identical selection and prior aggregate hashes, then reused the existing measurements. It did not repeat the old 118-check audit or 1,022-journal scan.

- **269 organizations**, 918 name entries, 913 distinct strings; 154 groups with multiple distinct names.
- Fields: 274 primary-name property occurrences, 627 alias-property occurrences, 17 previous-name occurrences. All 918 supplied language tags are missing; no explicit weak markers or overlength-name rejections.
- Script occurrences: 873 Latin, 43 Arabic, two Cyrillic and four Han (mixed scripts can overlap). Candidate group pairs: **39 Latin–Arabic, two Latin–Cyrillic, four Latin–Han**.
- Three exact-name duplicate pairs; conservative normalization adds none. They involve three groups, not a confirmed identity family.
- The prior overlap result remains historical: all earlier 200 OpenSanctions IDs recur; 69 additional source-local IDs do not establish 69 independent identities. All 269 groups remain developer-exposed.
- Historical completed input: 2,905 records, with 732 persons and 1,904 other records excluded; zero cap exclusions. This attempt supplies no OFAC/EU parsed/rejected-record counts; those are unavailable, not zero.
- **Zero** human decisions, reviewed usable labels, identity merges, final-eligible groups or accepted corpus releases.

The limited [preservation baseline](../../data/eval-comparisons/completion-08b-02r/preserved-inputs-before.json) covers 11 relevant old files, not the entire workspace or models. The [final comparison](../../data/eval-comparisons/completion-08b-02r/preserved-inputs-after.json) records their result. The TLS-fix log separately verifies unchanged executed policy, claim, worker and receipt. New audit input/code hashes remained unchanged during its run. Old reports, source snapshots and review stores were not rewritten.

Fictional example: an OFAC response declares a different ZIP size → the size gate rejects it before body reads, consumes the attempt and stops EU. A fictional old record renamed from `Fictional Former Harbor` to `Fictional Current Harbor` retains its former-name exposure history; renaming never makes it fresh evaluation data.

The unchanged Step 08 targets remain about **5,000 usable reference families + 2,000 independent absent-query families**, at least **200 positive and 200 negative reviews**, adjudication of every used hard negative, and **100 independent final positives per claimed direction**. Full source acquisition, cross-source equivalence review/quarantine, a real label ledger, qualified multilingual reviewers and protected fresh final-data custody are still missing. Sanctions-domain evaluation cannot be replaced by generic organizations; shared developer-exposed data cannot become fresh final cases by relabeling or copying it. Step 09 prerequisites are not met.

## Closure and exact next approval

| Phase | Decision |
| --- | --- |
| Recovery implementation | PASS with focused tests, explicit lineage, reserved accounting and safe failure states. |
| Initial pre-acquisition checks | Permission/route/size-policy and resources passed; **TLS trust prerequisite was missed**. Offline correction now passes, but provider connectivity is unverified. |
| Bounded acquisition | STOPPED after one charged OFAC attempt; no body obtained, EU unattempted. No retry. |
| Validation/reporting | PASS for partial evidence; complete corpus release correctly withheld. |
| Full Step 08 | INCOMPLETE. |

Recommend an explicitly approved **replacement OFAC/EU attempt using the remaining byte allowance**, rather than another blanket 34 MB allocation:

1. Preserve both consumed claims and both partial/interruption records. Create a distinct continuation policy/claim that binds this failed recovery receipt and carries forward its **4,000,000-byte reservation**. No history rewrite or automatic resume.
2. Configure the isolated worker with the hash-verified installed CA bundle above. Check loaded trust/verification flags and resources before creating its claim; use existing focused tests and only add tests required by the new cumulative-accounting policy.
3. Permit **three new charged HTTP attempts**: OFAC export plus at most its one exact reviewed redirect, then one direct EU request. This raises the recovery attempt ceiling from **three to four cumulatively**: one already spent plus three new. It is **one additional request slot**, and an explicit replacement-source attempt—not automatic retry permission.
4. Cap new received response bodies at **30,000,000 bytes combined**, keeping OFAC's ≤4,000,000-byte/source cap and EU's ≤30,000,000-byte/source cap, each further restricted by the remaining combined allowance. The failed attempt's reserved 4 MB plus the proposed 30 MB remains within the **existing 34 MB recovery byte ceiling**. Original-session conservative accounting plus that ceiling remains **67,015,245 bytes**; no larger byte ceiling is requested.
5. Expected OFAC/EU bodies total 28,481,721 bytes, leaving **1,518,279 bytes** under the proposed 30 MB cap before redirect/error bodies. Current headers may differ; reject before body reads if they do not fit. Keep exact endpoints/object, publisher pins, no automatic retries, all retention/memory/disk safeguards and the 60-minute session limit. Count all retained original/recovery/continuation directories together; do not refresh the 2 GiB/100 MB ceilings.
6. On complete success, verify the distinct multi-session manifest, produce the candidate audit/release, and return for review/custody decisions. On any failure, preserve evidence and stop. No additional discovery call, source substitution, UN/Wikidata, labels, training, Step 09 or publication.

Implementation scope for that decision is limited to the existing acquisition/corpus budget-binding code and relevant focused tests, a new continuation policy/private evidence directory, an explicitly configured worker and updated status report. The current 34 MB policy is immutable and not executable again. Historical supply remains an unverified future-yield scenario: 11,610 OFAC + 1,779 EU source-local groups; overlap, script yield and usable independent-family acceptance still need measurement. Earlier storage/review-cost estimates remain assumptions in the [08B-2 report](completion-08b-02.md), not new measurements.

**Exact owner decision:** authorize that one replacement attempt package—**three new requests, one additional request slot cumulatively, at most 30 MB new bodies within the unchanged 34 MB recovery ceiling**—with the verified local CA configuration and strict gates. This request is required by the user's no-automatic-retry/new-batch boundary and exhausted source attempt, not by a new inferred approval rule.

## Beginner 5W1H

- **What:** made recovery explicit, reused the good source, attempted OFAC once and stopped safely; found and guarded a missing certificate setup.
- **Why:** a receipt is the acquisition record. An interrupted receipt must not be rewritten as success, and HTTPS needs trusted certificates before it can safely identify a server.
- **When:** before full corpus assembly and any human labeling or independent ML splits.
- **Where:** new private `completion-08b-02r` evidence; existing artifacts remain historical.
- **Who:** software checks integrity/resources; publishers determine allowed reuse; the owner authorizes another attempt; qualified humans and a separate custodian must later establish labels and freshness.
- **How:** pinned policy, one-use claims, conservative reservations, strict size/redirect/TLS gates, focused fictional tests, guarded execution and reuse of verified aggregate evidence.

Stop here pending the explicit continuation decision.
