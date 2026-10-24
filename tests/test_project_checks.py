"""Adversarial checks of the maintenance helper's evidence and privacy boundaries."""

from __future__ import annotations

from email.message import Message
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib
from types import SimpleNamespace

from packaging.utils import canonicalize_name
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checks():
    spec = importlib.util.spec_from_file_location(
        "watchlist_project_checks_test", ROOT / "scripts/project_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def qa_python():
    """Require the separate, already-installed QA environment; never acquire it."""
    configured = os.environ.get("QA_PYTHON", str(ROOT / ".tools/qa/bin/python"))
    executable = shutil.which(configured)
    if executable is None:
        pytest.fail(
            "The reviewed QA interpreter is missing; install it separately or set QA_PYTHON. No acquisition was attempted."
        )
    # Preserve the venv interpreter path: resolving its symlink loses the venv.
    return str(Path(executable).absolute())


def run_qa(python: str, arguments: list[str], directory: Path):
    """Run real installed tools in isolated Python mode with offline defaults."""
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        UV_OFFLINE="1",
        UV_PYTHON_DOWNLOADS="never",
        PIP_NO_INDEX="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        RUFF_CACHE_DIR=str(directory / "ruff-cache"),
    )
    return subprocess.run(
        [python, "-I", "-B", *arguments],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=150,
    )


def put(root: Path, name: str, text: str = "fixture\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_real_qa_environment_is_isolated_and_matches_declared_lock(qa_python, tmp_path):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    declared = dict(item.split("==", 1) for item in project["dependency-groups"]["qa"])
    declared = {canonicalize_name(name): version for name, version in declared.items()}
    assert set(declared) == {"ruff", "pre-commit", "detect-secrets"}
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {
        canonicalize_name(item["name"]): item["version"] for item in lock["package"]
    }
    assert all(locked.get(name) == version for name, version in declared.items())
    code = """
from importlib import metadata
import json
from pathlib import Path
import re
import site
import sys
print(json.dumps({
    'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
    'user_site_enabled': site.ENABLE_USER_SITE, 'sys_path': sys.path,
    'config': (Path(sys.prefix) / 'pyvenv.cfg').read_text(),
    'installed': {re.sub(r'[-_.]+', '-', item.metadata['Name']).lower(): item.version
                  for item in metadata.distributions()},
}))
"""
    process = run_qa(qa_python, ["-c", code], tmp_path)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    prefix = Path(result["prefix"]).resolve()
    assert prefix != Path(result["base_prefix"]).resolve()
    assert prefix != Path(sys.prefix).resolve(), (
        "QA must not reuse the application environment."
    )
    assert result["user_site_enabled"] is False
    assert "include-system-site-packages = false" in result["config"].lower()
    assert "polyglot-watchlist" not in result["installed"]
    assert all(
        result["installed"].get(name) == version for name, version in declared.items()
    )
    assert all(
        locked.get(name) == version for name, version in result["installed"].items()
    )
    assert all(
        not Path(path).is_relative_to(ROOT) or Path(path).is_relative_to(prefix)
        for path in result["sys_path"]
    )


@pytest.mark.parametrize("with_canary", [False, True])
@pytest.mark.parametrize(
    "start_method", [None, "forkserver"], ids=["default", "forkserver"]
)
def test_real_detector_accepts_clean_files_and_rejects_fabricated_key(
    qa_python, tmp_path, with_canary, start_method
):
    project = tmp_path / "project"
    put(project, "README.md", "Fictional, harmless scanner input.\n")
    put(project, "src/example.py", "fictional_value = 7\n")
    canary = (
        "-----BEGIN "
        + "RSA PRIVATE KEY-----\nnot a real key\n-----END "
        + "RSA PRIVATE KEY-----\n"
    )
    if with_canary:
        put(project, "src/tls/canary.pem", canary)
    before = tree_bytes(project)
    code = """
import importlib.util
import json
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('real_project_checks', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if sys.argv[3]:
    module.SCANNER_BOOTSTRAP = (
        "import multiprocessing as mp\\n"
        f"mp.set_start_method({sys.argv[3]!r}, force=True)\\n"
        + module.SCANNER_BOOTSTRAP
    )
print(json.dumps(module.secret_scan(Path(sys.argv[2])), sort_keys=True))
"""
    process = run_qa(
        qa_python,
        [
            "-c",
            code,
            str(ROOT / "scripts/project_checks.py"),
            str(project),
            start_method or "",
        ],
        tmp_path,
    )
    assert process.returncode == 0, (
        "The actual installed scanner failed; raw diagnostics are withheld."
    )
    result = json.loads(process.stdout)
    assert (
        result["detector"] == "detect-secrets" and result["detector_version"] == "1.5.0"
    )
    assert (
        result["credential_verification"] is False
        and result["python_socket_guard"] is True
    )
    assert result["status"] == ("failed" if with_canary else "passed")
    expected = (
        [{"path": "src/tls/canary.pem", "line": 1, "type": "Private Key"}]
        if with_canary
        else []
    )
    assert result["findings"] == expected
    assert canary not in process.stdout and "not a real key" not in process.stdout
    assert all(set(item) == {"path", "line", "type"} for item in result["findings"])
    assert not process.stderr and tree_bytes(project) == before


def test_real_ruff_enforces_reviewed_scope_without_rewriting_files(qa_python, tmp_path):
    put(tmp_path, "pyproject.toml", (ROOT / "pyproject.toml").read_text())
    selected = put(tmp_path, "scripts/project_checks.py", "value=1\nundefined_name\n")
    excluded = put(tmp_path, "src/watchlist/legacy.py", "another_undefined_name\n")
    before = {path: path.read_bytes() for path in (selected, excluded)}
    lint = run_qa(
        qa_python, ["-m", "ruff", "check", ".", "--output-format", "json"], tmp_path
    )
    assert lint.returncode == 1, lint.stderr
    findings = json.loads(lint.stdout)
    assert [(Path(item["filename"]), item["code"]) for item in findings] == [
        (selected, "F821")
    ]
    formatting = run_qa(qa_python, ["-m", "ruff", "format", "--check", "."], tmp_path)
    assert formatting.returncode == 1, formatting.stderr
    assert all(path.read_bytes() == content for path, content in before.items())
    selected.write_text("value = 1\n")
    for arguments in (["check", "."], ["format", "--check", "."]):
        process = run_qa(qa_python, ["-m", "ruff", *arguments], tmp_path)
        assert process.returncode == 0, process.stderr
    assert excluded.read_bytes() == before[excluded]


def test_real_precommit_accepts_project_configuration(qa_python, tmp_path):
    process = run_qa(
        qa_python,
        ["-m", "pre_commit", "validate-config", str(ROOT / ".pre-commit-config.yaml")],
        tmp_path,
    )
    assert process.returncode == 0, process.stderr


def test_make_exports_selected_interpreters_and_uv_to_child_processes(tmp_path):
    """Makefile-defined values must reach nested tools, not only Make recipes."""
    expected = {
        "PYTHON": "selected-python",
        "QA_PYTHON": "selected-qa-python",
        "UV": "selected-uv",
    }
    expression = "import json, os; print(json.dumps({key: os.environ.get(key) for key in ('PYTHON', 'QA_PYTHON', 'UV')}))"
    probe = put(
        tmp_path,
        "probe.mk",
        "\n".join(
            [f"override {key} := {value}" for key, value in expected.items()]
            + [
                ".PHONY: environment-contract",
                "environment-contract:",
                f"\t@{shlex.quote(sys.executable)} -I -B -c {shlex.quote(expression)}",
                "",
            ]
        ),
    )
    environment = dict(os.environ)
    for name in (*expected, "MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        environment.pop(name, None)
    process = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-f",
            str(ROOT / "Makefile"),
            "-f",
            str(probe),
            "environment-contract",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == expected


def test_publication_scope_is_explicit_and_sorted(checks, tmp_path):
    included = [
        "README.md",
        ".env.example",
        "src/watchlist/example.py",
        "tests/test_example.py",
        "src/data.bin",
        "src/tls/client.pem",
        "src/extensionless",
        "scripts/check.py",
        "docs/design.md",
        "eval/configs/sample.json",
        "eval/fixtures/sample.json",
    ]
    excluded = [
        ".env",
        ".env.local",
        "data/source.sqlite",
        "data/private.json",
        "models/weights.bin",
        "dist/leaked.json",
        "src/__pycache__/extra.py",
        "src/.env",
    ]
    for name in included + excluded:
        put(tmp_path, name)
    before = tree_bytes(tmp_path)
    result = checks.published_files(tmp_path)
    assert [path.relative_to(tmp_path).as_posix() for path in result] == sorted(
        included
    )
    assert all(
        path.is_absolute() and path.is_file() and not path.is_symlink()
        for path in result
    )
    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize("kind", ["file", "directory", "root"])
def test_publication_scope_rejects_symlink_escapes(checks, tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    put(outside, "sensitive.py", "fictional private content\n")
    project = tmp_path / "project"
    project.mkdir()
    if kind == "file":
        (project / "README.md").symlink_to(outside / "sensitive.py")
    elif kind == "directory":
        (project / "src").mkdir()
        (project / "src/linked").symlink_to(outside, target_is_directory=True)
    else:
        linked = tmp_path / "linked-project"
        linked.symlink_to(project, target_is_directory=True)
        project = linked
    with pytest.raises(checks.CheckError, match="symlink"):
        checks.published_files(project)


def test_secret_detector_missing_or_wrong_version_is_an_explicit_failure(
    checks, tmp_path, monkeypatch
):
    put(tmp_path, "README.md")
    attempted = []
    monkeypatch.setattr(
        checks.subprocess, "run", lambda *args, **kwargs: attempted.append(args)
    )

    def missing(name):
        raise checks.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(checks.metadata, "version", missing)
    with pytest.raises(checks.CheckError, match="not installed"):
        checks.secret_scan(tmp_path)
    monkeypatch.setattr(checks.metadata, "version", lambda name: "0.0.0")
    with pytest.raises(checks.CheckError, match="reviewed"):
        checks.secret_scan(tmp_path)
    assert not attempted


def fake_scanner(checks, monkeypatch, payload, *, returncode=0):
    calls = []
    monkeypatch.setattr(checks.metadata, "version", lambda name: "1.5.0")

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, returncode, payload, "sensitive scanner diagnostic"
        )

    monkeypatch.setattr(checks.subprocess, "run", run)
    return calls


def test_detector_receipt_omits_secret_values_and_unknown_type_text(
    checks, tmp_path, monkeypatch
):
    put(tmp_path, "src/example.py")
    sentinel = "fictional-sensitive-" + "value-123"
    payload = {
        "version": "1.5.0",
        "results": {
            "src/example.py": [
                {
                    "line_number": 2,
                    "type": "Secret Keyword",
                    "secret": sentinel,
                    "hashed_secret": sentinel,
                },
                {"line_number": 3, "type": sentinel, "secret": sentinel},
            ]
        },
    }
    calls = fake_scanner(checks, monkeypatch, json.dumps(payload))
    result = checks.secret_scan(tmp_path)
    assert result["status"] == "failed" and result["credential_verification"] is False
    assert result["findings"] == [
        {"path": "src/example.py", "line": 2, "type": "Secret Keyword"},
        {"path": "src/example.py", "line": 3, "type": "other detector finding"},
    ]
    assert sentinel not in json.dumps(result)
    command, options = calls[0]
    assert command[:6] == [
        sys.executable,
        "-I",
        "-B",
        "-c",
        checks.SCANNER_BOOTSTRAP,
        "scan",
    ]
    assert (
        "--all-files" in command
        and "--no-verify" in command
        and command[-1] == "src/example.py"
    )
    assert options["cwd"] == tmp_path and options["capture_output"] is True
    assert options["env"]["UV_OFFLINE"] == options["env"]["PIP_NO_INDEX"] == "1"
    assert options["timeout"] == checks.SCANNER_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "case",
    ["exact", "changed-bytes", "extra-line", "extra-type", "duplicate", "other-file"],
)
def test_reviewed_non_secret_exception_matches_exact_content_and_one_finding(
    checks, tmp_path, monkeypatch, case
):
    path = put(tmp_path, "src/example.py", "synthetic harmless format example\n")
    original_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reason = "Synthetic format example used only by this exception-policy regression."
    monkeypatch.setattr(
        checks,
        "REVIEWED_NON_SECRET_FINDINGS",
        {
            "src/example.py": {
                "file_sha256": original_digest,
                "findings": frozenset({(1, "Secret Keyword")}),
                "reason": reason,
            }
        },
    )
    finding = {"line_number": 1, "type": "Secret Keyword"}
    reported = {"src/example.py": [finding]}
    if case == "changed-bytes":
        path.write_text("different synthetic content\n")
    elif case == "extra-line":
        reported["src/example.py"].append({"line_number": 2, "type": "Secret Keyword"})
    elif case == "extra-type":
        reported["src/example.py"].append({"line_number": 1, "type": "Private Key"})
    elif case == "duplicate":
        reported["src/example.py"].append(dict(finding))
    elif case == "other-file":
        put(tmp_path, "src/independent.py", "independent synthetic fixture\n")
        reported["src/independent.py"] = [dict(finding)]
    fake_scanner(
        checks, monkeypatch, json.dumps({"version": "1.5.0", "results": reported})
    )
    result = checks.secret_scan(tmp_path)
    reviewed_count = 0 if case == "changed-bytes" else 1
    unresolved_count = 0 if case == "exact" else 1
    assert result["status"] == ("passed" if case == "exact" else "failed")
    assert result["detected_finding_count"] == reviewed_count + unresolved_count
    assert result["reviewed_non_secret_count"] == reviewed_count
    assert result["unresolved_finding_count"] == unresolved_count
    assert len(result["findings"]) == unresolved_count
    assert result["reviewed_non_secret_findings"] == (
        [
            {
                "path": "src/example.py",
                "line": 1,
                "type": "Secret Keyword",
                "file_sha256": original_digest,
                "reason": reason,
            }
        ]
        if reviewed_count
        else []
    )


@pytest.mark.parametrize(
    "payload",
    [
        "invalid scanner output",
        "[]",
        '{"version": "wrong", "results": {}}',
        '{"version":"1.5.0","results":{"../undeclared.py":[]}}',
        '{"version":"1.5.0","results":{"README.md":"wrong"}}',
        '{"version":"1.5.0","results":{"README.md":[{"line_number":true,"type":"Secret Keyword"}]}}',
        '{"version":"1.5.0","results":{"README.md":[{"line_number":0,"type":"Secret Keyword"}]}}',
        '{"version":"1.5.0","results":{"README.md":[{"line_number":2,"type":"Secret Keyword"}]},"results":{}}',
    ],
)
def test_invalid_detector_evidence_is_rejected_without_echoing_output(
    checks, tmp_path, monkeypatch, payload
):
    put(tmp_path, "README.md")
    fake_scanner(checks, monkeypatch, payload)
    with pytest.raises(checks.CheckError) as error:
        checks.secret_scan(tmp_path)
    assert payload not in str(error.value)


def test_scanner_process_failure_does_not_expose_raw_diagnostics(
    checks, tmp_path, monkeypatch
):
    put(tmp_path, "README.md")
    sentinel = "fictional-sensitive-" + "failure"
    fake_scanner(checks, monkeypatch, sentinel, returncode=1)
    with pytest.raises(checks.CheckError) as error:
        checks.secret_scan(tmp_path)
    assert sentinel not in str(
        error.value
    ) and "sensitive scanner diagnostic" not in str(error.value)


def test_scanner_child_never_executes_a_project_or_pythonpath_shadow_module(
    checks, tmp_path, monkeypatch
):
    """Use a real Python child; the installed detector itself may be unavailable."""
    project = tmp_path / "project"
    project.mkdir()
    pythonpath = tmp_path / "pythonpath"
    pythonpath.mkdir()
    marker = tmp_path / "shadow-code-executed"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('unexpected execution')\n"
        'print(\'{"version":"1.5.0","results":{}}\')\n'
    )
    put(project, "detect_secrets.py", source)
    put(pythonpath, "detect_secrets.py", source)
    put(project, "README.md", "Fictional harmless scanner input.\n")
    monkeypatch.setenv("PYTHONPATH", str(pythonpath))
    monkeypatch.setattr(checks.metadata, "version", lambda name: "1.5.0")
    try:
        result = checks.secret_scan(project)
    except checks.CheckError as error:
        assert "scanner failed" in str(error).lower()
    else:
        assert result["detector_version"] == "1.5.0"
    assert not marker.exists(), "The child imported project-controlled detector code."


@pytest.mark.parametrize(
    "event", ["socket.connect", "socket.getaddrinfo", "socket.sendto"]
)
def test_scanner_child_rejects_a_network_attempt_even_when_caught(
    checks, qa_python, tmp_path, event
):
    """A detector file scan cannot hide an audit event by catching its exception."""
    put(tmp_path, "README.md", "Fictional harmless scanner input.\n")
    exercise = """
import sys
from detect_secrets.core.secrets_collection import SecretsCollection
event = sys.argv[1]
def caught_attempt(*args, **kwargs):
    try:
        sys.audit(event, 'fictional-private-endpoint')
    except RuntimeError:
        pass
SecretsCollection.scan_file = caught_attempt
sys.argv = ["detect-secrets", "scan", "--all-files", "--no-verify", "README.md"]
"""
    process = run_qa(
        qa_python,
        ["-c", exercise + checks.SCANNER_BOOTSTRAP, event],
        tmp_path,
    )
    assert process.returncode == 86
    assert not process.stdout and not process.stderr


def test_scanner_timeout_does_not_echo_captured_output(checks, tmp_path, monkeypatch):
    put(tmp_path, "README.md")
    monkeypatch.setattr(checks.metadata, "version", lambda name: "1.5.0")
    sentinel = "fictional-timeout-" + "sensitive-value"

    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 120, output=sentinel, stderr=sentinel)

    monkeypatch.setattr(checks.subprocess, "run", timeout)
    with pytest.raises(checks.CheckError) as error:
        checks.secret_scan(tmp_path)
    assert sentinel not in str(error.value)


def test_fictional_evaluation_is_deterministic_from_an_unrelated_directory(
    checks, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    first, second = checks.eval_smoke(), checks.eval_smoke()
    assert first == second
    assert first["status"] == "passed" and first["regression_only"] is True
    assert first["benchmark_protocol_version"] == "evaluation-v2"
    assert first["query_count"] > 1 and len(first["rankings_fingerprint"]) == 64
    assert first["aggregates"] and not list(tmp_path.iterdir())
    assert "timing" not in json.dumps(first) and "latency" not in json.dumps(first)


def test_inventory_distinguishes_missing_licenses_and_version_mismatches(
    checks, tmp_path, monkeypatch
):
    registry_marker = "fictional-registry-" + "credential"
    lock = put(
        tmp_path,
        "uv.lock",
        f"""version = 1
[[package]]
name = "Example_Package"
version = "1.2.3"
source = {{ registry = "https://user:{registry_marker}@example.invalid/simple" }}
[[package]]
name = "missing-local-package"
version = "9.8.7"
source = {{ registry = "https://example.invalid/simple" }}
""",
    )
    unknown = Message()
    unknown["Name"] = "example-package"
    unknown["License"] = "UNKNOWN"
    known = Message()
    known["Name"] = "extra-tool"
    known["License-Expression"] = "MIT"
    monkeypatch.setattr(
        checks.metadata,
        "distributions",
        lambda: [
            SimpleNamespace(metadata=unknown, version="1.2.4"),
            SimpleNamespace(metadata=known, version="2.0.0"),
        ],
    )
    result = checks.dependency_inventory(tmp_path)
    observed = {item["name"]: item for item in result["installed_packages"]}
    assert observed["example-package"]["matches_lock_version"] is False
    assert observed["example-package"]["license_status"] == "unresolved"
    assert observed["extra-tool"]["matches_lock_version"] is None
    assert observed["extra-tool"]["license_status"] == "metadata_present_unreviewed"
    assert result["lock_sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert "missing-local-package" in {
        item["name"] for item in result["locked_packages"]
    }
    assert registry_marker not in json.dumps(
        result
    ) and "example.invalid" not in json.dumps(result)


@pytest.mark.parametrize(
    "event", ["socket.connect", "socket.getaddrinfo", "socket.sendto"]
)
def test_network_guard_does_not_echo_endpoint_or_payload(checks, event):
    sentinel = "fictional-private-" + "endpoint"
    with pytest.raises(checks.CheckError) as error:
        checks._deny_network(event, (sentinel,))
    assert event in str(error.value) and sentinel not in str(error.value)
    checks._deny_network("open", (sentinel,))


def test_temporary_environment_restores_values_even_after_failure(checks, monkeypatch):
    monkeypatch.setenv("WATCHLIST_EXISTING_TEST", "original")
    monkeypatch.delenv("WATCHLIST_NEW_TEST", raising=False)
    with pytest.raises(RuntimeError):
        with checks._temporary_environment(
            {"WATCHLIST_EXISTING_TEST": "temporary", "WATCHLIST_NEW_TEST": "temporary"}
        ):
            assert os.environ["WATCHLIST_EXISTING_TEST"] == "temporary"
            raise RuntimeError("fictional failure")
    assert os.environ["WATCHLIST_EXISTING_TEST"] == "original"
    assert "WATCHLIST_NEW_TEST" not in os.environ


def local_fixture(root: Path):
    for name in ("embeddings", "reranking"):
        (root / "models" / name).mkdir(parents=True)
        put(
            root,
            f"eval/configs/{name}.json",
            json.dumps(
                {
                    "model": {"model_path": f"models/{name}"},
                    "cache_path": "original-cache",
                }
            ),
        )
    for name in (
        "test_embedding_model.py",
        "test_reranker_model.py",
        "test_agent_e5.py",
    ):
        put(root, "tests/integration/" + name, "# fictional test placeholder\n")
    put(root, "original-cache/sentinel.txt", "must remain unchanged\n")


def report_outcome(plugin, *, passed=False, skipped=False, failed=False):
    plugin.pytest_runtest_logreport(
        SimpleNamespace(when="call", passed=passed, skipped=skipped, failed=failed)
    )


@pytest.mark.parametrize(
    "mode", ["all-pass", "all-skip", "zero-tests", "caught-network"]
)
def test_local_model_runner_requires_three_passes_and_isolates_all_writes(
    checks, tmp_path, monkeypatch, mode
):
    local_fixture(tmp_path)
    before = tree_bytes(tmp_path)
    original_cwd = Path.cwd()
    original_environment = dict(os.environ)
    scratch_locations = []

    def fake_pytest(arguments, *, plugins):
        scratch = Path.cwd()
        scratch_locations.append(scratch)
        assert scratch != tmp_path and not scratch.is_relative_to(tmp_path)
        assert "no:cacheprovider" in arguments
        for name in ("embeddings", "reranking"):
            config = json.loads((scratch / f"eval/configs/{name}.json").read_text())
            assert (
                Path(config["model"]["model_path"])
                == (tmp_path / "models" / name).resolve()
            )
            assert Path(config["cache_path"]).is_relative_to(scratch)
        for key in ("HF_HOME", "XDG_CACHE_HOME", "TORCH_HOME"):
            assert Path(os.environ[key]).is_relative_to(scratch)
        assert all(
            os.environ[key] == "1"
            for key in (
                "RUN_EMBEDDING_INTEGRATION",
                "RUN_RERANKER_INTEGRATION",
                "RUN_AGENT_E5_INTEGRATION",
            )
        )
        if mode == "caught-network":
            with pytest.raises(checks.CheckError):
                sys.audit("socket.connect", "fictional endpoint")
        for _ in range(0 if mode == "zero-tests" else 3):
            report_outcome(
                plugins[0], skipped=mode == "all-skip", passed=mode != "all-skip"
            )
        return 0

    monkeypatch.setattr(pytest, "main", fake_pytest)
    result = checks.local_model_tests(tmp_path)
    assert result["status"] == ("passed" if mode == "all-pass" else "failed")
    assert result["original_configs_unchanged"] is True
    assert (
        (result["network_attempts"] == ["socket.connect"])
        if mode == "caught-network"
        else not result["network_attempts"]
    )
    assert (
        tree_bytes(tmp_path) == before
        and Path.cwd() == original_cwd
        and dict(os.environ) == original_environment
    )
    assert all(not path.exists() for path in scratch_locations)


def test_missing_local_models_fail_before_creating_scratch_or_loading_pytest(
    checks, tmp_path, monkeypatch
):
    put(
        tmp_path,
        "eval/configs/embeddings.json",
        '{"model":{"model_path":"missing-model"}}',
    )
    before = tree_bytes(tmp_path)
    calls = []
    monkeypatch.setattr(pytest, "main", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(checks.CheckError, match="already-acquired"):
        checks.local_model_tests(tmp_path)
    assert calls == [] and tree_bytes(tmp_path) == before


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_existing_output_is_rejected_before_running_any_check(
    checks, tmp_path, monkeypatch, capsys, kind
):
    output = tmp_path / "receipt.json"
    if kind == "file":
        output.write_text("preserve previous evidence")
    elif kind == "directory":
        output.mkdir()
    else:
        output.symlink_to(tmp_path / "missing-target")
    called = []
    monkeypatch.setattr(checks, "eval_smoke", lambda: called.append(True))
    assert checks.main(["eval-smoke", "--output", str(output)]) == 1
    assert not called
    assert "already exists" in capsys.readouterr().err
    if kind == "file":
        assert output.read_text() == "preserve previous evidence"


def test_report_uses_exclusive_output_and_finite_json(checks, tmp_path):
    path = tmp_path / "nested/receipt.json"
    expected = {"status": "passed", "value": "fictional"}
    checks.write_report(expected, path)
    assert json.loads(path.read_text()) == expected
    with pytest.raises(checks.CheckError):
        checks.write_report({"status": "failed"}, path)
    assert json.loads(path.read_text()) == expected
    invalid = tmp_path / "invalid/new.json"
    with pytest.raises(ValueError):
        checks.write_report({"value": float("nan")}, invalid)
    assert not invalid.exists()
