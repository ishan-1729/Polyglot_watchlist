# Phase 3 completion: existing RapidFuzz evaluation

Phase 3 Step B was explicitly approved. Implementation and evaluation are complete; Phase 4 has not begun.

## What changed and why — 5W1H

- **What:** deterministic spelling queries, frozen reference views, partition/overlap checks, ranking metrics, timing and JSON/Markdown reports around the unchanged Phase 1 matcher.
- **Why:** passing software tests says the implementation works as specified; evaluation reveals whether its ranking helps under declared query changes.
- **Who:** the learner reviews the protocol and examples; the program computes results; public provider IDs supply working record labels, not verified identities.
- **When:** settings were fixed before benchmark runs. Training/calibration groups stayed reserved. A new scorer or dataset needs a later approved experiment.
- **Where:** source under `src/watchlist/`, tests under `tests/`, fictional config/results under `eval/`; public detailed results stay local under `data/evaluation/public-small/`.
- **How:** frozen data → labeled query and reference views → audits → existing RapidFuzz → ranks/timing → metrics with denominators → human review.

The [protocol ADR](../adr/0002-evaluation-protocol.md) contains the DAG, definitions, decisions, query/index policies and limits. The [data card](../data-card.md) retains public-source terms and attribution.

## Actual results

All **126 tests passed in 0.87 seconds** on the final test run. Both full benchmark runs were then repeated in memory; all queries, rankings, audit records and non-timing results matched the saved results exactly. No new dependencies were installed.

These headline rows include only eligible **test challenge** queries, excluding exact/formatting sanity checks and diagnostic ambiguities:

| Dataset | Index entities | Positive queries / target groups | Recall@1 | Recall@10 | Recall@50 | MRR |
|---|---:|---:|---|---|---|---|
| fictional | 12 | 27 / 3 | 20/27 = 0.7407 | 25/27 = 0.9259 | N/A: k covers corpus | 0.792094 |
| public-small | 20 | 141 / 6 | 129/141 = 0.9149 | 141/141 = 1.0000 | N/A: k covers corpus | 0.943282 |

A high public Recall@10 here means finding a record among half of a 20-record index. It does not predict retrieval against thousands of entities. The 141 public challenge queries come from only six target groups and are not independent observations. Results are query-weighted, so entities with more aliases contribute more. No confidence interval, identity accuracy, operational guarantee or probability is claimed.

Fictional run: 94 queries, comprising 65 eligible positives across sanity/challenge, 26 diagnostic queries and 3 absent queries; zero skipped operations. Public run: 272 queries, comprising 269 eligible positives and 3 diagnostics; seven skipped operations. Skips include single-token word transformations and entities without a second normalized name. Complete reasons are saved in JSON.

The fictional absent-target suite returned suggestions for **3/3 queries**. This is the expected unthresholded behavior, not a measured threshold FPR. No public absent-target ground truth was invented.

### Test challenge slices

| Dataset | Perturbation/script | Positive queries | Top-1 hits | MRR |
|---|---|---:|---:|---:|
| fictional | kind:adjacent_swap | 6 | 6 | 1.000000 |
| fictional | kind:deletion | 6 | 6 | 1.000000 |
| fictional | kind:heldout_alias | 3 | 2 | 0.833333 |
| fictional | kind:missing_word | 6 | 6 | 1.000000 |
| fictional | kind:word_order | 6 | 0 | 0.147757 |
| fictional | script:ARABIC | 5 | 3 | 0.716667 |
| fictional | script:LATIN | 22 | 17 | 0.809237 |
| public-small | kind:adjacent_swap | 36 | 36 | 1.000000 |
| public-small | kind:deletion | 36 | 36 | 1.000000 |
| public-small | kind:heldout_alias | 4 | 3 | 0.800000 |
| public-small | kind:missing_word | 31 | 30 | 0.983871 |
| public-small | kind:word_order | 34 | 24 | 0.803023 |
| public-small | script:ARABIC | 4 | 4 | 1.000000 |
| public-small | script:LATIN | 137 | 125 | 0.941626 |

Fictional word-order changes performed poorly: 0/6 targets ranked first. Character-order edit similarity does not ignore token order. This is an observed limitation, not a reason to silently substitute token-sort scoring. The small Arabic slices do not establish multilingual competence; some queries still have same-script reference aliases. Available reference scripts are recorded per query. Empty Cyrillic test challenge slices are N/A, not zero accuracy.

### Search timing

| Dataset | Queries | Timed calls | Median ms | p95 ms |
|---|---:|---:|---:|---:|
| fictional | 94 | 1880 | 0.02 | 0.021042 |
| public-small | 272 | 5440 | 0.058792 | 0.065625 |

Environment recorded by the run:

```json
{
  "python": "3.14.0",
  "platform": "macOS-27.0.1-arm64-arm-64bit-Mach-O",
  "machine": "arm64",
  "processor": "arm",
  "rapidfuzz": "3.14.6"
}
```

One warm-up call per query precedes 20 measurements. The timer includes current normalization, alias comparison and sorting; database loading, query generation and output writing are excluded. p95 uses nearest rank: sorted measurement at `ceil(0.95 × n)`. Small timings vary with hardware/load; these are not service latency or throughput guarantees. Repeated timing observations are not additional accuracy examples.

## Worked examples from actual saved rankings

### Example 1: heldout_alias

Query: `سيرا لومين`. Original: `سيرا لومين`. Target: `syn-007`. Reference view: `heldout`.

| Rank | Record | Matched alias | Similarity |
|---:|---|---|---:|
| 1 | syn-006 | Naro Zefir | 10.000000 |
| 2 | syn-007 | Sira Lumen | 10.000000 |
| 3 | syn-008 | Daro Nuvem | 10.000000 |

Target rank: **2**. Recall@1 contribution: **0**; Recall@10 contribution: **1**; reciprocal rank: **1/2 = 0.500000**. Recall@50 is N/A for the 12-record corpus.

The Arabic alias was removed from the target reference; the remaining target alias is Latin. Several candidates tie at 10.0, and stable ID ordering puts the target second. Matching the space and other character structure is not evidence of translation.

### Example 2: deletion

Query: `Moonbery Loom`. Original: `Moonberry Loom`. Target: `syn-010`. Reference view: `full`.

| Rank | Record | Matched alias | Similarity |
|---:|---|---|---:|
| 1 | syn-010 | Moonberry Loom | 92.857143 |
| 2 | syn-009 | Copper Kite | 30.769231 |
| 3 | syn-004 | Aster Quill | 15.384615 |

Target rank: **1**. Recall@1 contribution: **1**; Recall@10 contribution: **1**; reciprocal rank: **1/1 = 1.000000**. Recall@50 is N/A for the 12-record corpus.

Deleting one character still leaves this query closest to its generating record. The score is a string-similarity measure, not a probability.

### Example 3: word_order

Query: `Loom Moonberry`. Original: `Moonberry Loom`. Target: `syn-010`. Reference view: `full`.

| Rank | Record | Matched alias | Similarity |
|---:|---|---|---:|
| 1 | syn-001 | Luma Vesper | 28.571429 |
| 2 | syn-003 | Élo Nivara | 28.571429 |
| 3 | syn-010 | Moonberry Loom | 28.571429 |

Target rank: **3**. Recall@1 contribution: **0**; Recall@10 contribution: **1**; reciprocal rank: **1/3 = 0.333333**. Recall@50 is N/A for the 12-record corpus.

Three leading candidates tie at 28.571429. Stable ID ordering puts the target third. The scorer operates on character order, so rearranging words is a substantial change.

## Calculations in plain language

`Recall@k = hits / eligible_positive_queries`. For our fictional challenge suite, Recall@1 is 20/27, not 20/94: sanity, diagnostics, development and absent queries do not belong in that denominator. Each metric stores its numerator and denominator. When k spans the entire corpus, the evaluator records null with a reason and the count of uninformative positive queries.

`MRR = sum(1 / target_rank) / eligible_positive_queries`. A rank-1 success contributes 1, rank 2 contributes 0.5, and rank 3 contributes one third. The sum may be fractional. Ambiguous and absent queries are excluded. Tests use target ranks [1,2,12,60] in a 100-candidate example: Recall@1=.25, Recall@10=.5, Recall@50=.75, MRR=.4. Those hand examples are tests, not project benchmark results.

A failure means an eligible positive target did not rank first. The stored explanation distinguishes a strictly higher-scoring wrong record from a tied score resolved by ID. The readable report shows up to 20 failures, while JSON retains every query and full ranking. Skipped, diagnostic and absent cases stay visible separately.

## File and function walkthrough

### `src/watchlist/perturbations.py`

`script_category` inspects alphabetic Unicode character names and labels Latin, Arabic, Cyrillic, mixed, other or no alphabetic script. Digits/punctuation do not decide script; this is not language detection. `variants` hashes seed plus alias ID to choose reproducible positions. It emits exact/formatting controls, a deletion, an adjacent swap, a missing word and first/last word swap, recording the operation. Unavailable positions return an explicit skip. These functions run before retrieval, locally, to give the learner controlled experiments without adding a language model.

Function locations: `script_category` line 7, `variants` line 17.

### `src/watchlist/evaluation_data.py`

`fingerprint` serializes canonical JSON and hashes it with SHA-256. `validate_partitions` checks exact entity coverage, duplicate IDs, allowed partitions and one partition per provider group. `build_benchmark` sorts entities and aliases before fingerprinting; builds full and held-out reference views; chooses one withheld alias by stable ID; removes normalized-equivalent copies; generates queries only for development, test and ambiguity groups. The query dictionary preserves original labels/provenance and operation metadata. Name maps identify collisions and unintended exact overlap. Duplicate/cross-partition query text becomes diagnostic rather than inflating positive metrics. `audit_queries` checks query ID uniqueness, group/partition ancestry, target presence and withheld-alias absence. These checks prevent known leakage mechanisms; unknown upstream identity duplicates are still possible. No name similarity merges IDs.

Function locations: `fingerprint` line 13, `validate_partitions` line 18, `build_benchmark` line 33, `audit_queries` line 136.

### `src/watchlist/evaluate.py`

`metric` packages a number with numerator, denominator and reason. `summarize` filters eligible positives, checks candidate count for each k, counts hits, sums reciprocal ranks and separately describes absent-target suggestions. `latency_summary` sorts milliseconds and computes median/p95. `evaluate_queries` calls the existing matcher once for rankings/warm-up, then measures 20 repeat calls; it stores full candidate evidence, target rank and a factual failure reason. `aggregate` separates partition, suite, perturbation and script slices. `run` loads either existing fictional records or read-only SQLite, verifies public split snapshot/group consistency, builds the benchmark and records environment/config/source/view/query fingerprints. `render_report` derives Markdown tables from the same computed JSON values. `main` reads configuration, writes three result artifacts and displays the test challenge summary. Expected configuration/file/database errors become CLI errors. No imports trigger downloads or evaluation.

Function locations: `metric` line 21, `summarize` line 25, `latency_summary` line 56, `evaluate_queries` line 64, `aggregate` line 98, `run` line 119, `render_report` line 158, `main` line 187.

### Configurations, fixtures and tests

| File | What/why and how it is used |
|---|---|
| `eval/configs/baseline.json` | Fictional dataset, fixed seed, partition/absent fixture paths, 20 timing repetitions and output directory. Read before scoring. |
| `eval/configs/public-small.json` | Separate existing SQLite/split paths and local-only public output destination. No download option. |
| `eval/fixtures/fictional-partitions.json` | Explicit ID ownership agreed in Step A. Train groups remain reserved. |
| `eval/fixtures/absent-queries.json` | Three authored fictional names whose intended records are absent from the fictional index. |
| `tests/test_perturbations.py` | Checks edit mechanics, reproducibility, skipped operations and Unicode categories. |
| `tests/test_evaluation_data.py` | Checks input-order invariance, same-name IDs remaining separate, group/query leakage rejection, withheld aliases, absent collisions and reserved groups. |
| `tests/test_evaluation.py` | Hand-calculated metrics, null/N/A behavior, excluded denominators, nearest-rank timing, real tied ranking, deterministic repeated runs and CLI files. |
| `eval/results/fictional/queries.jsonl` | One labeled query per line, including diagnostics. Generated by the actual run. |
| `eval/results/fictional/results.json` | Full rankings, metrics, timing samples, fingerprints, audit and environment. |
| `eval/results/fictional/report.md` | Readable tables and up to 20 failures generated from computed results. |
| `data/evaluation/public-small/queries.jsonl`, `results.json`, `report.md` | Equivalent public-derived artifacts; local and ignored. |

### Documentation and ignore rules

| File | Change |
|---|---|
| `docs/adr/0002-evaluation-protocol.md` | New record of scope, labels, split/index rules, metric definitions, DAG and limits. |
| `docs/progress/phase-03.md` | This report: actual results, examples, commands, code teaching and remaining uncertainties. |
| `docs/evaluation-plan.md` | Added implemented Phase 3 protocol link and scope. |
| `docs/implementation-phases.md` | Added current completion status and explicit Phase 4 gate. |
| `README.md` | Added offline evaluation commands and generated report links. |
| `.gitignore` | Added `data/evaluation/` so public-derived details stay local. |

Existing matching, normalization, entity loading, database, ingestion and split code were not changed. No dependencies/configuration lock, prior report, raw source, database or Phase 2 split manifest was modified. No Git operation or service was started.

## Label audit and remaining uncertainty

All 45 distinct public query source-alias pairs were checked against SQLite using entity ID, alias ID and original text; every pair matched. The displayed source spellings were inspected for record association and script coverage. This verifies ancestry only. It is not an independent multilingual semantic or identity audit; the true rate of incorrect upstream aliases remains unknown. The original fictional labels are authored assumptions, and all generated transformations are traceable.

The dataset is small, ID-selected, alias-imbalanced and already partly inspected. Synthetic deletions/token changes are not realistic frequencies of user error. Seven public entities have only one normalized alias and cannot support held-out-alias evaluation; three of those are in evaluated partitions and appear in the skip log. Unknown duplicated upstream entities can still cross splits. Collisions are excluded with counts rather than adjudicated into new identity labels. A second alias may be a different organisation name rather than a minor spelling, making alias holdout a different task from typos.

Generated queries sharing an entity or text across perturbation types are correlated. The raw query total is not an independent sample size. Timing varies and does not measure startup/SQLite loading. Script classification is deliberately limited and cannot identify language, transliteration quality or script direction quality. Full rankings on 12/20 candidates cannot establish large-corpus recall, effective negative filtering, or thresholds at 99% recall.

## Commands and checks actually run

Read-only inspection: `cat AGENTS.md`, source reads and `.gitignore` inspection. Code/config/docs were created with shell heredocs and local Python scripts. No installer or network command ran.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m watchlist.evaluate --config eval/configs/baseline.json
.venv/bin/python -m watchlist.evaluate --config eval/configs/public-small.json
```

The first test command produced **1 failed, 125 passed in 0.98s**. The failure reversed alias order and found different fingerprints/reference views. Fixed by sorting aliases before constructing the source fingerprint and full reference view. The second test run produced **126 passed in 0.87s**. The benchmark commands then wrote the saved outputs reported above.

A subsequent local Python script called `run(config)` again for each complete configuration, removed only the `timing` section from old/new result objects, and asserted equality. Both passed. The same script checked all 45 distinct public source-alias pairs against read-only SQLite. Separate local scripts inspected slice counts and selected worked examples from saved results. No scorer adjustment followed the results. A temporary documentation-writing script initially had an unterminated string and failed before writing the report; correcting its newline escaping fixed it. This did not affect application code or benchmark results.

## Comparison with the original portfolio objectives

| Original proposal objective | What Phase 3 established |
|---|---|
| Evaluation before models/agents | Implemented and hand-tested harness around existing scorer; no models added. |
| Entity-level splits and synthetic query labels | Implemented partitions, ancestry/overlap checks and deterministic perturbations; unknown duplicates remain a limitation. |
| Recall@10/@50 | Recall@10 computed with counts; Recall@50 marked N/A because these corpora are too small. |
| Results by script and perturbation | Computed available slices with empty/unsupported slices explicit. No assumed hardest script. |
| Latency | Measured warm local ranking only, with environment and observation counts. |
| Failure gallery | All rankings/failures in JSON and up to 20 failures in generated Markdown. |
| Hand-check labels | Source ancestry audited; independent real-world alias correctness remains unverified. |
| 95% confidence intervals | Not claimed for tiny, biased, correlated teaching samples. Counts and limitations replace misleading certainty. |
| FPR at 99% recall; automatic decisions at 99% precision | Not supported; no threshold or calibrated probability exists. |
| Embeddings, model/LLM comparisons, calibration, agents and memory | Later phases, not started. |
| Reproduce numbers with one command | Each corpus has one offline Python command; no Makefile wrapper was needed in this phase. |

A good outcome here is an understandable, reproducible baseline including weaknesses, not achieving a promised accuracy. Phase 4 would require a separate model/license/download/compute proposal and your explicit approval before any embedding work.

**STOP: Phase 3 is complete. Request explicit approval before Phase 4.**

Final documentation checks: local links resolved, all three new application modules parsed, and both generated reports exactly matched rendering of their saved JSON results. Changes after the 126-test run were documentation only.
