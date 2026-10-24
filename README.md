# Polyglot Watchlist — research name matching

This is the Completion Step 06 publication snapshot. See [publication scope and historical evidence](docs/publication.md) for the included fictional inputs, preserved reports and intentionally unavailable local evidence links.

A local multilingual candidate-retrieval prototype with a resumable human-review workflow. It suggests possible reference-record matches; it does not establish identity, wrongdoing, current sanctions status, or clearance. It is not a live screening/compliance service and is not affiliated with INTERPOL.

The default demonstration uses invented names. All existing fictional, public-subset, and bilingual evaluation examples have been inspected and are **regression-only evidence**. A regression check asks whether software changes preserve expected behavior on known examples; it does not measure performance on unseen data.

## Current state

Completion Steps 00–05 delivered the preservation and repair work below. The [Step 06 report](docs/progress/completion-06.md) records the engineering checks, approval scope and final acceptance status. Completion Steps are distinct from the historical Phase 0–10 records. See the [current phase guide](docs/implementation-phases.md), [completion plan](docs/project-completion-plan.md), and [evaluation repair report](docs/progress/completion-05.md).

| Capability | Implemented behavior |
| --- | --- |
| Fictional baseline | Packaged records, Unicode normalization, deterministic RapidFuzz alias ranking, JSON CLI. |
| Source evidence | Verified v3 SQLite snapshots, schema/content checks, explicit rebuild of historical v2 sources into new destinations. |
| Multilingual retrieval | Pinned local E5-small, exact NumPy search, alias caches. |
| Reranking experiment | Pinned pretrained MiniLM scores frozen E5 shortlists; disabled in the review workflow. |
| Human review | LangGraph pause/resume, explicit annotations, saved evidence, deterministic explanations, audit links, checked crash recovery. |
| Evaluation | Bound query/source/view ancestry, separate partition/presence/ambiguity labels, script sets, explicit shortlist metrics. |
| Historical inspection | A separate archive reader verifies preserved cases without executing an incompatible workflow. |

There is no project fine-tuning, fitted calibration, automatic match/clear policy, frontier-LLM comparison, long-term reviewer memory, API/UI, or deployed HF/Azure/Microsoft 365 integration. These remain work in the completion plan; Project 2 is excluded. Missing external access is tracked in the [access/resource ledger](docs/access-and-resource-ledger.md).

## Run the existing environment

From the project directory:

```sh
export UV_CACHE_DIR="$PWD/.tools/uv-cache"

env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist --name '  LUMA   VESPER  ' --top-k 3

WATCHLIST_WHEELHOUSE=data/eval-comparisons/completion-06/wheelhouse \
  make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv test
```

The CLI uses the packaged fictional fixture and needs neither model weights nor an API key. Tests use fictional records, deterministic vectors, and temporary stores. The full test target includes packaging checks, which require a compatible locally cached RapidFuzz wheel. The shown wheelhouse contains the separately approved CPython 3.14/macOS ARM64 wheel; another host needs its own approved compatible cache. Optional tests can skip when their packages are absent; a partial environment is not evidence that the full project passed. Already-local model checks are separate opt-in tests, not downloads.

**Python 3.14 is the declared target (`>=3.14,<3.15`); local CPython 3.14.0 on macOS ARM64 is the demonstrated runtime.** Python 3.11–3.13 are outside the narrowed declaration. Hosted CI uses Python 3.14.0 on Ubuntu 24.04; see the [actual run history and conclusions](https://github.com/raiha-siddiqui/Polyglot_watchlist/actions/workflows/ci.yml). Windows is not a tested target; review storage uses POSIX file locks.

The inspected local `uv` 0.13.5 executable has been copied with a checksum receipt to `.tools/bin/uv`; no temporary installer path is required. The reviewed local metadata/tool cache is `.tools/uv-cache`. Set `UV_CACHE_DIR` to its absolute path so checks that change directory still use the same cache. Other hosts need compatible, approved tools and cached artifacts. The project requires that uv version, and Makefile commands accept a `UV` executable override. The existing `.venv` can run directly while its interpreter and packages remain available. A lockfile records exact package versions/artifact hashes; it does not prove every platform or optional combination works.

After obtaining any required installation/network approval, choose a nonexistent environment directory and request a fresh environment from the reviewed lock. The example uses `.venv-new` to preserve the baseline `.venv`:

```sh
export UV_CACHE_DIR="$PWD/.tools/uv-cache"

env UV_PROJECT_ENVIRONMENT=.venv-new UV_PYTHON_DOWNLOADS=never \
  .tools/bin/uv sync --locked --offline --dev --extra embeddings --extra agent --python python3.14

env UV_PROJECT_ENVIRONMENT=.tools/qa-new UV_PYTHON_DOWNLOADS=never \
  .tools/bin/uv sync --locked --offline --only-group qa --no-install-project --python python3.14
```

These commands succeed only if the interpreter and all selected packages are already available locally. Select the new environment paths through `PYTHON` and `QA_PYTHON` when using them. Stop on an offline cache miss; acquiring tools, dependencies, or weights needs a separate bounded approval. Do not regenerate the lock merely to make a demonstration run. A passing lock check establishes consistency with declared requirements; it does not prove a fresh installation of every optional extra.

## Local engineering checks

The Makefile selects installed tools explicitly and sets offline flags. It does not acquire missing dependencies. The application uses `.venv`; quality tools use the separate `.tools/qa` environment. Start with:

```sh
export UV_CACHE_DIR="$PWD/.tools/uv-cache"

make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv help
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv lock-check
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv lint
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv secret-scan
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv eval-smoke
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv inventory

WATCHLIST_WHEELHOUSE=data/eval-comparisons/completion-06/wheelhouse \
  make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv package-smoke
```

`eval-smoke` has passed with 157 deterministic current-contract fictional queries, excluding timing from its comparison. `inventory` separates installed packages, lock entries and unreviewed license metadata; see the [inventory evidence and limits](docs/access-and-resource-ledger.md). The project's own release-license decision remains with its owner. An inventory is not a legal clearance.

The packaging checks build a wheel/source archive, rebuild the wheel from the archive, install the core package into an empty environment, verify packaged resources and native RapidFuzz, and run the fictional CLI outside the repository. They also exercise the separate locked QA setup. The core check installs only this project and RapidFuzz; it does not reproduce every optional model/agent dependency on every platform. Receipts under `data/eval-comparisons/completion-06/` bind each checked build to its input/artifact hashes; the Step 06 report records actual outcomes.

`build` requires a new `DIST_DIR`; existing output is refused. `test-local-models` is an explicit opt-in for the three already-local model checks. Quality tooling uses Ruff 0.14.10, pre-commit 4.5.1 and detect-secrets 1.5.0 in `.tools/qa`; `QA_PYTHON` can select another approved environment. The three pre-commit hooks invoke the same lock/lint/scan targets without installing dependencies or rewriting files. Scanner reports distinguish reviewed non-secret fingerprints/fixtures from unreviewed findings. A missing tool, a failed scanner, or wrapper tests alone cannot establish a successful source scan.

CI runs on pull-request/manual events with reviewed full action commit pins, read-only repository permissions and no persisted checkout credentials. Its approved bootstrap acquires locked dependencies and a size/hash-verified RapidFuzz wheel before a separate Linux network-isolated check stage. Runtime assertions verify the isolated network namespace, dropped privileges/capabilities and no-new-privileges. The scanner stays sequential under its socket guard; clean-install checks require a genuine native RapidFuzz extension, including supported CPU-specific backends. [GitHub Actions](https://github.com/raiha-siddiqui/Polyglot_watchlist/actions/workflows/ci.yml) records the exact commits and actual outcomes. Dispatch alone is not a passing result.

## How retrieval works

An **entity** is a reference record; an **alias** is one of its spellings. Different records may have the same name. The input is checked for nonblank text and the 200-code-point limit, normalized with NFKC/case folding/whitespace collapse, and compared with the selected aliases. Original text remains available as evidence. Normalization does not translate, transliterate, or strip accents.

RapidFuzz uses normalized Levenshtein character-edit similarity. E5 embeds queries and aliases into vectors and uses cosine similarity. Each returns one candidate per entity through its best retained alias, with stable ID-based ties. Neither score is an identity probability; unrelated input can receive suggestions because no rejection threshold exists.

The fictional exact-name example deliberately returns both `syn-001` and `syn-012` for `Luma Vesper` at 100 similarity. It demonstrates shared-name ambiguity. Historical measured comparisons remain in [Phase 4](docs/progress/phase-04.md) and [Phase 5A](docs/progress/phase-05a.md); they are not fresh generalization results.

## Source snapshots and compatibility

New source-backed work uses explicitly rebuilt v3 snapshots, when present locally:

```sh
.venv/bin/python -B -m watchlist \
  --db data/source-v3/sample.sqlite --name 'Moonberry Loom' --top-k 3
```

The original `data/sample.sqlite` and `data/watchlist.sqlite` are preserved historical v2 files. Normal loading rejects them with migration guidance; it never silently substitutes another database. See the [source migration guide](docs/maintenance/source-database-migration.md).

The public snapshot is a historical, narrow OpenSanctions UN selection. Provider terms were recorded at acquisition; Step 06 performs no new online license verification. The [data card](docs/data-card.md) distinguishes saved provenance from current permission. Public availability is not unrestricted-use permission or identity ground truth.

## Evaluate without overwriting history

All existing datasets remain exposed and regression-only, including their v2 representations. Current comparisons validate every query before cache/model work, send only retained aliases to retrieval, and require a new output root. With the already-approved local E5 files and optional dependencies available:

```sh
env PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -B -m watchlist.compare_retrieval \
  --config eval/configs/embeddings.json --dataset multilingual \
  --output-root data/eval-comparisons/manual-multilingual-01
```

Choose a fresh destination each time; existing result/cache directories and historical result trees are refused. New caches live inside the output root. For the public subset, choose `--dataset public-small` and explicitly pass `--database data/source-v3/watchlist.sqlite`, with a different new root. Missing source/model files cause an error, not a download.

`--requested-k 5` evaluates a shortlist. Reports separate index population, requested K, returned count, and evaluated depth. Recall eligibility uses the index and depth. A missing target contributes zero to MRR@K without an invented later rank; full MRR is unavailable for truncated rankings. Threshold false-positive rate remains unavailable because there is no decision threshold.

`--regression-only` selects the exact **legacy row contract**. Omitting it selects the current contract; it does not make an exposed dataset fresh. Saved Phase 3/4/5 outputs and configs remain historical. In particular, do not run the old reranking evaluator as a default command: its historical output destinations are not isolated by the new comparison CLI. Use recorded replay evidence or a separately reviewed isolated harness.

## Local human review and recovery

Every successful retrieval, including an empty candidate list, pauses for human review. A **checkpoint** saves workflow progress; the **case ledger** saves requests, candidate evidence, annotations, and audit events. Both stores must describe the same permitted workflow state before execution resumes.

For a new fictional demonstration, prepare a separate agent JSON config from `config/agent.json`, preserving its policy fields and pointing `workspace` at a **new disposable directory**. Keep original configs/stores unchanged. Use a separate embedding config/cache when isolating model work. Replace these placeholders with the prepared config and returned UUID:

```sh
.venv/bin/python -B -m watchlist.agent start \
  --config /ABSOLUTE/PATH/TO/demo-agent.json --name 'Lumen Sira'
.venv/bin/python -B -m watchlist.agent status \
  --config /ABSOLUTE/PATH/TO/demo-agent.json --thread-id SAVED_THREAD_UUID
```

Copy the returned form, supply a new submission UUID, choose `candidate_for_follow_up`, `none_selected`, or `unresolved`, and enter your own reason. Follow-up requires a displayed candidate ID; other outcomes require JSON `null`. Preserve the exact packet digest, revision, and checkpoint ID. Submit with `review --review-file /ABSOLUTE/PATH/TO/review.json`, using the same config/thread ID. These are human annotations, not identity findings.

Duplicate/stale reviews fail. After an interrupted accepted submission use `recover`, not a replacement review. Status/audit inspection does not initialize missing storage. Recovery reuses surviving evidence; a genuine pre-retrieval request can still require its original local model. Never regenerate a missing companion, delete WAL files, or rewrite fingerprints to bypass an error. See the [recovery matrix](docs/maintenance/recovery-state-matrix.md).

For historical evidence use the separate archive interface:

```sh
.venv/bin/python -B -m watchlist.review archive verify --archive data/review-archives/v1
.venv/bin/python -B -m watchlist.review archive inspect \
  --archive data/review-archives/v1 --case-id SAVED_CASE_UUID
```

Archive verification never grants permission to execute the old workflow. Local actor labels and hash links are not authenticated identities or protection against replacement of all local records. Keep review notes and source/model artifacts private and outside release packages.

## Evidence and further reading

- [Completion Step 05: actual tests, model checks, historical replay and limits](docs/progress/completion-05.md)
- [Data card](docs/data-card.md) and [model card](docs/model-card.md)
- [Phase guide and approval gates](docs/implementation-phases.md)
- [Access, costs, terms and dependency inventory](docs/access-and-resource-ledger.md)
- [Architecture decisions](docs/adr/) and [backup/restore guidance](docs/maintenance/baseline-and-backup.md)

Training, calibration, new sources, hosted services, and Microsoft 365 delivery need their own approved scope and evidence. Passing local fixtures cannot establish operational screening accuracy or a legal/compliance guarantee.
