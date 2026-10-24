# Phase 4 — pretrained multilingual retrieval

Status: approved Phase 4 implementation and evaluation complete. **STOP before Phase 5; explicit approval is required.**

## Actual results

Final full test run, with local-model integration explicitly enabled: **145 passed in 3.97 seconds**. The offline unit-only run passed **144 tests, one deselected, in 0.97 seconds**. A simulated baseline-only installation with NumPy imports blocked passed **127 tests, four modules skipped, in 0.89 seconds**.

A fresh model process reproduced all **430** saved query candidate orders and winning alias IDs. Maximum absolute cosine difference was **0.0** on this machine (acceptance tolerance 1e-6). All seven reference views were verified cache hits. Eleven existing files hashed immediately before evaluation—including both SQLite files, old result files, matcher, normalizer and database adapter—were unchanged afterward. This check covers the evaluation interval, not a complete pre-phase filesystem audit.

The comparisons comprise 94 original fictional, 272 public-subset and 64 new bilingual queries. Each method had 20 timed calls per query: **8,600 observations per method**, not 8,600 independent accuracy examples. Headline rows below are eligible test challenges only.

| Dataset | Method | Queries / groups | Recall@1 | Recall@10 | MRR |
|---|---|---:|---|---|---:|
| fictional | rapidfuzz | 27 / 3 | 20/27 (0.7407) | 25/27 (0.9259) | 0.792094 |
| fictional | e5_small | 27 / 3 | 26/27 (0.9630) | 27/27 (1.0000) | 0.981481 |
| public-small | rapidfuzz | 141 / 6 | 129/141 (0.9149) | 141/141 (1.0000) | 0.943282 |
| public-small | e5_small | 141 / 6 | 141/141 (1.0000) | 141/141 (1.0000) | 1.000000 |
| multilingual | rapidfuzz | 30 / 6 | 16/30 (0.5333) | N/A | 0.670741 |
| multilingual | e5_small | 30 / 6 | 25/30 (0.8333) | N/A | 0.911111 |

Recall@50 is N/A everywhere (indices contain 12, 20 and 10 entities). Public 141/141 is a result on synthetic transformations of only six target groups among twenty candidate records; it is not evidence of perfect real-world screening. Both methods preserve the old benchmark query labels, views and partitions. Paired RapidFuzz scores and rankings matched the saved Phase 3 results exactly.

### What improved and what did not

| Dataset / test slice | Query count | RapidFuzz top-1 hits | E5 top-1 hits |
|---|---:|---:|---:|
| fictional / challenge / kind:adjacent_swap | 6 | 6 | 6 |
| fictional / challenge / kind:deletion | 6 | 6 | 6 |
| fictional / challenge / kind:heldout_alias | 3 | 2 | 2 |
| fictional / challenge / kind:missing_word | 6 | 6 | 6 |
| fictional / challenge / kind:word_order | 6 | 0 | 6 |
| fictional / cross-script-only / all | 1 | 0 | 1 |
| fictional / cross-script-only / ARABIC→LATIN | 1 | 0 | 1 |
| public-small / challenge / kind:adjacent_swap | 36 | 36 | 36 |
| public-small / challenge / kind:deletion | 36 | 36 | 36 |
| public-small / challenge / kind:heldout_alias | 4 | 3 | 4 |
| public-small / challenge / kind:missing_word | 31 | 30 | 31 |
| public-small / challenge / kind:word_order | 34 | 24 | 34 |
| multilingual / challenge / kind:cross_script | 12 | 2 | 8 |
| multilingual / challenge / kind:deletion | 12 | 11 | 11 |
| multilingual / challenge / kind:word_order | 6 | 3 | 6 |
| multilingual / cross-script-only / all | 12 | 2 | 8 |
| multilingual / cross-script-only / ARABIC→LATIN | 6 | 1 | 4 |
| multilingual / cross-script-only / LATIN→ARABIC | 6 | 1 | 4 |
| multilingual / cross-script-only / translation | 8 | 0 | 6 |
| multilingual / cross-script-only / transliteration | 4 | 2 | 2 |

Known-alias exact lookups are separate sanity checks, not part of challenge scores. Their full script slices and denominators are in each generated report. The original fictional test has only one true cross-script query; the public test has **zero** queries with no same-script target alias. Public improvements therefore do not establish cross-script retrieval.

The new fixture provides twelve test cross-script queries: six in each direction, drawn from six entities. E5 improves authored translations (6/8 versus 0/8), but its four person-like transliterations have the same 2/4 top-1 count as RapidFuzz. RapidFuzz cross-script hits can result from shared spaces and ID tie ordering, not understanding another alphabet. E5 regresses on `Neri Vasko` and on the original fictional abbreviation `Tavi O.`. No model or preprocessing was changed in response.

Both methods still suggest candidates for all three fictional absent-target queries. This is expected for unthresholded ranking and is not a calibrated false-positive rate. Same-name diagnostic records remain excluded from positive denominators.

### Measured warm latency

| Dataset | Method | Observations | Median ms | p95 ms |
|---|---|---:|---:|---:|
| fictional | rapidfuzz | 1880 | 0.034083 | 0.037375 |
| fictional | e5_small | 1880 | 4.935417 | 5.451667 |
| public-small | rapidfuzz | 5440 | 0.072000 | 0.079916 |
| public-small | e5_small | 5440 | 5.078791 | 5.365667 |
| multilingual | rapidfuzz | 1280 | 0.026666 | 0.029292 |
| multilingual | e5_small | 1280 | 4.929229 | 5.223875 |

E5 median encoding time is about 4.89–5.01 ms; vector search/grouping is about 0.040–0.068 ms. Model construction took **0.742431 seconds**, excluding imports and checksum verification. Reference-cache preparation times and shapes are in each JSON. Component medians need not sum to the total median. p95 uses the nearest-rank convention. Timings are local warm measurements on the inspected M4 MacBook Air, CPU/four threads, not service latency or throughput guarantees.

### Actual acquisition and resources

- Model: `intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, ten selected files. Main weights: 470,641,600 bytes. Selected files: **493,292,828 bytes**; metadata: **1,067,261 bytes**; successful acquisition total: **494,360,089 bytes**, below 600,000,000. The earlier rejected metadata request transferred an additional bounded metadata response before the successful attempt; even counting that request remains below the approved cap. HTTP protocol overhead is not measured.
- Installed versions: NumPy 2.5.4, PyTorch 2.14.1, Sentence Transformers 6.1.0, Transformers 5.20.2, tokenizers 0.23.3; unchanged RapidFuzz 3.14.6; pytest 9.1.1. `uv.lock` records transitive versions and hashes. The installer prepared forty packages; the conservative compatible-wheel size bound inspected before installation was 261,427,051 bytes, below the 2 GB dependency allowance. Actual aggregate network package bytes were not independently metered.
- Observed disk allocation after imports: `.venv` about 893 MiB and model directory about 472 MiB. Reference caches are small (well under 1 MiB); the public full-view float32 array itself is 79×384×4 = 121,344 bytes. These fit the planned 5 GB local budget. Peak RAM and total first-import wall time were not profiled; no memory-performance claim is made.

### Worked examples: actual rankings

#### Example 1: Loom Moonberry

Target `syn-010`; operation `word_order`; dataset `fictional`.

| Method | Rank | Candidate ID | Original winning alias | Raw score |
|---|---:|---|---|---:|
| rapidfuzz | 1 | syn-001 | Luma Vesper | 28.571429 |
| rapidfuzz | 2 | syn-003 | Élo Nivara | 28.571429 |
| rapidfuzz | 3 | syn-010 | Moonberry Loom | 28.571429 |
| e5_small | 1 | syn-010 | Moonberry Loom | 0.992725 |
| e5_small | 2 | syn-002 | Lumo Vespar | 0.853796 |
| e5_small | 3 | syn-001 | Luma Vesper | 0.834031 |

- rapidfuzz: target rank 3; Recall@1 contribution 0; reciprocal rank 1/3 = 0.333333. Recall@10 contribution 1.
- e5_small: target rank 1; Recall@1 contribution 1; reciprocal rank 1/1 = 1.000000. Recall@10 contribution 1.

Word order causes an edit-distance tie, while the pretrained representation ranks the intended invented record first.

#### Example 2: مخبز القمر الذهبي

Target `ml-003`; operation `cross_script`; dataset `multilingual`.

| Method | Rank | Candidate ID | Original winning alias | Raw score |
|---|---:|---|---|---:|
| rapidfuzz | 1 | ml-001 | Blue Cedar Library | 11.111111 |
| rapidfuzz | 2 | ml-005 | Green River Workshop | 10.000000 |
| rapidfuzz | 3 | ml-006 | Green Mountain Workshop | 8.695652 |
| e5_small | 1 | ml-003 | Golden Moon Bakery | 0.812395 |
| e5_small | 2 | ml-004 | Silver Moon Bakery | 0.790263 |
| e5_small | 3 | ml-008 | Nera Vasko | 0.789462 |

- rapidfuzz: target rank 9; Recall@1 contribution 0; reciprocal rank 1/9 = 0.111111. Recall@10 is N/A for this ten-record universe.
- e5_small: target rank 1; Recall@1 contribution 1; reciprocal rank 1/1 = 1.000000. Recall@10 is N/A for this ten-record universe.

The query uses Arabic but this reference view contains only English aliases. Original script and matched alias stay visible.

#### Example 3: Tavi O.

Target `syn-011`; operation `heldout_alias`; dataset `fictional`.

| Method | Rank | Candidate ID | Original winning alias | Raw score |
|---|---:|---|---|---:|
| rapidfuzz | 1 | syn-011 | Tavi Orlun | 60.000000 |
| rapidfuzz | 2 | syn-004 | Aster Quill Workshop | 20.000000 |
| rapidfuzz | 3 | syn-006 | Naro Zefir | 20.000000 |
| e5_small | 1 | syn-008 | Daro Nuvem | 0.860451 |
| e5_small | 2 | syn-011 | Tavi Orlun | 0.859723 |
| e5_small | 3 | syn-005 | Mira Velune | 0.838744 |

- rapidfuzz: target rank 1; Recall@1 contribution 1; reciprocal rank 1/1 = 1.000000. Recall@10 contribution 1.
- e5_small: target rank 2; Recall@1 contribution 0; reciprocal rank 1/2 = 0.500000. Recall@10 contribution 1.

A regression: another invented name has slightly higher cosine. An abbreviation is unreliable identity evidence.

#### Example 4: Neri Vasko

Target `ml-007`; operation `cross_script`; dataset `multilingual`.

| Method | Rank | Candidate ID | Original winning alias | Raw score |
|---|---:|---|---|---:|
| rapidfuzz | 1 | ml-007 | نيري فاسكو | 10.000000 |
| rapidfuzz | 2 | ml-008 | نيرا فاسكو | 10.000000 |
| rapidfuzz | 3 | ml-004 | مخبز القمر الفضي | 6.250000 |
| e5_small | 1 | ml-008 | نيرا فاسكو | 0.865557 |
| e5_small | 2 | ml-007 | نيري فاسكو | 0.864315 |
| e5_small | 3 | ml-004 | مخبز القمر الفضي | 0.804202 |

- rapidfuzz: target rank 1; Recall@1 contribution 1; reciprocal rank 1/1 = 1.000000. Recall@10 is N/A for this ten-record universe.
- e5_small: target rank 2; Recall@1 contribution 0; reciprocal rank 1/2 = 0.500000. Recall@10 is N/A for this ten-record universe.

E5 confuses two similar invented names. RapidFuzz ranks the target first through a score tie resolved by ID, not knowledge of Arabic.

#### Example 5: Amber Kite Studio

Target `ml-010`; operation `exact`; dataset `multilingual`.

| Method | Rank | Candidate ID | Original winning alias | Raw score |
|---|---:|---|---|---:|
| rapidfuzz | 1 | ml-009 | Amber Kite Studio | 100.000000 |
| rapidfuzz | 2 | ml-010 | Amber Kite Studio | 100.000000 |
| rapidfuzz | 3 | ml-005 | Green River Workshop | 30.000000 |
| e5_small | 1 | ml-009 | Amber Kite Studio | 1.000000 |
| e5_small | 2 | ml-010 | Amber Kite Studio | 1.000000 |
| e5_small | 3 | ml-006 | Green Mountain Workshop | 0.808418 |

- rapidfuzz: diagnostic ambiguity; no positive-metric contribution.
- e5_small: diagnostic ambiguity; no positive-metric contribution.

The two identical names belong to separate IDs. Both score perfectly for same-text lookup; names alone cannot resolve their identities.

### One complete input-to-output path

The authored fixture associates `ml-003` with English `Golden Moon Bakery` and Arabic `مخبز القمر الذهبي`. Its Arabic cross-script query targets `ml-003`, while the English-only view indexes `ml-003-en` and excludes every Arabic alias. This fixture is separate from SQLite; the public comparison uses the existing SQLite adapter and the same downstream path.

1. Preserve the original query and label. Normalize a copy and prefix it: `query: مخبز القمر الذهبي`.
2. Actual tokenizer IDs: `[0, 41, 1294, 12, 15092, 1325, 1469, 213339, 92851, 179, 2]`. These are vocabulary indices, not identity labels.
3. The encoder and mean pool produce shape [1, 384]. First eight actual coordinates: `[0.0178059, -0.0026258, -0.025783, -0.0970803, 0.0556591, -0.0022428, -0.0134066, 0.0371727]`. The vector's measured length is 1.0.
4. Compare that vector to cached English alias vectors, take the highest alias score per entity, and sort. Example 2 shows the actual top three; `ml-003` ranks first with cosine 0.812395.
5. Compare the target ID to ranked IDs: E5 contributes 1 to Recall@1 and 1 to reciprocal rank. RapidFuzz places it ninth, contributing 0 and 1/9. The report averages these contributions with the other eligible queries.
6. Return original aliases and provenance for human inspection. No probability, automated identity verdict or SQLite mutation occurs.

## What, why, who, when, where and how

**What:** a pretrained multilingual E5-small bi-encoder represents names as 384-number vectors. Exact NumPy cosine search ranks aliases, then keeps the best alias for each distinct entity ID. **Why:** test whether learned multilingual representations help where character edits struggle, without changing the original RapidFuzz method. **Who:** the learner reviews the labels and candidate evidence; the software computes rankings. No model decides a person's identity. **When:** after the Phase 3 baseline and explicit Phase 4 approval; no training or threshold fitting occurs. **Where:** everything runs locally, using the existing fictional records, read-only public SQLite snapshot, and a separate invented English/Arabic fixture. **How:** frozen queries and reference views feed both methods; the same metric functions measure both; full rankings, provenance and timings are saved.

See the [architecture and DAG](../adr/0003-embedding-choice.md), [model card](../model-card.md), [original evaluation protocol](../adr/0002-evaluation-protocol.md) and [public data terms](../data-card.md).

## Beginner's guide to the calculations

A tokenizer divides `query: golden moon bakery` into the model's vocabulary pieces and numbers. The transformer encoder uses surrounding pieces to compute a vector for each piece. Mean pooling combines valid token vectors into one vector. The supplied model pipeline performs that pooling. A dimension is one coordinate in the resulting 384-number representation; individual coordinates are not named attributes such as nationality or identity.

The model is a **bi-encoder**: it encodes each name separately. Reference names can therefore be encoded once and cached. A **cross-encoder** would jointly inspect each query/candidate pair, requiring another experiment and approval. No weights are trained in this phase.

For q=(1,2), a=(2,1), the dot product is 1×2+2×1=4. Each length is sqrt(5), so cosine is 4/5=0.8. `unit_vectors` divides each row by its length; dot products of these unit vectors equal cosine. A high cosine means similar directions in this model's space. It is not an 80% identity probability.

Every alias receives a score, but each entity appears once: its maximum alias score wins. Exact alias ties use alias ID; entity ties use entity ID. Two different records with identical names remain separate. Ranking cannot resolve their identity from names alone.

Recall@k counts eligible targets ranked at most k, divided by eligible positive queries. MRR averages 1/rank: first gives 1, second gives 0.5, fourth gives 0.25. Diagnostic ambiguities and absent targets do not enter those denominators. Recall@10 is N/A for the ten-entity bilingual fixture because returning ten returns everyone. Recall@50 is N/A for all three small corpora. Null is not zero accuracy.

## File and function walkthrough

The following explains what each addition does, why it exists, when it runs, where its inputs/outputs live, who consumes the output, and how its important operations work.

### `src/watchlist/matching_embeddings.py`

- `unit_vectors`: used at encoding, cache loading and search boundaries. Converts arrays to float32, checks two dimensions and finite values, computes row lengths with `axis=1, keepdims=True`, rejects zero/nonfinite lengths, divides each row by its length. These checks prevent invalid scores from silently reaching the learner.
- `rank_vectors`: receives one query vector, ordered alias vectors and the original entities. Checks positive integer k, distinct entity IDs, nonempty aliases and matching shapes. `matrix @ q[0]` computes all alias dot products; clipping only removes floating-point excursions outside [-1,1]. `offset` maps flattened vector rows back to aliases. The negative-score sort key puts larger scores first. Returns the existing `Candidate` structure with original script, alias ID and provenance intact.
- `SCORER_NAME` names the new method; the original matcher and normalizer are unchanged.

### `src/watchlist/embeddings.py`

- `MODEL_ID`, `REVISION`, `MODEL_FILES`: constrain acquisition to the approved model revision and ten selected files. Alternate framework weights are excluded.
- `file_hash`: reads one-megabyte chunks into a SHA-256 digest, so integrity checks need not load a whole weight file into memory.
- `validate_config`: rejects unapproved model, device, precision, dimensions, prefix, pooling or normalization. Batch size is an integer from one to eight. Freezing this contract prevents a later run from silently changing the experiment.
- `verify_model`: reads the local acquisition receipt and verifies its model/revision/file set and every file checksum. It runs before loading weights and requires no network.
- `fetch_model`: the explicit network entry point. Checks remote revision and selected advertised sizes, then streams to partial files while enforcing size limits. Verifies upstream SHA-256 where supplied; records a local hash for every file. Only completed verified files receive their final names. An acquisition receipt is written after all files finish. An incomplete directory requires inspection before retrying. This is intentional fail-closed behavior, not automatic resumable downloading.
- `E5Encoder.__init__`: verifies files, imports Torch/Sentence Transformers lazily, fixes seed 42, CPU/four threads and deterministic algorithms, disables remote code, and loads local safetensors. `eval()` disables training behavior. Records configuration, hashes and library versions for the experiment and cache.
- `E5Encoder.encode`: preserves source records while normalizing a separate input copy and adding `query: ` to both query and reference names. Checks token lengths before inference, rejecting truncation beyond 512 tokens. Encodes in batches, returns normalized float32 vectors, and verifies the expected row count and 384 columns. Empty input returns an empty correctly shaped matrix.
- `cached_aliases`: fingerprints model metadata and complete ordered entity/alias/provenance records. The fingerprint names a `.npy` matrix and JSON manifest. A hit verifies manifest, checksum and shape; `allow_pickle=False` prevents loading Python objects. A miss encodes aliases and writes the matrix and manifest. Changed provenance/configuration creates a different key. Only reference vectors are cached for timing; queries are encoded anew.
- `main`: exposes explicit `fetch` and offline `verify` commands. Merely importing a module does not download a model.

### `src/watchlist/compare_retrieval.py`

- `phase3_benchmark`: rebuilds the existing reference views, verifies source/split audit and query fingerprints against the saved Phase 3 results, then consumes those original queries. Public SQLite is read through the existing read-only adapter.
- `multilingual_benchmark`: builds English-only, Arabic-only and bilingual views from authored fixtures. Checks ID uniqueness, query ancestry and partition consistency. Cross-script views contain no query-script aliases, preventing exact lookup from masquerading as cross-script retrieval.
- `compare`: prepares alias caches, obtains both full rankings on the same view, checks the entity universe, and measures 20 fresh calls after an untimed warm-up per query. E5 timing includes query encoding, exact search and entity grouping. It retains each query, label, candidate and factual failure reason, then reuses Phase 3 metric aggregation. Additional slices separate cross-script directions and organisation translations from person-like transliterations.
- `report`: renders computed metrics with denominators and paired improvements/regressions. All rankings and unsuccessful queries remain in JSON, even when the readable report displays only a subset.
- `main`: loads one encoder, runs selected corpora, checks paired RapidFuzz candidate scores/order against Phase 3, and writes JSON/Markdown. Public-derived outputs remain in the ignored local data directory.

### Function locations and test helpers

Locations in the completed application files: `embeddings.py`: `file_hash` 24,
`validate_config` 33, `verify_model` 44, `fetch_model` 57, `E5Encoder` 106,
constructor 109, `encode` 131, `cached_aliases` 148, CLI `main` 174.
`matching_embeddings.py`: `unit_vectors` 11, `rank_vectors` 22.
`compare_retrieval.py`: `phase3_benchmark` 22, `multilingual_benchmark` 45,
`compare` 75, `report` 139, its nested `show` formatter 141, CLI `main` 167.
`show` formats a computed value and denominator, or N/A for null values; it does
not calculate accuracy. Line numbers are navigation aids for this revision.

The test-only `FakeEncoder` classes return simple fixed two-number vectors and
track calls, making cache and evaluator behavior hand-checkable without weights.
The test-only `Model` supplies token counts and outputs for prefix/truncation
checks. The `entity` helper constructs tiny fictional records. The mocked HTTP
`response` helper returns authored bytes instead of opening a network connection.
These helpers are used only by pytest; they do not substitute for the separately
measured real-model results.

### Existing code modified narrowly

`src/watchlist/evaluate.py` extracts failure wording into `ranking_failure`. Its default wording preserves Phase 3 behavior; the embedding caller can say “cosine similarity” instead of incorrectly saying “edit similarity.” Metric formulas and the RapidFuzz algorithm are unchanged. `tests/test_evaluation.py` verifies both wordings.

### Configuration, fixtures, dependencies and tests

| File | Purpose and use |
|---|---|
| `eval/configs/embeddings.json` | Frozen model/version/device/prefix settings, cache directory, three dataset names and twenty timing repetitions. Read before inference. |
| `eval/fixtures/multilingual_entities.json` | Ten invented records with original English/Arabic names: two development, six test, two same-name ambiguity records. Distinct IDs persist. |
| `eval/fixtures/multilingual_queries.json` | Sixty-four fixed queries with target ID, source alias, operation, script, partition and translation/transliteration labels. No online translation or random generation during scoring. |
| `tests/test_matching_embeddings.py` | Hand-calculated cosine, best-alias grouping, negative scores, deterministic ties, invalid vectors/dimensions and k. |
| `tests/test_embeddings.py` | Mocked acquisition size/hash checks, prefix/token limits, cache reuse/invalidation/corruption and configuration rejection; no network or real weights. |
| `tests/test_compare_retrieval.py` | Same query/entity universe using a fake encoder, preserved Phase 3 fixtures and bilingual cross-script/ambiguity checks. |
| `tests/integration/test_embedding_model.py` | Explicit opt-in real local model test: shape, float32, unit length and repeated inference within 1e-6. No download. |
| `pyproject.toml` | Optional `embeddings` dependency extra and integration marker. Core RapidFuzz mode does not import these libraries. |
| `uv.lock` | Managed exact versions and distribution hashes for reproducible dependency resolution. |
| `.gitignore` | Ignores local model weights and embedding cache; public evaluation outputs were already ignored. |

NumPy stores vectors and performs dot products. PyTorch runs the pretrained neural network. Sentence Transformers assembles tokenization, encoder and pooling; its managed dependencies include Transformers, tokenizers and safetensors. Hugging Face Hub is a transitive dependency, but inference uses local files only. No new database or hosted inference service is used.

Embedding test modules skip when NumPy is absent, allowing a baseline-only installation to keep running its tests. Having NumPy does not trigger downloading weights. Real-model testing additionally requires the explicit integration opt-in.

### Documentation and generated artifacts

- `docs/adr/0003-embedding-choice.md`: architecture DAG, frozen protocol, model/search choice, cache and fair-comparison decisions.
- `docs/model-card.md`: model revision, license attribution, intended use, official model-documentation links and limitations.
- `docs/progress/phase-04.md`: this teaching/completion report.
- `README.md`, `docs/design.md`, `docs/evaluation-plan.md`, `docs/implementation-phases.md`: current phase status and reproducible commands; historical reports remain historical.
- `eval/results/phase04/{fictional,multilingual}/{results.json,report.md}`: computed fictional rankings, metrics, timing and readable summaries.
- `data/evaluation/phase04/public-small/{results.json,report.md}`: equivalent local-only public-derived results.
- `data/models/e5-small/`: approved model files and acquisition receipt; ignored, not application code.
- `data/embedding-cache/`: checksum-protected reference matrices and manifests; ignored and rebuildable.

## Known implementation limitations

The cache is a local single-process cache. Matrix and manifest are separate writes; concurrent writers and crash-safe multi-file transactions are not implemented. A checksum mismatch stops evaluation. The acquisition receipt is an integrity record, not protection against an attacker who can rewrite both receipt and files. Fixed seeds cannot guarantee bitwise equality across different hardware or library versions.

The authored Arabic aliases are teaching labels, not independently reviewed multilingual identity evidence. Organisation-name translation differs from person-name transliteration. The fixture is tiny, intentionally contains similar names, and is visible to the implementer. Existing test results have already been inspected. No test outcome was used to select a different model or tune this run. Unknown upstream duplicates and model pretraining overlap remain possible.

No accuracy or latency claim extends beyond these local corpora. Model construction, Python imports, file verification, SQLite loading and reference preparation are excluded from warm query latency; construction/reference timings are recorded separately. Peak process memory has not been measured. No score calibration, decision threshold, fine-tuning, reranker, Qdrant, LangGraph, deployment or Phase 5 work is included.

## Commands actually run and why

Commands ran from the project root. The temporary uv paths were available during approved installation but no longer exist at the final check. The installed `.venv` remains usable. Recreating dependencies uses `uv sync --locked --extra embeddings --dev` with an available uv installation and any required network approval; do not assume a temporary path persists.

```sh
UV_CACHE_DIR=/tmp/polyglot-phase1-uv-cache /tmp/polyglot-phase1-tools/bin/uv add --optional embeddings --no-sync numpy sentence-transformers torch
UV_CACHE_DIR=/tmp/polyglot-phase1-uv-cache /tmp/polyglot-phase1-tools/bin/uv sync --locked --extra embeddings --dev --dry-run
UV_CACHE_DIR=/tmp/polyglot-phase1-uv-cache /tmp/polyglot-phase1-tools/bin/uv sync --locked --extra embeddings --dev
```

These managed the optional dependencies, inspected the proposed installation, then installed approved packages. Model acquisition was explicit:

```sh
SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/python -m watchlist.embeddings fetch --config eval/configs/embeddings.json
.venv/bin/python -m watchlist.embeddings verify --config eval/configs/embeddings.json
```

The first fetch stopped at the metadata cap; after correcting that bounded check, the second succeeded. `verify` checked the completed local receipt and hashes. No new public data was downloaded.

```sh
.venv/bin/python -m pytest -q tests/test_embeddings.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest -q -m 'not integration'
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 RUN_EMBEDDING_INTEGRATION=1 .venv/bin/python -m pytest -q -m integration tests/integration/test_embedding_model.py
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 RUN_EMBEDDING_INTEGRATION=1 .venv/bin/python -m pytest -q
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m watchlist.compare_retrieval --config eval/configs/embeddings.json
```

The focused acquisition/cache tests passed 5/5. Earlier full unit runs passed 143 and then 144 tests as coverage was added. The final results are listed above. The integration-only first run passed in 66.72 seconds with a deprecation warning; the corrected final full suite passed in 3.97 seconds. First-run imports and subsequent filesystem caching differ, so these durations do not isolate model startup performance.

Local inline Python checks also:

- blocked NumPy imports through an import hook and invoked `pytest.main(['-q'])` to simulate core-only installation;
- hashed eleven existing files before and after evaluation;
- instantiated a fresh encoder, loaded all seven cached reference views, reranked all 430 queries, asserted identical entity/alias order and score differences ≤1e-6, and checked each Markdown report equals `report(saved_json)`;
- extracted real tokenizer IDs, vector coordinates, ranks and metrics for this report;
- inspected installed versions through `importlib.metadata`, parsed new modules with `ast`, and inspected disk usage with `du -sh`.

Verification receipts are local under `data/evaluation/phase04/verification-before.json` and `verification.json`. This second pass did not overwrite benchmark timings or rerun the twenty timing repetitions. Routine reads used `cat`, `rg`, `sed`, `head`, `tail`, `ls` and `pwd`; edits used local Python scripts and shell heredocs. A read-only `git status --short` check found no Git repository; no repository was initialized or committed. A diagnostic `ps` command was denied by the sandbox; it was unnecessary and was not escalated. A Torch `-X importtime` probe and an offline Sentence Transformers import probe completed successfully while investigating the first integration startup.

## Errors, warnings and fixes

1. Model metadata was 1,067,261 bytes, exceeding the first one-megabyte metadata guard. The fetch refused it before downloading model files. The revised metadata ceiling is eight megabytes and metadata still counts toward the unchanged 600 MB total cap. A mocked acquisition test covers oversized advertised files and bad checksums. No cap on approved weight acquisition was enlarged.
2. Optional embedding test modules originally imported NumPy unconditionally. `pytest.importorskip` now skips those modules in a core-only installation; the simulated installation verified this behavior.
3. Sentence Transformers warned that `get_sentence_embedding_dimension` was renamed. Changed the dimension check to `get_embedding_dimension`, and reran the full suite successfully. The inference protocol did not change.
4. The dependency resolver repaired an invalid upstream requirement spelling (`>= '2.7'` to `>=2.7`); installation completed. Torch prints a macOS redirect-support note from its distributed utilities. This experiment uses local inference, not distributed training; the note did not prevent testing or evaluation.
5. An interrupted early test process had no confirmed outcome and is not counted as a successful run. Later explicit runs supply the reported results. Temporary tooling paths disappearing does not affect the existing virtual environment.

## Comparison with the friend's original portfolio proposal

| Proposed objective | What Phase 4 establishes / what remains |
|---|---|
| Off-the-shelf multilingual-e5 or LaBSE baseline | One pinned E5-small model measured; alternatives reviewed from documentation, not claimed as evaluated. |
| Compare fuzzy and dense retrieval | Same query labels, reference aliases and entity universe, unchanged RapidFuzz rankings, paired metrics and failures. |
| Cross-script name matching | A small authored English/Arabic diagnostic improves, but person-like transliteration still fails; public cross-script evidence remains insufficient. |
| Retrieve top 50 / Recall@10 and @50 | Exact search and entity grouping work. Corpus sizes make Recall@50 uninformative, and bilingual Recall@10 is also N/A. |
| Entity-level evaluation and reproducibility | Existing splits preserved; new development/test/ambiguity IDs separate; pinned model, hash receipts, offline tests and repeatable rankings. Unknown upstream duplicate identities and pretraining overlap are unresolved. |
| Measurable speed and cost | Local CPU timings include fresh query encoding; no paid API. E5 costs several milliseconds versus fractions of a millisecond here. No throughput or peak-memory claim. |
| FPR at 99% recall / auto-decisions at 99% precision | Not established: no calibrated threshold or sufficiently independent operational dataset. |
| Fine-tuned bi-encoder / cross-encoder | Not implemented; future optional Phase 5 needs a separate data and experiment review. |
| Agent, human-review persistence, memory and audit | Later phases; current outputs provide candidate evidence for human inspection only. |
| Model card, decision record, reproducible results | Added now, with commands and all raw ranks; no deployment, CI, Makefile or PDF scaffold added. |

## Acceptance and next approval gate

The frozen model loaded locally; offline unit and opt-in integration tests passed; alias grouping and source evidence are retained; original Phase 3 inputs and RapidFuzz rankings were checked; all three paired experiments and failure galleries were saved; repeated inference reproduced results; limits and acquisition costs are documented. Improvement was a question, not a required acceptance threshold.

The result supports continuing research into word order and some cross-script retrieval. It does not justify replacing human judgment, treating cosine as a probability, or assuming a perfect public-subset score generalizes. A larger independently reviewed benchmark would be needed before meaningful operational conclusions; no such download is authorized by this phase.

**STOP: Phase 4 is complete.** The next decision is whether to approve **Phase 5 planning only**: review data adequacy and failure cases before deciding whether fine-tuning or reranking is justified, or explicitly defer training. No Phase 5 implementation begins without a separate explicit approval.

Final documentation/artifact checks passed: all three new application modules parsed; all three generated reports matched their saved JSON rendering; local links in seven changed/new documentation files resolved; all eleven pre-evaluation file hashes remained unchanged. Changes since the final 145-test run were documentation only. The compatibility demo `.venv/bin/python -m watchlist --name 'Luma Vespr' --top-k 3` returned `syn-001` and the distinct same-name `syn-012` at 90.909091, followed by `syn-002` at 81.818182, with the original research-review notice. No identities were merged.
