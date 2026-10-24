# Phase 00 report — planning only

Date: 2026-10-21, user timezone Asia/Kolkata. Status: Phase 0 planning delivered; Phase 1 awaits explicit approval. The user's request authorized these planning documents. No application functionality was implemented.

## What changed, file by file

| New file | Contents and reason |
|---|---|
| [design.md](../design.md) | A one-page design brief followed by a request DAG, an explanation of all 16 nodes, a separate offline feedback cycle, safety/review boundaries, an extensive technology/timing map, an illustrative example, and unresolved decisions. Establishes what Project 1 means before code exists. |
| [evaluation-plan.md](../evaluation-plan.md) | Defines records, queries, labels, source provenance, canonical duplicate groups, independent splits, reference-index rules, perturbations, metric denominators, calibration constraints, uncertainty, safety/memory experiments, and harness acceptance. Prevents impressive-looking but misleading results. |
| [implementation-phases.md](../implementation-phases.md) | Proposes Phases 0–10, milestones and gates; lists exact Phase 1 files, intended functions, algorithm/output contract, dependency setup gates, commands, tests, and acceptance criteria. Later phases remain provisional until their own preflight and approval. |
| [phase-00.md](phase-00.md) | This progress report, preserving what was done and what remains unverified. |

No existing project file was edited. `AGENTS.md` and the HTML proposal were read and preserved. No source package, fixture, tests, README, dependency configuration, database, Git repository, or model was created. Function and application-code line explanations are not applicable because Phase 0 added Markdown only. The Phase 1 file table explains planned function responsibilities; it does not describe implemented functions.

## Commands and operations actually run

All shell commands below ran locally from `/Users/odin/Desktop/polyglot-watchlist-starter`. No browser, network request, installation, paid call, or Git command was used.

1. `pwd && rg --files -g 'AGENTS.md' -g '*.md' -g 'internship-2093-portfolio-plan.html' -g 'pyproject.toml' -g 'uv.lock'` — confirmed the working directory and located instructions/reference without assuming application files existed.
2. `cat AGENTS.md && cat docs/reference/internship-2093-portfolio-plan.html` — read the inputs. The combined HTML output was truncated, so this was followed by targeted extraction rather than treating truncated text as complete.
3. `python3 - <<'PY' … PY` using `html.parser.HTMLParser` and `pathlib.Path` — printed the full text of the reference's `p1`, `standards`, `ai`, and `copilot` sections without executing HTML, loading remote fonts, or installing a parser. The optional Microsoft layer was read only to identify Project 1 extensions and exclude Project 2 work.
4. `ls -la && rg -n 'section id=|id="p1|id="standards|id="ai' docs/reference/internship-2093-portfolio-plan.html` — inspected local contents and located reference sections.
5. `python3 - <<'PY' … PY` using `pathlib`, `hashlib`, and `json` — recorded the five pre-existing files and their SHA-256 hashes in `/tmp/polyglot-phase0-before.json`. This temporary validation manifest is outside the project and is not an application artifact.
6. `apply_patch` — created the three requested planning documents, one at a time after announcing each file and its purpose.
7. `python3 - <<'PY' … PY` using `pathlib`, `collections`, `hashlib`, `json`, and `re` — checked the three planning documents for trailing newlines, balanced code fences, trailing whitespace, local link targets, Mermaid edge structure and cycles, node-table coverage, phase coverage, original-file hashes, and the exact set of new files. The command exited successfully, code 0.
8. `apply_patch` — created this fourth file after announcing its purpose.
9. `python3 - <<'PY' … PY` — checked all four documents' structure and local links, compared all original hashes, and asserted that exactly the four intended Markdown files were added. Exit code 0. `rg -n '^## |^### ' docs/design.md docs/evaluation-plan.md docs/implementation-phases.md docs/progress/phase-00.md` then indexed document headings for review.
10. `apply_patch` — recorded that completed final integrity result in this report.

The ellipses above abbreviate inline documentation-inspection scripts, not hidden setup commands. No persistent Python script or test suite was added. Planned Phase 1 commands in the implementation plan have not run.

## Actual check results

The completed pre-report check printed:

```text
PASS document structure: docs/design.md (164 lines)
PASS document structure: docs/evaluation-plan.md (114 lines)
PASS document structure: docs/implementation-phases.md (188 lines)
PASS diagram 1: 16 nodes, 17 edges, cycle=False
PASS diagram 2: 7 nodes, 7 edges, cycle=True
PASS phases 0–10 present
PASS 9 local links; all 5 pre-existing files unchanged; exactly 3 planning files added; no .git directory
```

The fourth added file is this report, written after that check. Cycle checks used a local topological traversal of the diagram edges; node IDs were also checked against the explanation table. This is a structural check of the diagram text, not validation by a Mermaid renderer. No visual layout/rendering check was performed.

The subsequent integrity pass including this report printed:

```text
PASS final integrity: exactly 4 Markdown files added; all 5 original files unchanged; 14 local links resolve; document structure valid; no .git directory
```

No pytest tests, CLI execution, benchmark, license verification, model evaluation, dependency setup, or public-data checks ran. There are no accuracy, recall, false-positive, calibration, cost, or latency results to report. Documentation checks do not demonstrate application correctness.

## Illustrative input and output, not an executed demo

Proposed input: `  LUMA   VESPER  `.

Proposed normalization: `luma vesper`.

Proposed fictional candidate: entity `syn-001`, name `Luma Vesper`, alias evidence from `fictional-synthetic-v1`, a named raw similarity score, and the message “Possible record match for research review; not identity confirmation.” No numerical score is reported because the matcher does not exist yet. An unrelated name may still receive low-scoring candidates in Phase 1; it will not receive an automatic clearance verdict.

## Design decisions and limitations

- The project assists record review. It does not identify people or establish criminality. Initial tests and demos use invented records.
- The initial request path is small Python functions. Neural models, calibration, LangGraph, memory, audit persistence, and interfaces are deferred to approved phases.
- The request DAG is forward-only. The separate learning feedback cycle uses completed reviews to propose a new frozen model/policy for future requests; it never retrains during a live request.
- Public-data terms, package versions, APIs, model weights/licenses, cloud access, pricing, and claims from the reference have not been verified. No source or model has been approved for acquisition.
- Phase 1's proposed 12 entities test software behavior, not generalization. Same-script normalization and authored aliases do not establish cross-script matching ability.
- Duplicate sources and uncertain aliases require review. Evaluation keeps related groups together and separates reference-index presence from supervised label use.
- Calibration can be infeasible with too few independent examples. The plan permits retaining raw ranking and human review instead of inventing confidence.
- Hash chaining is limited tamper evidence relative to a trusted digest, not immutability. Memory can preserve mistakes unless correction, provenance, and isolation are tested.
- No implementation bugs can yet be diagnosed. Current limitations are planning assumptions, unverified external details, and lack of executed application tests.

## Detailed 5W1H recap

**What are we building?** A research-only multilingual name-to-record matching prototype. It searches reference aliases, returns possible candidate entities and supporting evidence, and eventually supports persistent human review. A candidate is a suggestion, not an identity conclusion. Phase 0 delivered the plan only.

**Why build it this way?** Names vary in spelling and writing systems. Exact matching misses alternatives; broad matching can overwhelm a reviewer. A simple baseline and a carefully reviewed evaluation harness let us distinguish genuine improvement from data leakage or fragile examples. Small phases make each function explainable to the learner.

**Who does what?** The learner approves phases, reviews labels and design choices, inspects changes, and learns to explain them. The coding assistant implements only approved work and reports actual checks. A future human reviewer evaluates candidate evidence and can leave a case unresolved. An optional LLM drafts or parses constrained text; it does not decide identity or direct tools from untrusted records.

**When does each part happen?** Phase 1 creates the synthetic local baseline. Phases 2–3 add permitted data and baseline evaluation. Phase 4 measures pretrained embeddings; Phase 5 optionally trains models. Phase 6 studies calibration and abstention. Phases 7–8 add orchestration, review persistence, memory, explanation, and audit tests. Phases 9–10 add a local interface and reproducible demonstration. Each transition waits for explicit approval; there is no assumed deadline.

**Where do data and work live?** Planning lives in `docs/`; later Python lives in `src/watchlist/`, tests in `tests/`, and evaluation configurations/results in `eval/`. Initial data are fictional and local. Public data require approved terms and provenance. Remote compute, model APIs, Microsoft integrations, hosting, publication, and Git operations remain separate approval decisions.

**How will we know it works?** Phase 1 checks known inputs, exact/typo/ambiguous matches, Unicode handling, grouping, tie-breaking, error handling, and CLI output locally. Later evaluation uses independent entity groups, fixed snapshots, known positive and absent-target queries, retrieval and error metrics, slice counts, and defensible uncertainty. Results are saved with versions and commands. If the evidence does not support a claim, the report says so and the system keeps uncertainty visible.

## Next phase and approval boundary

The next proposed step is only Phase 1: 12 fictional entities, conservative normalization, one RapidFuzz scorer, a JSON CLI, unit tests, README, managed dependencies if approved, and a phase report. Its exact file list and acceptance criteria are in [the implementation plan](../implementation-phases.md).

Request the user's approval or revisions before starting Phase 1. Dependency installation or network use needs explicit scope authorization before execution. Do not start Phase 2 or any later phase automatically.
