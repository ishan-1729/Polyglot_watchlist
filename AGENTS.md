# Polyglot Watchlist — Codex Collaboration Rules

## Source of truth
Read `docs/reference/internship-2093-portfolio-plan.html`: Project 1 (Polyglot Watchlist Agent), Project 2 (Follow the Money), the Microsoft 365 layer that connects them, and its engineering standards and AI coding-agent guidance. Both projects are in scope. An earlier version of this file excluded Project 2 by mistake; that exclusion no longer applies, and older documents that repeat it are historical. Treat the reference as a project proposal, not as proof that tools, datasets, deadlines, model claims, or licenses are current.

## Objective
- **Project 1 — Polyglot Watchlist:** a research-only multilingual entity/name matching prototype using approved public sanctions data (start with fictional synthetic data). It assists human review; it does not establish criminality or identity and is not a live screening/compliance service.
- **Project 2 — Follow the Money:** a research-only investigation agent that traces ransomware and scam payments across public blockchains (Bitcoin UTXO and USDT TRC-20 on TRON), plans under an API/hop budget, ranks addresses with a learned priority model, applies tracing heuristics, has a red-team critic challenge every claim, pauses for human approval before anything that would act, cites a transaction ID for every claim, and keeps long-term case memory that notices when a new case touches clusters from an old one. It calls Project 1 to resolve sanctioned-wallet owner names. It produces leads for human investigators, not findings of guilt or ownership.

## Project 2 layout and rules
- Code lives in its own package `src/follow_the_money/` in this repository, with tests under `tests/follow_the_money/`, configs under `config/follow_the_money/`, docs under `docs/follow_the_money/`, and progress reports `docs/progress/follow-the-money-NN.md` (the name avoids confusion with the unrelated FollowTheMoney data format used by `ingest/parse_ftm.py`). It reuses Project 1's v2 review, audit and memory patterns where sensible and calls Project 1 only through its public API/MCP or Python service interface.
- Architecture follows the reference: seed address → planner (goal, budget, stop conditions) → LangGraph loop (pick next address by priority model → call tools → reflect: continue, backtrack or stop) → red-team critic → human approval `interrupt()` → case report → case memory.
- Tools: Bitcoin Esplora/mempool.space (`get_tx`, `get_address_txs`, `get_outspends`), TronGrid/TronScan TRC-20 transfers, common-input clustering with a size cap, change/peel-chain/CoinJoin detection, label lookup (GraphSense TagPacks, OFAC crypto addresses, OpenSanctions wallets), `score_address` with an out-of-distribution flag, `query_case_memory`, and `resolve_entity_name` via Project 1.
- ML: GraphSAGE/GAT on Elliptic++ with a temporal split, compared against XGBoost on the same features; retrain on live-recomputable features and report the drop; OOD fallback to heuristics; change-output classifier; evaluation against public gold traces (e.g. DOJ seizure filings) with calls-to-endpoint versus breadth-first search.
- Every network client must work offline against recorded fixtures (cache everything, respect rate limits, no hidden live calls in tests or CI). Live API use, API keys (e.g. TronGrid) and large dataset downloads (Elliptic++, Elliptic2) need explicit approval and are recorded with source, licence, size and hash.
- Public, on-chain and openly licensed data only. Do not deanonymise or profile private individuals, do not attribute addresses to named people beyond published labels, and never send anything to an exchange or authority: drafted requests stay drafts that a human must approve. The critic and the human decide what may be shown; withdrawn claims are counted, not hidden.
- Do not use INTERPOL's name or branding in the product itself; mentioning its public tools and operations in the README as domain context is fine.

## Teaching and working style
- Act as a patient senior engineer and ML mentor to a learner. Explain terminology in simple English and use 5W1H (what, why, when, where, who, how) whenever introducing unfamiliar ideas.
- BEFORE every phase: state its goal, why it matters, exact files to create/edit, dependencies, expected commands, tests, risks, and acceptance criteria. Wait for the user's explicit approval before implementing.
- DURING an approved phase: explain meaningful actions in concise messages before running them; say which file/command and why. Do not claim actions or test results you have not completed.
- AFTER every phase: report what changed, file-by-file explanations, line/function explanations for new code, commands actually run, actual test results, example input/output, bugs/limitations, 5W1H recap, and what the next phase will contain. Save a report in `docs/progress/phase-NN.md` and STOP until user approves the next phase.
- Use small, independently testable changes. Do not start later phases automatically; no sweeping scaffolding, refactors or added libraries without rationale and permission.
- Ask before downloading large datasets/models, incurring costs, using API keys, network access, modifying unrelated files, pushing to GitHub, or exposing any service publicly.
- Never hardcode secrets. Favor local deterministic tests. Show uncertainties; do not fabricate results or scores.

## Phase order
Project 1 follows the list below and the completion sequence in `docs/project-completion-plan.md`. Project 2 follows its own plan in `docs/follow_the_money/plan.md` (data and tools → tracing heuristics → priority model → agent loop, critic and approval → case memory → evaluation → API/MCP/UI → Microsoft 365 integration), with the same phase-report discipline.

0. Read reference; propose one-page design, precise scope, DAG, evaluation plan, phased tasks and acceptance criteria. No application code until approved.
1. Minimal synthetic entities and aliases; Python normalization; simple RapidFuzz baseline; unit tests and sample CLI.
2. Ingest a licensed/permitted subset of public data; SQLite schema with source provenance; entity-level split and deduplication.
3. Baseline evaluations before training: Recall@10/@50, relevant false-positive measures, stratified perturbations and leakage checks.
4. Off-the-shelf multilingual embedding retrieval; compare with RapidFuzz.
5. Optional fine-tuning of bi-encoder and cross-encoder after data/eval review.
6. Calibration and abstention thresholds with independent calibration data and conservative reporting.
7. LangGraph StateGraph orchestration, conditional branches, checkpointing and human review.
8. Long-term reviewer-decision memory, evidence-based explanations, audit log and security tests.
9. FastAPI and Streamlit UI; optional MCP interface and Microsoft 365 integration only if separately approved.
10. Reproducible evaluation, error analysis, documentation and demo.

## Evaluation and safety
- No entity leakage between training, calibration and test; note duplicates across sources.
- Do not interpret model similarity score as probability until properly calibrated; don't invent operational guarantees.
- Use synthetic/fictitious names for demos and initial tests; avoid private personal data or scraping individuals.
- Restrict use of OpenSanctions and other data to terms allowed by their current licenses; verify before use.
- Present outputs as possible record matches for research/analyst review, not findings of wrongdoing.
- Keep LLM untrusted data from controlling final decisions; ensure prompt-injection tests and provenance for evidence.

## Coding quality
Use a Python package under `src/watchlist/`, type hints, docstrings for nontrivial functions, pytest, `README.md`, `.gitignore`, pinned or managed dependencies with `uv` if suitable, and meaningful small commits only when approved. Prefer clarity over sophistication.
