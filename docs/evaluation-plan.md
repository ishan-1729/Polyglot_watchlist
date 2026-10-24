# Polyglot Watchlist — evaluation plan

Date: 2026-10-21. Status: historical proposal plus implemented Phase 3 protocol; approved Phase 4 comparison complete; measured results are in progress/phase-04.md.
Scope: [Project 1 design](design.md). Phase gates: [implementation plan](implementation-phases.md).

## What we are measuring

The question is: given a query and a fixed reference snapshot, can the program retrieve the intended record without presenting too many unrelated records? This measures record matching under a defined labeling process. It does not measure whether a real person is sanctioned, whether two people are identical, or whether anyone committed wrongdoing.

A **query** is one submitted name. A **candidate** is a retrieved entity, not a single alias. A **positive query** has a labeled target entity in the index; an **absent-target query** has no correct entity in the index. A **negative pair** combines a query with a different entity. These units have different denominators and must not be mixed.

Who: the learner reviews labels, the harness, and reported results; the assistant implements approved checks. Where: local versioned fixtures, manifests, and evaluation outputs. When: correctness checks in Phase 1, data/split checks in Phase 2, measured baselines in Phase 3 before any training, then identical-protocol comparisons. How: fixed inputs, frozen configurations, explicit labels, and reproducible commands.

## Dataset progression and labels

1. **Phase 1 fictional fixtures.** Propose 12 fictional entities with 2–3 aliases each, at least one person-like and one organisation-like record, and examples in Latin, Cyrillic, and Arabic scripts. Different entities may share a name to demonstrate ambiguity. Each record carries `synthetic: true` and `fictional-synthetic-v1` provenance. These are software tests, not a benchmark of real-world performance.
2. **Phase 2 permitted subset.** Select one source and a bounded size only after reviewing current terms and receiving download approval. Store source URL/identifier, source record ID, retrieval date, file checksum, license/terms reference, transformation version, and canonical group ID. Keep raw data only where terms permit. Add more sources only with explicit scope approval.
3. **Query labels.** Store query ID, source entity group, target ID or absent-target label, base alias, script direction, perturbation type, seed, and label confidence. Preserve ambiguity: do not force a single ground-truth match when the source cannot support one. Keep unresolved examples out of headline metrics and report their count separately.
4. **Label audit.** Manually inspect up to 100 sampled alias pairs, or all if fewer, stratified by source and script. Report inspected count, discrepancies, uncertainty, and exclusions. A shared source entity ID is a working label, not proof of identity. Authored perturbations can create accidental collisions and need checks too.

No private personal records or individual scraping. Public-data results cannot automatically be redistributed; code, aggregate results, and synthetic demos may need separate packaging.

## Entity grouping and leakage prevention

**Leakage** means information from evaluation examples affects model learning or choices, making results appear stronger than they are. Splitting randomly by name pair is unsafe because different aliases can describe the same entity.

- Link confirmed duplicates across sources into canonical entity groups before allocating splits. Use source links and reviewed evidence; identical names alone do not justify merging. Quarantine unresolved possible duplicate groups that could cross split boundaries.
- Keep every alias, generated query, and reviewed decision for a group in the same split. Store immutable split manifests and a fixed seed; sort identifiers before random assignment.
- Separate training, development, calibration-fitting, threshold-selection, and final test groups. A starting allocation for an adequately sized corpus is 50/15/10/10/15 percent. These are proposed allocations, not measured counts. If there are too few independent groups or script examples, reduce the experiment's scope or postpone calibration/training rather than claim statistical support.
- Training fits model weights. Development chooses scorers, normalization, model settings, and candidate depth. Calibration-fitting learns a score-to-frequency mapping. Threshold-selection chooses review policy. Final test is untouched until configuration freezes. No result from the final test may be used to tune the same reported experiment.
- In Phase 3, training/calibration portions remain reserved; baseline settings are chosen on development only. In Phase 4, an off-the-shelf model is evaluated without local training, but checkpoint selection still uses development data.
- Mine training negatives only from training groups. No test-entity aliases, query labels, or reviewer decisions become supervised learning examples. For pair datasets, both members must obey partition boundaries.
- Check disjoint group sets, source-ID overlap, cross-source duplicate mappings, repeated normalized queries, copied aliases, and perturbation ancestry. Shared generic names are possible across genuinely different entities; report these collisions and retain the ambiguity rather than deleting hard cases to improve scores.

### Index presence is not supervised training

To retrieve a held-out entity, the evaluation index must contain its reference record. This is permitted: the frozen matcher reads its reference aliases without training on the held-out query/target label. Use a documented, fixed index of permitted reference aliases, containing held-out targets and distractors; all compared methods use the same snapshot. Exclude target entities entirely for absent-target tests.

Avoid trivial retrieval as the only test: query from an alias withheld from that entity's reference aliases when possible. If there is only one alias, test a declared perturbation and label it as such. Keep exact-alias lookup as a separate sanity slice. Do not include a generated test query verbatim in the reference index except in that explicit exact-lookup slice. Check index/query overlap and report unavoidable generic-name collisions. A test result on a familiar pretrained model also cannot prove its original pretraining corpus never included public names.

## Query suites and stratification

**Stratification** means showing separate results for meaningful groups so an overall average cannot hide failures. Each perturbation inherits its entity's split. Use fixed seeds and preserve the untouched original.

| Suite | Construction and reason |
|---|---|
| Exact and formatting | Case, whitespace, and compatible Unicode forms; correctness checks for normalization. |
| Character noise | Insertions, deletions, replacements, and adjacent swaps, with severity recorded. |
| Name structure | Word-order swaps, dropped middle tokens, initials, and particle variants; some changes are ambiguous and require label review. |
| Romanization variants | Authored or reviewed alternate spellings; do not assume machine transliteration is ground truth. |
| Cross-script | Reference/query script pairs such as Arabic→Latin, Cyrillic→Latin, and same-script controls. Report direction and sample size. |
| Mixed script | Mixed writing systems, including look-alike characters; test both misses and spurious suggestions. |
| Hard negatives | Distinct entities with similar names; development and training mining obey split boundaries. |
| Absent target | Fictional unrelated names initially; later approved labels with target absent from the snapshot. A missing target is not evidence about the wider world. |
| Ambiguity and missing context | Identical names on different records, missing fields, contradictory fields; expected response retains uncertainty. |

Report by script direction, perturbation, entity type, source, name length, and missing metadata where sample sizes allow. Do not assert that any particular language is hardest before measuring it.

## Metrics and denominators

Let Q+ be the number of answerable positive queries. Let Q0 be the number of absent-target queries. Rank distinct entity IDs by each entity's best alias score, with stable tie-breaking; duplicate aliases must not fill the top-k list.

| Metric | Exact question and calculation | Use and limitation |
|---|---|---|
| Recall@k, k=10 and 50 | Number of positive queries with a labeled correct entity in the first k distinct candidates divided by Q+. For multiple justified targets, a hit means at least one; disclose this policy. | Retrieval metric, not decision accuracy. Effective k is min(k, index entity count). Small Phase 1 fixtures cannot demonstrate meaningful Recall@50. |
| Top-1 record accuracy | Positive queries whose first candidate is a labeled correct entity divided by Q+. | Optional ranking diagnostic; ambiguous labels reported separately. |
| Pair false-positive rate | Negative query–entity pairs above a frozen score threshold divided by all evaluated negative pairs. | Useful scorer diagnostic; not a query-level false-alarm rate. |
| Absent-target false-suggestion rate | Absent-target queries with at least one candidate above a frozen reporting threshold divided by Q0. | Measures false suggestions per query. A top-k system with no threshold always returns candidates on a nonempty index; report that behavior rather than inventing selectivity. |
| Wrong accepted-record rate | Queries for which a simulated policy accepts an incorrect entity divided by all evaluated queries; also report errors divided by accepted suggestions. | Includes selecting a wrong record when the correct one exists. Only for later offline policy experiments. |
| End-to-end recall | Positive queries whose target is both retrieved and selected by the fixed experimental policy divided by Q+. | Retrieval misses remain failures; do not report reranker-only recall as end-to-end recall. |
| False-negative / low-score error | Positive queries routed to a simulated low-score negative branch divided by Q+. | Required before any study of negative routing; match precision cannot justify “clear” decisions. |
| Review rate and coverage | Queries routed to human review divided by all queries; coverage is the share not routed to review under the experimental policy. | Operational-sounding numbers remain research simulations. Distinguish a pending review from a completed one. |
| Precision | Correct suggested/accepted entities divided by all suggested/accepted entities at the defined unit. | Depends on target prevalence and selection policy; disclose both. Undefined with no suggestions. |
| ECE and reliability plot | In fixed probability bins, compare average predicted match probability with observed labeled-match frequency; ECE is the count-weighted absolute gap. | Phase 6 only; report binning and counts, before/after calibration. Small-bin estimates can mislead. |
| Latency | Per-query elapsed time; median and p95, sample count, hardware, corpus size, warm/cold status. | Report retrieval, model, and total times separately. |
| Cost per 1,000 queries | Measured billable usage times recorded prices, scaled to 1,000; disclose local compute assumptions separately. | Optional approved API experiments; local execution is not a claim of zero total cost. |

The reference's “false-positive rate at 99% recall” is an experiment target, not an acceptance guarantee. Select any threshold on development/threshold-selection data, freeze it, and report achieved test recall with test false-positive measures. If 99% recall is unattainable or unsupported by sample size, say so. Never move the threshold on the final test to manufacture the headline.

## Baselines before training

1. Phase 1 establishes normalized string similarity behavior and stable entity-level ranking.
2. Phase 3 builds and hand-checks the evaluation harness, then measures that baseline. Add Jaro–Winkler, token-sort, or phonetic comparisons only as separately justified small changes.
3. Phase 4 compares one permitted pretrained embedding model against the frozen baseline on the same query/index protocol. Keep model revision, tokenizer settings, pooling, normalization, and distance function with results. Consider a hybrid union only after development evidence; deduplicate by entity before ranking.
4. Phase 5 may train a bi-encoder, then a cross-encoder, with separate approvals if worthwhile. Report retrieval ceiling and conditional reranking quality separately. A reranker cannot recover a missing target.
5. An optional frontier-LLM pair benchmark uses the same evidence, versioned prompts, strict outputs, and recorded responses. Match candidate sets for reranking comparisons, or label a differing end-to-end system separately. A language model is a comparator, not an oracle or assumed upper bound.

Every comparison records corpus/query counts, split IDs, versions, configuration, run command, seed, hardware, metrics, and failures. Commit operations require approval; results are first saved locally.

## Calibration and conservative routing

Calibration estimates the frequency of a **labeled record match** for a specified scoring population; it does not estimate criminality or establish identity. Candidate-pair probabilities do not automatically describe the top-ranked candidate after selection. Fit/evaluate on the same defined selection process that will use the score, including realistic negative candidates and retrieval failures where relevant.

Fit a proposed logistic/Platt or isotonic mapping on calibration-fitting groups, select thresholds on different groups, then evaluate once on final test groups. Inspect whether score ordering, sample size, and script coverage support the chosen method. If they do not, retain raw-score ranking and human review.

For an offline two-threshold study, define both upper-branch wrong-match risk and lower-branch missed-target risk separately. Estimate review coverage and plot risk versus coverage. Use explicit one-sided bounds and account for threshold search/multiple comparisons; a binomial interval evaluated on the same adaptively selected sample is not a free guarantee. Clustered aliases violate independent-pair assumptions. Independent confirmation or an appropriate risk-control method is needed for stronger claims.

No numeric target such as 99% precision becomes an operational guarantee. Even zero observed errors in a small sample provides weak evidence. Distribution changes, new scripts, changed retrieval, new snapshots, or new models invalidate automatic reuse of calibration; review and re-evaluate. Deploying automatic decisions is outside this prototype's scope.

## Uncertainty, memory, and safety experiments

- For measured rates, show numerator, denominator, and a 95% interval where defensible. Bootstrap independent entity groups rather than individual correlated aliases; retain all queries for a sampled group together. Use a fixed resampling seed and record the number of resamples. Absent-target queries need documented independent generating groups too. Degenerate zero-error bootstrap intervals need an appropriate conservative bound or explicit warning, not an unsupported certainty claim.
- Small slices may receive counts and an “insufficient evidence” label instead of a strong comparative claim. Report uncertain labels and excluded cases alongside metrics.
- Memory evaluation uses chronological earlier reviews and later queries, with duplicate and split checks. Compare the same future queries with/without memory. Separate repeat-case assistance from unseen-entity generalization. Report errors propagated by stale decisions, reviewer corrections, and workload; do not count stored test answers as model improvement.
- Before adding LLM explanations, test 5–10 planted instructions in synthetic free-text fields, including attempts to alter policy, hide evidence, or reveal other cases. Scores/routing must remain unchanged when only non-evidential malicious instructions change; output must not follow the planted instruction or fabricate source references. Validate factual evidence changes separately.
- Later tests cover unauthorized review access, duplicate resume, stale snapshot/version use, failed persistence, malformed inputs, checkpoint recovery, audit modification detection relative to a trusted anchor, and memory correction/deletion. No service is exposed publicly for these tests.

## Harness acceptance and reporting

Phase 1 uses `pytest` with manually specified expected behavior. Phase 3 adds tiny hand-calculated ranking fixtures: target first, target below k, absent target, duplicate aliases, ties, empty input/index, and zero denominators. A zero-denominator metric is reported as undefined with its count, never silently converted to a good score. A deliberately leaking manifest must fail validation.

The later proposed entry point is `uv run python -m watchlist.evaluate --config eval/configs/baseline.json`; a future `make eval` can wrap it. Neither exists or was run in Phase 0. Offline reruns must reproduce metric values from the same artifacts; timing is expected to vary and is reported separately. Tests must not download data or call live APIs.

Final reporting includes a baseline/comparison table, script/perturbation slices, uncertainty, provenance, reproducible commands, limitations, and up to 20 reviewed failures (all failures if fewer). Use synthetic examples publicly unless real-data redistribution is explicitly permitted. Do not fill future tables with guessed scores or reuse the reference's CV placeholders.

## Phase 3 implemented protocol

The [Phase 3 ADR](adr/0002-evaluation-protocol.md) freezes the approved fictional-first, unchanged-RapidFuzz experiment. [Actual results](progress/phase-03.md) distinguish sanity, challenge, ambiguity and absent-target suites. Public data use the existing 20-record snapshot only. Recall@1/@10 and MRR include denominators; Recall@50 is N/A when k covers the corpus. No training, calibration, new scorer or larger-source acquisition occurred. Earlier sections remain the broader future evaluation plan.


## Phase 4 paired protocol

See the [frozen embedding decision](adr/0003-embedding-choice.md) and [actual completion report](progress/phase-04.md). Existing Phase 3 query hashes, audits and RapidFuzz rankings are checked before reporting paired results. A separate ten-entity fictional bilingual fixture tests English↔Arabic retrieval with same-script aliases removed, plus exact lookup, deletion and word order. Translation and transliteration are separate diagnostics. Recall@10 is N/A on that ten-entity index; Recall@50 is N/A throughout. Query latency includes fresh model encoding. All candidate rankings and denominators are saved. No local model training or threshold selection occurs.

## Implemented Phase 5A paired protocol

The latest approval narrows the original plan to **E5-only** candidate reranking;
RapidFuzz and E5 implementations and earlier outputs remain unchanged.
`eval/configs/reranking.json` freezes the model commit and SHA-256 of the three
Phase 4 artifacts. The evaluator checks queries, labels, alias-view fingerprints
and candidate IDs before inference. Primary K=5; K=10 is sensitivity only.
Every available alias of each shortlisted entity is scored, without restoring
withheld aliases. Maximum raw alias logit gives the entity score, with stable
alias-ID/entity-ID ties. The reranker never sees target labels during scoring.

For N eligible positives, H retrieved targets and C first-ranked targets:
candidate Recall@K=H/N; end-to-end Recall@1=C/N; conditional accuracy=C/H;
MRR@K is mean reciprocal rank, with zero for a target outside K. Coverage is
N/A when K spans the index; zero-denominator metrics are N/A. Ambiguous and
absent-target probes remain recorded but are excluded from single-target ranking
metrics. Counts and entity groups are shown, with overlapping slices labeled.

Five fresh timed calls follow one warm-up per query/K. New timing covers
reranking only; Phase 4 E5 timing is historical, not a simultaneous total pipeline
measurement. Exact known aliases are sanity checks; challenge metrics exclude
exact and formatting. Typos, word order, held-out aliases and true cross-script
views are reported separately. Existing test examples are exposed exploratory
diagnostics, not a new held-out generalization study. No model/setting selection
is justified by choosing the best test slice or K after this run.

See [Phase 5A](progress/phase-05a.md) for results, failures and limitations.
No probabilities, calibrated false-positive rates, training or threshold changes
are introduced by this protocol.

## Phase 7A workflow checks (implemented)

This milestone evaluates workflow reliability, not a new retrieval method. The [actual report](progress/phase-07a.md) records tests and a fictional process-restart walkthrough. Acceptance covers strict review validation, unmodified candidate/evidence order, empty-result review, no-MiniLM imports, real SQLite subprocess pause/resume, five abrupt-crash boundaries, concurrent/duplicate/stale rejection and audit corruption checks. A separately opted-in local E5 integration compares IDs/order/aliases/provenance and scores within 1e-6 against the unchanged ranker. No benchmark evaluator or previous result output is rerun/overwritten. No accuracy, calibration or human-review quality improvement is inferred from passing software tests.
