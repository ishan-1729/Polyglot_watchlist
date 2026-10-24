# Phase 8 planning record — case memory and reviewer feedback

Date: 2026-10-22. **Planning complete; implementation not approved.** Full specification: [Phase 8 plan](../phase-08-plan.md).

## Scope and 5W1H

- **What:** designed an exact-identifier case-history index and an opt-in memory-aware review workflow, with persistent SQLite, explicit historical context, feedback boundaries and evaluation.
- **Why:** let a reviewer find earlier work without turning a past annotation or similar name into a purported identity fact.
- **Who:** the learner approves implementation and supplies review judgments; the software would retrieve reference evidence and preserve history. The assistant performed local inspection and documentation only.
- **When:** after implemented Phase 7A, before any Phase 8 application work. Training, calibration and later interfaces remain deferred.
- **Where:** local source/docs/tests and saved demo artifacts. No network, package installation, migration, model execution or external service was used.
- **How:** inspect actual workflow/version rules, design schema and lifecycle controls, propose chronological fictional evaluation, document commands/tests/acceptance, then stop for approval.

## Files created

| File | What and why |
|---|---|
| `docs/phase-08-plan.md` | Detailed teaching/design plan: short- versus long-term memory, safe facts and non-inferences, scoped identifiers, SQLite tables, DAG, source-copy/import strategy, versioned CLI compatibility, stale review controls, privacy/retention, future feedback curation, evaluation, files/commands/tests/resources and two-day example. |
| `docs/progress/phase-08-planning.md` | This action record, distinguishing the proposed implementation from checks actually performed. |

No pre-existing document or application file is intentionally edited. New tables, modules, configuration, fixtures and result paths named in the plan are proposals only; no application scaffolding is created.

## Important findings behind the plan

1. Phase 7A already persists cases but has no cross-case record index. Its packet digest does not cover a memory context.
2. Its workflow fingerprint includes every Python/SQL file inside `src/watchlist/agent/`. Adding a memory module there would break old-case version checks. Therefore propose a separate `watchlist.case_memory` package/CLI and new workspace; leave v1 code and stores intact.
3. The v1 service constructor performs schema initialization and permission writes. It must not be used on original stores as a purported read-only importer. Propose coherent SQLite backups under the old writer lock, with verification on copies only.
4. Source entity/alias IDs are record identifiers, not verified global identities. Use a registered namespace plus ID, and require the same snapshot for default lookup. Same-name `syn-001` and `syn-012` remain distinct.
5. The saved Phase 7A case is explicitly a simulated assistant annotation. It cannot be treated as a human-labeled positive training pair. Legacy origin is unknown unless explicitly classified in an import manifest.
6. Memory can retrieve an exact prior record yet still be unhelpful for a new query. Evaluate correct linking separately from task usefulness, workload and anchoring.

## Recommended implementation boundary

Fictional-only first pilot, existing pinned dependencies, no downloads. Separate versioned graph using unchanged E5, exact identifier lookups, no reranker or thresholds. Freeze the exact displayed memory context into the new packet. Revalidate relevant history/expiry on resume, use idempotent publication and preserve different annotations. Propose 3 cards per candidate, 90-day visibility expiry (not deletion or a legal rule), and a 24-episode fictional evaluation across 12 entity groups. No training/export feature in this milestone.

Public-derived memory reuse, broader identifier mappings, end-to-end sensitive-data deletion and any training-label curation need their own permission/evidence review. The historical data card was read; its source terms were not reverified online in this turn. No new legal permission is claimed.

## Reads and checks actually performed

- Read `AGENTS.md`; original Project 1 including its agent/memory, evaluation and build order, plus engineering standards and AI coding-agent guidance.
- Read current architecture/evaluation/implementation documents and relevant Phase 7A report sections, including file/function explanations, actual test ledger, demonstration and limitations; read the data card for the recorded source scope and attribution constraints.
- Inspected all Phase 7A graph/state/node/retrieval/CLI/storage/audit code and the application schema; read state, mocked workflow, subprocess recovery, audit, CLI and local-E5 integration tests.
- Inspected saved demonstration JSON without invoking the CLI/service or opening SQLite. Confirmed the stored note explicitly identifies a simulated fictional annotation and preserved its classification in the proposal.
- Read installed package metadata: LangGraph 1.2.16, checkpoint 4.3.0, SQLite saver 3.1.2, pytest 9.1.1. No dependency change or current-version internet lookup.
- Before documentation creation, recorded SHA-256 for **146 pre-existing files** under source, tests, docs, evaluation, configuration and data, plus root project instructions/dependency/README/ignore files. Excluded bytecode, model-weight directories and embedding cache. Included existing review databases, source datasets and result artifacts. Inventory stored temporarily at `/tmp/phase08-before.json`.
- Tools used: local `cat`, `sed`, `rg --files`, `rg -n` and Python standard-library file/JSON/hash/metadata reads; shell heredocs wrote only the two Markdown planning documents. No pytest, graph invocation, benchmark, SQL/migration, model load, Git operation or package installer ran.

Final checks: both new Markdown files have balanced code fences and valid existing local Markdown-link targets. The Mermaid request graph was checked for defined nodes and absence of cycles; it was not visually rendered. Names of proposed future files are code-formatted text, not links claiming those files already exist.

The post-edit scope check confirms all **146 inventoried pre-existing files are byte-identical**, with exactly the two intended new planning documents and no new application/configuration/test/data artifacts in the inventoried scope. This is a documentation-scope check, not proof of the proposed runtime behavior. The Phase 7A 213-test count is historical and is not presented as a new test run.

## Remaining uncertainties and stop

The separate CLI maintenance tradeoff, panel cap and expiry default require user acceptance. Actual workload benefit/anchoring risk is unmeasured. Reviewer authentication, independent label adjudication, source-ID continuity, public-note permission/retention and complete deletion across backups/checkpoints remain unresolved beyond the fictional pilot. The migration/outbox/context-validation design requires implementation and failure tests before making reliability claims.

**Stop: request explicit approval of the bounded Phase 8 implementation plan or revisions. No Phase 8 implementation, training, automatic thresholds or later phase has started.**
