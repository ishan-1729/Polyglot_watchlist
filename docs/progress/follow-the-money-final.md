**Project 2 — Follow the Money: final delivery report**

Delivered the local research implementation through phases 00–09. External
access and validation work remains BLOCKED below. Nothing was sent to an
exchange or authority; no push or merge occurred.

Delivered phases:

- **00–02:** plan/DAG, typed Bitcoin and TRC-20 clients, replay/cache/rate limits
  and budget accounting, published-label provenance, Ransomwhere loader, capped
  clustering, change/peel/CoinJoin heuristics and historical freeze signals.
- **03:** temporal GraphSAGE/GAT and XGBoost experiments, full/live-feature
  retraining, OOD fallback, weak-label change classifier and trace-value learning.
- **04–05:** durable LangGraph loop and independent critic, transaction-cited
  claims, withdrawal counts, digest-bound human approval, draft-only reports,
  Project 1 public-service resolution, audited case memory and scoped rules.
- **06:** frozen synthetic tasks, BFS comparisons, consistency/cost/latency,
  critic/memory checks and a cited public DOJ transaction-pair replay.
- **07–08:** authenticated FastAPI, official MCP stdio and streamable HTTP,
  Streamlit reviewer, offline CI configuration, generated Microsoft manifests/
  API plugin, Studio instructions, approval templates and a working local
  Microsoft Agents SDK/Agents Playground integration.
- **09:** hardening, both-project README, data/model cards, reproduction guide,
  distribution checks, source hashes and phase/final reports.

The implementation contains 29 Project 2 Python modules and 15 test modules.
File/function explanations and exact commands/results are in
[phase reports 00–09](follow-the-money-09.md); the
[source receipt](../../config/follow_the_money/source-verification.json) records
47 source/test/script files and their hashes.

Verification completed in the Linux mirror on Python 3.14.9, using one pytest
process at a time:

| Final check | Actual result |
|---|---|
| Complete Project 2 suite | **133 passed**, 114 upstream warnings, 85.91s |
| Targeted Project 1/auth/audit/recovery/packaging/tooling regressions | **358 passed**, 176.01s |
| Total final selections | **491 passed**; entire Project 1 suite was not rerun |
| Ruff / format | Clean; **183 files** already formatted |
| Pinned uv lock | **170 packages** resolved; offline lock check passed |
| Distribution | Wheel/sdist built; **154 packaged files** byte-verified; installed import/CLI help passed outside repository |
| Interfaces | Actual MCP transports, Streamlit review flow and SDK HTTP activity tested |
| Microsoft artifacts | Official declarative v1.9 / plugin v2.4 schema validation passed |

The initial broader regression run failed because the mirror excluded packaged
P1 data and packaging assertions assumed one package. Both were corrected and
the identical selection rerun successfully. Details, earlier failures and
warning types are preserved in Phase 09. Local demonstration servers were
stopped. Hosted CI and Windows execution were not claimed.

Measured results, with provenance:

- **Synthetic temporal graph:** 600 nodes, 360/120/120 temporal split. Test
  average precision, full → live-feature subset: GraphSAGE **0.946293 →
  0.699059**; GAT **0.572325 → 0.562924**; XGBoost **0.930949 → 0.711873**.
  These are constructed feature proxies, not Elliptic or real-wallet accuracy.
- **27 synthetic search runs:** branching endpoint in **3 queries** with either
  priority policy; BFS exhausts **12**. Pass³ across three tasks: BFS **2/3**,
  heuristic **3/3**, learned value **3/3**. Schema-valid tool calls: 100%.
  Critic withdrew **10/10** planted amount errors and retained **12/12** supported
  fixture claims. Memory: TP=1, FP=0, FN=0, TN=3. Value graph-distance MAE
  **0.358491** on 17 held-out rows after 51 training rows from simulated reviews.
  These graph variants share one authored structure.
- **Six public replay runs:** both BFS and priority reach the cited historical
  endpoint in **one query**. Exact funding/spending outpoints and the
  **124016260-satoshi** output were verified against recordings and the
  [2025 DOJ filing](https://www.justice.gov/usao-ma/media/1390101/dl?inline=),
  affidavit page 13, paragraphs 35–38. No real efficiency gain or ownership
  finding is claimed. All public cases remain awaiting approval.
- Evaluation replay used **zero live calls** and $0 external service charges;
  local hardware/electricity cost was not measured. Development recording used
  **seven bounded public Bitcoin GETs total**. Source URLs, terms, dates, sizes
  and hashes are in the [manifest](../../config/follow_the_money/manifest.json).
- Actual **Agents Playground 0.2.29 → SDK 1.9.0 → LangGraph** routing created a
  synthetic case with 12 critic outcomes and no approval. Browser visual
  inspection, Teams publication and tenant/Azure deployment were not performed.

[Training](../../config/follow_the_money/training-results.json),
[search](../../config/follow_the_money/evaluation-results.json),
[public gold](../../config/follow_the_money/public-gold-results.json), and
[verification](../../config/follow_the_money/verification-results.json) receipts
preserve exact values, including measured latency.

Documented deviations: CrewAI excludes Python 3.14, so the critic is a LangGraph
subgraph. PyTorch Geometric installed successfully; no plain-torch substitute
was needed. Real Elliptic training was replaced by explicitly synthetic pipeline
verification. The integrated learned search demo uses the own-trace value model;
GNNs remain offline experiments, and ordinary/public tracing uses heuristics
until a suitable model is validated. No provider-backed LLM ablation ran.
Colonial's redacted affidavit cannot support a txid-level gold trace; a separate
2025 public pair was used. Value training now requires completed simulated
reviews and critic-retained targets; its earlier pending-review experiment is
explicitly superseded.

| BLOCKED item | Owner | Next action |
|---|---|---|
| Git commits, including initial plan commit | Coordinator | Stage/review/commit preserved changes in a writable Git environment; use the requested co-author trailer |
| Real Elliptic++ / Elliptic2 training | Dataset owner + engineer | Verify permitted no-login data and feature mapping; provide an approved subset under 2 GB; Elliptic2 metadata is 25.8 GB |
| OpenSanctions acquisition | Project/data owner | Establish applicable terms and permission before downloading |
| Live TRON verification | Project owner | Supply authorized access/key and approve a bounded recording run |
| Provider LLM evaluation | Project owner + engineer | Configure an approved provider/key and run the recorded ablation; deterministic fallback already works |
| Unredacted Colonial gold / broader real evaluation | Data owner + analyst | Provide permitted complete transaction citations and independent adjudicated tasks |
| Real-world calibration and analyst/value study | Analyst + ML engineer | Collect genuinely reviewed traces and evaluate independent temporal cases |
| M365 tenant/Azure/Teams deployment | Tenant administrator + owner | Provide subscription/tenant, HTTPS hosting, identity/vault configuration and platform validation |
| Windows execution / hosted CI | Coordinator | Run the committed checks on Windows and GitHub; wheel availability alone is not runtime validation |

**Uncommitted handoff:** branch `project-2` remains at
`fb32c9f93fa0f76becd4017eb44cd741d2aaf583`. Git staging exits 128 because the
worktree `index.lock` is on a read-only filesystem. No Project 2 commits were
created. As authorized, all changes remain available: modified `.gitignore`,
`Makefile`, `README.md`, `pyproject.toml`, `uv.lock`, `tests/test_packaging.py`;
new `src/follow_the_money/`, `tests/follow_the_money/`,
`config/follow_the_money/`, `docs/follow_the_money/`, progress reports 00–09 and
this report, `scripts/ftm_record.py`, `scripts/ftm_m365.py`, and
`.github/workflows/follow-the-money.yml`. Raw data/caches remain gitignored.
