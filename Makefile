# Use an activated environment or pass PYTHON=/absolute/path/to/python.
# UV is an executable path, not a command with extra arguments.
PYTHON ?= python3
# Keep approved quality tools separate from the application environment.
QA_PYTHON ?= .tools/qa/bin/python
UV ?= uv
DIST_DIR ?= dist
QUALITY_FILES = scripts/project_checks.py tests/test_project_checks.py tests/test_packaging.py \
	src/watchlist/ingest/source_registry.py src/watchlist/ingest/acquire.py \
	src/watchlist/ingest/_parse_common.py src/watchlist/ingest/parse_ftm.py \
	src/watchlist/ingest/parse_un.py src/watchlist/ingest/parse_ofac.py \
	src/watchlist/ingest/parse_eu.py src/watchlist/ingest/parse_wikidata.py \
	tests/test_source_acquisition.py tests/test_source_adapters.py \
	src/watchlist/corpus.py \
	src/watchlist/label_review.py \
	src/watchlist/ingest/link_records.py \
	src/watchlist/ingest/full_acquire.py \
	src/watchlist/ingest/resource_guard.py \
	src/watchlist/ingest/wikidata_api.py \
	src/watchlist/ingest/metadata_preflight.py \
	tests/test_corpus.py \
	tests/test_label_review.py \
	tests/test_record_links.py \
	tests/test_full_acquisition.py \
	tests/test_resource_guard.py \
	tests/test_wikidata_api.py \
	tests/test_metadata_preflight.py \n	src/watchlist/baselines.py \n	src/watchlist/calibration.py \n	src/watchlist/evaluate_baselines.py \n	src/watchlist/evaluate_policy.py \n	src/watchlist/hybrid_retrieval.py \n	src/watchlist/llm/__init__.py \n	src/watchlist/llm/client.py \n	src/watchlist/llm/comparison.py \n	src/watchlist/llm/explanations.py \n	src/watchlist/llm/parsing.py \n	src/watchlist/llm/prompts.py \n	src/watchlist/llm/schemas.py \n	src/watchlist/llm/validation.py \n	src/watchlist/model_artifacts.py \n	src/watchlist/preprocessing.py \n	src/watchlist/reconciliation.py \n	src/watchlist/review/contracts.py \n	src/watchlist/review/locking.py \n	src/watchlist/review/nodes.py \n	src/watchlist/review/recovery.py \n	src/watchlist/review/service.py \n	src/watchlist/review/storage.py \n	src/watchlist/review/validation.py \n	src/watchlist/review/workflow.py \n	src/watchlist/review_policy.py \n	src/watchlist/structured_input.py \n	src/watchlist/synthetic_corpus.py \n	src/watchlist/training.py \n	src/watchlist/training_data.py \n	src/watchlist/training_losses.py \n	src/watchlist/vector_index.py \n	tests/review_v2_support.py \n	tests/test_baselines.py \n	tests/test_calibration.py \n	tests/test_explanation_grounding.py \n	tests/test_hybrid_retrieval.py \n	tests/test_llm_comparison.py \n	tests/test_llm_contracts.py \n	tests/test_model_artifacts.py \n	tests/test_preprocessing.py \n	tests/test_prompt_injection.py \n	tests/test_reconciliation.py \n	tests/test_review_policy.py \n	tests/test_review_v2_cli.py \n	tests/test_review_v2_concurrency.py \n	tests/test_review_v2_contracts.py \n	tests/test_review_v2_portability.py \n	tests/test_review_v2_recovery.py \n	tests/test_review_v2_service.py \n	tests/test_structured_input.py \n	tests/test_synthetic_corpus.py \n	tests/test_training.py \n	tests/test_training_data.py \n	tests/test_training_losses.py \n	tests/test_vector_index.py
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

.PHONY: help test test-local-models lock-check lint build package-smoke eval-smoke secret-scan inventory source-preflight source-tests

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
	  'source-preflight  Inspect reviewed source policies offline; no download.' \
	  'source-tests   Run fictional acquisition and adapter boundary tests.' \
	  'Overrides: PYTHON=<executable> QA_PYTHON=<executable> UV=<executable> DIST_DIR=<new-directory>'

test:
	"$(PYTHON)" -B -m pytest -q -m 'not integration' -p no:cacheprovider

test-local-models:
	"$(PYTHON)" -B scripts/project_checks.py local-model-tests

lock-check:
	"$(UV)" lock --check --offline

lint:
	"$(QA_PYTHON)" -I -B -m ruff check --config pyproject.toml \
		$(QUALITY_FILES)
	"$(QA_PYTHON)" -I -B -m ruff format --check --config pyproject.toml \
		$(QUALITY_FILES)

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

source-preflight:
	"$(PYTHON)" -B -m watchlist.ingest.acquire preflight --profile feasibility --registry config/data-sources.json

source-tests:
	"$(PYTHON)" -B -m pytest -q tests/test_source_acquisition.py tests/test_source_adapters.py tests/test_corpus.py tests/test_label_review.py tests/test_record_links.py tests/test_full_acquisition.py tests/test_resource_guard.py tests/test_wikidata_api.py tests/test_metadata_preflight.py -p no:cacheprovider
