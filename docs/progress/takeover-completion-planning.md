# Takeover and complete-project planning review

Date: 2026-10-23. Status: **planning and review only; application fixes have not started**.

The user asked to take over `codex://threads/01a15ac7-ed7a-70e2-8a86-183ebd94d216`, understand the work, and provide a complete step-by-step repair and completion plan. The source chat is titled **Plan Polyglot Watchlist Phase 0**. The user then requested five Astra/max subagents, paused work while the workspace limit was changed, restarted, and authorized continuing the review.

The saved [completion plan](../project-completion-plan.md) is the proposed execution sequence. It includes all remaining Project 1 research, engineering, interfaces, integrations and presentation deliverables. Its future commands/files are proposals; they are not claims of implementation.

## Scope and authorization

The most recent source-chat work completed Phase 7A and approved **planning only** for Phase 8. The source user decisions preserve E5-small, keep MiniLM experimental, retain human review, and exclude automatic match/clear decisions. The new request requires full planning, including actual later training/calibration and external integrations; it does not itself authorize executing those phases, network acquisition, migrations, costs, credentials, Git initialization or publication.

The original reference is a proposal, with current licenses, SDK APIs, free tiers and performance claims requiring verification at their respective approved preflights. Project 2 remains excluded. The Microsoft custom-engine wrapper described specifically for Project 2 is also excluded; Project 1's Copilot Studio/declarative-agent work is included.

## Five specialist reviews

The session reported six available agent slots after restart. Five specialists were assigned explicitly to `gpt-6-astra` with reasoning effort `max`:

| Worker | Ownership | Work actually performed |
|---|---|---|
| `reliability_review` | Validation, database identity/content, read-only access, compatibility and recovery | Source/test inspection, isolated fictional reproductions, fresh 85-test focused run |
| `data_evaluation_review` | Source/corpus/grouping/splits, query contracts, metrics and benchmark coverage | Source/results inspection, read-only aggregate inventories and fictional in-memory evaluation probes |
| `training_calibration_review` | Training, negative mining, model comparison, calibration, thresholds and final confirmation | Read-only review of code/configs/results/plans; no training or test rerun |
| `workflow_memory_review` | Shared service, exact-ID memory, lifecycle, feedback, security and LLM grounding | Read-only architecture/code/plan review; no test run or database mutation |
| `interfaces_release_review` | API/UI/MCP, tracing/CI, packaging, hosted demo, Azure/M365 and final release | Read-only implementation/reference review; no deployment, network or test run |

An interrupted review was resumed. The interfaces worker later encountered a transient account concurrency error, then completed after other reviews finished. Workspace concurrency and account/provider concurrency are separate constraints; the file change does not promise unrestricted simultaneous provider capacity. All five specialist reports were received and incorporated.

The coordinator reconciled their recommendations into one service architecture and one completion ledger. Workers did not edit project application code or existing stores. Short final consistency reviews of the consolidated document were requested from the reliability, training/calibration and interfaces specialists; their final corrections are incorporated before delivery.

## What was learned

The implemented path is normalization → E5 retrieval → immutable evidence → explicit human pause → validated review → deterministic explanation → audit. Separate SQLite stores hold case/audit records and LangGraph checkpoints. There is no generative LLM, fitted calibrator, trained model, cross-case memory implementation, API, UI or external integration.

The local public snapshot has 20 legal-entity groups and 79 names, with only three Arabic names. Its 7/3/2/2/6 group allocation is inadequate for the intended training/calibration claims. Already inspected benchmarks remain regression diagnostics. The saved MiniLM reranking experiment regressed on the primary small tests, so it remains experimental; that does not remove actual task-specific training from the completion plan.

Five reliability defects reproduced:

1. Inspection and malformed command paths create/chmod stores.
2. Non-object JSON can escape as an uncaught `TypeError`.
3. Reimport/loader behavior does not verify stored logical content against frozen source provenance.
4. Initializers overlay unrelated SQLite databases.
5. Lost checkpoint storage can be mistaken for unstarted progress, causing retrieval replay.

A sixth observation is intentional: source-byte changes alter the workflow fingerprint. The repair sequence preserves v1 and adds independent archival verification before changing hashed code; execution checks are not removed.

Two evaluation helper gaps also reproduced: incomplete query/absent-row validation, and Recall@50 eligibility based on returned count rather than index size. These are not proof that historical saved measurements are wrong. Existing frozen regeneration/hash checks and full-ranking callers provide additional protections.

The first operational work should therefore be preservation and archive compatibility, followed by validation/opening, database integrity, recovery and evaluation repairs. New features then build on those verified contracts.

## Files created in this planning pass

| File | Explanation |
|---|---|
| `docs/project-completion-plan.md` | A 33-step sequence (00–32), verified status, prioritized defect register, five-worker responsibility split, dependency DAG, exact proposed file families, commands, tests, risks, acceptance criteria, full reference-to-evidence ledger, claim rules, teaching glossary, fictional walkthrough and first approval package |
| `docs/progress/takeover-completion-planning.md` | This review record: scope, actual work, evidence, actual test results, validation and the implementation stop boundary |

No application function was created or edited, so there is no new application code to explain line by line. Existing phase reports remain history. The workspace `.codex/config.toml` change belongs to the preceding explicitly authorized configuration task, not this application-planning pass.

## Commands and checks actually performed

Read-only work used `rg`, `cat`, `sed`, `nl -ba`, Python standard-library file/hash/JSON/HTML inspection, and Codex chat-reading tools. The coordinator read `AGENTS.md`, Project 1 and its M365/engineering/presentation/AI guidance, current phase/design/ADR material, README/dependency/configuration files and workflow/normalization source. Specialists inspected their assigned implementation, tests, plans and saved result JSON. The latest source-chat approvals and final reports were inspected directly.

The coordinator recorded an initial SHA-256 inventory for **149 pre-existing files** under `src`, `tests`, `docs`, `config`, `eval`, `data`, and the selected root instruction/README/dependency/configuration files. Model-weight directories, embedding caches, bytecode, virtual environments and test caches were excluded. Existing datasets, review databases and result files were included. The temporary manifest is:

```text
/var/folders/8w/7kfcg3b950b35c5wq83bfld80000gp/T/polyglot-completion-planning-rn4w81_q/before.json
```

The reliability worker used `TemporaryDirectory`, existing fictional fixtures and a fake retriever for its probes. It altered only newly created temporary databases and a temporary copy of relevant source to reproduce the hash behavior. Selected actual probe outputs:

```json
{
  "missing_workspace_status": {
    "exit": 0,
    "files": ["cases.sqlite", "checkpoints.sqlite", "writer.lock"]
  },
  "tampered_reimport": {
    "created": false,
    "same_snapshot": true,
    "loaded_display": "Fictional altered entity",
    "altered_alias_loaded": true
  },
  "import_unrelated99": {"created": true, "user_version": 2},
  "ledger_unrelated0": {"user_version": 1},
  "missing_checkpoint_pending": {
    "status_review_status": "not_requested",
    "checkpoint_id": null,
    "retrieval_calls": 1
  },
  "missing_checkpoint_complete": {
    "status_review_status": "not_requested",
    "recover_error": "final event differs from checkpoint evidence",
    "retrieval_calls": 1
  }
}
```

The fresh focused test command executed by that worker was:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B - <<'PY'
from tempfile import TemporaryDirectory
from pathlib import Path
import pytest

with TemporaryDirectory(prefix="polyglot-reliability-tests-") as temp:
    raise SystemExit(pytest.main([
        "-q", "-p", "no:cacheprovider",
        "--basetemp", str(Path(temp) / "pytest"),
        "tests/test_agent_cli.py",
        "tests/test_agent_state.py",
        "tests/test_agent.py",
        "tests/test_review_resume.py",
        "tests/test_review_audit.py",
        "tests/test_database.py",
        "tests/test_ingest.py",
    ]))
PY
```

Actual result: **85 passed, 13 warnings, 10.75 seconds**. The warnings concern LangSmith's deprecated `asyncio.iscoroutinefunction` use for a future Python version. They were recorded, not “fixed” through an unapproved dependency upgrade. An earlier interrupted test invocation had no collected final result and is not counted. No integration/model tests were run in this pass. The earlier **213-test** result is historical and is not a new run or an additional 213 tests.

The data worker's fictional in-memory probes demonstrated that malformed query ancestry and absent-row contracts passed the existing audit helper, and that a 50-result shortlist from a 1,000-entity index produced Recall@50 N/A. Aggregate source inventories were read-only. No raw source names are republished in this report.

Documentation validation checks cover all 33 numbered steps, required per-step goal/files/commands/acceptance content, local Markdown links, balanced fences, defined Mermaid nodes and acyclic graphs, plus the protected-file inventory. These checks do not render the Mermaid diagrams or prove future application behavior.

Actual final documentation check: **33 numbered steps, 13 valid local links, two structurally acyclic Mermaid diagrams, zero reported issues**. All **149 inventoried pre-existing files remained byte-identical**. Exactly the two intended planning documents were added in the inventoried scope. No application/configuration/test/data file was changed by this planning pass.

Final specialist consistency checks corrected: original SQLite sidecar preservation and external simulation attribution; pending-archive decoding and the legitimate early-crash exception; calibration finalization after hybrid/feedback/parser changes; training-only feedback endpoints and protection of final query outputs as well as labels; domain-specific calibration; durable Azure/Postgres requirements; public-session isolation; exact artifact hashes versus numerical tolerances; and final clean rebuild after integration additions.

## 5W1H recap

- **What:** reviewed the existing project and designed a complete repair/research/delivery plan.
- **Why:** correctness and evaluation gaps must be fixed before additional features or performance claims; every reference deliverable needs concrete closure evidence.
- **Who:** five requested Astra/max specialists plus the coordinator; the learner remains the approver and accountable experiment/review owner.
- **When:** after implemented Phase 7A and Phase 8 planning, before new application work.
- **Where:** the local workspace and temporary fictional test directories; source-chat history was read through Codex tools.
- **How:** compare the proposal, approvals, implementation and saved results; reproduce important gaps; define ordered small phases with dependencies, tests and measurable acceptance.

## Outstanding work and stop

No defect is claimed fixed. No new dataset, model, calibration, memory, API, UI, hosted demo or Microsoft integration is claimed implemented. Current licenses/entitlements were not reverified online. Human label review, reviewer participation, adequate independent confirmation data, compute and external account/tenant access remain real implementation prerequisites with explicit steps in the plan.

The next proposed phase is Step 00 preservation/backup verification. Local Git initialization is included only if explicitly approved. The archive reader follows as Step 01 before source changes that invalidate old execution hashes. [AGENTS.md](../../AGENTS.md) requires explicit phase approval before implementation; the user is being asked to approve a concrete, documented first scope, not an unspecified whole-project rewrite.
