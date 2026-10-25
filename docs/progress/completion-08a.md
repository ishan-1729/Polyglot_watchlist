# Completion Step 08A — planning and offline audit

Date: 2026-10-25, Asia/Kolkata. **Step 07: COMPLETE under the approved revision. Step 08A: COMPLETE as planning/offline analysis. Full Step 08: NOT COMPLETE. Step 08B: APPROVAL REQUIRED.**

This report follows the completion-plan numbering, which is distinct from the older application `phase-NN` sequence. Those historical phase reports are preserved. This is the new detailed progress record for the user's DECISION 2; it does not replace any earlier report.

## What was completed

Applied the explicit three-source Step 07 revision and verified its evidence before beginning Step 08A. OpenSanctions UN, OFAC and EU each supplied 200 retained source-local groups. Direct UN and Wikidata remain investigated but not acquired. The [formal closure](completion-07-approved.md) records the permission evidence, receipts, 520 passing offline acquisition/parser tests, lint/preflight results and unchanged historical records. No excluded source is represented as successful.

For Step 08A, five existing specialist workers divided the offline work into audit, source feasibility, corpus design, partition/custody design, and evidence/resource verification. The coordinator integrated their documents, resolved inconsistencies and completed final checks. The authoritative proposal is the [central plan](../step-08a-plan.md). The original Step 08 requirements remain verbatim in the completion plan.

No network request, new source acquisition, paid resource, training, human label, identity merge, partition, final-label inspection or corpus release was performed. No application module, dependency, GitHub publication checkout or CI workflow was changed. Resolved infrastructure was not reopened, and no hosted CI run was requested.

## Measured audit findings

| Observation | Result | Interpretation |
| --- | ---: | --- |
| Existing source-qualified groups | 600; 200 per successful source | Provider records, not 600 confirmed independent identities. |
| Name-evidence entries / distinct original strings | 3,293 / 3,072 | Alias count is not independent sample size. |
| Multiple-name / singleton-name groups | 386 / 214 | Singletons have no within-record natural positive pair; their broader usability still needs review. |
| Missing language tags | 1,824 entries, 55.39%; 482 groups have none | Script detection cannot fill language, nationality or identity labels. |
| Explicit weak names | 49 entries across 23 OFAC groups | Preserve strength evidence; do not automatically count these as reliable positives. |
| Latin–Arabic / Latin–Cyrillic / Latin–Han script presence | 35 / 96 / 4 groups | Candidate coverage only; none establishes the final evaluation target. |
| Strict single-script pair candidates | 35 / 88 / 4 groups | Mixed-script evidence explains the difference from presence counts. |
| Exact / normalized duplicate candidate pairs | 69 / 83 | Normalization adds 14 cross-source candidates. None is a reviewed merge. |
| Normalized pair breakdown | 4 within-source; 79 cross-source; 166 involved groups | Candidate components have size two in this sample; not a global deduplication result. |
| Mechanical structure/provenance failures | 0 | Required fields, types, source classifications and primary-name membership passed. This is not legal or factual identity certification. |
| Provider referents | 5,687 distinct OpenSanctions referents | Not resolved externally; unmatched references in a capped subset are not automatically invalid. |
| Existing selected JSONL files | 1,152,233 bytes | Approximately 1,920 bytes/group for this biased sample. |
| Parsed object / peak traced loading allocation | 5,713,492 / 5,853,756 bytes | Excludes interpreter baseline; not RSS or full mixed-source acquisition memory. |

All 3,293 names fit the application's current 200-code-point normalization limit; no name was truncated. The audit saves aggregates, not source names, identifiers, candidate endpoints or individual-name hashes. All inputs retain their original whole-file hashes.

Source-local yield in completed Step 07 inputs was 269 OpenSanctions, 11,610 OFAC and 1,779 EU eligible records, totalling 13,658 before the retention cap. The retained first-200 samples are biased; their script fractions cannot safely predict complete-input coverage. The existing 600 are a subset of those 13,658, not additional supply.

## Targets, review and scientific independence

The plan preserves approximately **5,000 usable reference families plus 2,000 additional independent absent-query families**, at least **200 proposed positive and 200 negative candidate reviews**, adjudication of every hard negative actually used, and **100 independent final positive families per claimed Latin↔Arabic, Latin↔Cyrillic and Latin↔Han direction**. Translation, transliteration and spelling variation remain separate tags.

The primary absent cohort is a controlled fixed-index experiment: choose 2,000 independently reviewed families and exclude every equivalent copy from the declared reference index. They cannot also count toward its 5,000 reference families. “Absent” means no equivalent record in that index; it does not mean globally unsanctioned. Natural background nonmembers may be a separately reported supplement. Uncertain identity/non-equivalence links quarantine the affected components before splitting.

Obtaining 7,000 accepted independent families from the observed 13,658 source-local candidates requires about 51.25% accepted independent yield. That is a break-even calculation, not an observed acceptance rate. The plan therefore neither promises the targets from one tranche nor reduces them if the tranche falls short.

The currently inspected 600 groups and equivalent copies/descendants are conservatively marked exposed development/learning candidates. Fresh protected material needs actual separate custody before acquisition or inspection through developer-accessible paths. Under strict 15% final allocation within a script stratum, at least 667 fresh eligible families are needed to reserve 100 final positives; a predeclared stratified policy is an alternative, with no favorable-seed search. Later Step 09 keeps whole families in approximately 50/15/10/10/15 training/development/calibration/threshold/final roles. No role assignments were made here.

The corpus design separates source evidence, reviewed equivalence, leakage-family dependence, uncertain links, review events and immutable releases. Similarity scores and shared parent/subsidiary relationships cannot become identity labels automatically. A single reviewer is not claimed to be independent double review; named qualified reviewers, disagreements, exclusions and final custody remain real execution requirements.

## Source decisions and unresolved inputs

Direct UN remains legally pending: an applicable list-specific grant or written permission covering compilation, normalization/indexing and local matching is missing, alongside verified permitted endpoint access. A working URL would not resolve the rights question. No permission inquiry or download was sent.

Wikidata's Action API is the provisional supplemental candidate for bounded known-QID labels, aliases and type evidence. Saved evidence supports the historical CC0 assessment and prior WDQS/User-Agent rules; it does not verify today's Action or REST API contract. Prior HTTP 504 failures remain preserved, without inventing a server-side cause. REST is a separately reviewable alternative, not an automatic fallback.

The 600 records yielded no established QID seed inventory under the documented exact-pattern scan. A curator must supply and review finite seeds/search terms; discovery bias, complete type-graph checks, statement ranks, revision provenance and complete multilingual fields require verification. Initial direct organization qualification remains unchanged. Wikidata cannot silently substitute for fresh sanctions-domain evaluation or establish absence labels by membership alone.

## Resources and next package

Read-only host observations recorded 16 GiB RAM, 47% OS free-memory estimate and 50.03 GiB free disk. These are snapshots, not reserved capacity. Full acquisition peak RSS and human review throughput are unmeasured.

The detailed proposal retains the original 100 MB planning ceiling but allocates only a **59 MB first tranche**: 5 MB official metadata, 5 MB OpenSanctions, 4 MB OFAC, 30 MB EU and 15 MB conditional Wikidata pilot. The remaining 41 MB is unallocated. None is authorized by this planning report. Caps include failures, with no automatic retry or source substitution. The [central plan](../step-08a-plan.md) owns the exact request, per-response, retention, deadline, decoded-size, disk and memory limits.

The proposed safeguards include 1.5/2 GiB soft/hard aggregate acquisition RSS, 2 GiB total new artifacts, 100 MB normalized selections, at least 10 GiB free disk, OS memory admission/stop thresholds, and at most 60 minutes live work. They require implementation and fictional tests; they are not existing controls. Mixed raw responses remain memory-only.

An explicitly assumed 2–5 minutes to screen each of 7,000 accepted families implies about 233–583 reviewer hours before difficult identity work, disagreement and independent review. The minimum 400 label items at an assumed 3–10 minutes require 20–66.7 hours per pass. These overlap and must not be added into a project total. Cash cost is approved hours multiplied by an agreed rate; no quote, hiring commitment or paid resource is established. A human pilot must measure actual effort.

**Recommended next approval is deliberately partial:** 08B-0 offline implementation plus 08B-1 official metadata/source preflight only, capped at 5,000,000 received body bytes, 16 HTTP transactions including redirects, 512,000 bytes per response, 30 seconds/request, no automatic retries, and 60 minutes overall. This would not activate the other 54 MB, dataset branches, human review, training or Step 09. Current `fetch --profile full` is unimplemented; offline implementation must precede its use. Concrete endpoint policy, reviewer/custodian readiness and conditional seed/API decisions must be reviewed before separate live-dataset approval.

## File-by-file explanation

| File | Purpose and completed work |
| --- | --- |
| [Central plan](../step-08a-plan.md) | Integrates preserved targets, measured audit, 7,000-family path, script coverage, exact bounded package, proposed files/tests and approval boundary. |
| [Source feasibility](../planning/step-08a-source-feasibility.md) | Distinguishes cached permission facts from unverified Action/REST contracts; designs bounded discovery and type checks; keeps direct UN blocked. |
| [Corpus design](../planning/step-08a-corpus-design.md) | Defines proposed schema, source-qualified IDs, review/equivalence/quarantine/release contracts, 18 invariants and 19 fictional acceptance cases. These are designs, not executed implementation tests. |
| [Partition and approval gates](../planning/step-08a-partition-and-approval-gates.md) | Maps user and original Step 08/09 obligations; defines exposure, family allocation, withholding, absence, custody and invalidation rules. |
| [Resource plan](../planning/step-08a-resources.md) | Separates measured size/host facts from extrapolations; specifies request/time/memory/disk bounds and human effort scenarios. |
| [Offline audit helper](../../data/eval-comparisons/completion-08a/audit/audit_existing.py) | Reproduces aggregate counts and checks from hash-anchored existing selections; denies socket use and emits private aggregate evidence. It is an analysis artifact, not a new application command. |
| [Audit results](../../data/eval-comparisons/completion-08a/audit/results.json), [report](../../data/eval-comparisons/completion-08a/audit/report.md), [receipt](../../data/eval-comparisons/completion-08a/audit/receipt.json) | Save machine-readable counts, readable findings, whole-file hashes, command and 34 named successful checks. |
| [Artifact verifier](../../data/eval-comparisons/completion-08a/audit/verify_outputs.py), [verification](../../data/eval-comparisons/completion-08a/audit/verification.json) | Verify 15 output-integrity, privacy, syntax and network-denial checks. |
| [Resource probe](../../data/eval-comparisons/completion-08a/resource-probe.json) | Saves read-only commands, host observations and scenario arithmetic. |
| README and access/resource ledger | Replace stale “Step 08 has not started” wording with 08A planning complete / 08B unapproved, and link current evidence. |
| [Final validator](../../data/eval-comparisons/completion-08a/validate_completion.py), this report and final validation receipt | Provide phase teaching, actual results, traceability and final preservation/link/scan evidence. |

Step 07's living plan, permissions and two policy JSON changes are explained separately in its [closure report](completion-07-approved.md). No historical progress report was edited.

## Audit code walkthrough

Function names and line anchors refer to the saved audit helper, not future application code:

| Function (starting line) | What it does and why |
| --- | --- |
| `deny_network` (26) | Rejects every `socket.*` audit event so accidental networking fails locally. |
| `check`, `digest`, `read_input` (74, 81, 86) | Record named assertions, hash whole files, reject unsafe input paths and anchor unchanged evidence. Individual names are not hashed into outputs. |
| `normalized_key`, `weak`, `summary` (101, 112, 122) | Apply NFKC/case/whitespace cleanup without truncation; identify explicitly weak fields; compute integer-size summaries. Normalized equality only proposes candidates. |
| `object_size`, `load_memory` (136, 153) | Estimate reachable Python object bytes and traced load allocations; neither claims full process RSS. |
| `pairs_from_keys`, `component_histogram`, `pair_summary`, `collision_summary` (173, 185, 206, 222) | Build candidate pairs and aggregate graph/source counts without outputting endpoints. Indexed candidate discovery is checked against brute force. |
| `referent_summary` (241) | Count provider references without declaring equivalence or resolving them on the network. |
| `structurally_valid`, `provenance_valid`, `audit_source` (276, 309, 355) | Check field contracts and source-specific classification/name evidence, then measure names/scripts/strength/lengths. |
| `json_bytes`, `scalar_strings`, `private_new_file`, `write_report` (481, 485, 496, 502) | Serialize deterministic aggregates, inspect output disclosure, refuse overwriting and write private evidence/report files. |
| `main` (565) | Orchestrate hash checks, read-only audit, fictional normalization examples, aggregation and receipt creation. |
| Verifier `deny_network`, `digest`, `strings`, `main` (18, 28, 32, 42) | Independently check saved artifacts, structured text disclosure, private modes and that socket creation is denied before connection. |

The final validator uses `deny_network` to block sockets, `digest` to hash whole artifacts, `read` to load explicit receipts, and `main` to check preservation, links, fences and recorded results before writing a new receipt. It distinguishes the intentional living-ledger status update from frozen evidence. Its preliminary hash comparison included a heading marker absent from the original snapshot convention; matching that convention confirmed preservation without changing the plan text.

Fictional input `  Fable　Harbor  ` becomes `fable harbor`. This nominates equality candidates; it does not establish an identity. A fictional 201-code-point name is rejected by the existing application normalizer, not truncated by this audit. No real example or final label is exposed.

## Commands, actual results and limitations

The approved Step 07 closure ran the source-test/lint Make targets and offline acquisition preflight; their saved logs show **520 passed** and exit zero. Step 08A ran:

```sh
.venv/bin/python -B data/eval-comparisons/completion-08a/audit/audit_existing.py
.venv/bin/python -B data/eval-comparisons/completion-08a/audit/verify_outputs.py
.tools/qa/bin/python -I -B -m ruff check data/eval-comparisons/completion-08a/audit/audit_existing.py data/eval-comparisons/completion-08a/audit/verify_outputs.py
```

Results: **34 audit checks passed; 15 verifier checks passed; scoped Ruff passed.** The first verifier attempt had a false positive: a three-character source string appeared inside an unrelated capitalized status word. Complete-name Unicode-boundary checks corrected that error while retaining the stricter substring check for longer names. The failed attempt and correction are recorded, and no source value was printed. The audit refuses existing output files; reruns need a reviewed new output destination rather than overwriting evidence.

Read-only resource commands were `sysctl -n hw.memsize`, `vm_stat`, `memory_pressure -Q`, and standard-library Python disk/file-size probes. Local `rg` and Python HTML/JSON inspection supported the source/requirements review and QID pattern scan. No current external service was contacted.

Final integration uses the existing offline secret scanner and a local hash/link/requirements validator:

```sh
.tools/qa/bin/python -I -B scripts/project_checks.py secret-scan --output /Users/odin/Desktop/polyglot-watchlist-starter/data/eval-comparisons/completion-08a/final-secret-scan.json
.venv/bin/python -B data/eval-comparisons/completion-08a/validate_completion.py
```

The final validator also passed scoped Ruff. Its exact command, exit status, file count and preservation findings are saved in [final-validation.json](../../data/eval-comparisons/completion-08a/final-validation.json); the [secret-scan receipt](../../data/eval-comparisons/completion-08a/final-secret-scan.json) defines the publication scope actually scanned. This scan is not a claim about every private artifact. Existing input hashes, original Step 08 text and all 20 pre-existing progress reports are checked again. The fresh audit's separate privacy checks cover its private aggregate outputs.

Remaining limitations are substantive data work: unknown accepted independent yield, severe Han shortfall, missing language metadata, unreviewed duplicate candidates and weak aliases, unverified current API contracts, missing curator seeds, human review capacity/custody, unimplemented full-profile safeguards, and purpose-specific permission checks before larger acquisition or later training/release. None is silently marked complete.

## Traceability of the ten requested deliverables

1. Existing 600-group usability, duplicate, script and provenance audit: private aggregate audit and verification.
2. Approximately 5,000 reference plus 2,000 independent absent groups: central 7,000-family supply and yield scenarios.
3. Arabic/Cyrillic/Han priority and 100 final groups per direction: central coverage gate, fresh-family bound and corpus review contract.
4. Action versus REST suitability: source feasibility comparison with explicit current-contract uncertainty and no sanctions-domain substitution.
5. Direct UN legal hold: preserved source registry/permissions, closure and source plan.
6. Schema, source-qualified IDs, equivalence/quarantine, human review and immutable releases: corpus design.
7. Measured acquisition/disk/memory/time/review estimates: resource probe, audit memory measurements and resource plan; assumptions labelled.
8. Exact bounded Step 08B and approvals: central 59 MB proposal and partial 5 MB next recommendation; none executed.
9. Step 09 independence: partition/custody plan, all-copy exclusion, exposure ledger design and whole-family allocation.
10. Detailed progress, file/function explanations, evidence, commands, risks and 5W1H: this report and linked receipts.

## Beginner-friendly recap and stop

**What:** we closed the approved feasibility step and designed the larger reviewed corpus. **Why:** more aliases do not automatically mean more independent identities or correct labels. **When:** after verified Step 07 evidence, before any new acquisition or training. **Where:** local planning documents and private aggregate audit artifacts. **Who:** the owner approves resources, publishers grant reuse rights, qualified human reviewers judge identity/name relationships, and an independent custodian protects final evaluation. **How:** preserve source evidence, nominate and review candidates, quarantine uncertainty, freeze immutable releases, then allocate complete families without leakage.

Recommended next action: approve only **08B-0 offline implementation and 08B-1 bounded official metadata preflight**, under the explicit 5 MB limits above. Separate readiness review and authorization remain necessary for dataset acquisition and human-review execution. Work stops here as requested; full Step 08 remains open until its actual corpus, label-review, provenance and coverage acceptance criteria pass.
