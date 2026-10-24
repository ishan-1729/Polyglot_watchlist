# Decision 0004 — defer training; measure pretrained reranking first

Status: **Phase 5A inference-only pilot approved**, 2026-10-21. Training remains unapproved. The latest approval narrows reranking to the E5 arm; implementation and measured outcomes are recorded in [Phase 5A](../progress/phase-05a.md). See the [full Phase 5 plan](../phase-05-plan.md) and [planning progress record](../progress/phase-05.md).

## Context and decision proposed

Our public training partition has seven entities and twenty-one aliases. Four entities provide thirty-seven unordered distinct-name combinations; only one has multiple scripts. The twenty-record public benchmark's 141 challenge queries come from six test groups. Current test examples have already been inspected. More synthetic pairs would not supply independent entity diversity.

Propose an inference-only pilot using `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revision `1427fd652930e4ba29e8149678df786c240d8825`, before any task-specific fine-tuning. It is a multilingual passage-relevance reranker, so transfer to names is an experiment. Its listed license is Apache-2.0; one safetensors file is approximately 471 MB. Model documentation and size sources are linked in the full plan. The bounded single-model acquisition is approved; its receipt and recovery accounting are documented in Phase 5A.

## Experiment boundary

Use the unchanged E5 output in a paired E5-versus-E5-plus-cross-encoder arm, per the latest explicit approval. RapidFuzz remains unchanged and is not reranked in this pilot. Freeze top-five entity IDs; score every available reference alias within those shortlisted entities; keep maximum alias logit and stable alias/entity tie rules. Preserve original-script evidence and source provenance. Do not reintroduce held-out aliases or inject targets. Predeclare K=10 as sensitivity only. Compare truncated baselines on the same candidate sets.

Report candidate Recall@K, end-to-end Recall@1, MRR@K, conditional top-1 accuracy given target retrieval, script/type slices, all failures and true timing scope. Preserve full Phase 4 reports. These familiar datasets remain regression diagnostics, not fresh holdouts. Neither raw logits nor sigmoid outputs are identity probabilities.

## Options deferred

- Fine-tuning existing E5-small: consider only if new, independently reviewed data exposes retrieval misses.
- Fine-tuning a small cross-encoder with binary cross-entropy: consider only if targets are retrieved but rank poorly and label/data readiness passes.
- XLM-R-base: a heavier base encoder requiring a scoring head and task training; not an already trained name matcher.
- Larger model comparisons, Colab uploads, dataset expansions, new dependencies and Phase 6: separately approved.

Recommend a future bounded CC0 Wikidata non-person organisation alias corpus, with a small feasibility gate before a 5,000-group target. Unknown attainable bilingual coverage and label review remain unresolved. Existing OpenSanctions data retains CC BY-NC obligations; no commercial reuse or publication rights are assumed.

## Consequences

We can learn whether joint pair scoring helps without confounding that question with tiny-data overfitting. This adds inference cost and may regress. A negative result is acceptable; it should not trigger unapproved training or more model downloads. The full plan defines budgets, sampling, disjoint splits, BCE arithmetic, DAGs, files, commands, tests and acceptance criteria.

**Current gate: stop after Phase 5A. Fine-tuning, dataset expansion, threshold changes, Phase 5B and Phase 6 require separate explicit approval.**
