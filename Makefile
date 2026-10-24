# Use an activated environment or pass PYTHON=/absolute/path/to/python.
# UV is an executable path, not a command with extra arguments.
PYTHON ?= python3
# Keep approved quality tools separate from the application environment.
QA_PYTHON ?= .tools/qa/bin/python
UV ?= uv
DIST_DIR ?= dist
export PYTHON QA_PYTHON UV

# These targets verify local inputs; they never acquire packages or models.
override PYTHONDONTWRITEBYTECODE := 1
override HF_HUB_OFFLINE := 1
override TRANSFORMERS_OFFLINE := 1
override HF_HUB_DISABLE_TELEMETRY := 1
override LANGSMITH_TRACING := false
override LANGCHAIN_TRACING_V2 := false
override UV_OFFLINE := 1
override UV_PYTHON_DOWNLOADS := never
override PIP_NO_INDEX := 1
override PIP_DISABLE_PIP_VERSION_CHECK := 1
export PYTHONDONTWRITEBYTECODE HF_HUB_OFFLINE TRANSFORMERS_OFFLINE HF_HUB_DISABLE_TELEMETRY
export LANGSMITH_TRACING LANGCHAIN_TRACING_V2 UV_OFFLINE UV_PYTHON_DOWNLOADS
export PIP_NO_INDEX PIP_DISABLE_PIP_VERSION_CHECK

.PHONY: help test test-local-models lock-check lint build package-smoke eval-smoke secret-scan inventory

help:
	@printf '%s\n' \
	  'Select an installed environment: make PYTHON=.venv/bin/python <target>' \
	  'test           Run all offline tests except explicitly opt-in model tests.' \
	  'test-local-models  Opt in to three already-local model tests with isolated caches.' \
	  'lock-check     Check lock consistency offline without installing anything.' \
	  'lint           Check the reviewed Ruff scope without changing files.' \
	  'build          Build wheel and source archive into a new DIST_DIR (default: dist).' \
	  'package-smoke  Check packaging and installation outside this checkout.' \
	  'eval-smoke     Run deterministic current-contract fictional evaluation.' \
	  'secret-scan    Scan the declared publication scope; requires detect-secrets.' \
	  'inventory      Report lock and installed dependency/license metadata.' \
	  'Overrides: PYTHON=<executable> QA_PYTHON=<executable> UV=<executable> DIST_DIR=<new-directory>'

test:
	"$(PYTHON)" -B -m pytest -q -m 'not integration' -p no:cacheprovider

test-local-models:
	"$(PYTHON)" -B scripts/project_checks.py local-model-tests

lock-check:
	"$(UV)" lock --check --offline

lint:
	"$(QA_PYTHON)" -I -B -m ruff check --config pyproject.toml \
		scripts/project_checks.py tests/test_project_checks.py tests/test_packaging.py
	"$(QA_PYTHON)" -I -B -m ruff format --check --config pyproject.toml \
		scripts/project_checks.py tests/test_project_checks.py tests/test_packaging.py

build:
	@test ! -e "$(DIST_DIR)" && test ! -L "$(DIST_DIR)" || { printf '%s\n' 'Build output exists; choose a new DIST_DIR to preserve it.' >&2; exit 1; }
	"$(UV)" build --offline --no-build-isolation --python "$(PYTHON)" --out-dir "$(DIST_DIR)"

package-smoke:
	UV="$(UV)" "$(PYTHON)" -B -m pytest -q tests/test_packaging.py -p no:cacheprovider

eval-smoke:
	"$(PYTHON)" -B scripts/project_checks.py eval-smoke

secret-scan:
	"$(QA_PYTHON)" -I -B scripts/project_checks.py secret-scan

inventory:
	"$(PYTHON)" -B scripts/project_checks.py inventory
