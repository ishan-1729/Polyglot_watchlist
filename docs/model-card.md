# Model card — local retrieval and experimental reranking

Updated during approved Completion Step 06, 2026-10-24. This local prototype retrieves possible reference records for human research review. It does not confirm identity, establish wrongdoing, provide clearance, or operate a live compliance service. No model has been fine-tuned by this project and no score-to-probability calibration has been fitted.

## Components actually used

| Component | Role and current status |
| --- | --- |
| RapidFuzz normalized Levenshtein | Deterministic character-edit baseline and the default fictional JSON CLI. |
| `intfloat/multilingual-e5-small` | Pinned pretrained embedding retriever; incumbent in the local human-review workflow. |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Pinned pretrained reranking pilot over frozen E5 candidates; experimental and disabled in the review workflow. |

A **bi-encoder** converts each query/alias independently into a vector so retrieval can compare them efficiently. A **cross-encoder** jointly reads a query/alias pair and scores that pair, making reranking a short candidate list practical. These are model architectures, not evidence that names identify the same real entity. The developer evaluates their ranking behavior; the human reviewer supplies any annotation.

## E5-small recipe and provenance

- Model repository: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small).
- Pinned revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
- License label recorded for that distribution: MIT. This is saved metadata, not a new online terms verification or an audit of training-data rights.
- Technical report referenced by the saved model documentation: [Multilingual E5 Text Embeddings](https://arxiv.org/abs/2402.05672).
- Configuration: `eval/configs/embeddings.json`; selected local files and SHA-256 values: `data/models/e5-small/acquisition.json`.
- Recorded main safetensors file: 470,641,600 bytes. Other framework copies were not needed for the selected local recipe.

The pinned model documentation describes 12 encoder layers, 384-dimensional embeddings and 100 supported languages. Language-count claims belong to the source model card; they are not measured project coverage or a promise of name-matching/transliteration quality.

The implemented inference path is normalization → `query: ` prefix on both sides → tokenizer → encoder and supplied mean pooling → unit-length float32 vectors → exact NumPy cosine search → best retained alias per entity. It runs on CPU with four threads, reference batch size eight, and a 512-token limit enforced by rejection rather than silent truncation. Original aliases and provenance remain candidate evidence. Local-file verification precedes loading, remote code is disabled, and automatic download is disabled.

Alias caches bind ordered reference records, model/configuration metadata and vector checksums. Current comparisons cache only views actually used by their query subset; a held-out-only run does not encode an unused full-alias view. New CLI comparison caches are inside the new output root. Cache verification detects a mismatch with its recorded evidence; it is not an independent source-authenticity guarantee.

## MiniLM reranking recipe and provenance

- Checkpoint: [cross-encoder/mmarco-mMiniLMv2-L12-H384-v1](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1).
- Pinned revision: `1427fd652930e4ba29e8149678df786c240d8825`.
- Recorded license label: Apache-2.0, from the pinned model card/API metadata. Local acquisition artifacts retain supplied notices, file hashes, byte accounting and provenance.
- Configuration: `eval/configs/reranking.json`; local model path: `data/models/mmarco-minilm/`.

The [pinned upstream card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1/blob/1427fd652930e4ba29e8149678df786c240d8825/README.md) describes multilingual MS MARCO passage relevance, not identity matching. The pilot jointly tokenizes normalized query/alias pairs, performs CPU float32 inference without gradients, and returns raw logits using the checkpoint's identity activation. It scores only the aliases available in E5's frozen shortlist and takes the maximum alias score per entity. Historical primary K=5 and diagnostic K=10 settings remain recorded in the pilot evidence.

A negative logit is a valid ranking value. Applying a sigmoid does not turn that value into a calibrated identity probability. Reranking cannot recover a target absent from the retrieved shortlist. The [Phase 5A report](progress/phase-05a.md) preserves the measured negative/mixed result and recommendation; no new quality experiment was performed as part of the repair or documentation work.

## Evaluation contract and evidence status

The fictional baseline, public-small selection and authored bilingual fixture have all been inspected. Both legacy and current-contract comparisons label their use **regression-only**. The query rows and alias fingerprints required by historical reranking remain preserved through explicit legacy adapters. Current v2 rows derive stricter ancestry, independent labels, retained display names and script evidence. These changes do not create a fresh test set.

Completion Step 05's independent replay preserved 20 method streams and 878 historical aggregate slices with no numeric differences in the checked projection. This establishes compatibility with saved evidence, not new model accuracy or latency. See [Completion Step 05](progress/completion-05.md) for executed tests, actual local model checks, source fingerprints, deliberate v2 differences and limitations. No historical latency was remeasured by that replay.

Current metrics separate index size, requested K, returned count and evaluated depth. They report full MRR only when complete rankings support it, otherwise MRR@K at an explicit cutoff. Missing shortlist targets receive zero at that cutoff without invented tail ranks. Recall excludes cutoffs covering the whole tiny index and distinguishes insufficient evaluated depth. Positive, absent, ambiguous and unlabelable query counts are separate. A suggestion rate on absent queries is not a threshold-based false-positive rate.

A held-out alias is text deliberately removed from retrieval's reference view to test a harder condition. Current views also replace a display name that would reveal that alias. Scorers receive query text and the declared retained view; gold targets/labels are used only afterward to score the returned ranking. Repeat timing runs must reproduce the same candidates, aliases, scores and ordering.

## Scope limits and future work

Neither cosine, edit similarity, raw logits, nor a mathematical transform of them is an identity probability. Calibration would require a defined target, an independently held calibration set, and separate threshold selection and confirmation. That work is planned, not implemented. Automatic identity-match and clear decisions remain disabled regardless of raw score.

Limitations include correlated synthetic queries, few independent target groups, narrow script coverage, uncertain upstream duplicates, visible labels, unknown pretraining overlap, semantic similarity between distinct entities, and max-alias pooling bias. The small corpora cannot establish large-index Recall@50, population accuracy, operational false-positive rates, or a general multilingual guarantee. Floating-point results and timing can change with hardware, runtime, libraries and thread settings.

There is no trained project checkpoint, quantized deployment, approximate/vector-database search, frontier API comparison, or hosted model endpoint. Larger E5/LaBSE candidates in historical planning were documentation comparisons, not locally measured alternatives. Future training, cloud/GPU compute, external LLM calls and hosting require bounded approvals and the unresolved prerequisites in the [access ledger](access-and-resource-ledger.md).

Only local macOS CPython 3.14.0 has executed runtime evidence. The selected declaration is now `>=3.14,<3.15`; Python 3.11–3.13 are outside that range. Prepared Linux CI is not a hosted runtime result. Preserve execution manifests and original stores when changing dependencies: a valid archive remains inspectable while incompatible workflow execution stays blocked.

## Licenses, dependencies and distribution

The model license labels above describe pinned, locally recorded distributions. Code dependencies, model weights, public-source data and project-authored material have separate rights and notices. Preserve supplied model documentation/attribution; do not infer that a dependency metadata label authorizes all training data, source data, outputs or deployment purposes. Recheck the intended distribution/use before publication. This card makes no current legal determination; the separately approved tooling/dependency acquisition and GitHub action review do not verify model or source rights.

`pyproject.toml` declares the core package and optional `embeddings`/`agent` groups; `uv.lock` records resolved dependencies. The Step 06 inventory distinguishes locked packages, locally installed packages and declared license metadata, including missing/ambiguous entries. Inventory completeness is not a legal compatibility audit. See the [dependency/license overview and resolution actions](access-and-resource-ledger.md).

## 5W1H recap

- **What:** a lexical baseline, a pretrained embedding retriever and a separate pretrained reranking experiment.
- **Why:** compare candidate-ranking behavior with reproducible evidence before considering training or calibrated policy.
- **When:** verify files and query/view contracts before inference; compute metrics after retrieval; request review rather than an automatic identity verdict.
- **Where:** approved local CPU inference and isolated caches/results; no external inference endpoint is configured by this work.
- **Who:** developers evaluate the components; human reviewers annotate possible matches; the project owner approves future resources and promotion.
- **How:** pinned recipes, original alias evidence, explicit shortlist denominators, deterministic repeat checks, historical replay and conservative reporting.
