# Phase 7A — orchestration and human-review planning record

Date: 2026-10-22. **Planning complete; implementation awaits explicit approval.** The user selected a review-only milestone after Phase 5A. The original roadmap's training and calibration steps remain deferred; this is not a claim that Phase 6 has been completed.

## 5W1H

- **What:** a proposed LangGraph workflow wrapping unchanged E5 retrieval, with a durable human pause, deterministic explanation and bounded local audit.
- **Why:** preserve the exact evidence across a restart and record a human annotation without introducing unsupported automatic identity decisions.
- **Who:** the learner approves scope and reviews candidates; the software coordinates functions and preserves evidence; the assistant performed planning/read-only investigation only.
- **When:** after the measured negative MiniLM pilot; installation, code and execution wait for explicit approval.
- **Where:** local source/docs/results; official LangGraph/PyPI documentation and metadata after the user separately approved those reads.
- **How:** inspect existing contracts and saved results, verify API semantics/direct package versions, design state/transactions/recovery/tests, save a concrete proposal.

## Documentation changed

| File | What / why |
|---|---|
| `docs/phase-07-plan.md` | New full teaching plan: state schema, DAG, nodes, restart behavior, review vocabulary, provenance, SQLite/audit separation, CLI example, tests, exact proposed files/dependencies/commands, resource budgets and approval boundary. |
| `docs/adr/0005-review-workflow.md` | New concise proposed decision and alternatives, explicitly awaiting implementation approval. |
| `docs/progress/phase-07-planning.md` | This action/check record, separating verified documentation facts from untested implementation proposals. |
| `docs/implementation-phases.md` | Appended the user-directed review-only planning milestone and deferred training/calibration status; older phase history retained. |

No application code, tests, package files, model configuration, baseline data or result files are intentionally modified. No application directory is scaffolded and no checkpoint/review database is created.

## Reads and checks actually performed

- Read `AGENTS.md`; original HTML Project 1 plus engineering standards and coding-agent guidance (standard-library HTML text extraction); design, evaluation plan, implementation roadmap, all existing ADRs, data/model cards, Phase 5 training/evaluation plan and Phase 5A completion report.
- Inspected existing CLI, E5 encoder/cache/ranker/config, dependency file and ignore rules to identify adapter and persistence boundaries. Read saved Phase 5A JSON metrics for all three datasets; did not invoke an evaluator or model.
- Recorded a pre-edit SHA-256 inventory of **102 pre-existing project/document/data/result files**, excluding bytecode caches, for scope checking after the documentation edits.
- Local read commands included `cat`, `sed`, `rg --files`, `rg -n`; Python standard-library `pathlib`, `json`, `hashlib`, HTML parsing, `importlib.metadata` and `shutil.which` inspected files/versions. No pytest was run because this is planning-only.
- After explicit user approval for documentation/metadata reads, consulted official LangGraph Graph API, interrupts, persistence/checkpointer guides, and PyPI project/version metadata. Direct HTTPS metadata requests used Python urllib with the system certificate bundle. No package wheels, models or datasets were acquired.
- Verified direct proposed pins: `langgraph==1.2.16`, `langgraph-checkpoint==4.3.0`, `langgraph-checkpoint-sqlite==3.1.2`; all declare MIT and Python >=3.10. The declared checkpoint ranges overlap. This is not a solved lockfile or proof of Python 3.14 native-wheel/runtime compatibility.
- Local environment has Python 3.14 and the prior ML stack. LangGraph/checkpoint packages and pydantic were not installed. `uv` was absent from PATH; `.venv/bin/python -m pip --version` reported no pip module. No bootstrap was performed. PyPI lists uv 0.13.5 as a possible future isolated tool.
- Some guessed API-reference URLs were inaccessible through the browser tool; the working official conceptual pages supplied the verified StateGraph/interrupt/checkpointer behavior. A bounded 5 MB all-release uv JSON read was truncated and failed JSON parsing; the official PyPI release page provided its version/Apple Silicon wheel information instead. This was metadata only.

Verified API facts: same thread ID is needed for resume; interrupts expose serializable payloads; interrupted nodes restart from the beginning; a file-backed saver is needed across process exit; synchronous durability persists steps before continuing. Chosen application safeguards—submission ledger, packet digest, local lock, idempotent audit and two-store reconciliation—are design proposals requiring tests, not measured guarantees.

## Saved-result findings and recommendation

Primary K=5 challenge top-1: fictional 26/27→25/27, public 141/141→139/141, multilingual 25/30→21/30 for E5 versus E5+MiniLM. These were read from existing artifacts. Keep E5 as the proposed agent default, preserve but disable MiniLM in the agent path, defer training, and treat every retrieval as candidate suggestions for a human. The old RapidFuzz CLI remains a baseline.

The complete fictional walkthrough in the plan uses saved E5 ranking evidence for `Lumen Sira`; its review actions are illustrative proposed behavior. No new graph or human decision has been executed.

## Remaining checks and approval boundary

Full transitive dependency/wheel compatibility, actual checkpoint serializer/API behavior, process-restart recovery, crash-window reconciliation, resource overhead and UI usability remain untested. No new performance or test-passing result is claimed. Tests from Phase 5A are historical and are not presented as new runs.

The [full plan](../phase-07-plan.md) requests a bounded CLI-first Phase 7A implementation, including named package/tool setup within a proposed 100 MB payload ceiling. It excludes training, calibration/thresholds, new model/data, reranker activation, cross-case memory, Streamlit, public service and external API calls. **Stop until the user explicitly approves.**

## Final planning checks

All four planning/roadmap Markdown files passed local-link and code-fence checks. The Python snippets in the plan passed standard-library `ast.parse` syntax checks only; they were not imported or executed. The request DAG was reviewed for a forward-only successful path and separate recovery behavior; Mermaid was not visually rendered.

The post-edit SHA-256 scope check found exactly three new planning documents and the expected `docs/implementation-phases.md` edit. The other **101 of 102 pre-existing inventoried files** were byte-identical, including old application/test source, dependencies, SQLite snapshots, model configuration, split manifests, prior reports and result JSON. No pytest, model inference, evaluation, installation, Git initialization or application implementation occurred.
