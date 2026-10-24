# Completion Step 06 — reproducible engineering foundation

Date: 2026-10-24, Asia/Kolkata. **Status: complete within the approved Step 06 scope.** The previously blocked local tooling, runtime/lock and CI-preparation requirements are resolved. Final verification: **1,644 non-integration tests and 13 subtests passed; all 3 local model tests passed separately with zero skips and zero recorded network attempts.** Step 07 has not started.

This is Completion Step 06, not the historical calibration Phase 6. Hosted GitHub CI and its Linux isolation command have **not** been executed. The approved Step 06 acceptance criteria explicitly distinguish prepared CI from a separately approved hosted run; this report does not label preparation as remote success.

## What was incomplete, why, and how it was completed

| Previously open requirement | Why it was incomplete | Completed resolution |
| --- | --- | --- |
| Actual lint, formatting, pre-commit and secret detection | Ruff, pre-commit and detect-secrets were absent; wrapper tests could not prove real engine behavior. General acquisition had been declined. | Installed verified pinned tools into a separate QA environment, added the locked QA group, passed actual lint/format, positive/negative detector tests, and all three real hooks against a copied source snapshot. |
| Truthful Python support and consistent lock | Only Python 3.14 was demonstrated, but metadata declared 3.11–3.14. Offline metadata was insufficient to regenerate the lock. | Narrowed the declaration to `>=3.14,<3.15`, regenerated a coherent 113-entry lock, checked it offline and tested clean core/QA installations. Application versions stayed unchanged. |
| Functional CI preparation | The original manual draft deliberately failed before any setup; action commits and bootstrap were unverified. | Verified official action commits/source, implemented checkout/Python/uv and separate locked environments, added PR/manual events and offline checks with runtime isolation assertions. Local configuration, shell and guard checks passed. |

The earlier incomplete report is preserved as [the initial offline report](../../data/eval-comparisons/completion-06/completion-06-before-closure.md). Initial failed scans, transport attempts and test logs remain evidence; they were not overwritten or renamed into successful results.

## What “offline work” means here

Offline verification uses already-local interpreters, packages, model weights and fixtures. It does not contact package registries, model hubs or live providers. It does not mean simulated inference or skipped model tests: all three existing local model tests actually ran.

Acquisition and verification are separate activities. The user initially selected offline work and separately permitted one exact locked RapidFuzz wheel. After the remaining requirements were explained, the user delegated the bounded-access choice; the coordinator chose the proposed allowance of up to 150 MB for QA tools/dependency metadata and read-only official GitHub verification. Required inputs were acquired, then the checks ran offline. Missing local inputs cause a failure, not a silent download.

The Makefile enforces offline flags. The scanner and local-model helper additionally deny audited Python socket operations; this is not an operating-system sandbox. The prepared Linux CI uses a network namespace, dropped capabilities and no-new-privileges, and asserts those properties before running checks. Only a future approved Linux execution can verify that runtime behavior.

## Approved scope and work division

The user approved the Step 06 preflight in `completion-05.md`, including the runtime/build/lock changes, engineering checks and living documentation. The additional helper and helper-test files were explicitly approved. Five Astra/max workers owned metadata/acquisition, CI/hooks, Make/helper behavior, tests/packaging, and living documentation. The coordinator reviewed contracts and findings, ran final verification and owns this report.

Existing files changed: `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `docs/data-card.md`, `docs/model-card.md`, `docs/implementation-phases.md`.

New files: `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Makefile`, `.env.example`, `scripts/project_checks.py`, `tests/test_packaging.py`, `tests/test_project_checks.py`, `docs/access-and-resource-ledger.md`, and this report. Local tools/caches and receipts are ignored developer artifacts, not package contents.

No application source, original application tests, model weights/configurations, historical source stores, archived cases or historical phase reports were rewritten. No commit, push, remote change, dataset/model acquisition, paid/API-account call or deployment occurred. For actual pre-commit verification only, a disposable copied directory was initialized and staged as a temporary Git fixture, with no commit or remote; it was removed afterward. The original workspace still has no `.git` directory.

## File-by-file explanation

| File | Change and purpose |
| --- | --- |
| `pyproject.toml` | Declares Python 3.14; pins Hatchling 1.32.4, pytest 9.1.1 and uv 0.13.5; adds separate pinned QA dependencies; restricts sdist inputs; scopes Ruff to the three new Python files. Runtime requirement strings remain unchanged. |
| `uv.lock` | Generated by uv, not edited by hand. Records 113 entries. Preserves all 102 original third-party selections relevant to Python 3.14 and all 650 retained artifact hashes/sizes. Removes obsolete interpreter-specific alternatives and adds ten QA package names. |
| `Makefile` | Provides explicit offline lock/test/model/lint/build/package/evaluation/scan/inventory targets; exports chosen interpreters/tool paths; defaults QA to `.tools/qa/bin/python`; refuses an existing build destination. Ruff receives exact approved paths. |
| `.pre-commit-config.yaml` | Three local system hooks call lock checking, scoped lint/format and the source scanner. They neither acquire remote hook repositories nor rewrite source. |
| `.github/workflows/ci.yml` | Full verified action pins; read-only contents permission; checkout credentials not persisted; Python 3.14.0 and checksum-bound uv 0.13.5; separate locked runtime/QA setup; offline privilege/network assertions, real hooks, inventory, build, full non-integration tests and fictional evaluation. |
| `.gitignore` | Keeps local tools/caches, private evidence and source-store copies outside publication candidates. `.env.example` remains allowed. |
| `.env.example` | Credential-free shell/Make settings and separate QA interpreter. The application does not automatically read this file. |
| `scripts/project_checks.py` | Reusable deterministic evaluation, dependency/license inventory, strict real scanner wrapper and three-model runner. Receipts distinguish actual success, reviewed findings, missing inputs and limitations. |
| `tests/test_project_checks.py` | 47 cases covering real engine behavior plus malformed results, symlinks, redaction, import shadowing, socket denial, timeout, exact reviewed exceptions, Make propagation, output preservation and model pass-count enforcement. |
| `tests/test_packaging.py` | Eight checks for metadata/lock consistency, exact resources/RECORD hashes, bounded sdist contents, identical rebuild, empty core install, CLI execution and an empty QA environment reproduced offline from the lock. |
| `README.md` | Current capabilities and limitations, demonstrated runtime, explicit tools/cache commands, safe fresh-environment examples and distinction between local evidence and hosted CI. |
| `docs/data-card.md` | Fictional/public provenance, exposed regression-only fixtures and current source-v3 boundaries. Historical source terms are not asserted as current permission. |
| `docs/model-card.md` | Actual pretrained experiments and human-review workflow; no invented training, calibration or operational guarantees; current runtime limits. |
| `docs/implementation-phases.md` | Separates historical phases from Completion Steps and points to this acceptance report and the remaining approved-plan sequence. |
| `docs/access-and-resource-ledger.md` | Concrete owners/actions for source rights, compute, LLM budgets, HF, GitHub, Azure, tenant entitlements and release licensing. Unknown access remains unknown. |
| `docs/progress/completion-06.md` | Current acceptance, command/result evidence, teaching walkthrough, limits and next-step boundary. |

## New-code walkthrough

Line references refer to the frozen code verified in this closure.

- `project_checks.py:30`, `SCANNER_BOOTSTRAP`: loads the real detector with isolated Python imports, installs a socket audit guard first, and fails even if detector code catches a denied network operation. Credential verification remains disabled.
- `project_checks.py:107`, `REVIEWED_NON_SECRET_FINDINGS`: explicit exceptions for inspected historical checksums/revisions and a fictional test marker. Each binds a path, complete file digest, exact finding line/type and explanation. Changed contents or additional findings are not exempt.
- `project_checks.py:250`, `_contained_path`, and `:272`, `published_files`: reject symlink/escape paths and enumerate the declared publication-candidate scope. Local private data, weights, environments and `.env` files are not publication candidates. This is not a claim about a Git index.
- `project_checks.py:313`, `eval_smoke`: builds 157 current-contract fictional queries, evaluates RapidFuzz and omits timing so the receipt is deterministic. It marks results regression-only.
- `project_checks.py:353`, `_unique_scanner_object`: rejects duplicate JSON keys so a later `results` field cannot erase earlier findings.
- `project_checks.py:365`, `secret_scan`: requires the exact real detector version, bounds execution to 120 seconds, validates/redacts output, consumes each reviewed exception at most once and separately reports unresolved findings. Missing or malformed tooling fails.
- `project_checks.py:494`, `dependency_inventory`: distinguishes declared lock entries from installed distributions and preserves unknown license metadata; it does not issue legal clearance.
- `project_checks.py:563` and `:570`, `_deny_network` and `_temporary_environment`: reject audited Python network activity and restore environment settings after use.
- `project_checks.py:583`, `local_model_tests`: copies existing configs into temporary storage, requires local models before running, counts exactly three actual passes, rejects skips, verifies original configs and records attempted network operations.
- `project_checks.py:728`, `_check_output`, `:735`, `write_report`, and `:776`, `main`: preflight and exclusively create receipts; never overwrite earlier evidence; return failing exit codes for unsuccessful checks.
- `test_packaging.py:47`, `uv_executable`: makes the selected executable absolute before changing directories. `:79`, `run_checked`, preserves actual subprocess results under offline settings. `:122`, `distributions`, binds builds to input hashes and fresh output paths.
- `test_packaging.py:196` and `:216`: check supported-version semantics and actual offline lock consistency. uv normalizes the declared range to `==3.14.*`; equivalent spellings are not incorrectly compared as strings.
- `test_packaging.py:223`, `:243`, `:294` and `:318`: verify exact package resources, wheel metadata/RECORD, source-archive exclusions and byte-identical wheel rebuilding outside the checkout.
- `test_packaging.py:346`: installs exact hash-bound project/RapidFuzz wheels into an empty environment, validates native scoring/resources and runs the fictional CLI from another directory.
- `test_packaging.py:501`: starts with zero installed packages, synchronizes only the locked QA group offline, checks all 18 distributions and executes the three real tool CLIs. Package names are normalized because distribution metadata can spell `pre-commit` as `pre_commit`.
- `test_project_checks.py:87`, `:136`, `:187`, `:210`, `:219`: exercise real QA isolation, positive/negative detection, Ruff scope, pre-commit configuration and Make child environments. `:407` checks exact exception matching and nonmatching mutations; `:530` proves caught network attempts still fail.

## Actual results and evidence

| Check | Observed result |
| --- | --- |
| Final full suite | **1,644 passed, 3 deselected, 13 subtests passed in 103.03 s.** The deselected model cases all passed separately. [Log](../../data/eval-comparisons/completion-06/closure-full-suite.log). |
| Real local model tests | **3 passed in 11.12 s; zero skipped/failed and zero recorded network attempts.** Original configs unchanged. [Log](../../data/eval-comparisons/completion-06/closure-local-models.log). |
| Focused helper and packaging | **55 passed in 9.36 s**: 47 helper cases and eight package cases. Included again in the final full suite. [Receipt](../../data/eval-comparisons/completion-06/qa-closure/owned-tests-final.json). |
| Ruff | Actual check and format-check passed; all three scoped Python files already formatted. [Log](../../data/eval-comparisons/completion-06/closure-lint.log). |
| Real pre-commit hooks | All three hooks passed, none skipped, against a hash-bound 136-file copied snapshot. Original/copied publication files unchanged; temporary Git fixture removed. [Receipt](../../data/eval-comparisons/completion-06/ci-action-verification/precommit-copied-tree.json). |
| Real source scanner | 136 files, 70 reviewed non-secret findings, zero unresolved findings; no global detector suppression. Clean and invalid-key canaries passed. Initial failed scan retained. [Reviewed receipt](../../data/eval-comparisons/completion-06/qa-closure/publication-scan-reviewed.json). Final post-report scan is recorded separately below. |
| Lock | Offline `uv lock --check` passed: 113 packages. Original selected versions and retained artifact hashes/sizes preserved. [Preservation receipt](../../data/eval-comparisons/completion-06/tooling-closure/lock-preservation.json). |
| Core package | Empty install contains only the project and RapidFuzz; native scorer and all three resources work; rebuilt wheel bytes match. Final full-suite [package receipt](../../data/eval-comparisons/completion-06/closure-full-suite-packaging/receipt.json). |
| QA reproduction | Empty environment becomes exactly the 18 locked QA distributions offline; no project/system-package leakage; tool CLIs run. [Independent receipt](../../data/eval-comparisons/completion-06/tooling-closure/qa-offline-final.json). |
| Make build | Wheel and sdist built successfully in a fresh directory. A generic warning notes the local cache is under the checkout; archive-content tests confirm it is excluded. [Log](../../data/eval-comparisons/completion-06/closure-build.log). |
| Fictional evaluation | 157 queries; unchanged deterministic ranking fingerprint and complete receipt compared with initial evidence. [Receipt](../../data/eval-comparisons/completion-06/closure-eval.json). |
| Inventory | 82 application distributions, 113 lock entries; original installed versions unchanged. Separate QA inventory has 18 distributions with metadata present but unreviewed. The project's own license declaration remains unresolved. [Current application inventory](../../data/eval-comparisons/completion-06/closure-inventory.json). |
| CI configuration | Official commit/source verification, YAML and shell checks, and six actual bootstrap-guard cases passed. Hosted execution and Linux namespace behavior unrun. [Guard receipt](../../data/eval-comparisons/completion-06/ci-action-verification/bootstrap-guard-validation.json). |

The final [preservation check](../../data/eval-comparisons/completion-06/closure-preservation.json) checked 216 original files: exactly seven approved changes, 209 unchanged, zero missing and zero unexpected changes. All 82 original installed versions and the workflow fingerprint are unchanged. The entire fictional evaluation receipt matches the initial receipt, and the current inventory has zero installed-version mismatches.

The [post-report source scan](../../data/eval-comparisons/completion-06/closure-source-scan.json) and [closure verification](../../data/eval-comparisons/completion-06/closure-verification.json) bind the final publication files, documentation links and final report. The original archive verification from the initial part of Step 06 remains evidence for its inspected state: 37,357 files, four databases and one simulated-demo case. No new execution of historical cases is claimed.

## Commands actually run

The coordinator's final checks used the existing application environment and the new isolated QA environment. Equivalent absolute-path environment values, full commands, durations and exits are preserved in `closure-full-suite.json` and `closure-entrypoints.json`.

```sh
export UV_CACHE_DIR="$PWD/.tools/uv-cache"
export WATCHLIST_WHEELHOUSE="$PWD/data/eval-comparisons/completion-06/wheelhouse"
export WATCHLIST_PACKAGING_EVIDENCE="$PWD/data/eval-comparisons/completion-06/closure-full-suite-packaging"
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv test
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv lock-check
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv lint
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv \
  DIST_DIR=data/eval-comparisons/completion-06/closure-build build
make PYTHON=.venv/bin/python QA_PYTHON=.tools/qa/bin/python UV=.tools/bin/uv test-local-models
.venv/bin/python -B scripts/project_checks.py eval-smoke \
  --output data/eval-comparisons/completion-06/closure-eval.json
.venv/bin/python -B scripts/project_checks.py inventory \
  --output data/eval-comparisons/completion-06/closure-inventory.json
```

Evidence paths above now exist; use new destinations for another run. These are executed commands, not instructions to overwrite their receipts. The workers also ran actual pinned tool CLIs, uv dependency checks, focused pytest, offline QA sync, YAML/shell/guard checks and `pre_commit run --all-files` inside the disposable copied tree; their receipts preserve exact arguments.

## Defects found and fixed

Actual execution exposed faults that syntax-only checks did not catch. Hash verification is now bound to the installed wheel itself. uv paths are resolved before changing directories. Isolated QA imports cannot be replaced by source-tree modules. Duplicate scanner keys, timeouts and caught socket attempts fail safely. Real model tests must report exactly three passes. GNU Make 3.81 offline overrides are enforced using separate assignment/export declarations, and selected tool paths reach child processes.

Actual Ruff traversal of `.` reached an archived nested project configuration even though file inclusion was scoped. Make now passes only the three reviewed files and the explicit root config. Historical source was not reformatted. Python range normalization and package-name normalization were corrected in the new verification code. CI now carries explicit cache/library paths across its environment reset, rejects preexisting/dangling environment destinations, and checks required scientific imports so missing NumPy/Torch cannot hide behind skipped tests.

The first real scanner result contained 72 findings. Reviewed public hash/revision literals and the fictional exclusion marker were classified individually. Two new, owned checksum/test lines have documented local scanner annotations; 70 preserved findings are retained as exact-content reviewed exceptions. Changed bytes, added findings, altered types/locations and duplicates are tested failures. A “passed” scan means zero unresolved findings in the declared scope, not proof that every possible credential can be detected.

## Acquisition and preservation accounting

Pinned QA packages were checked against official PyPI metadata and exact wheel SHA-256/size before offline installation. Existing TLS certificate verification stayed enabled. Initial direct HTTP response bodies totaled **22,306,345 bytes**, including **20,756,691 wheel bytes**. Registry-cache bootstrap reused the same reviewed package versions. Native resolver traffic was sampled rather than individually captured; one run has no usable sample and is explicitly recorded as unknown, never zero.

The conservative tooling accounting is **98,806,345 bytes**, including allowances for native operations and protocol uncertainty, against its 120 MB allocation. Official GitHub verification transferred **1,689,907 HTTP payload bytes** within its 10 MB allocation. Together these are within the authorized 150 MB overall budget; these figures do not pretend to be an exact packet-level measurement. See the [transfer ledger](../../data/eval-comparisons/completion-06/tooling-closure/transfer-budget-final.json). The earlier separately approved RapidFuzz wheel remains in its original receipt.

Temporary transport experiments, certificates/private keys and disposable environments were removed; no system trust store was changed. The retained `.tools/qa`, `.tools/bin/uv` and `.tools/uv-cache` are local tooling. The existing `.venv` still has its original 82 distribution versions. Alternative old-Python lock entries for NetworkX 3.6.1, NumPy 2.4.6 and SciPy 1.17.1 were removed when narrowing support; the Python 3.14 application selections did not change.

## Example input/output and practical limits

The clean installed CLI ran with fictional input `Luma Vesper` and top K=1. It returned candidate `syn-001` with similarity 100, `synthetic: true`, and the research/non-identity notice. The fixture deliberately has a second entity sharing that name. Similarity 100 is not identity evidence or calibrated probability.

The real detector rejected a deliberately invalid private-key marker in a temporary file, while accepting a clean fixture. Its public finding contains only path, line and detector type; raw secret values are not returned. Live credential validation was disabled.

Validated runtime remains CPython 3.14.0/macOS ARM64. Fresh core and QA installs are demonstrated; a fresh full scientific stack on Linux is not. The Linux Torch/NVIDIA candidates alone are about 2.74 GB before other dependencies/unpacking, so a hosted run needs its separate acquisition/quota approval. No source/model download or live provider call was used in the checks.

Step 06 requires license/dependency inventory and accountable access actions, not an invented release license or assumed external accounts. The project-license/notices decision is explicitly assigned to Step 29; source rights, provider budgets and tenant entitlements retain their named later gates in the access ledger. They are unfinished project work, not requirements silently waived from the final project.

## 5W1H recap and next boundary

- **What:** closed the approved engineering-foundation requirements with actual tools, a coherent lock, clean installations, real tests and prepared CI.
- **Why:** successful execution in one old environment alone does not establish reproducibility or real quality-tool enforcement.
- **When:** acquire reviewed inputs under an explicit budget, then verify offline before advancing to data/model work.
- **Where:** approved metadata/tooling/tests/living documents, separate local tool/cache directories and fresh evidence paths.
- **Who:** five Astra/max workers implemented bounded areas; the coordinator reviewed/integrated evidence; the user controls later scope, access and publication.
- **How:** pinned/hash-checked inputs, isolated environments, exact artifact/exception checks, real positive/negative tests and truthful reporting of unrun remote work.

**Step 06 is complete within its approved scope. Step 07 has not started.** Step 07 will first present a detailed preflight for current source-permission review and bounded acquisition adapters: exact files, source/field limits, dependencies, commands, fictional failure tests, transfer limits, risks and acceptance criteria. The existing plan proposes at most 200 non-person groups and 10 MB per permitted source (50 MB total), but that source acquisition is not authorized by this tooling approval. Stop here until the user approves the next phase.
