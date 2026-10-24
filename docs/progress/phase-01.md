# Phase 01 — fictional Python name-matching baseline

Date: 2026-10-21, Asia/Kolkata. Status: implementation and application verification complete. Phase 2 has not started. The user explicitly approved Phase 1, then separately approved downloading uv, RapidFuzz, pytest, Hatchling, and required dependencies.

## Outcome and scope

Built a local Python package with 12 fictional entities and 24 aliases, conservative Unicode cleanup, a RapidFuzz character-edit baseline, typed result records, a JSON command-line demo, and 68 passing pytest cases. The package wheel also ran from an independent temporary environment outside the repository.

All names were authored for this fixture, including Latin, Cyrillic, and Arabic examples. No public sanctions data, private records, pretrained models, APIs, paid services, Git initialization, commits, public deployment, or Phase 2 work were used. Fictional names can coincidentally resemble real names. Non-Latin aliases are authored examples, not independently validated transliteration labels.

## Every created project file

| File | What it does and why |
|---|---|
| [pyproject.toml](../../pyproject.toml) | Declares the package, Python range, runtime/development dependencies, build backend, package directory, and test location. One place describes installation and testing. |
| [uv.lock](../../uv.lock) | Generated dependency resolution with exact versions, sources, markers, and hashes; makes the approved environment reproducible. Do not edit it manually. |
| [.gitignore](../../.gitignore) | Lists environments, Python/test caches, build outputs, and secret files to exclude if Git is later approved. It does not create a Git repository. |
| [README.md](../../README.md) | Explains running the existing environment, recreating it with uv, the algorithm, actual results, research boundaries, and limitations. |
| [src/watchlist/__init__.py](../../src/watchlist/__init__.py) | Marks the importable package and states its fictional research purpose. |
| [src/watchlist/__main__.py](../../src/watchlist/__main__.py) | Connects `python -m watchlist` to the CLI and returns its exit status to the shell. |
| [src/watchlist/data/synthetic_entities.json](../../src/watchlist/data/synthetic_entities.json) | Contains the 12 entities, 24 original alias strings, stable IDs, entity types, `synthetic: true`, and `fictional-synthetic-v1` source tags. |
| [src/watchlist/entities.py](../../src/watchlist/entities.py) | Defines typed records and validates JSON before the matcher uses it. Loads data relative to the installed package, not the shell's current directory. |
| [src/watchlist/normalize.py](../../src/watchlist/normalize.py) | Validates and creates comparable Unicode text while leaving the caller's original string intact. |
| [src/watchlist/matching.py](../../src/watchlist/matching.py) | Scores aliases, selects the best alias per entity, breaks ties consistently, and returns distinct candidates. |
| [src/watchlist/cli.py](../../src/watchlist/cli.py) | Parses arguments, calls the loader and matcher, reports errors, and prints JSON evidence with the limitation notice. |
| [tests/test_entities.py](../../tests/test_entities.py) | Checks fictional data integrity and rejection of corrupted JSON records. |
| [tests/test_normalize.py](../../tests/test_normalize.py) | Checks known Unicode transformations, preserved accents/scripts, idempotence, and input/expanded-length limits. |
| [tests/test_matching.py](../../tests/test_matching.py) | Checks hand-calculated scores, correct alias selection, ambiguity, stable ties, candidate counts, and invalid inputs. |
| [tests/test_cli.py](../../tests/test_cli.py) | Runs the real CLI in child processes, including a different working directory, and checks JSON, errors, help, and Unicode output. |
| [docs/progress/phase-01.md](phase-01.md) | This report: work, explanations, actual evidence, limitations, and the next approval boundary. |

The final SHA-256 comparison confirmed all nine pre-existing project files are unchanged. Phase 0 remains a historical proposed design. Generated `.venv/`, `.pytest_cache/`, and `__pycache__/` directories are local execution artifacts, covered by `.gitignore`, not additional source modules. No extra application scaffolding was introduced.

## Libraries and environment

| Component | Actual version | Role |
|---|---|---|
| Python | 3.14.0, macOS ARM64 | Runs the package and tests. Python 3.11–3.14 is declared; other versions were not tested. |
| uv | 0.13.4 | Resolves dependencies, generates the lock file, and creates/synchronizes isolated environments. |
| RapidFuzz | 3.14.6 | The only third-party runtime dependency; computes edit-based string similarity. |
| pytest | 9.1.1 | Executes local automated tests, including parameterized examples. |
| Hatchling | 1.32.4 | Packages `src/watchlist/` and the JSON resource into a wheel. Also locked as a development dependency for offline builds. |

Python's standard library supplies `unicodedata`, `dataclasses`, `importlib.resources`, `json`, `pathlib`, `typing`, and `argparse`. Tests additionally use `subprocess` and `sys`. These modules require no separate download. Other installed packages are transitive dependencies of the approved tools, recorded in `uv.lock`. A Windows-only dependency appears in the universal lock but was not installed on this Mac.

`uv` was initially unavailable on PATH. It was installed in `/tmp/polyglot-phase1-tools`, with cache `/tmp/polyglot-phase1-uv-cache`. Project dependencies live in `.venv/`. Temporary tooling/cache paths are not permanent installations; the README gives direct `.venv/bin/python` commands so the existing environment remains usable without them.

## Main code explained by line and purpose

Line numbers refer to the Phase 1 files as delivered. Type hints describe expected values for readers and tools; they do not themselves enforce input validity. The explicit checks provide runtime validation. A docstring is the explanation inside a function or class. A frozen dataclass is a small named record whose fields cannot be reassigned after creation; tuples also prevent changing the alias collection in place.

### Package configuration and entry points

- `pyproject.toml` lines 1–3 select Hatchling as the builder. Lines 5–10 name/version the package, declare Python compatibility, and require RapidFuzz. Lines 12–13 separate developer tools from runtime requirements. Lines 15–16 include the package under `src/watchlist`, including its JSON resource. Lines 18–20 point pytest at `tests/` and reject unregistered test markers.
- `uv.lock` begins with the lock format and Python range; subsequent package sections record exact versions and dependencies. The large RapidFuzz artifact list supports multiple platforms; it does not mean every wheel was downloaded. The lock fixes dependency choices, not the Python interpreter itself.
- `.gitignore` lines 1–7 exclude environment, caches, and builds. Lines 8–10 exclude `.env` secrets while allowing a future placeholder-only `.env.example`. Line 11 excludes Finder metadata. There is still no `.git` directory.
- `__init__.py` line 1 is the package purpose statement. `__main__.py` line 3 imports `main`; lines 5–6 call it only when executed as the entry point. `SystemExit` makes success 0 or validation failure 2 visible to the shell.
- Each JSON record follows the same structure: `entity_id` identifies the record; `name` is the canonical display name; `entity_type` is person or organisation; `source` and `synthetic` describe provenance; each alias has its own ID and original name. `syn-001` and `syn-012` intentionally share a name and remain separate entities. The canonical name must also occur among the aliases so it is searchable.

### `normalize.py`

| Lines | Simple explanation |
|---|---|
| 3–5 | Import Unicode handling and define the single 200-code-point length limit. A code point is a Unicode value, not necessarily one visible symbol. |
| 8–15 | Define `normalize_name(name: str) -> str` and document its order and limits. The function returns a new string; callers keep the original. |
| 16–19 | Reject non-text values and overlong original inputs before comparison. |
| 21 | NFKC converts compatible forms, such as full-width Latin letters, into a common representation. This can merge different originals, which is why display evidence is preserved. |
| 22 | `casefold()` handles Unicode case, including examples such as `ß`→`ss`; a second NFKC recomposes text changed by case folding. |
| 23 | `split()` recognizes Unicode whitespace; joining with one space removes leading/trailing whitespace and collapses repeated spaces/tabs. |
| 24–29 | Reject names that become blank or exceed the limit after expansion. For example, a ligature can expand into several letters. |
| 30 | Return the normalized comparison string. Accents and punctuation are not removed; no translation, transliteration, or word sorting occurs. |

Idempotence means normalizing an accepted normalized example again leaves it unchanged. The tests check this on the listed examples; they are not an exhaustive proof over all Unicode strings.

### `entities.py`

| Lines | Simple explanation |
|---|---|
| 3–10 | Import record/file/JSON utilities, reuse normalization, and define the only accepted Phase 1 source tag. |
| 13–30 | Define frozen `Alias` and `Entity` records. An entity contains a tuple of aliases and explicit provenance. |
| 33–38 | `_text()` checks that a required field exists and is a nonblank string. It returns the original spelling rather than silently cleaning stored evidence. |
| 41–48 | Define `load_entities()`. With no path, it loads packaged fictional data. A path is only a local testing seam, not public-source ingestion. |
| 49–59 | Find the resource inside the installed package or read the supplied path, decode JSON, and require a list at the root. |
| 61–70 | Accumulate validated entities and track IDs in sets; reject non-object records, repeated entity IDs, or whitespace-padded IDs. Sets provide direct membership checks. |
| 71–79 | Validate the canonical name, supported entity type, literal boolean `True`, and synthetic source. `is True` rejects integer `1` pretending to be the marker. |
| 81–98 | Require aliases, validate their IDs/names, reject globally duplicated alias IDs and normalized duplicate spellings within one entity, then preserve each original alias in an `Alias` record. |
| 99–100 | Require the canonical name to be represented among the searchable aliases. |
| 101–111 | Construct the validated `Entity`, freeze its alias collection as a tuple, and finally return all entities as a tuple. An empty JSON list returns an empty corpus. |

Two distinct records sharing a name is allowed. Two aliases in one record collapsing to the same normalized string is rejected. These are different situations: the first represents ambiguity, while the second redundantly repeats a searchable spelling.

### `matching.py`

| Lines | Simple explanation |
|---|---|
| 3–11 | Import the scorer and records; give the scoring method an explicit name for JSON output. |
| 14–25 | Define a candidate containing one entity's display name, best original alias, score, and source. It contains no probability or final identity verdict. |
| 28–39 | Define `rank_candidates()`, require a positive integer k, and normalize the query. The boolean check matters because Python otherwise treats `True` as an integer. |
| 40–47 | Start the result list and reject repeated entity objects or an entity without aliases. Other record validity is the loader's responsibility. |
| 48–57 | For each alias, normalize its text, calculate RapidFuzz similarity, scale from 0–1 to 0–100, and keep the original alias beside the score. |
| 58–60 | Select the best alias using `(-score, alias_id)`. The negative sign makes the largest score sort first; the ID breaks exact ties. `lambda` is a small function describing the comparison key. |
| 61–72 | Construct exactly one candidate for this entity, carrying forward the original evidence and synthetic provenance. |
| 73 | Sort all entities by descending score and then ascending entity ID. Input order cannot decide a tie. |
| 74 | Slice to at most k candidates. If fewer exist, return fewer; if none exist, return an empty list. |

With default unit edit costs and nonempty normalized strings, the score is `100 × (1 − edit_distance / max(lengths))`. One substitution between four-character strings gives 75; two equal normalized strings give 100. This measures text resemblance only. Stored aliases allow an Arabic query to find a record with a Latin canonical name; the scorer itself has not learned cross-script equivalence.

### `cli.py`

| Lines | Simple explanation |
|---|---|
| 3–10 | Import argument parsing and JSON conversion, then the loader, normalizer, and matcher. |
| 12–16 | Define the research notice printed with every successful result. |
| 19–26 | Define `main()`, require `--name`, read integer `--top-k` with default 5, and provide automatic help. Passing `argv` directly also supports unit testing. |
| 27–32 | Normalize, load, and rank. Convert expected input/data/file errors into argparse errors on stderr with exit code 2, rather than a raw traceback. |
| 34–38 | Retain the original query, normalized query, scorer name, and requested k in the result. |
| 39–42 | `enumerate(..., start=1)` numbers ranks; `asdict()` converts each candidate record into JSON-ready fields. |
| 43–46 | Attach the limitation message, print readable JSON preserving Unicode, and return exit code 0. |

The CLI does not save queries, contact an API, or let the user load arbitrary datasets. Invalid arguments produce no candidate JSON on stdout. A low score still appears because Phase 1 has no rejection threshold.

## Tests explained

Tests compare behavior against known expectations instead of calling the production scorer to calculate its own expected answer. `pytest.mark.parametrize` runs the same test with several input/expected-output rows; this is why there are 68 test cases but fewer than 68 test functions. `tmp_path` is pytest's isolated temporary directory. `monkeypatch` replaces a function only during one test; `capsys` captures printed output.

| File and lines | Main checks and why they matter |
|---|---|
| `test_normalize.py` 8–26 | Known case/space/full-width/decomposed-accent/Greek/ligature/Cyrillic/Arabic examples; expected output and repeat-normalization equality. |
| `test_normalize.py` 29–42 | Accents and scripts remain distinct; blank and non-string inputs fail. |
| `test_normalize.py` 45–54 | A 200-character input succeeds, 201 fails, and normalization expansion cannot exceed the limit. |
| `test_entities.py` 12–30 | Create a fresh tiny fictional record and temporary JSON file for each corruption test, avoiding shared mutation. |
| `test_entities.py` 33–47 | Check exact fixture IDs/counts, 24 aliases, types, provenance, alias uniqueness, planned ambiguity, and representative scripts. |
| `test_entities.py` 50–85 | Corrupt fields/types, omit a required field, or use the wrong JSON shape; assert specific validation failures. |
| `test_entities.py` 88–117 | Broken JSON, missing files, duplicate entity/alias IDs, normalized alias collisions, and empty-corpus handling. |
| `test_matching.py` 11–25 | Construct controlled records; expect exact match 100 and one edit in four characters 75 by hand. |
| `test_matching.py` 28–47 | Best alias preserves display evidence and only one entity slot; reverse both entity and alias input order and require identical tie results. |
| `test_matching.py` 50–69 | Keep two identical-name entities; cap k at 12; handle empty data; return documented zero-score candidates for unrelated text. |
| `test_matching.py` 72–93 | Reject invalid k, blank/overlong query, duplicate entity objects, and missing aliases. |
| `test_matching.py` 96–102 | Explicit Cyrillic/Arabic stored aliases return the intended record at 100; this checks lookup, not translation. |
| `test_cli.py` 13–22 | Launch `sys.executable -m watchlist`, capture stdout/stderr, and use a timeout to avoid a hanging test. |
| `test_cli.py` 25–51 | Run outside the repository; inspect actual JSON, original/normalized names, provenance, ranks, ambiguity, default k, and Unicode display. |
| `test_cli.py` 54–70 | Missing/blank/long names and invalid k yield exit 2, empty stdout, and useful errors without a traceback. |
| `test_cli.py` 73–88 | Simulate broken fixture loading and verify error handling; confirm help is available. |

## Commands actually run and results

Read-only inspection used `cat AGENTS.md`, `cat docs/implementation-phases.md`, `cat docs/design.md`, `cat docs/evaluation-plan.md`, `pwd`, `rg --files`, `python3 --version`, `command -v uv`, and `uv --version`. The first uv check failed because it was absent. A standard-library script inspected installed package availability and uv cache locations; none of the required packages/cache was initially present. A second script recorded the nine existing file hashes in `/tmp/polyglot-phase1-before.json`. The reference had been read during Phase 0; it remains unchanged.

Edits used `apply_patch`, after explaining each implementation group. The commands below are the executed setup/verification operations. In rows beginning with `uv`, the actual command prefix was:

```sh
UV_CACHE_DIR=/tmp/polyglot-phase1-uv-cache UV_PYTHON_DOWNLOADS=never /tmp/polyglot-phase1-tools/bin/uv
```

| Executed command or check | Actual result |
|---|---|
| `python3 -m venv /tmp/polyglot-phase1-tools` | Created the temporary tooling environment. |
| `/tmp/polyglot-phase1-tools/bin/python -m pip install --disable-pip-version-check uv` | Failed inside the restricted sandbox: package-server name resolution failed; no versions could be fetched. |
| Same install with `--no-cache-dir`, using approved network-capable execution | Succeeded; installed uv 0.13.4. No automatic approval rejection occurred. |
| `uv lock --python python3` | Succeeded; resolved 12 packages including the project and conditional dependency. |
| `uv sync --locked --dev --python python3` | Created `.venv`, built the editable local package, and installed 11 packages on this platform. |
| `.venv/bin/python` inline script using `inspect.signature()` and the installed `Levenshtein.normalized_similarity.__doc__` | Confirmed `(s1, s2, *, weights=(1, 1, 1), processor=None, score_cutoff=None, score_hint=None)` and documented 0–1 normalized similarity. No external API claim was assumed. |
| `uv run --locked --offline pytest -q` | Exit 0: **68 passed in 0.99s**. No test failures occurred. Time is this run's test duration, not matching latency. |
| `uv build --offline --no-build-isolation --wheel --out-dir /tmp/polyglot-phase1-dist` | Exit 0; built `polyglot_watchlist-0.1.0-py3-none-any.whl`. |
| `uv venv --offline --python python3 /tmp/polyglot-phase1-wheel-check` | Created the independent wheel-check environment. |
| `uv pip install --offline --python /tmp/polyglot-phase1-wheel-check/bin/python /tmp/polyglot-phase1-dist/polyglot_watchlist-0.1.0-py3-none-any.whl rapidfuzz==3.14.6` | Failed to resolve RapidFuzz from cache. |
| Same offline install with `--index-url https://pypi.org/simple` | Same cache-resolution failure. Python/platform diagnostics showed both environments using Python 3.14.0 ARM64. |
| Same install with explicit index, without `--offline`, under approved package access | Succeeded; installed the wheel and RapidFuzz 3.14.6. The precise cache failure cause was not established. |
| `/tmp/polyglot-phase1-wheel-check/bin/python` inline verification, working directory `/tmp` | Exit 0; confirmed module came from that environment's `site-packages`, all 12 packaged entities loaded, and CLI returned expected tied candidates. |
| `nl -ba` on application/configuration files and a Python AST inspection of test functions | Read actual line numbers for this walkthrough. |

The actual wheel import path was `/private/tmp/polyglot-phase1-wheel-check/lib/python3.14/site-packages/watchlist/__init__.py`. This confirms the packaging check did not import `src/watchlist` from the checkout. No application code changes were needed after the first passing test run.

A final `python3` standard-library check compared file hashes and the planned file list, validated local documentation links/fences/whitespace, and parsed the Python files with `ast.parse`. It exited 0 and printed:

```text
PASS scope: exactly 16 planned files added; all 9 original files unchanged; no Git repository
PASS documentation: 20 local links resolve; Markdown fences and whitespace valid
PASS Python syntax: 10 source/test files parse
```

These documentation/syntax checks supplement the actual pytest run; they do not replace it. The completed integrity results were then added to this report.

### Real CLI commands and outputs

Each row below was executed with `uv run --locked --offline python -m watchlist` using the full prefix above. A local Python subprocess script captured stdout, stderr, and exit codes in `/tmp/polyglot-phase1-samples.json`.

| Arguments | Exit | Actual result |
|---|---:|---|
| `--name "  LUMA   VESPER  " --top-k 3` | 0 | Normalized to `luma vesper`; `syn-001` 100.0, `syn-012` 100.0, `syn-002` 81.81818181818181. |
| `--name "Luma Vespr" --top-k 3` | 0 | `syn-001` and `syn-012` 90.9090909090909; `syn-002` 81.81818181818181. |
| `--name "Élo Nivara" --top-k 1` (decomposed accent) | 0 | Normalized to `élo nivara`; `syn-003`, original alias `Élo Nivara`, 100.0. |
| `--name "МИРА ВЕЛУНЕ" --top-k 1` | 0 | Normalized to `мира велуне`; `syn-005`, alias `Мира Велуне`, 100.0. |
| `--name "سيرا لومين" --top-k 1` | 0 | `syn-007`, same Arabic alias, 100.0. |
| `--name "ЖЖЖЖЖ"` | 0 | Five candidates `syn-001` through `syn-005`, all 0.0. |
| `--name "   "` | 2 | `python -m watchlist: error: name must not be blank` on stderr. |
| `--name "Luma Vesper" --top-k 0` | 2 | `python -m watchlist: error: top_k must be a positive integer` on stderr. |

The first candidate object from the first successful command was:

```json
{
  "rank": 1,
  "entity_id": "syn-001",
  "display_name": "Luma Vesper",
  "entity_type": "person",
  "matched_alias_id": "syn-001-a1",
  "matched_alias": "Luma Vesper",
  "similarity_score": 100.0,
  "synthetic": true,
  "source": "fictional-synthetic-v1"
}
```

The full response also contained the original/normalized query, scorer name, requested k, other candidates, and the notice: “Possible record match for research review; not identity confirmation. All reference records are fictional. Similarity scores are not probabilities. Low scores do not establish absence or provide clearance.” No score above is a benchmark metric or probability.

## Acceptance, changes from the proposal, and limitations

The application acceptance checks passed: exactly 12 entities/24 aliases, explicit fictional provenance, validated records, original text retained, Unicode examples, idempotence on tested inputs, entity-level grouping, deterministic alias/entity ties, meaningful errors, a working CLI, 68 passing tests, and packaged data loading outside the repository. Whether the learner can explain every function remains a learning review, not something automated tests can establish.

Small implementation details made explicit: used Hatchling as the minimal backend; installed uv temporarily after approval because it was absent; added a second NFKC after case folding and a post-normalization length check; required canonical names to appear among aliases; included Hatchling in the dev lock to support a build using the locked backend. All source files follow the approved Phase 1 file list. No later-phase features were introduced.

No application bug was observed in the executed checks. Two environment/setup issues occurred and were resolved as recorded above. The temporary offline wheel install could not resolve a cached dependency, so completely offline environment reconstruction was not established. Running the installed application and tests offline did succeed.

Remaining limitations:

- The dataset is deliberately tiny and invented. We measured software behavior, not real-world recall, false-positive rate, calibration, or multilingual generalization.
- Names can be ambiguous even at score 100. IDs break ties for reproducibility, not because the first tied entity is more likely correct.
- No transliteration, translation, phonetics, embeddings, training, metadata reconciliation, thresholding, probability mapping, or analyst decision persistence exists.
- Stored Arabic/Cyrillic aliases enable exact lookups; they do not establish matching ability between unseen scripts. Language review would be needed before trusting broader examples.
- NFKC/case folding can merge originals and expand characters. This is not comprehensive Unicode spoofing or invisible-character protection.
- Low-score results remain in the top-k output, including all-zero results. Users must inspect evidence; no automated identity or clearance judgment is made.
- The loader enforces fictional provenance metadata, but metadata alone cannot prove that arbitrary supplied data are truly fictional. The CLI only uses the bundled authored fixture.
- Data are reloaded and aliases normalized for every request. This clear full scan is suitable for 24 aliases; no scale or latency claim has been measured.
- Only Python 3.14.0 on this Mac was tested. Temporary uv/cache paths may disappear. No network services or public endpoints exist.

## Detailed 5W1H recap

**What did we build?** A minimal record-retrieval baseline: a Python package that returns possible fictional entities and the aliases responsible for their scores. “Baseline” means a simple starting method that future experiments can compare against. “Retrieval” means selecting candidates from the reference records, not confirming a person's identity.

**Why these choices?** Character-edit similarity is small enough to explain with pencil-and-paper examples. Unicode normalization removes formatting differences without deliberately discarding accents or changing scripts. Stable IDs preserve ambiguity and make repeated runs reproducible. Explicit validation catches bad data before it affects rankings. Tests keep these choices checkable as the project grows.

**Who is responsible?** You approved the phase and package access and will review the explanation. The assistant wrote the authored fixture, code, tests, and documentation and ran the listed checks. The eventual human analyst remains responsible for interpreting candidates. There is no LLM or autonomous decision-maker in this phase.

**When does each operation happen?** Environment setup happens before running the package. On each CLI invocation, argument parsing precedes normalization, data loading, alias scoring, entity ranking, and JSON output. Automated tests run during development. No model trains during a query, and no next phase starts without approval.

**Where do the pieces live?** Source is in `src/watchlist`, fictional data are packaged under `src/watchlist/data`, tests are in `tests`, and learning reports are in `docs/progress`. Runtime dependencies are isolated in `.venv`; temporary tools, captures, and the wheel check live under `/tmp`. User queries are printed locally and not saved by the application or sent over the network.

**How does one request work?** For `  LUMA   VESPER  `, the CLI keeps the original text and normalizes a comparison copy to `luma vesper`. The loader supplies validated fictional aliases. RapidFuzz compares each alias, the matcher keeps one best alias per entity, and stable IDs resolve score ties. JSON shows both exact-name entities at 100 and a third similar record at about 81.82. The notice explains why these are review candidates. Separate tests verify that changing input order cannot change ties and that invalid input exits cleanly.

## Stop before Phase 2

Phase 2 would propose one permitted public-data subset, a provenance-preserving SQLite schema, duplicate handling, and entity-level splits. Source terms, download scope, exact files, commands, and acceptance tests must be reviewed and approved first. Nothing from Phase 2 has been started. Request approval or Phase 1 revisions before proceeding.
