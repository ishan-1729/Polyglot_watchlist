# Phase 5 — planning and training-readiness audit only

Date: 2026-10-21. **Step A complete; Step B awaiting approval. No training results exist.** This is a planning record, not a Phase 5 implementation completion claim. Phase 6 has not begun.

## 5W1H

- **What:** audited available records/splits, inspected saved Phase 4 results and proposed an inference-only cross-encoder pilot before training.
- **Why:** seven public training entities cannot support a credible generalization claim, regardless of how many synthetic pairs are generated.
- **Who:** the learner approves experiments and reviews labels; software measures record retrieval; a competent language reviewer is needed for defensible bilingual labels.
- **When:** planning follows the completed Phase 4 comparison. Model acquisition, implementation and any later training require explicit approval.
- **Where:** local source/tests/docs and read-only SQLite/results; official web documentation for current model/data terms.
- **How:** inspect existing contracts and evidence, calculate counts from saved records, compare documented model roles/resources, and specify a bounded fair experiment.

## Files changed in this planning step

| File | What and why |
|---|---|
| `docs/phase-05-plan.md` | New detailed teaching/experiment plan covering fine-tuning concepts, actual data audit, licenses, model candidates, hardware estimates, future dataset, sampling/splits, BCE example, metrics, DAGs, proposed files/commands and approval gates. |
| `docs/adr/0004-training-decision.md` | New proposed decision: defer training, test one pretrained multilingual reranker first. Explicitly awaiting approval. |
| `docs/progress/phase-05.md` | This planning audit and action/check record; will later distinguish actual approved experiments from proposals. |
| `docs/implementation-phases.md` | Appended current Phase 5 planning status and narrower next approval boundary. |

No application source, tests, dependency declarations/lock, original data, checkpoints, split manifests or evaluation results were intentionally changed. No new functions were implemented; their proposed responsibilities appear in the plan rather than being represented as working code.

## Actual read-only findings

SQLite has 20 legal-entity records, 79 searchable aliases: 76 Latin and three Arabic. Alias properties are 20 `name` plus 59 `alias`; no weak-alias rows in this selected snapshot. Split counts are train 7, development 3, calibration fit 2, threshold selection 2, test 6. The seven training records have 21 aliases; four have at least two distinct normalized names and together yield 37 unordered combinations. Only one train entity is cross-script. No normalized cross-record collision is listed in the existing manifest; unknown duplicate identities remain possible.

Saved Phase 4 test-challenge top-1 counts remain RapidFuzz→E5: fictional 20/27→26/27, public 129/141→141/141, bilingual 16/30→25/30. These were read from JSON, not rerun. The public test has only six target groups; familiar synthetic benchmarks are not untouched future holdouts. The actual limitations motivate the proposal; no new performance number is asserted.

## Commands and checks actually performed

- `cat AGENTS.md`, `rg --files`, `cat`/`sed` reads of the reference's Project 1, engineering and agent guidance; design/evaluation/phase documents; ADRs/data/model cards; source and tests.
- Local `.venv/bin/python` read-only audit using existing `load_database`, `connect_database(..., readonly=True)`, `normalize_name` and `script_category`; counted aliases/partitions and n(n−1)/2 possible within-ID pairs; read saved Phase 4 JSON aggregates/failure rows.
- Browser searches/reads of official Hugging Face model cards/file listings and commit metadata, Sentence Transformers/PyTorch documentation, OpenSanctions/Creative Commons terms, Wikidata licensing/access guidance and Colab resource documentation. These were documentation reads, not dataset or weight acquisition. Some direct Hugging Face raw/API URLs were inaccessible through the browser tool; the public model page, file listing and linked full commit supplied the verified facts instead. Exact file-hash verification remains an acquisition prerequisite.
- Local Python computed SHA-256 for 78 existing project/data/result files before documentation edits, to verify the scope afterward.
- Documentation written with shell heredocs and a small local Python text edit. No installer, fetch CLI, trainer, GPU job or new evaluation run was invoked. No Git operation was performed in this planning step.

No pytest suite was run during planning because executable code did not change. The 145-test result belongs to Phase 4 and is not presented as a new test run. Future tests, budgets and commands in the plan are proposals only. Final documentation/scope-check outcome is recorded below once verified.

## Recommendation and remaining uncertainties

Request approval only for **5A: implement a pretrained MiniLM reranking pilot on existing frozen data**, with one pinned model download capped at 600 MB and no new dependencies unless separately approved. Use K=5 plus predeclared K=10 diagnostic, CPU float32, raw logits and paired unchanged retrievers. No fine-tuning or larger data acquisition is included.

Still unknown: whether a passage reranker helps names; actual inference memory/time; compatibility of the selected checkpoint with the existing runtime; achievable Wikidata bilingual alias yield; reviewer-confirmed label quality; unknown entity duplicates; and pretraining overlap. The plan labels resource envelopes and corpus targets as estimates, not measurements. Neither a perfect tiny benchmark nor a low future training loss warrants identity or screening guarantees.

**STOP after Step A. Await explicit approval for the specific experiment. No Phase 6.**

Final checks: exactly the three new Markdown files and the implementation-phase status update listed above were found. The other 77 files in the 78-file pre-edit inventory had identical SHA-256 values. Local Markdown links and code-fence pairing passed. The illustrative BCE values (0.2231 and 1.6094) and MRR@5 example (0.625) were verified with standard-library arithmetic. These are documentation checks, not an ML evaluation or pytest run.
