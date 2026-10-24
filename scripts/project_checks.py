"""Offline engineering checks with explicit inputs and fresh JSON receipts.

Run from any directory with the intended installed Python environment. This
helper never installs dependencies, acquires models, or rewrites old evidence.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "project-checks-v1"
DETECTOR_VERSION = "1.5.0"
SCANNER_TIMEOUT_SECONDS = 120
# Isolated Python still loads the selected virtual environment's site-packages.
# Install the socket guard before loading any detector or verification plugin.
# Scan each file in this process: Linux's forkserver uses a local socket, and
# spawned detector workers would not inherit this process's Python audit hook.
SCANNER_BOOTSTRAP = """\
import json
import sys

network_attempts = []

def deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        network_attempts.append(event)
        raise RuntimeError("Network access forbidden during secret scan.")

sys.addaudithook(deny_network)
sys.argv = ["detect-secrets", *sys.argv[1:]]
try:
    from detect_secrets.core.baseline import format_for_output
    from detect_secrets.core.scan import get_files_to_scan
    from detect_secrets.core.secrets_collection import SecretsCollection
    from detect_secrets.main import parse_args

    args = parse_args()
    secrets = SecretsCollection(root=args.custom_root)
    for filename in get_files_to_scan(
        *args.path,
        should_scan_all_files=args.all_files,
        root=args.custom_root,
    ):
        secrets.scan_file(filename)
    if not network_attempts:
        print(json.dumps(format_for_output(secrets, is_slim_mode=args.slim)))
finally:
    if network_attempts:
        raise SystemExit(86)
"""
PUBLICATION_ROOTS = (
    "src",
    "tests",
    "scripts",
    ".github",
    "docs",
    "config",
    "eval/configs",
    "eval/fixtures",
)
PUBLICATION_FILES = (
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".env.example",
)
IGNORED_DIRECTORIES = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", ".tools"}
)
OFFLINE_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "LANGSMITH_TRACING": "false",
    "LANGCHAIN_TRACING_V2": "false",
    "UV_OFFLINE": "1",
    "UV_PYTHON_DOWNLOADS": "never",
    "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
}
# Only these known detector categories are echoed. Other category text is
# replaced with a fixed label so arbitrary scanner strings cannot leak values.
SAFE_FINDING_TYPES = frozenset(
    {
        "AWS Access Key",
        "Base64 High Entropy String",
        "Basic Auth Credentials",
        "GitHub Token",
        "GitLab Token",
        "Hex High Entropy String",
        "JSON Web Token",
        "OpenAI Token",
        "Private Key",
        "Secret Keyword",
        "Slack Token",
        "Stripe Access Key",
    }
)


# Individually reviewed non-credential findings in preserved files. Every
# exception binds the whole file, location and detector type. Changed content
# or additional findings require a new review; files remain in every scan.
REVIEWED_NON_SECRET_FINDINGS = {
    "docs/progress/completion-00.md": {
        "file_sha256": "05f434b5abc82484bb78872b4eea2a5bff16c6949d9601af0f7db8ef6a516fa5",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (201,)),
        "reason": "Historical archive-manifest checksum recorded in the completed preservation report.",
    },
    "docs/releases/v1-manifest.json": {
        "file_sha256": "4d4b5a0e177a2f25b6f23a7f47eb19368b76eacb07fbeb8fdb09473648ae219d",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset(
            (line, "Hex High Entropy String")
            for line in (
                30,
                31,
                45,
                49,
                66,
                73,
                77,
                81,
                96,
                106,
                109,
                113,
                149,
                154,
                159,
                164,
                169,
                174,
                179,
                184,
                189,
                194,
                199,
                204,
                209,
                214,
                219,
                224,
                229,
                234,
                239,
                244,
                249,
                254,
                259,
                264,
                269,
                274,
                279,
                284,
                289,
                294,
                299,
                304,
                309,
                314,
                319,
                324,
                329,
                334,
                339,
                344,
            )
        ),
        "reason": "Preserved release manifest contains recorded file, environment and model integrity checksums.",
    },
    "eval/configs/embeddings.json": {
        "file_sha256": "e75703a1998e2f7ae45c4fd5a2ac4726b72b82c20b8f8300a58c8cd62cd907d0",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (4,)),
        "reason": "Pinned public embedding-model revision, not a credential.",
    },
    "eval/configs/reranking.json": {
        "file_sha256": "7a7a0e8c20839c232c924ff77c4f9960321a982c45eb1f8fa5ebd9b4f1688ae5",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset(
            (line, "Hex High Entropy String") for line in (4, 26, 27, 28)
        ),
        "reason": "Pinned public reranker revision and recorded model-file integrity checksums.",
    },
    "scripts/preserve_v1.py": {
        "file_sha256": "53386192a5fdef606a631956adbd3d8bee78bf3a944b9a97c52d9a69b03ba8ec",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset(
            (line, "Hex High Entropy String") for line in (1584, 1596)
        ),
        "reason": "Historical preservation and audit integrity fingerprints.",
    },
    "src/watchlist/embeddings.py": {
        "file_sha256": "6c2dab46bf2c7f272ea4f43d10182857483f0e71938ff6aea61465a4c6299858",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (18,)),
        "reason": "Pinned public embedding-model revision, not a credential.",
    },
    "src/watchlist/reranking.py": {
        "file_sha256": "903399ce7b496275de5f5fed3cfe007370493574786fb9b2bd5d49546781fc3f",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (23,)),
        "reason": "Pinned public reranker revision, not a credential.",
    },
    "src/watchlist/review/archive.py": {
        "file_sha256": "dc93518b0fe577e5a6f6b4a6bf239e268abee04a1123b43880c39b890c58a829",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (586,)),
        "reason": "Historical audit integrity fingerprint.",
    },
    "src/watchlist/review/compat_v1.py": {
        "file_sha256": "87b9a94db130b0ccd93aedddc97759eef8eba21f15c92416fbbaedb3067e8d5e",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset(
            (line, "Hex High Entropy String") for line in (988, 1000)
        ),
        "reason": "Frozen compatibility reader's historical integrity fingerprints.",
    },
    "tests/test_evaluation_data.py": {
        "file_sha256": "dee3509cc45b3f8763811169169a42bf4661097cfd0a6557b4e176b2dc80b649",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (233, 234)),
        "reason": "Expected legacy query/audit fingerprints in the reproducibility regression.",
    },
    "tests/test_preserve_v1.py": {
        "file_sha256": "9945159228f530cb3838c52fcd31f1940b1959a9fe288994f251d58bad7ed6a4",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Secret Keyword") for line in (293,)),
        "reason": "Clearly labelled fictional value used only to test exclusion from a preserved snapshot.",
    },
    "tests/test_review_archive.py": {
        "file_sha256": "048edcdfe12b236f3a7ad979936c0d7d239ce4ff1832afdcae00db19f1bafb25",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (616,)),
        "reason": "Fictional integrity-check digest used by an archive regression.",
    },
    "tests/test_review_compatibility.py": {
        "file_sha256": "339d7cb3a6e183dd933395f318bf3edd71b9bba4c391cf60530f72aaf9e04e37",  # pragma: allowlist secret -- reviewed whole-file SHA256 only
        "findings": frozenset((line, "Hex High Entropy String") for line in (585,)),
        "reason": "Fictional integrity-check digest used by a compatibility regression.",
    },
}


class CheckError(ValueError):
    """A failed check with a message safe to print without credential values."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(check: str, **fields: object) -> dict:
    return {"schema_version": PROTOCOL, "check": check, "status": "passed", **fields}


def _contained_path(root: Path, path: Path) -> Path:
    """Reject links and path escapes, including a linked directory ancestor."""
    root = root.absolute()
    path = path.absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CheckError("Publication path escapes the declared root.") from exc
    current = root
    if current.is_symlink():
        raise CheckError("Publication root must not be a symlink.")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CheckError(
                "Publication scope contains a symlink; review it explicitly."
            )
    if not path.resolve().is_relative_to(root.resolve()):
        raise CheckError("Publication path escapes the declared root.")
    return path


def published_files(root: Path = ROOT) -> list[Path]:
    """List the reviewed file scope without traversing data or environments.

    This is an explicit source-tree scan, not a claim about a Git index. Local
    data, model weights, archives, build outputs, caches and .env files are out
    of scope; the placeholder-only .env.example is included. File extensions
    do not exempt secrets such as private keys or extensionless credentials.
    """
    root = Path(root).absolute()
    _contained_path(root, root)
    found = set()
    for name in PUBLICATION_FILES:
        path = _contained_path(root, root / name)
        if path.is_file():
            found.add(path)
    for name in PUBLICATION_ROOTS:
        base = _contained_path(root, root / name)
        if not base.exists():
            continue
        if not base.is_dir():
            raise CheckError("A declared publication directory is not a directory.")
        for current, directories, filenames in os.walk(base, followlinks=False):
            directories[:] = sorted(
                d for d in directories if d not in IGNORED_DIRECTORIES
            )
            for directory in directories:
                _contained_path(root, Path(current) / directory)
            for filename in sorted(filenames):
                if filename == ".env" or filename.startswith(".env."):
                    continue
                path = Path(current) / filename
                if path.suffix not in {".pyc", ".pyo"}:
                    path = _contained_path(root, path)
                    if not path.is_file():
                        raise CheckError(
                            "Publication scope includes a non-regular file."
                        )
                    found.add(path)
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())


def eval_smoke() -> dict:
    """Exercise the current contract on packaged fiction; omit variable timings."""
    from watchlist.entities import load_entities
    from watchlist.evaluate import aggregate, evaluate_queries
    from watchlist.evaluation_data import build_benchmark, fingerprint

    entities = load_entities()
    assignments = {
        entity.entity_id: {"group_id": entity.entity_id, "partition": "test"}
        for entity in entities
    }
    absent = [
        {
            "id": "smoke-absent-001",
            "text": "Fictional Nebula Spoonworks",
            "partition": "test",
        }
    ]
    views, queries, audit = build_benchmark(
        entities, assignments, seed=42, absent=absent
    )
    rows, _ = evaluate_queries(views, queries, repetitions=1, requested_k=10)
    for row in rows:
        row["regression_only"] = True
    return _receipt(
        "eval-smoke",
        benchmark_protocol_version=views.protocol_version,
        regression_only=True,
        fixture="packaged fictional-synthetic-v1",
        query_count=len(queries),
        queries_fingerprint=fingerprint(queries),
        rankings_fingerprint=fingerprint(rows),
        aggregates=aggregate(rows),
        skipped_transformations=len(audit["skipped"]),
        limitations=[
            "Software regression smoke only; not generalization evidence or operational performance."
        ],
    )


def _unique_scanner_object(pairs: list[tuple[str, object]]) -> dict:
    """Do not let duplicate fields discard previously reported findings."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError(
                "Secret scanner returned duplicate fields; raw output is withheld."
            )
        result[key] = value
    return result


def secret_scan(root: Path = ROOT) -> dict:
    """Run the pinned detector without verification and return no secret values."""
    root = Path(root).absolute()
    paths = published_files(root)
    if not paths:
        raise CheckError("Secret scan has no files in its declared publication scope.")
    try:
        detector_version = metadata.version("detect-secrets")
    except metadata.PackageNotFoundError as exc:
        raise CheckError(
            f"Secret scan requires detect-secrets=={DETECTOR_VERSION} in QA_PYTHON; it is not installed."
        ) from exc
    if detector_version != DETECTOR_VERSION:
        raise CheckError(
            f"Secret scan requires the reviewed detect-secrets=={DETECTOR_VERSION} version."
        )
    relative_paths = [path.relative_to(root).as_posix() for path in paths]
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                SCANNER_BOOTSTRAP,
                "scan",
                "--all-files",
                "--no-verify",
                *relative_paths,
            ],
            cwd=root,
            env={**os.environ, **OFFLINE_ENV},
            capture_output=True,
            text=True,
            check=False,
            timeout=SCANNER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise CheckError(
            "Secret scanner exceeded its time limit; raw diagnostics are withheld."
        ) from exc
    if process.returncode:
        raise CheckError(
            "Secret scanner failed; raw diagnostics are withheld to avoid exposing values."
        )
    try:
        payload = json.loads(process.stdout, object_pairs_hook=_unique_scanner_object)
    except (ValueError, TypeError) as exc:
        raise CheckError(
            "Secret scanner returned invalid JSON; raw output is withheld."
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != DETECTOR_VERSION
        or not isinstance(payload.get("results"), dict)
    ):
        raise CheckError(
            "Secret scanner returned an unsupported result contract; raw output is withheld."
        )
    allowed = set(relative_paths)
    findings = []
    reviewed_findings = []
    for filename, entries in payload["results"].items():
        if filename not in allowed or not isinstance(entries, list):
            raise CheckError(
                "Secret scanner reported an undeclared path or malformed findings."
            )
        review = REVIEWED_NON_SECRET_FINDINGS.get(filename)
        reviewed_locations = set()
        if review is not None:
            path = _contained_path(root, root / filename)
            if _digest(path) == review["file_sha256"]:
                reviewed_locations = set(review["findings"])
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or type(entry.get("line_number")) is not int
                or entry["line_number"] < 1
                or not isinstance(entry.get("type"), str)
            ):
                raise CheckError(
                    "Secret scanner returned a malformed finding; raw output is withheld."
                )
            category = (
                entry["type"]
                if entry["type"] in SAFE_FINDING_TYPES
                else "other detector finding"
            )
            finding = {"path": filename, "line": entry["line_number"], "type": category}
            location = (entry["line_number"], entry["type"])
            if location in reviewed_locations:
                # An exception covers one observed finding, never duplicates.
                reviewed_locations.remove(location)
                reviewed_findings.append(
                    {
                        **finding,
                        "file_sha256": review["file_sha256"],
                        "reason": review["reason"],
                    }
                )
            else:
                findings.append(finding)
    return _receipt(
        "secret-scan",
        status="failed" if findings else "passed",
        detector="detect-secrets",
        detector_version=detector_version,
        credential_verification=False,
        python_socket_guard=True,
        file_count=len(paths),
        files=relative_paths,
        detected_finding_count=len(findings) + len(reviewed_findings),
        reviewed_non_secret_count=len(reviewed_findings),
        unresolved_finding_count=len(findings),
        findings=sorted(
            findings, key=lambda item: (item["path"], item["line"], item["type"])
        ),
        reviewed_non_secret_findings=sorted(
            reviewed_findings,
            key=lambda item: (item["path"], item["line"], item["type"]),
        ),
        scope="Explicit source/configuration/documentation files; no Git staging claim.",
    )


def _package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_inventory(root: Path = ROOT) -> dict:
    """Report installed and locked metadata, preserving unknown license status."""
    root = Path(root)
    lock_path = root / "uv.lock"
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    locked = sorted(
        (
            {
                "name": package["name"],
                "version": package["version"],
                "source_kinds": sorted(package.get("source", {})),
            }
            for package in lock.get("package", [])
        ),
        key=lambda item: (_package_name(item["name"]), item["version"]),
    )
    locked_versions: dict[str, set[str]] = {}
    for package in locked:
        locked_versions.setdefault(_package_name(package["name"]), set()).add(
            package["version"]
        )
    installed = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        classifiers = sorted(
            value
            for value in distribution.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        )
        expression = distribution.metadata.get("License-Expression")
        legacy_license = distribution.metadata.get("License")
        if legacy_license and ("\n" in legacy_license or len(legacy_license) > 200):
            legacy_license = "Long license text is present in installed metadata; review the package license files."
        if legacy_license in {None, "", "UNKNOWN", "Unknown"}:
            legacy_license = None
        expected = sorted(locked_versions.get(_package_name(name), set()))
        installed.append(
            {
                "name": name,
                "version": distribution.version,
                "locked_versions": expected,
                "matches_lock_version": distribution.version in expected
                if expected
                else None,
                "license_expression": expression,
                "license_classifiers": classifiers,
                "legacy_license": legacy_license,
                "license_status": "metadata_present_unreviewed"
                if expression or classifiers or legacy_license
                else "unresolved",
            }
        )
    installed.sort(key=lambda item: (_package_name(item["name"]), item["version"]))
    return _receipt(
        "inventory",
        python_version=sys.version.split()[0],
        lock_sha256=_digest(lock_path),
        locked_packages=locked,
        installed_packages=installed,
        limitations=[
            "Installed metadata is not proof of license compatibility or permission to redistribute.",
            "Lock entries may target other platforms/extras; uninstalled packages have no local license review.",
            "Version comparison does not establish wheel hashes or complete environment reproducibility.",
        ],
    )


def _deny_network(event: str, args: tuple) -> None:
    """Reject Python socket operations without logging endpoint or payload data."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise CheckError(f"Network access forbidden during local checks ({event}).")


@contextmanager
def _temporary_environment(updates: dict[str, str]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def local_model_tests(root: Path = ROOT) -> dict:
    """Opt in to existing local weights with temporary configs, stores and caches."""
    root = Path(root).resolve()
    configs = {}
    for name in ("embeddings", "reranking"):
        path = root / "eval" / "configs" / f"{name}.json"
        if not path.is_file():
            raise CheckError(
                "Local-model tests require both existing model configuration files."
            )
        config = json.loads(path.read_text(encoding="utf-8"))
        model_path = Path(config["model"]["model_path"])
        if not model_path.is_absolute():
            model_path = root / model_path
        if not model_path.is_dir():
            raise CheckError(
                "Local-model tests require already-acquired model files; no download was attempted."
            )
        config["model"]["model_path"] = str(model_path.resolve())
        configs[name] = (config, _digest(path))
    test_paths = [
        root / "tests" / "integration" / name
        for name in (
            "test_embedding_model.py",
            "test_reranker_model.py",
            "test_agent_e5.py",
        )
    ]
    if not all(path.is_file() for path in test_paths):
        raise CheckError("Local-model test files are missing.")
    try:
        import pytest
    except ImportError as exc:
        raise CheckError(
            "Local-model tests require pytest and the approved agent/embeddings dependencies."
        ) from exc
    attempts = []
    guard = {"active": False}

    class Outcomes:
        """A skipped optional dependency must not look like a model-test pass."""

        def __init__(self) -> None:
            self.passed = 0
            self.failed = 0
            self.skipped = 0

        def pytest_runtest_logreport(self, report: object) -> None:
            if report.when == "call" and report.passed:
                self.passed += 1
            if report.failed:
                self.failed += 1
            if report.skipped:
                self.skipped += 1

        def pytest_collectreport(self, report: object) -> None:
            if report.skipped:
                self.skipped += 1
            if report.failed:
                self.failed += 1

    outcomes = Outcomes()

    def guarded_network(event: str, args: tuple) -> None:
        if guard["active"] and event in {
            "socket.connect",
            "socket.getaddrinfo",
            "socket.sendto",
        }:
            attempts.append(event)
            _deny_network(event, args)

    # Python audit hooks cannot be removed; disable this one when the check ends.
    sys.addaudithook(guarded_network)
    with TemporaryDirectory(prefix="watchlist-local-model-check-") as temporary:
        scratch = Path(temporary).resolve()
        (scratch / "eval" / "configs").mkdir(parents=True)
        for name, (config, _) in configs.items():
            if "cache_path" in config:
                config["cache_path"] = str(scratch / "alias-cache")
            (scratch / "eval" / "configs" / f"{name}.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
        updates = {
            **OFFLINE_ENV,
            "RUN_EMBEDDING_INTEGRATION": "1",
            "RUN_RERANKER_INTEGRATION": "1",
            "RUN_AGENT_E5_INTEGRATION": "1",
            "HF_HOME": str(scratch / "huggingface"),
            "XDG_CACHE_HOME": str(scratch / "cache"),
            "TORCH_HOME": str(scratch / "torch"),
        }
        original_directory = Path.cwd()
        try:
            guard["active"] = True
            with _temporary_environment(updates):
                os.chdir(scratch)
                exit_code = pytest.main(
                    [
                        "-q",
                        "-m",
                        "integration",
                        "-p",
                        "no:cacheprovider",
                        "--tb=short",
                        "--basetemp",
                        str(scratch / "pytest"),
                        *map(str, test_paths),
                    ],
                    plugins=[outcomes],
                )
        finally:
            guard["active"] = False
            os.chdir(original_directory)
    unchanged = all(
        _digest(root / "eval" / "configs" / f"{name}.json") == digest
        for name, (_, digest) in configs.items()
    )
    return _receipt(
        "local-model-tests",
        status="passed"
        if (
            exit_code == 0
            and outcomes.passed == 3
            and not outcomes.failed
            and not outcomes.skipped
            and not attempts
            and unchanged
        )
        else "failed",
        exit_code=int(exit_code),
        network_attempts=attempts,
        temporary_caches=True,
        test_outcomes={
            "passed": outcomes.passed,
            "failed": outcomes.failed,
            "skipped": outcomes.skipped,
        },
        original_configs_unchanged=unchanged,
        limitations=[
            "Python socket auditing is not an operating-system network sandbox."
        ],
    )


def _check_output(output: Path | None) -> None:
    if output is not None and (output.exists() or output.is_symlink()):
        raise CheckError(
            "Output already exists; select a new JSON file to preserve evidence."
        )


def write_report(result: dict, output: Path | None) -> None:
    """Save a complete fresh receipt, or print a compact result without a path."""
    if output is None:
        compact = {
            key: value
            for key, value in result.items()
            if key
            not in {
                "aggregates",
                "locked_packages",
                "installed_packages",
                "files",
                "reviewed_non_secret_findings",
            }
        }
        if "locked_packages" in result:
            compact["locked_package_count"] = len(result["locked_packages"])
        if "installed_packages" in result:
            compact["installed_package_count"] = len(result["installed_packages"])
            compact["unresolved_license_count"] = sum(
                package["license_status"] == "unresolved"
                for package in result["installed_packages"]
            )
        print(
            json.dumps(
                compact, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
            )
        )
        return
    text = (
        json.dumps(
            result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        )
        + "\n"
    )
    _check_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("eval-smoke", "secret-scan", "inventory", "local-model-tests"):
        command = commands.add_parser(name)
        command.add_argument(
            "--output", type=Path, help="new JSON receipt; existing files are refused"
        )
    args = parser.parse_args(argv)
    actions = {
        "eval-smoke": eval_smoke,
        "secret-scan": secret_scan,
        "inventory": dependency_inventory,
        "local-model-tests": local_model_tests,
    }
    try:
        _check_output(args.output)
        with _temporary_environment(OFFLINE_ENV):
            result = actions[args.command]()
        write_report(result, args.output)
    except (CheckError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps({"check": args.command, "status": "failed", "error": str(exc)}),
            file=sys.stderr,
        )
        return 1
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
