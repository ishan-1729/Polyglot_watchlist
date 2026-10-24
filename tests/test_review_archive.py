"""Historical readers are exercised only against complete fictional archives."""

from dataclasses import dataclass
import copy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pytest

from agent_support import FakeRetriever, form
from watchlist.agent.state import workflow_hash
from watchlist.agent.storage import ReviewService
from watchlist.review.archive import recipe_contract


REPOSITORY = Path(__file__).resolve().parents[1]
QUERY_MARKERS = {
    "completed": "Fictional completed Luma Vesper private query",
    "pending": "Fictional pending Mira Solace private query",
    "interrupted": "Fictional interrupted Orin Vale private query",
}
REASON_MARKER = "Fictional review note reserved for explicit inspection."


@pytest.fixture(scope="module")
def reader():
    return importlib.import_module("watchlist.review.archive")


@pytest.fixture(scope="module")
def preservation_builder():
    spec = importlib.util.spec_from_file_location(
        "preserve_v1_review_archive_fixture", REPOSITORY / "scripts" / "preserve_v1.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class FictionalArchive:
    project: Path
    archive: Path
    cases: dict


@pytest.fixture(scope="module")
def base_archive(tmp_path_factory, preservation_builder):
    """Build real v1 records, including a process killed after submission commit."""
    root = tmp_path_factory.mktemp("fictional-review-archive")
    project = root / "project"
    project.mkdir()
    shutil.copytree(REPOSITORY / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(REPOSITORY / "config", project / "config")
    shutil.copytree(REPOSITORY / "eval" / "configs", project / "eval" / "configs")
    for name in ("pyproject.toml", "uv.lock", ".gitignore"):
        shutil.copy2(REPOSITORY / name, project / name)
    # Package initialization is not part of v1's workflow fingerprint. A reader
    # importing archived Python would fail here instead of inspecting inert data.
    (project / "src" / "watchlist" / "__init__.py").write_text(
        "raise RuntimeError('Archived Python must never execute during inspection')\n"
    )
    workspace = project / "data" / "review"
    cases = {}
    with ReviewService(workspace, FakeRetriever()) as service:
        pending = service.start(QUERY_MARKERS["completed"], {"fixture": "archive-reader"})
        review_form = {**form(pending), "reason": REASON_MARKER}
        cases["completed"] = service.review(pending["thread_id"], review_form)
        cases["pending"] = service.start(QUERY_MARKERS["pending"], {"fixture": "archive-reader"})
        cases["interrupted"] = service.start(QUERY_MARKERS["interrupted"], {"fixture": "archive-reader"})
    crash_after_submission = """
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from agent_support import FakeRetriever
from watchlist.agent.storage import ReviewService
def stop(stage):
    if stage == 'after_submission':
        os._exit(77)
with ReviewService(Path(sys.argv[2]), FakeRetriever(fail=True), stop) as service:
    service.review(sys.argv[3], json.loads(sys.argv[4]))
"""
    interrupted = cases["interrupted"]
    accepted_form = {**form(interrupted), "reason": REASON_MARKER}
    result = subprocess.run(
        [sys.executable, "-B", "-c", crash_after_submission, str(REPOSITORY / "tests"), str(workspace),
         interrupted["thread_id"], json.dumps(accepted_form)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 77, result.stderr
    archive = project / "data" / "review-archives" / "reader-fixture"
    preservation_builder.apply_archive(project, workspace, archive, include_runtime=False)
    return FictionalArchive(project, archive, cases)


@pytest.fixture
def fictional_archive(base_archive, tmp_path):
    archive = tmp_path / "archive"
    shutil.copytree(base_archive.archive, archive)
    return FictionalArchive(base_archive.project, archive, base_archive.cases)


def tree_snapshot(root):
    """Ignore access time while checking bytes, membership, modes, and identity."""
    snapshot = {}
    for path in [root, *sorted(root.rglob("*"))]:
        metadata = path.lstat()
        value = (stat.S_IFMT(metadata.st_mode), stat.S_IMODE(metadata.st_mode), metadata.st_ino,
                 metadata.st_mtime_ns, metadata.st_ctime_ns)
        if stat.S_ISREG(metadata.st_mode):
            value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
        elif stat.S_ISLNK(metadata.st_mode):
            value += (os.readlink(path),)
        snapshot[str(path.relative_to(root))] = value
    return snapshot


def rewrite_manifest(archive, change):
    """Re-sign changed metadata so its semantic checks must reject the input."""
    path = archive / "manifest.json"
    manifest = json.loads(path.read_text())
    change(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    marker = archive / "COMPLETE.json"
    complete = json.loads(marker.read_text())
    complete["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    marker.write_text(json.dumps(complete, sort_keys=True) + "\n")


def assert_rejected_without_mutation(reader, fixture):
    before = tree_snapshot(fixture.archive)
    with pytest.raises(reader.ArchiveError):
        reader.verify_archive(fixture.archive)
    with pytest.raises(reader.ArchiveError):
        reader.inspect_case(fixture.archive, fixture.cases["completed"]["audit_id"])
    assert tree_snapshot(fixture.archive) == before


def test_verify_returns_only_case_catalogue_and_integrity_summary(reader, fictional_archive):
    before = tree_snapshot(fictional_archive.archive)
    result = reader.verify_archive(fictional_archive.archive)
    assert result["status"] == "verified"
    assert result["archive_format"] == "polyglot-preservation-v1"
    assert result["execution_allowed"] is False
    verification = result["verification"]
    assert verification["scope"] == "historical_integrity_and_v1_protocol"
    assert verification["case_count"] == 3
    assert verification["databases_verified"] == 2
    assert verification["files_verified"] > 2
    marker = json.loads((fictional_archive.archive / "COMPLETE.json").read_text())
    assert verification["archive_manifest_sha256"] == marker["manifest_sha256"]
    cases = {item["case_id"]: item for item in result["cases"]}
    assert set(cases) == {case["audit_id"] for case in fictional_archive.cases.values()}
    for original in fictional_archive.cases.values():
        row = cases[original["audit_id"]]
        assert row["thread_id"] == original["thread_id"]
        assert row["compatibility"]["stored_workflow_sha256"] == original["state"]["workflow_sha256"]
        assert row["compatibility"]["execution_allowed"] is False
        assert row["annotation_origin"] == "unknown"
        assert isinstance(row["state"], str) and row["state"]
    encoded = json.dumps(result)
    for private_text in [*QUERY_MARKERS.values(), REASON_MARKER]:
        assert private_text not in encoded
    assert tree_snapshot(fictional_archive.archive) == before


@pytest.mark.parametrize("kind", ["completed", "pending", "interrupted"])
def test_inspect_reads_completed_pending_and_interrupted_evidence(reader, fictional_archive, kind):
    before = tree_snapshot(fictional_archive.archive)
    original = fictional_archive.cases[kind]
    result = reader.inspect_case(fictional_archive.archive, original["audit_id"])
    assert result["status"] == "verified"
    assert result["execution_allowed"] is False
    case = result["case"]
    assert case["case_id"] == original["audit_id"]
    assert case["thread_id"] == original["thread_id"]
    assert case["initial"]["query"] == QUERY_MARKERS[kind]
    assert case["packet"]["query"] == QUERY_MARKERS[kind]
    assert case["latest_state"]["review_status"] == ("recorded" if kind == "completed" else "pending")
    assert case["latest_state"]["audit_status"] == ("committed" if kind == "completed" else "pending")
    assert case["compatibility"]["execution_allowed"] is False
    assert case["checkpoint"] is not None
    if kind == "pending":
        assert case["submission"] is None
    else:
        assert case["submission"]["reason"] == REASON_MARKER
    if kind == "interrupted":
        assert case["latest_state"]["reviewer_decision"] is None
    assert tree_snapshot(fictional_archive.archive) == before


def test_unknown_case_id_is_rejected_without_mutation(reader, fictional_archive):
    before = tree_snapshot(fictional_archive.archive)
    with pytest.raises(reader.ArchiveError):
        reader.inspect_case(fictional_archive.archive, str(uuid4()))
    assert tree_snapshot(fictional_archive.archive) == before


@pytest.mark.parametrize("kind", ["completed", "pending", "interrupted"])
def test_different_current_workflow_does_not_block_historical_inspection(reader, fictional_archive, monkeypatch, kind):
    original = fictional_archive.cases[kind]
    changed_hash = "0" * 64
    assert original["state"]["workflow_sha256"] != changed_hash
    monkeypatch.setattr(reader, "_current_execution_manifest", lambda: {
        "status": "available", "sha256": changed_hash, "file_count": 1, "packages": {},
    })
    before = tree_snapshot(fictional_archive.archive)
    result = reader.inspect_case(fictional_archive.archive, original["audit_id"])
    case = result["case"]
    assert result["status"] == "verified"
    assert case["initial"]["query"] == QUERY_MARKERS[kind]
    compatibility = case["compatibility"]
    assert compatibility["stored_workflow_sha256"] == original["state"]["workflow_sha256"]
    assert compatibility["current_workflow_sha256"] == changed_hash
    assert compatibility["current_execution_match"] is False
    assert compatibility["execution_allowed"] is False
    assert result["execution_allowed"] is False
    catalogue = reader.verify_archive(fictional_archive.archive)
    assert all(case["compatibility"]["current_execution_match"] is False for case in catalogue["cases"])
    assert tree_snapshot(fictional_archive.archive) == before


def test_unavailable_current_workflow_is_reported_separately_from_archive_integrity(reader, fictional_archive, monkeypatch):
    monkeypatch.setattr(reader, "_current_execution_manifest", lambda: {
        "status": "unavailable", "reason": "Fictional current implementation is unavailable",
    })
    result = reader.inspect_case(fictional_archive.archive, fictional_archive.cases["pending"]["audit_id"])
    assert result["status"] == "verified"
    compatibility = result["case"]["compatibility"]
    assert compatibility["current_workflow_sha256"] is None
    assert compatibility["current_execution_match"] is None
    assert compatibility["execution_allowed"] is False


@pytest.mark.parametrize("damage", ["missing_complete", "marker_schema", "manifest_schema", "receipt_schema"])
def test_missing_completion_or_unknown_archive_contract_is_rejected(reader, fictional_archive, damage):
    archive = fictional_archive.archive
    marker_path = archive / "COMPLETE.json"
    if damage == "missing_complete":
        marker_path.unlink()
    elif damage == "marker_schema":
        marker = json.loads(marker_path.read_text())
        marker["schema"] = "unknown-preservation-format-v99"
        marker_path.write_text(json.dumps(marker))
    elif damage == "manifest_schema":
        rewrite_manifest(archive, lambda manifest: manifest.update(schema="unknown-preservation-format-v99"))
    else:
        receipt_path = archive / "verification.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["verifier"] = "unknown-logical-verifier-v99"
        receipt_path.write_text(json.dumps(receipt))
        marker = json.loads(marker_path.read_text())
        marker["verification_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        marker_path.write_text(json.dumps(marker))
    assert_rejected_without_mutation(reader, fictional_archive)


@pytest.mark.parametrize("damage", ["changed", "missing", "extra"])
def test_tampered_missing_or_extra_archive_members_are_rejected(reader, fictional_archive, damage):
    member = fictional_archive.archive / "payload" / "project" / "pyproject.toml"
    if damage == "changed":
        member.write_bytes(member.read_bytes() + b"\n# fictional tampering\n")
    elif damage == "missing":
        member.unlink()
    else:
        extra = fictional_archive.archive / "unrecorded.txt"
        extra.write_text("fictional unrecorded member")
        extra.chmod(0o600)
    assert_rejected_without_mutation(reader, fictional_archive)


@pytest.mark.parametrize("category", ["payload/project", "databases"])
def test_resigned_manifest_requires_both_raw_and_normalized_database_members(reader, fictional_archive, category):
    relative = category + "/data/review/cases.sqlite"
    (fictional_archive.archive / relative).unlink()

    def remove_member(manifest):
        manifest["entries"] = [entry for entry in manifest["entries"] if entry["path"] != relative]

    rewrite_manifest(fictional_archive.archive, remove_member)
    assert_rejected_without_mutation(reader, fictional_archive)


@pytest.mark.parametrize("unsafe", ["../escape", "/fictional/absolute/escape", "payload/project/../../escape"])
def test_resigned_manifest_traversal_is_rejected(reader, fictional_archive, unsafe):
    rewrite_manifest(fictional_archive.archive, lambda manifest: manifest["entries"][0].update(path=unsafe))
    assert_rejected_without_mutation(reader, fictional_archive)


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_archive_member_links_are_rejected(reader, fictional_archive, tmp_path, kind):
    member = fictional_archive.archive / "databases" / "data" / "review" / "cases.sqlite"
    outside = tmp_path / "outside.sqlite"
    shutil.copy2(member, outside)
    outside_before = outside.read_bytes()
    member.unlink()
    if kind == "symlink":
        member.symlink_to(outside)
    else:
        os.link(outside, member)
    assert_rejected_without_mutation(reader, fictional_archive)
    assert outside.read_bytes() == outside_before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_normalized_database_sidecars_are_rejected_without_recovery(reader, fictional_archive, suffix):
    sidecar = fictional_archive.archive / "databases" / "data" / "review" / ("cases.sqlite" + suffix)
    sidecar.write_bytes(b"fictional sidecar must never be recovered")
    sidecar.chmod(0o600)
    assert_rejected_without_mutation(reader, fictional_archive)


AUDITED_READER = r"""
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, unquote, urlsplit

archive = Path(sys.argv[1]).resolve()
case_id = sys.argv[2]
original_project = Path(sys.argv[3]).resolve()
denied = []
connections = []
forbidden = ('watchlist.agent', 'langgraph', 'langchain', 'torch', 'transformers', 'sentence_transformers')
mutation_events = {'os.mkdir', 'os.chmod', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink',
                   'os.truncate', 'os.utime', 'tempfile.mkstemp', 'tempfile.mkdtemp', 'subprocess.Popen',
                   'os.system', 'socket.connect', 'socket.bind', 'socket.getaddrinfo'}

def reject(event):
    denied.append(event)
    raise AssertionError('Read-only archive reader attempted ' + event)

def audit(event, args):
    if event in mutation_events:
        reject(event)
    if event == 'open':
        path, mode, flags = args
        if isinstance(path, (str, bytes, os.PathLike)) and Path(os.fsdecode(path)).absolute().is_relative_to(original_project):
            reject('original-project-read')
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            reject('write-open')
    if event == 'import' and any(args[0] == prefix or args[0].startswith(prefix + '.') for prefix in forbidden):
        reject('forbidden-import:' + args[0])
    if event == 'sqlite3.connect':
        value = os.fspath(args[0])
        parsed = urlsplit(value)
        options = parse_qs(parsed.query)
        path = Path(unquote(parsed.path)).resolve()
        if (parsed.scheme != 'file' or options.get('mode') != ['ro'] or options.get('immutable') != ['1']
                or not path.is_relative_to(archive / 'databases')):
            reject('non-immutable-or-original-sqlite')
        connections.append(str(path.relative_to(archive)))

sys.addaudithook(audit)
from watchlist.review.archive import inspect_case, verify_archive
verified = verify_archive(archive)
inspected = inspect_case(archive, case_id)
loaded = sorted(name for name in sys.modules if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden))
print(json.dumps({'verified': verified['status'], 'case_id': inspected['case']['case_id'],
                  'denied': denied, 'connections': connections, 'forbidden_loaded': loaded}))
"""


def test_clean_subprocess_reader_performs_no_writes_setup_or_heavy_imports(fictional_archive):
    before = tree_snapshot(fictional_archive.archive)
    original_before = tree_snapshot(fictional_archive.project / "data" / "review")
    case_id = fictional_archive.cases["interrupted"]["audit_id"]
    result = subprocess.run(
        [sys.executable, "-B", "-c", AUDITED_READER, str(fictional_archive.archive), case_id,
         str(fictional_archive.project)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["verified"] == "verified"
    assert receipt["case_id"] == case_id
    assert receipt["denied"] == []
    assert receipt["forbidden_loaded"] == []
    assert set(receipt["connections"]) == {"databases/data/review/cases.sqlite", "databases/data/review/checkpoints.sqlite"}
    assert tree_snapshot(fictional_archive.archive) == before
    assert tree_snapshot(fictional_archive.project / "data" / "review") == original_before


@pytest.mark.parametrize("operation", ["verify", "inspect"])
def test_archive_cli_reads_complete_fictional_archive(fictional_archive, operation):
    before = tree_snapshot(fictional_archive.archive)
    arguments = [sys.executable, "-B", "-m", "watchlist.review", "archive", operation,
                 "--archive", str(fictional_archive.archive)]
    if operation == "inspect":
        arguments.extend(["--case-id", fictional_archive.cases["completed"]["audit_id"]])
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "verified"
    assert output["execution_allowed"] is False
    if operation == "verify":
        assert QUERY_MARKERS["completed"] not in result.stdout
        assert REASON_MARKER not in result.stdout
    else:
        assert output["case"]["initial"]["query"] == QUERY_MARKERS["completed"]
    assert tree_snapshot(fictional_archive.archive) == before


def test_archive_cli_unknown_case_is_a_concise_failure(fictional_archive):
    before = tree_snapshot(fictional_archive.archive)
    result = subprocess.run(
        [sys.executable, "-B", "-m", "watchlist.review", "archive", "inspect", "--archive",
         str(fictional_archive.archive), "--case-id", str(uuid4())],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert isinstance(json.loads(result.stderr)["error"], str)
    assert "Traceback" not in result.stderr
    assert tree_snapshot(fictional_archive.archive) == before


@dataclass(frozen=True)
class FictionalFingerprint:
    root: Path
    manifest: dict
    files: dict
    packages: dict


def add_metadata(fixture, relative, content):
    path = fixture.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    fixture.manifest["entries"].append({"kind": "file", "path": relative})
    return path


@pytest.fixture
def captured_fingerprint(tmp_path):
    """Minimal inert sources and installed-distribution headers, without a runtime."""
    root = tmp_path / "captured-fingerprint"
    source_prefix = "payload/project/src/watchlist/"
    contents = {
        "agent/state.py": b"# fictional historical state implementation\n",
        "agent/schema.sql": b"-- fictional historical schema\n",
        "normalize.py": b"# fictional normalize\n",
        "embeddings.py": b"# fictional embeddings\n",
        "matching_embeddings.py": b"# fictional matching\n",
        "entities.py": b"# fictional entities\n",
        "database.py": b"# fictional database\n",
    }
    manifest = {"entries": [], "runtime": {
        "included": True, "site_packages_relative": ".venv/lib/python3.14/site-packages",
    }}
    files = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    packages = {"langgraph": "0.0.11", "langgraph-checkpoint": "0.0.12",
                "langgraph-checkpoint-sqlite": "0.0.13", "ormsgpack": "0.0.14"}
    fixture = FictionalFingerprint(root, manifest, files, packages)
    for name, content in contents.items():
        add_metadata(fixture, source_prefix + name, content)
    # Neither unrelated files nor nested Python should alter the v1 algorithm.
    add_metadata(fixture, source_prefix + "agent/notes.txt", b"not execution source\n")
    add_metadata(fixture, source_prefix + "agent/vendor/ignored.py", b"not top-level agent source\n")
    for name, version in packages.items():
        folder = name.replace("-", "_") + "-" + version + ".dist-info"
        relative = "payload/environment/lib/python3.14/site-packages/" + folder + "/METADATA"
        add_metadata(fixture, relative, f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode())
    return fixture


def test_current_execution_fingerprint_exactly_matches_existing_workflow_hash(reader):
    current = reader._current_execution_manifest()
    assert current["status"] == "available"
    assert current["sha256"] == workflow_hash()
    assert current["file_count"] > 5


def test_captured_execution_fingerprint_uses_only_captured_sources_and_versions(reader, captured_fingerprint, monkeypatch):
    def reject_live_versions(_name):
        raise AssertionError("Historical fingerprint must not substitute current package versions")

    monkeypatch.setattr(reader.distribution_metadata, "version", reject_live_versions)
    fixture = captured_fingerprint
    before = tree_snapshot(fixture.root)
    result = reader._captured_execution_manifest(fixture.root, fixture.manifest)
    canonical = json.dumps({"files": fixture.files, "packages": fixture.packages}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert result["status"] == "verified"
    assert result["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert result["packages"] == fixture.packages
    assert result["source_files"] == {"status": "verified", "count": 7}
    assert tree_snapshot(fixture.root) == before


@pytest.mark.parametrize("damage", [
    "duplicate_distribution", "duplicate_name", "duplicate_version", "missing_name",
    "missing_version", "empty_version", "mismatched_name", "mismatched_folder",
])
def test_captured_execution_rejects_duplicate_or_malformed_relevant_metadata(reader, captured_fingerprint, damage):
    fixture = captured_fingerprint
    relative = "payload/environment/lib/python3.14/site-packages/langgraph-0.0.11.dist-info/METADATA"
    if damage == "duplicate_distribution":
        add_metadata(fixture, "payload/environment/lib/python3.14/site-packages/another-0.0.1.dist-info/METADATA",
                     b"Name: langgraph\nVersion: 9.9.9\n\n")
    elif damage == "mismatched_folder":
        unrelated = "payload/environment/lib/python3.14/site-packages/unrelated_0-1.dist-info/METADATA"
        (fixture.root / unrelated).parent.mkdir()
        (fixture.root / relative).rename(fixture.root / unrelated)
        next(entry for entry in fixture.manifest["entries"] if entry["path"] == relative)["path"] = unrelated
    else:
        content = {
            "duplicate_name": b"Name: langgraph\nName: langgraph\nVersion: 0.0.11\n\n",
            "duplicate_version": b"Name: langgraph\nVersion: 0.0.11\nVersion: 9.9.9\n\n",
            "missing_name": b"Version: 0.0.11\n\n",
            "missing_version": b"Name: langgraph\n\n",
            "empty_version": b"Name: langgraph\nVersion: \n\n",
            "mismatched_name": b"Name: fictional-unrelated-package\nVersion: 0.0.11\n\n",
        }[damage]
        (fixture.root / relative).write_bytes(content)
    with pytest.raises(reader.ArchiveError):
        reader._captured_execution_manifest(fixture.root, fixture.manifest)


def test_nested_vendor_metadata_cannot_substitute_for_captured_installed_distribution(reader, captured_fingerprint):
    fixture = captured_fingerprint
    relative = "payload/environment/lib/python3.14/site-packages/langgraph-0.0.11.dist-info/METADATA"
    (fixture.root / relative).unlink()
    fixture.manifest["entries"] = [entry for entry in fixture.manifest["entries"] if entry["path"] != relative]
    add_metadata(fixture, "payload/environment/lib/python3.14/site-packages/vendor/langgraph-9.9.9.dist-info/METADATA",
                 b"Name: langgraph\nVersion: 9.9.9\n\n")
    with pytest.raises(reader.ArchiveError, match="required execution package metadata"):
        reader._captured_execution_manifest(fixture.root, fixture.manifest)


def test_nested_vendor_metadata_does_not_override_captured_installed_version(reader, captured_fingerprint):
    fixture = captured_fingerprint
    add_metadata(fixture, "payload/environment/lib/python3.14/site-packages/vendor/langgraph-9.9.9.dist-info/METADATA",
                 b"Name: langgraph\nVersion: 9.9.9\n\n")
    result = reader._captured_execution_manifest(fixture.root, fixture.manifest)
    assert result["status"] == "verified"
    assert result["packages"]["langgraph"] == "0.0.11"


def test_excluded_runtime_is_not_reported_as_a_captured_execution_environment(reader, captured_fingerprint):
    fixture = captured_fingerprint
    fixture.manifest["runtime"] = {"included": False}
    result = reader._captured_execution_manifest(fixture.root, fixture.manifest)
    assert result["status"] == "not_captured"
    assert result["source_files"] == {"status": "verified", "count": 7}
    assert "sha256" not in result
    assert "packages" not in result


def test_disk_inventory_propagates_directory_walk_permission_error(reader, tmp_path, monkeypatch):
    denial = PermissionError(13, "Fictional archive directory cannot be read")

    def failed_walk(_root, *, followlinks=False, onerror=None):
        if onerror is not None:
            onerror(denial)
        return iter(())

    monkeypatch.setattr(reader.os, "walk", failed_walk)
    with pytest.raises(PermissionError) as captured:
        reader._all_disk_members(tmp_path)
    assert captured.value is denial




def _recipe_digest(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class TestRecipeContract(unittest.TestCase):
    """Verify evidence classification and rejection without an executable model."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="polyglot-recipe-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "project"
        self.project.mkdir()
        self.entries: list[dict] = []
        self.source = "src/watchlist/data/synthetic_entities.json"
        self.model_root = "data/models/e5-small"
        self.receipt_path = self.model_root + "/acquisition.json"
        source = [{"entity_id": "fictional-1", "name": "Synthetic Example",
                   "entity_type": "person", "synthetic": True,
                   "source": "fictional-synthetic-v1",
                   "aliases": [{"alias_id": "fictional-1-a", "name": "Synthetic Example"}]}]
        self._capture_json(self.source, source)
        members = {}
        for name in ("1_Pooling/config.json", "README.md", "config.json",
                     "model.safetensors", "modules.json", "sentence_bert_config.json",
                     "sentencepiece.bpe.model", "special_tokens_map.json",
                     "tokenizer.json", "tokenizer_config.json"):
            content = ("fictional bytes for " + name).encode("utf-8")
            self._capture(self.model_root + "/" + name, content)
            members[name] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        self.receipt = {"model_id": "intfloat/multilingual-e5-small",
                        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3", "files": members}
        self._capture_json(self.receipt_path, self.receipt)
        self.recipe = {
            "config": {"model": {"model_id": self.receipt["model_id"],
                                 "revision": self.receipt["revision"],
                                 "model_path": self.model_root, "batch_size": 1},
                       "cache_path": "data/cache/fictional"},
            "db": None,
            "reference_sha256": _recipe_digest([dict(source[0], provenance=None)]),
            "model_receipt_sha256": _recipe_digest(self.receipt),
            "packages": {name: "1.0" for name in
                         ("numpy", "torch", "transformers", "sentence-transformers", "tokenizers")},
        }

    def _capture(self, relative: str, content: bytes) -> None:
        destination = self.project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        path = "payload/project/" + relative
        self.entries = [entry for entry in self.entries if entry["path"] != path]
        self.entries.append({"category": "project", "kind": "file", "path": path,
                             "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})

    def _capture_json(self, relative: str, content: object) -> None:
        self._capture(relative, (json.dumps(content, indent=2) + "\n").encode("utf-8"))

    def _check(self, *, recipe=None, entries=None, retrieval=None) -> dict:
        return recipe_contract(self.recipe if recipe is None else recipe, self.project,
                               "/recorded/project", self.entries if entries is None else entries,
                               retrieval=retrieval)

    def _retrieval(self) -> dict:
        return {"reference_sha256": self.recipe["reference_sha256"],
                "encoder": {"config": copy.deepcopy(self.recipe["config"]["model"]),
                            "packages": copy.deepcopy(self.recipe["packages"]),
                            "files": copy.deepcopy(self.receipt["files"])}}

    def test_complete_fictional_inputs_and_saved_retrieval_are_verified(self) -> None:
        result = self._check(retrieval=self._retrieval())
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["source_snapshot"]["status"], "verified")
        self.assertEqual(result["model_receipt"]["digest_kind"], "canonical_json_sha256")
        self.assertEqual(result["model_files"]["verified_files"], 10)
        self.assertEqual(result["model_files"]["weights_status"], "verified")
        self.assertEqual(result["retrieval_packages"]["status"], "recorded_only")
        self.assertIs(result["resume_authorized"], False)

    def test_opaque_fixture_needs_no_source_model_or_runtime(self) -> None:
        with patch.object(os, "open", side_effect=AssertionError("unexpected file read")):
            result = self._check(recipe={"fixture": "preservation-only"}, entries=[],
                                 retrieval={"model": "MOCK"})
        self.assertEqual(result["status"], "recorded_only")
        self.assertIs(result["resume_authorized"], False)

    def test_omitted_inventory_is_not_captured_and_never_reads_original_paths(self) -> None:
        with patch.object(os, "open", side_effect=AssertionError("unexpected file read")):
            result = self._check(entries=[])
        for key in ("source_snapshot", "model_receipt", "model_files"):
            self.assertEqual(result[key]["status"], "not_captured")

    def test_receipt_and_weight_capture_statuses_are_separate(self) -> None:
        entries = [e for e in self.entries if not e["path"].endswith("/model.safetensors")]
        result = self._check(entries=entries)
        self.assertEqual(result["model_receipt"]["status"], "verified")
        self.assertEqual(result["model_files"]["verified_files"], 9)
        self.assertEqual(result["model_files"]["weights_status"], "not_captured")
        self.assertEqual(result["status"], "not_captured")

    def test_omitted_source_is_not_a_bad_reference_digest(self) -> None:
        entries = [e for e in self.entries if e["path"] != "payload/project/" + self.source]
        result = self._check(entries=entries)
        self.assertEqual(result["source_snapshot"]["status"], "not_captured")
        self.assertEqual(result["model_files"]["status"], "verified")

    def test_omitted_receipt_does_not_claim_weights_are_verified(self) -> None:
        entries = [e for e in self.entries if e["path"] != "payload/project/" + self.receipt_path]
        result = self._check(entries=entries, retrieval=self._retrieval())
        self.assertEqual(result["model_receipt"]["status"], "not_captured")
        self.assertEqual(result["model_files"]["weights_status"], "not_captured")

    def test_source_digest_mismatch_is_an_error(self) -> None:
        self.recipe["reference_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fictional reference differs"):
            self._check()

    def test_receipt_digest_uses_canonical_json_not_raw_file_bytes(self) -> None:
        raw_digest = hashlib.sha256((self.project / self.receipt_path).read_bytes()).hexdigest()
        self.assertNotEqual(raw_digest, self.recipe["model_receipt_sha256"])
        self.recipe["model_receipt_sha256"] = raw_digest
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self._check()

    def test_unsupported_model_cannot_hide_a_present_receipt_mismatch(self) -> None:
        self.recipe["config"]["model"]["model_id"] = "fictional/unsupported"
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self._check()

    def test_matching_unsupported_profile_records_receipt_but_does_not_verify_weights(self) -> None:
        self.recipe["config"]["model"]["model_id"] = "fictional/unsupported"
        self.receipt["model_id"] = "fictional/unsupported"
        self._capture_json(self.receipt_path, self.receipt)
        self.recipe["model_receipt_sha256"] = _recipe_digest(self.receipt)
        (self.project / self.model_root / "model.safetensors").unlink()
        result = self._check()
        self.assertEqual(result["model_receipt"]["status"], "verified")
        self.assertEqual(result["model_files"]["weights_status"], "not_verified")
        self.assertEqual(result["status"], "recorded_only")

    def test_saved_retrieval_must_match_config_packages_source_and_receipt_files(self) -> None:
        retrievals = []
        for field in ("config", "packages", "reference", "files"):
            retrieval = self._retrieval()
            if field == "config":
                retrieval["encoder"]["config"]["batch_size"] = True
            elif field == "packages":
                retrieval["encoder"]["packages"]["numpy"] = "2.0"
            elif field == "reference":
                retrieval["reference_sha256"] = "0" * 64
            else:
                retrieval["encoder"]["files"]["model.safetensors"]["sha256"] = "0" * 64
            retrievals.append((field, retrieval))
        for field, retrieval in retrievals:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "differs"):
                self._check(retrieval=retrieval)

    def test_present_file_inventory_must_match_acquisition_receipt(self) -> None:
        for field, value in (("size", 1), ("sha256", "0" * 64)):
            entries = copy.deepcopy(self.entries)
            next(e for e in entries if e["path"].endswith("/model.safetensors"))[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "inventory differs"):
                self._check(entries=entries)

    def test_same_length_file_tamper_is_rejected(self) -> None:
        path = self.project / self.model_root / "model.safetensors"
        path.write_bytes(b"x" * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, "differs from inventory"):
            self._check()

    def test_listed_missing_file_is_not_treated_as_omitted_capture(self) -> None:
        (self.project / self.source).unlink()
        with self.assertRaisesRegex(ValueError, "missing or unsafe"):
            self._check()

    def test_absolute_recorded_model_path_rebases_to_capture(self) -> None:
        self.recipe["config"]["model"]["model_path"] = "/recorded/project/" + self.model_root
        self.assertEqual(self._check()["model_files"]["status"], "verified")

    def test_external_recorded_model_and_database_paths_are_never_opened(self) -> None:
        self.recipe["config"]["model"]["model_path"] = "/outside/model"
        self.recipe["db"] = "/outside/original.sqlite"
        with patch.object(os, "open", side_effect=AssertionError("unexpected file read")):
            result = self._check()
        self.assertEqual(result["source_snapshot"]["status"], "not_captured")
        self.assertEqual(result["model_receipt"]["status"], "not_captured")

    def test_captured_source_database_is_recorded_without_opening_it(self) -> None:
        self.recipe["db"] = "/recorded/project/data/source.sqlite"
        self.recipe["config"]["model"]["model_path"] = "/outside/model"
        self.entries.append({"category": "database", "kind": "file",
                             "path": "databases/data/source.sqlite", "size": 1, "sha256": "0" * 64})
        with patch.object(os, "open", side_effect=AssertionError("database opened")):
            result = self._check()
        self.assertEqual(result["source_snapshot"]["status"], "recorded_only")
        self.assertIs(result["source_snapshot"]["original_recipe_database_opened"], False)
        self.assertIs(result["source_snapshot"]["reference_digest_reconstructed"], False)

    def test_traversing_paths_are_rejected(self) -> None:
        for field in ("model_path", "cache_path", "db"):
            recipe = copy.deepcopy(self.recipe)
            target = recipe["config"]["model"] if field == "model_path" else recipe["config"] if field == "cache_path" else recipe
            target[field] = "../escape"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "traversing"):
                self._check(recipe=recipe)

    def test_final_symlink_is_rejected(self) -> None:
        source = self.project / self.source
        target = self.project.parent / "outside-source.json"
        target.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "missing or unsafe"):
            self._check()

    def test_directory_symlink_is_rejected(self) -> None:
        directory = self.project / "src/watchlist/data"
        target = self.project.parent / "outside-data"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "missing or unsafe"):
            self._check()

    def test_duplicate_captured_json_keys_are_rejected(self) -> None:
        self._capture(self.receipt_path, b'{"duplicate":1,"duplicate":2}')
        with self.assertRaisesRegex(ValueError, "duplicate captured JSON key"):
            self._check()

    def test_nonfinite_nonprimitive_partial_and_malformed_recipes_are_rejected(self) -> None:
        invalid = [{"fixture": float("nan")}, {"fixture": b"bytes"},
                   {"config": {}}, dict(self.recipe, reference_sha256="invalid")]
        for recipe in invalid:
            with self.subTest(keys=tuple(recipe)), self.assertRaises(ValueError):
                self._check(recipe=recipe)

    def test_receipt_file_set_and_resource_limit_are_enforced(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["files"]["unexpected.bin"] = {"bytes": 1, "sha256": "0" * 64}
        self._capture_json(self.receipt_path, receipt)
        self.recipe["model_receipt_sha256"] = _recipe_digest(receipt)
        with self.assertRaisesRegex(ValueError, "receipt file set"):
            self._check()
        receipt = copy.deepcopy(self.receipt)
        receipt["files"]["model.safetensors"]["bytes"] = 600_000_001
        self._capture_json(self.receipt_path, receipt)
        self.recipe["model_receipt_sha256"] = _recipe_digest(receipt)
        with self.assertRaisesRegex(ValueError, "budget exceeded"):
            self._check()
