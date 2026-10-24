# Completion Step 05 — evaluation contracts and shortlist metrics

Date: 2026-10-24, Asia/Kolkata. Status: **complete within the approved evaluation-repair scope**, under explicit user approval. Final verification: **1,589 non-integration tests, 13 subtests and all 3 local model integration tests passed**. This is Completion Step 05, not the historical fine-tuning/reranking Phase 5. Step 06 is not started.

## Approved scope and preflight

The goal is to reject invalid evaluation queries before retrieval and calculate metrics from explicit ranking depths. The approved files are `src/watchlist/evaluation_data.py`, `src/watchlist/evaluate.py`, `src/watchlist/compare_retrieval.py`, `src/watchlist/splits.py`; new `src/watchlist/evaluation_metrics.py` and `src/watchlist/scripts.py`; the four existing evaluation/comparison/split test files; new `tests/test_evaluation_metrics.py`, `tests/test_evaluation_protocol.py` and `tests/test_scripts.py`; and this report. Separate comparison evidence goes in `data/eval-comparisons/completion-05/`.

Five Astra/max workers own: query/data contracts, metrics and baseline evaluation, script sets and splits, paired comparison and compatibility, and independent adversarial tests plus historical replay. The coordinator owns preservation, integration review, final verification and this report. Dependencies remain the existing offline Python environment. No training, data/model acquisition, dependency installation, network, API, Git operation or deployment is included.

The intended checks are focused tests, the complete offline suite, saved-ranking historical replay, archive compatibility and baseline preservation. Existing local E5/MiniLM smoke tests will also run with temporary configs/caches and blocked networking; this does not authorize a new model-quality experiment or download.

Acceptance: altered ancestry, wrong alias ownership, absent collisions and invalid views fail before retrieval; a target at rank 30 in a top-50 list from 1,000 indexed entities counts at Recall@50; a target outside that shortlist is a miss; impossible claims of an observed rank beyond the returned list are rejected. Truncated rankings report MRR@K without inventing tail ranks. Every historical comparison reproduces or has an explained difference. Original artifacts remain unchanged.

## Baseline evidence

- Step 04 ended with **1,211 passed, 3 deselected, 13 subtests passed**, plus all three local integrations passed separately.
- Before Step 05 implementation, the four original focused test files passed **20 tests in 0.22 s**. Their tests did not expose E1/E2.
- `before-files.json` records hashes, modes and sizes for **210 existing files**. Four original evaluation source files were separately copied into `baseline-source/` for independent historical comparison.
- The independent `baseline-reproductions.json` records nine invalid query mutations accepted by the original audit, and the 1,000-entity/top-50/rank-30 example incorrectly producing Recall@50 N/A. The reproduction uses authored in-memory records and records the baseline source hashes.
- The metrics owner's test-first run observed **3 failures in 0.03 s**: the rank-30 denominator error, truncated output labeled as full MRR, and an impossible reported rank 51 in a 50-record output. Saved output: `metrics-E2-before.txt`.

## Design decisions implemented

The current benchmark contract uses five experiment partitions: training, development, calibration fitting, threshold selection and test. Presence and ambiguity are separate labels. Historical `partition='absent'` and `partition='ambiguity'` values remain in preserved artifacts; any conversion for current diagnostics must be explicit and documented, without implying that previously exposed examples are fresh test data.

Query validation binds a query to its source alias, original text, transformation, normalized text, role, labels and exact reference view. A reference view is the allowed set of aliases for that search. Held-out aliases are deliberately removed before retrieval. A sealed context means the validator retains the original expected contents and rejects changed caller values; it is an in-process integrity check, not protection from arbitrary Python reflection or a forged trusted data source.

Metrics distinguish the full index size, requested shortlist size, returned record count and depth actually evaluated. A gold label is the known reference answer used to calculate metrics; search and pair scorers must receive only query text and allowed reference aliases, never these answers.

Script sets identify the supported scripts actually present in text. For example, Latin+Arabic and Arabic overlap and cannot count as a disjoint-script test. Unknown or unsupported letters must not be treated as proof of script separation. This is script detection, not language identification.

Historical generation and ranking checks retain an explicit regression-only path, because existing reranking artifacts depend on exact old query and view fingerprints. New experiments must use the new validated contract. Existing source/model/config files and historical reports will not be rewritten to fit the new contract.

## File and function walkthrough

Line numbers below identify entry points in the final source; the named functions explain the adjacent validation branches.

| File / entry point | What changed and why |
| --- | --- |
| `src/watchlist/evaluation_data.py:187`, `_ordered_source` | Validates source IDs, globally owned alias IDs, text, origin, provenance and existing entity types, including the public parser's `legal_entity`. Sorts and freezes original records before query generation. |
| `evaluation_data.py:238`, `_retained_display`, `_validate_views` | Requires every reference alias to belong to its original entity. Current views derive display names from retained aliases, closing a second channel through which a removed alias could reach a scorer. Historical names remain unchanged for exact replay. |
| `evaluation_data.py:281`, `_AuditContext`, `BenchmarkViews`, `_bind`, `audit_queries` | Stores canonical original records, assignments, views and expected query rows privately. Audits every supplied row, including absence, before retrieval. Valid subsets/reordering are accepted; altered fields, duplicate IDs, plain unbound dictionaries, changed views and synchronized public-hash rewrites are rejected. |
| `evaluation_data.py:357`, `query_labels`, `_validate_absent`, `_decorate`, `_label_queries` | Separates data-use roles from presence/ambiguity, checks absent IDs and normalized source-name collisions, binds transformation ancestry and actual scripts, and keeps conflicting or duplicated examples diagnostic. Absence versus a generated perturbation excludes the conflicting rows; it does not invent a clean label. |
| `evaluation_data.py:488`, `build_benchmark`, `build_authored_benchmark` | Creates current-contract queries from canonical assignments or validated authored transformations. Training/calibration/threshold roles are validated but do not generate development/test queries. Explicit old ambiguity mappings stay development diagnostics. |
| `evaluation_data.py:532`, `build_legacy_benchmark`, `bind_legacy_authored_benchmark` | Reproduces old rows/views for explicit regression use. The original `fingerprint()` JSON semantics stay unchanged for old cache and artifact hashes. |
| `src/watchlist/evaluation_metrics.py:31`, `_label`, `_candidate_ids`, `_validate_row` | Validates label combinations, integer counts, finite scores, distinct candidate IDs, deterministic ties, observed rank and ranking-depth consistency. Booleans/floats cannot masquerade as counts. |
| `evaluation_metrics.py:106`, `ranking_fields` | Derives observed target rank from returned candidates after retrieval. Records index size, requested K, returned count and evaluated depth separately. Gold answers are used only here, after the ranker finishes. |
| `evaluation_metrics.py:135`, `summarize` | Computes Recall eligibility from index population and evaluated depth. Counts positive, absent, ambiguous and unlabelable rows independently. Reports full MRR only for complete positive rankings; reports MRR at each evaluated depth otherwise. Keeps suggestion rate separate from unavailable threshold FPR. |
| `evaluation_metrics.py:201`, `adapt_legacy_full_ranking` | Requires an independently supplied index population and complete saved candidate evidence. Preserves old diagnostic status as unlabelable instead of re-adjudicating it. Rejects missing or contradictory original rank fields. |
| `src/watchlist/evaluate.py:42`, `_verify_alias_view`, `evaluate_queries` | Audits the entire batch before any retrieval, passes only text and the selected Entity tuple to the ranker, validates returned alias evidence, and requires timed repetitions to reproduce the same ranking. |
| `evaluate.py:95`, `aggregate`, `run`, `render_report`, `main` | Aggregates actual current partition labels; public runs check stored provider-group ownership and snapshot provenance. All supported exposed datasets are marked regression-only. The CLI computes and serializes first, then exclusively creates a new output directory; existing output is refused. |
| `src/watchlist/compare_retrieval.py:23`, exposed-fixture wrapper and benchmark factories | Separates legacy-contract opt-in from dataset usage. Both legacy and current factories mark known exposed data as regression-only without changing historical query bytes. Public factories require an explicit source-v3 override and verify stored group IDs. |
| `compare_retrieval.py:183`, `_cross_script`, `_check_candidates`, `compare` | Uses the scripts of the target's retained aliases, audits before caching/encoding, caches only used views, validates candidate aliases/counts and detects timed ranking drift. Both RapidFuzz and E5 receive the same allowed reference view. |
| `compare_retrieval.py:289`, `report`, `_output_destinations`, `main` | Reports explicit depth metrics, handles missing shortlist ranks, requires a new output root, preflights every requested benchmark before model construction, and isolates caches under that root. Historical report/cache destinations are protected. |
| `src/watchlist/scripts.py:25`, `ScriptProfile`, `script_profile`, `script_set`, `disjoint_scripts` | Provides immutable supported-script sets with explicit uncertainty. Latin, Arabic, Cyrillic and Han are recognized by Unicode names/categories; unknown letters, detached marks and relevant controls block unsupported disjointness claims. Digits/punctuation alone prove no script. |
| `src/watchlist/splits.py:16`, `validate_seed`, `_identifier`, `validate_assignments`, `assign_groups` | Rejects malformed seeds, IDs, provider links, duplicate records, incomplete assignment coverage and groups crossing partitions. The valid existing seeded group-bucket algorithm is unchanged. |

The six application files are four edited modules and two new modules. Retrieval algorithms, embedding/reranking implementations, frozen archive compatibility reader, dependencies and historical artifact formats were not changed.

| Test file | Evidence covered |
| --- | --- |
| `tests/test_evaluation_data.py` | 104 source/alias/query ancestry, absence, immutable-view, role, display-name, script and legacy-contract cases. |
| `tests/test_evaluation.py` | Audit-before-retrieval, alias evidence, repeat consistency, config/source validation, regression labels and no-overwrite CLI behavior. |
| `tests/test_evaluation_metrics.py` | Hand-checkable shortlist arithmetic, denominator exclusions, full/truncated/mixed-depth MRR, invalid candidates/counts/ranks and explicit legacy adaptation. Together with the evaluator tests: 81 focused passes. |
| `tests/test_compare_retrieval.py` | 57 current/legacy factory, source-group, pre-inference audit, used-view cache, shortlist, script, timing-repeat and output-protection cases. The four unchanged reranking-evaluation tests also pass. |
| `tests/test_splits.py` | 68 strict input/assignment/provider-group cases and preservation of valid deterministic splits. |
| `tests/test_scripts.py` | 60 supported, mixed, neutral, combining-mark and uncertain-script cases. |
| `tests/test_evaluation_protocol.py` | 28 independent adversarial tests, including forged public hashes and the real unchanged reranking path with a spy pair scorer. The entire Entity records and exact alias pairs reaching retrieval/scoring are inspected, including a canonical display name deliberately withheld from the view. |
| `docs/progress/completion-05.md` | This implementation, teaching, evidence and next-step approval report. |

## Test-first findings and integration corrections

The original audit accepted nine deliberately invalid mutations in the saved baseline reproduction. New data-contract tests initially produced 22 failures and one pass, with six deselections. The initial comparison regression selection had 38 failures and two passes. New script-module tests initially could not collect because that module did not yet exist. These are mixed API and behavioral test-first evidence; missing APIs alone do not prove an original runtime defect.

Later boundary tests exposed malformed-input, reserved-role, Unicode mark, display-name and source-schema cases. Their fixes were retested: data 104 passes; metrics/evaluator 81; scripts/splits 128; comparison plus unchanged reranking tests 61. In particular, the public source uses `legal_entity`, so the source validator now accepts that existing domain type without changing any source record. Cross-script checks use target aliases rather than unrelated distractors. Both timed comparison methods now reject changed output instead of silently timing a different ranking.

## Historical replay and intentional differences

`historical-baseline-check.json` and `historical-current-replay.json` record **20 method streams and 878 aggregate slices with zero exact historical differences**. The replay covers baseline RapidFuzz, the retrieval comparison and reranking artifacts for fictional, public-small and multilingual data. It checks the original metric projection, candidate-derived target ranks, and numeric values/numerators/denominators projected through the new metric contract.

The replay also checks original Phase 3 query JSONL fingerprints, all three legacy query/view/cache fingerprints, every saved retrieval matched alias, and every saved reranker alias list/display/provenance against its declared view. Public replay explicitly uses `data/source-v3/watchlist.sqlite`; original configs still name the historical database and were not silently rewritten. No historical latency was remeasured and no new model-quality experiment was run.

The current representation intentionally adds protocol version, presence/ambiguity, ranking depth, label counts and exclusion reasons. New query IDs/hashes change because they bind that additional content. Current script labels distinguish Han and mixed scripts; legacy coarse labels remain unchanged. Current views sanitize display names; legacy views preserve their bytes. Previously exposed ambiguity/absence roles have explicit development mappings in the comparison factories. These changes do not turn old examples into fresh generalization evidence. A regression metric replay preserves old labels; it is distinct from rebuilding queries under stricter current exclusion rules.

Recall at K covering the entire index remains N/A under the project's historical informative-index policy. The report now distinguishes this from insufficient evaluated depth. Legacy reason strings can differ under the current representation while numeric metric projections remain identical.

## Executed examples

The hand-check receipt records eight passing arithmetic examples and two rejected invalid contracts. For an index of 1,000 entities and a requested/returned/evaluated top 50:

| Observed evidence | Recall@50 | MRR@50 | Full MRR |
| --- | --- | --- | --- |
| Target at rank 30 | 1 | 1/30 | N/A |
| Target absent from returned 50 | 0 | 0 | N/A |
| Claimed rank 51 with only 50 returned | Rejected | Rejected | Rejected |

A genuinely observed rank 51 from a longer ranking, evaluated only through depth 50, is a miss at that cutoff. A shorter returned list can also count as a miss at its declared evaluated cutoff; returned length is not substituted for index population. Missing tail ranks are never fabricated.

Actual script example: `Luma ليلى` yields `{ARABIC, LATIN}` and `Luma` yields `{LATIN}`, so disjointness is false. Actual held-out fixture: `Maple Loom` is queried against a target whose display name and remaining alias are both `منسج القيقب`; the withheld text does not reach the scorer through metadata.

The current baseline CLI ran using separate scratch canonical partition/absence files, requested K=10 and two timing repetitions. Its 94-query result is saved in `data/eval-comparisons/completion-05/cli-fictional/`. The original `ambiguity` roles were explicitly mapped to development for this schema demonstration; source-name collisions are derived by the current contract. `cli-conversion.json` documents the mapping. This example is not the exact historical diagnostic-label replay; that replay uses the explicit legacy adapters above.

For the CLI's unchanged test challenge slice, 27 eligible queries across three target groups produced Recall@1 = 20/27, Recall@10 = 25/27 and MRR@10 = 0.7856407995296885. Full MRR is unavailable because only 10 of 12 records were returned; Recall@50 is uninformative for this 12-record index. These are regression/demo results, not estimates of real-world matching quality.

## Commands actually executed

Commands used the existing offline environment, with `PYTHONDONTWRITEBYTECODE=1`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, Python `-B` and pytest's cache provider disabled. They ran from `/Users/odin/Desktop/polyglot-watchlist-starter`.

```sh
# Focused worker checks (some repeated after confirmed failures/fixes).
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evaluation_data.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evaluation_metrics.py tests/test_evaluation.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_scripts.py tests/test_splits.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_compare_retrieval.py tests/test_reranking_evaluation.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_evaluation_protocol.py

# Full offline suite and all three already-local model checks.
.venv/bin/python -B -m pytest -q -m 'not integration' -p no:cacheprovider
.venv/bin/python -B data/eval-comparisons/completion-05/run-local-integration.py

# Independent saved-ranking replay, arithmetic, and actual factory audits.
.venv/bin/python -B data/eval-comparisons/completion-05/replay_saved_rankings.py --current --output historical-current-replay.json
.venv/bin/python -B data/eval-comparisons/completion-05/check_metric_examples.py --output metric-hand-checks-final.json
.venv/bin/python -B data/eval-comparisons/completion-05/check_current_factories.py --output current-factory-checks.json

# Current baseline CLI demonstration; existing outputs are refused.
.venv/bin/python -B -m watchlist.evaluate --config data/eval-comparisons/completion-05/cli-config.json

# Preserved archive remains inspectable, without running the historical workflow.
.venv/bin/python -B -m watchlist.review archive verify --archive data/review-archives/v1
.venv/bin/python -B -m watchlist.review archive inspect --archive data/review-archives/v1 --case-id e449b466-466d-4b81-9a29-cb3c9d957823
```

Independent replay and hand-check commands are recorded with their scripts/receipts under `data/eval-comparisons/completion-05/`. Inline Python also created scratch CLI inputs, compared original file hashes/modes/sizes and parsed all 13 changed/new Python files with `ast.parse`; no import-time compilation was used for that syntax check.

## Final verification

| Check | Actual outcome |
| --- | --- |
| Full offline non-integration suite | **1,589 passed, 3 deselected, 13 subtests passed in 90.02 s**. The three deselected tests all passed separately below. |
| All three already-local model integrations | **3 passed in 6.89 s**, zero network attempts, isolated temporary configs/caches. Tests cover E5 vector shape/normalization/repeatability, MiniLM finite/repeatable logits, and E5 evidence/review restart parity. |
| Historical saved-ranking replay | **20 streams, 2,946 method-query rows, 878 exact aggregate slices, 878 current numeric projections, zero differences**. |
| Actual current benchmark factories | **94 fictional, 272 public-small and 64 multilingual queries**; all audit successfully, carry current protocol plus exposed-dataset regression usage, and retain safe display names. All 32 replay inputs stayed identical. |
| Arithmetic examples | **8 passed**, plus **2 invalid contracts rejected**. |
| Preserved archive verification and case inspection | Both exited 0 with verified evidence: **37,357 files, 4 databases, 1 simulated-demo case**. |
| Existing-file preservation | **210 checked: exactly 8 approved changes, 202 unchanged, 0 missing, 0 unexpected changes**. |
| Python syntax and whitespace | All **13** edited/new Python files parse; final newlines present, no trailing whitespace. |
| Current baseline CLI example | Exited 0; 94 queries, separate current-contract output, regression-only result. |

The archive manifest remains `ece00da970f15c517c597f45dcc51cf86de7887feb778422492f2d5e88803d0d`. Its stored workflow remains `545944411abe85d270737fe708de8e75e67e1516698d7b54df4e7313dc9960b9`; the current workflow remains `39a6725f106463b59e885010e7142d65f76c48188db00ed24c43d27d09c3314a`. Archive compatibility still reports captured execution match true, current execution match false and execution allowed false. The historical case was inspected, not executed.

All receipts are under `data/eval-comparisons/completion-05/`: `full-suite-final.log`, `local-integration.log`, `local-integration-result.json`, `historical-current-replay.json`, `current-factory-checks.json`, `metric-hand-checks-final.json`, `archive-verify.json`, `archive-inspect.json`, `preservation-result.json`, `python-source-check.json`, `cli-example.log` and `cli-fictional/`. Source hashes for all six modules and seven test files are recorded in `python-source-check.json`. Earlier failing/intermediate evidence is retained separately.

## Limits and remaining project work

No known approved Step 05 acceptance defect remains after final verification. The broader completion plan remains unfinished.

The sealed audit context detects changes relative to trusted in-process construction. It is not an isolation sandbox, cryptographic label custody or proof that an upstream source is authentic. Public provider groups are checked against the database; unknown real-world duplicates may still exist. Script detection is the documented `unicode-name-category-conservative-v1` approximation using runtime Unicode 16.0.0, not full Unicode Script_Extensions or language recognition. Unknown script evidence blocks disjointness claims.

Scores remain similarities, not probabilities. No thresholds, calibration, training, operational guarantees or new data access are introduced. Fresh evaluation data and later governance work remain scheduled in their own explicitly approved completion steps. The three existing local inference tests were all executed; none was deferred. Preserved historical APIs retain their documented quirks only in explicit regression mode.

## 5W1H recap

- **What:** repaired query contracts, reference-view isolation, script evidence and shortlist metrics.
- **Why:** invalid ancestry or the wrong denominator can make an apparently successful experiment misleading.
- **When:** validation runs before retrieval/cache/model work; metric scoring runs after candidates are returned.
- **Where:** six evaluation/split/script modules, seven test files and a separate evidence directory.
- **Who:** the coordinator and five Astra/max workers implement and independently review; a human still judges possible record matches.
- **How:** frozen construction evidence, explicit labels/depth fields, conservative exclusions, adversarial tests, hand arithmetic, historical replay and offline integration checks.

## Step 06 preflight — awaiting explicit approval

**Goal and reason:** make the engineering foundation reproducible and identify external access blockers before later data/model/integration work. A reproducible build is one another environment can install and run from declared inputs, rather than depending on this checkout's temporary paths.

**Sequence:**

1. Inspect the declared Python 3.11–3.14 support and locally available runtimes. Test the matrix that can actually be exercised, or propose a truthful support-range change for review. Do not claim untested versions work.
2. Verify `uv.lock`, optional dependency groups, package data, wheel/source distribution contents and installation/execution outside the repository. Record and justify any build/tooling dependency change before acquisition.
3. Add scoped Ruff/pre-commit checks, deterministic CI, small fictional evaluation, secret scanning and dependency/license inventory. Avoid global formatting of fingerprinted v1 files. Use reviewed action commit SHAs, minimal permissions and no privileged secrets for untrusted PR code.
4. Add incremental Makefile entry points for tests, lint, package smoke and evaluation; update living project status documents while preserving historical reports.
5. Create an access/resource ledger for source terms, compute, frontier-LLM provider/key/budget, HF hosting/account, Azure subscription/budget and Microsoft tenant/admin/Copilot requirements. Every unknown needs a named resolution owner and concrete deliverable. Network verification and acquisition require separate explicit authorization; an unverified ledger entry must remain unverified.

**Exact proposed files:** edit `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `docs/data-card.md`, `docs/model-card.md`, `docs/implementation-phases.md`; create `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Makefile`, `.env.example`, `docs/access-and-resource-ledger.md`, `tests/test_packaging.py` and `docs/progress/completion-06.md`. New checks and fixtures must remain inside that reviewed scope or receive a specific scope amendment.

**Dependencies:** the completed repair contracts, current baseline/archives, available runtimes and locally cached build/lint tools. Missing packages, remote action-SHA verification and external account checks need explicit acquisition/network approval. No secrets should be copied into repository files or evidence.

**Expected commands:** inspect runtime/tool versions and lock/package metadata; `uv sync --locked --offline --dev --extra embeddings --extra agent` only when the declared packages are cached; `uv run --locked --offline ruff check .`; `uv run --locked --offline ruff format --check .` with explicitly reviewed exclusions/scoped migration; `uv build --offline --no-build-isolation`; isolated installation and CLI smoke from another working directory; `make test`; `make eval-smoke`. Record actual commands/results, including unsupported or unavailable tools.

**Tests and acceptance:** clean local build/install/run outside the repository; truthful supported-runtime declaration; package data present in artifacts; offline fictional CI/evaluation fixtures pass; no secrets in reviewed staged content; every external requirement either verified with evidence or assigned a specific unresolved action. A prepared workflow is not a verified remote CI run: only an approved actual GitHub run can establish that. Preserve the existing archive and review compatibility checks if the environment changes.

**Risks:** runtime/lock changes can alter execution fingerprints, so follow Completion Step 01 compatibility policy. Formatting can alter preserved code hashes; scope it deliberately. Local caches may not contain the required tools. External terms/access/budgets cannot be established from assumptions. This preflight does not authorize network, costs, downloads, Git operations or deployment.

**Approval boundary:** Step 05 ends here. Step 06 implementation has not started. Per `AGENTS.md` (“AFTER every phase … STOP until user approves the next phase”), wait for explicit Step 06 approval.
