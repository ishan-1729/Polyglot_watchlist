"""Preservation checks use fictional temporary projects, never project stores."""

from dataclasses import dataclass
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest
import ormsgpack

from agent_support import FakeRetriever, form
from watchlist.agent.storage import ReviewService


REPOSITORY = Path(__file__).resolve().parents[1]
UTILITY = REPOSITORY / "scripts" / "preserve_v1.py"


@pytest.fixture(scope="module")
def preservation():
    """Load only the standalone utility; it must not execute its CLI on import."""
    spec = importlib.util.spec_from_file_location("preserve_v1_under_test", UTILITY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class FictionalProject:
    project: Path
    workspace: Path
    output: Path
    case: dict


@pytest.fixture
def fictional_project(tmp_path):
    """Copy small code/config inputs and create a new, completed fictional case."""
    project = tmp_path / "project"
    project.mkdir()
    shutil.copytree(REPOSITORY / "src", project / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(REPOSITORY / "config", project / "config")
    shutil.copytree(REPOSITORY / "eval" / "configs", project / "eval" / "configs")
    for name in ("pyproject.toml", "uv.lock", ".gitignore"):
        shutil.copy2(REPOSITORY / name, project / name)
    workspace = project / "data" / "review"
    with ReviewService(workspace, FakeRetriever()) as service:
        pending = service.start("Luma Vesper", {"fixture": "preservation-only"})
        case = service.review(pending["thread_id"], form(pending))
    # A preservation command must not silently "repair" these source modes.
    workspace.chmod(0o750)
    for member in workspace.iterdir():
        if member.is_file():
            member.chmod(0o640)
    return FictionalProject(project, workspace, project / "data" / "review-archives" / "v1", case)


def source_snapshot(fixture):
    """Record original membership, content and permissions without opening SQLite."""
    result = {}
    for path in sorted(fixture.project.rglob("*")):
        relative = path.relative_to(fixture.project)
        if relative.parts[:2] == ("data", "review-archives"):
            continue
        metadata = path.lstat()
        value = (stat.S_IFMT(metadata.st_mode), stat.S_IMODE(metadata.st_mode))
        if path.is_file() and not path.is_symlink():
            value += (hashlib.sha256(path.read_bytes()).hexdigest(), metadata.st_ino)
        elif path.is_symlink():
            value += (os.readlink(path),)
        result[str(relative)] = value
    return result


def apply(preservation, fixture):
    return preservation.apply_archive(fixture.project, fixture.workspace, fixture.output, include_runtime=False)


def test_dry_run_does_not_create_or_modify_any_project_file(preservation, fictional_project):
    before = source_snapshot(fictional_project)
    result = preservation.preflight(fictional_project.project, fictional_project.workspace, fictional_project.output,
                                   include_runtime=False)
    assert isinstance(result, dict)
    assert not fictional_project.output.exists()
    assert not fictional_project.output.parent.exists()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("missing", ["cases.sqlite", "checkpoints.sqlite", "writer.lock"])
def test_missing_required_store_member_fails_without_recreation(preservation, fictional_project, missing):
    (fictional_project.workspace / missing).unlink()
    before = source_snapshot(fictional_project)
    for operation in (preservation.preflight, preservation.apply_archive):
        with pytest.raises(preservation.PreservationError):
            operation(fictional_project.project, fictional_project.workspace, fictional_project.output,
                      include_runtime=False)
        assert source_snapshot(fictional_project) == before
        assert not fictional_project.output.exists()


def test_existing_destination_is_never_overwritten(preservation, fictional_project):
    fictional_project.output.mkdir(parents=True)
    sentinel = fictional_project.output / "do-not-overwrite.txt"
    sentinel.write_bytes(b"existing owner data")
    sentinel.chmod(0o640)
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert sentinel.read_bytes() == b"existing owner data"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o640
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("member", ["cases.sqlite", "checkpoints.sqlite", "writer.lock"])
def test_store_symlink_is_rejected(preservation, fictional_project, tmp_path, member):
    source = fictional_project.workspace / member
    outside = tmp_path / (member + ".outside")
    source.rename(outside)
    source.symlink_to(outside)
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert source_snapshot(fictional_project) == before
    assert not fictional_project.output.exists()


def test_store_hardlink_is_rejected(preservation, fictional_project, tmp_path):
    os.link(fictional_project.workspace / "cases.sqlite", tmp_path / "shared-inode.sqlite")
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert source_snapshot(fictional_project) == before
    assert not fictional_project.output.exists()


@pytest.mark.parametrize("relative", ["data/review/archive", "src/archive"])
def test_archive_cannot_overlap_inputs(preservation, fictional_project, relative):
    destination = fictional_project.project / relative
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        preservation.apply_archive(fictional_project.project, fictional_project.workspace, destination,
                                   include_runtime=False)
    assert not destination.exists()
    assert source_snapshot(fictional_project) == before


def test_destination_symlink_ancestor_is_rejected(preservation, fictional_project, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    fictional_project.output.parent.symlink_to(external, target_is_directory=True)
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert list(external.iterdir()) == []
    assert source_snapshot(fictional_project) == before


def test_sqlite_connections_never_target_original_stores(preservation, fictional_project, monkeypatch):
    original_connect = sqlite3.connect
    attempted_paths = []

    def guarded_connect(database, *args, **kwargs):
        raw = os.fspath(database)
        parsed = unquote(urlsplit(raw).path) if raw.startswith("file:") else raw
        path = Path(parsed).resolve()
        attempted_paths.append(path)
        assert not path.is_relative_to(fictional_project.workspace.resolve()), "SQLite opened a source store"
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(preservation.sqlite3, "connect", guarded_connect)
    before = source_snapshot(fictional_project)
    apply(preservation, fictional_project)
    preservation.verify_archive(fictional_project.output)
    assert attempted_paths, "The staged backup must undergo real SQLite verification"
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("operation", ["preflight", "apply_archive"])
def test_busy_writer_fails_promptly_without_touching_sources(fictional_project, operation):
    before = source_snapshot(fictional_project)
    runner = """
import runpy
import sys
from pathlib import Path
module = runpy.run_path(sys.argv[1])
module[sys.argv[2]](Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]), include_runtime=False)
"""
    with (fictional_project.workspace / "writer.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            [sys.executable, "-c", runner, str(UTILITY), operation, str(fictional_project.project),
             str(fictional_project.workspace), str(fictional_project.output)],
            capture_output=True, text=True, timeout=10,
        )
    assert result.returncode != 0
    assert "PreservationError" in result.stderr
    assert "busy" in result.stderr.lower()
    assert not fictional_project.output.exists()
    assert source_snapshot(fictional_project) == before


def test_idle_sqlite_reader_prevents_claiming_quiescence(preservation, fictional_project):
    reader_code = """
from pathlib import Path
import sqlite3
import sys
connection = sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)
connection.execute('SELECT COUNT(*) FROM cases').fetchone()
print('READY', flush=True)
sys.stdin.read()
connection.close()
"""
    reader = subprocess.Popen([sys.executable, "-c", reader_code, str(fictional_project.workspace / "cases.sqlite")],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([reader.stdout], [], [], 10)[0], "Temporary reader did not become ready"
        assert reader.stdout.readline().strip() == "READY"
        before = source_snapshot(fictional_project)
        with pytest.raises(preservation.PreservationError, match="another descriptor"):
            preservation.preflight(fictional_project.project, fictional_project.workspace, fictional_project.output,
                                   include_runtime=False)
        assert not fictional_project.output.exists()
        assert source_snapshot(fictional_project) == before
    finally:
        reader.communicate(timeout=10)


@pytest.mark.parametrize("member", ["cases.sqlite", "checkpoints.sqlite", "writer.lock"])
def test_required_store_member_must_be_regular_file(preservation, fictional_project, member):
    path = fictional_project.workspace / member
    path.unlink()
    path.mkdir()
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert source_snapshot(fictional_project) == before
    assert not fictional_project.output.exists()


def test_cross_store_case_mismatch_is_rejected(preservation, fictional_project, tmp_path):
    unrelated = tmp_path / "unrelated-fictional-store"
    with ReviewService(unrelated, FakeRetriever()) as service:
        pending = service.start("Another fictional case", {"fixture": "different-case"})
        service.review(pending["thread_id"], form(pending))
    shutil.copy2(unrelated / "checkpoints.sqlite", fictional_project.workspace / "checkpoints.sqlite")
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert source_snapshot(fictional_project) == before


def test_verify_missing_archive_does_not_initialize_it(preservation, tmp_path):
    absent = tmp_path / "absent-archive"
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(absent)
    assert not absent.exists()


def test_archive_is_private_under_permissive_umask_and_uses_independent_files(preservation, fictional_project):
    before = source_snapshot(fictional_project)
    source_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in fictional_project.project.rglob("*")
                     if path.is_file()}
    previous_umask = os.umask(0)
    try:
        apply(preservation, fictional_project)
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(fictional_project.output.stat().st_mode) == 0o700
    for path in fictional_project.output.rglob("*"):
        assert not path.is_symlink()
        if path.is_dir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o700
        elif path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert (path.stat().st_dev, path.stat().st_ino) not in source_inodes
    assert source_snapshot(fictional_project) == before


def test_root_secret_files_are_not_copied(preservation, fictional_project):
    secret_value = "FICTIONAL_SECRET_FOR_EXCLUSION_TEST_ONLY"
    for name in (".env", ".env.local", "credentials.json", "id_rsa"):
        (fictional_project.project / name).write_text(secret_value)
    before = source_snapshot(fictional_project)
    apply(preservation, fictional_project)
    for path in fictional_project.output.rglob("*"):
        if path.is_file():
            assert secret_value.encode() not in path.read_bytes(), str(path.relative_to(fictional_project.output))
    assert source_snapshot(fictional_project) == before


def leave_committed_wal(fixture):
    """Exit a real writer without SQLite cleanup, leaving a second case in WAL."""
    writer = """
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from agent_support import FakeRetriever, form
from watchlist.agent.storage import ReviewService
with ReviewService(Path(sys.argv[1]), FakeRetriever()) as service:
    for connection in (service.db, service.checkpoints):
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
    pending = service.start('Fictional committed WAL case', {'fixture': 'wal-only'})
    completed = service.review(pending['thread_id'], form(pending))
    print(json.dumps({'thread_id': completed['thread_id'], 'audit_id': completed['audit_id']}), flush=True)
    os._exit(77)
"""
    result = subprocess.run([sys.executable, "-c", writer, str(fixture.workspace), str(REPOSITORY / "tests")],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 77, result.stderr
    for name in ("cases.sqlite-wal", "checkpoints.sqlite-wal"):
        assert (fixture.workspace / name).stat().st_size > 0
    return json.loads(result.stdout)


def archive_snapshot(root):
    """Hash archive members so verify/restore cannot quietly rewrite the archive."""
    return {str(path.relative_to(root)): (stat.S_IMODE(path.stat().st_mode), hashlib.sha256(path.read_bytes()).hexdigest())
            for path in root.rglob("*") if path.is_file()}


def rewrite_manifest(archive, update):
    """Re-sign a hostile manifest to exercise path/schema checks, not only hashes."""
    path = archive / "manifest.json"
    manifest = json.loads(path.read_text())
    update(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    marker = archive / "COMPLETE.json"
    complete = json.loads(marker.read_text())
    complete["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    marker.write_text(json.dumps(complete, sort_keys=True) + "\n")


def first_payload(archive):
    manifest = json.loads((archive / "manifest.json").read_text())
    entry = next(entry for entry in manifest["entries"] if entry["kind"] == "file")
    return archive / entry["path"]


@pytest.fixture
def fictional_runtime(fictional_project, tmp_path):
    """Use tiny runtime-shaped trees; never inspect or copy the host framework."""
    environment = fictional_project.project / ".venv"
    (environment / "bin").mkdir(parents=True)
    (environment / "bin" / "python").write_bytes(b"fictional interpreter; never execute\n")
    (environment / "lib" / "python3.14" / "site-packages").mkdir(parents=True)
    framework = tmp_path / "fictional-framework"
    framework.mkdir()
    runtime = {"included": True, "framework_root": str(framework), "environment_relative": ".venv",
               "python_relative": ".venv/bin/python", "site_packages_relative": ".venv/lib/python3.14/site-packages",
               "python_version": "3.14.0", "platform": "fictional-test-host", "same_host_only": True,
               "creation_configuration": {}}
    return runtime, framework


def archive_with_fictional_runtime(preservation, fixture, runtime):
    """Exercise real inventory and restore while supplying only fictional bytes."""
    apply(preservation, fixture)
    inventory = [entry for entry in preservation._inventory(fixture.project, runtime)
                 if entry["category"] != "project"]
    for entry in inventory:
        target = fixture.output / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if entry["kind"] == "directory":
            target.mkdir(exist_ok=True)
        elif entry["kind"] == "file":
            shutil.copyfile(entry["source"], target)
            target.chmod(0o600)
    for category in ("environment", "python-framework"):
        root = fixture.output / "payload" / category
        if root.is_dir():
            root.chmod(0o700)
            for path in root.rglob("*"):
                if path.is_dir():
                    path.chmod(0o700)

    def include_runtime(manifest):
        manifest["runtime"] = {**runtime, "framework_root": "/Library/Frameworks/Python.framework/Versions/3.14"}
        manifest["entries"].extend({key: value for key, value in entry.items() if key != "source"}
                                   for entry in inventory)

    rewrite_manifest(fixture.output, include_runtime)
    return inventory


def test_runtime_link_through_linked_directory_restores_captured_target(
        preservation, fictional_project, fictional_runtime, tmp_path):
    runtime, framework = fictional_runtime
    real_directory = framework / "Versions" / "A" / "lib"
    real_directory.mkdir(parents=True)
    (real_directory / "fixture.data").write_bytes(b"fictional captured runtime resource\n")
    (framework / "Versions" / "Current").symlink_to("A", target_is_directory=True)
    (framework / "Tool").symlink_to("Versions/Current/lib/fixture.data")
    before = source_snapshot(fictional_project)
    inventory = archive_with_fictional_runtime(preservation, fictional_project, runtime)
    link = next(entry for entry in inventory if entry["path"] == "payload/python-framework/Tool")
    assert link["target"] == "Versions/Current/lib/fixture.data"
    assert link["target_exists"] is True
    assert not (fictional_project.output / link["path"]).exists(), "Archived links must remain inert metadata"
    archived = archive_snapshot(fictional_project.output)
    destination = tmp_path / "restored-linked-directory"
    preservation.restore_archive(fictional_project.output, destination, smoke=False)
    restored_link = destination / "python-framework" / "Tool"
    assert restored_link.is_symlink()
    assert os.readlink(restored_link) == link["target"]
    assert restored_link.read_bytes() == b"fictional captured runtime resource\n"
    assert restored_link.resolve() == destination / "python-framework" / "Versions" / "A" / "lib" / "fixture.data"
    assert source_snapshot(fictional_project) == before
    assert archive_snapshot(fictional_project.output) == archived


def test_dangling_internal_runtime_link_is_declared_and_restored_exactly(
        preservation, fictional_project, fictional_runtime, tmp_path):
    runtime, framework = fictional_runtime
    (framework / "Documentation").symlink_to("share/doc/absent.html")
    before = source_snapshot(fictional_project)
    inventory = archive_with_fictional_runtime(preservation, fictional_project, runtime)
    link = next(entry for entry in inventory if entry["path"] == "payload/python-framework/Documentation")
    assert link["target"] == "share/doc/absent.html"
    assert link["target_exists"] is False
    archived = archive_snapshot(fictional_project.output)
    destination = tmp_path / "restored-dangling-link"
    preservation.restore_archive(fictional_project.output, destination, smoke=False)
    restored_link = destination / "python-framework" / "Documentation"
    assert restored_link.is_symlink()
    assert not restored_link.exists()
    assert os.readlink(restored_link) == "share/doc/absent.html"
    assert source_snapshot(fictional_project) == before
    assert archive_snapshot(fictional_project.output) == archived


@pytest.mark.parametrize("attack", ["relative_escape", "absolute_escape", "cycle", "prefix_cycle"])
def test_runtime_inventory_rejects_escaped_or_cyclic_links(preservation, fictional_project, fictional_runtime, attack):
    runtime, framework = fictional_runtime
    if attack == "relative_escape":
        (framework / "first").symlink_to("../outside-missing.data")
    elif attack == "absolute_escape":
        (framework / "first").symlink_to(framework.parent / "outside-missing.data")
    elif attack == "cycle":
        (framework / "first").symlink_to("second")
        (framework / "second").symlink_to("first")
    else:
        (framework / "first").symlink_to("first/inside")
    with pytest.raises(preservation.PreservationError):
        preservation._inventory(fictional_project.project, runtime)
    assert not fictional_project.output.exists()


@pytest.mark.parametrize("attack", ["relative_escape", "absolute_escape", "cycle", "prefix_cycle"])
def test_resigned_manifest_rejects_escaped_or_cyclic_runtime_links(
        preservation, fictional_project, fictional_runtime, tmp_path, attack):
    runtime, framework = fictional_runtime
    (framework / "anchor.data").write_bytes(b"fictional runtime resource")
    (framework / "first").symlink_to("anchor.data")
    (framework / "second").symlink_to("anchor.data")
    archive_with_fictional_runtime(preservation, fictional_project, runtime)

    def corrupt_target(manifest):
        links = {entry["path"]: entry for entry in manifest["entries"] if entry["kind"] == "link"}
        first = links["payload/python-framework/first"]
        if attack == "relative_escape":
            first["target"] = "../outside-missing.data"
            first["target_exists"] = False
        elif attack == "absolute_escape":
            first["target"] = "/fictional-outside/missing.data"
            first["target_exists"] = False
        elif attack == "cycle":
            first["target"] = "second"
            links["payload/python-framework/second"]["target"] = "first"
        else:
            first["target"] = "first/inside"

    rewrite_manifest(fictional_project.output, corrupt_target)
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)
    destination = tmp_path / "must-not-restore-invalid-runtime-link"
    with pytest.raises(preservation.PreservationError):
        preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert not destination.exists()


def test_normal_archive_verify_and_restore_preserve_case_and_source(preservation, fictional_project, tmp_path):
    before = source_snapshot(fictional_project)
    result = apply(preservation, fictional_project)
    assert isinstance(result, dict)
    assert (fictional_project.output / "COMPLETE.json").is_file()
    archived = archive_snapshot(fictional_project.output)
    verified = preservation.verify_archive(fictional_project.output)
    assert isinstance(verified, dict)
    destination = tmp_path / "restored"
    restored = preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert isinstance(restored, dict)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    restored_database = destination / "databases" / "data" / "review" / "cases.sqlite"
    with sqlite3.connect(restored_database) as connection:
        assert connection.execute("SELECT thread_id, audit_id FROM cases").fetchall() == [
            (fictional_project.case["thread_id"], fictional_project.case["audit_id"])
        ]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    for relative in ("pyproject.toml", "uv.lock", "src/watchlist/agent/state.py"):
        assert (destination / "project" / relative).read_bytes() == (fictional_project.project / relative).read_bytes()
    assert not (destination / "project" / ".venv").exists()
    assert source_snapshot(fictional_project) == before
    assert archive_snapshot(fictional_project.output) == archived


def test_wal_only_committed_case_survives_backup_and_restore(preservation, fictional_project, tmp_path):
    wal_case = leave_committed_wal(fictional_project)
    # Prove this fixture would lose the committed case if only the main DB were copied.
    main_only = tmp_path / "main-only.sqlite"
    shutil.copy2(fictional_project.workspace / "cases.sqlite", main_only)
    with sqlite3.connect(main_only) as connection:
        assert connection.execute("SELECT COUNT(*) FROM cases").fetchone() == (1,)
    before = source_snapshot(fictional_project)
    apply(preservation, fictional_project)
    destination = tmp_path / "restored-wal"
    preservation.restore_archive(fictional_project.output, destination, smoke=False)
    with sqlite3.connect(destination / "databases" / "data" / "review" / "cases.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM cases").fetchone() == (2,)
        assert connection.execute("SELECT audit_id FROM cases WHERE thread_id=?", (wal_case["thread_id"],)).fetchone() == (
            wal_case["audit_id"],
        )
        assert connection.execute("SELECT COUNT(*) FROM audit_events WHERE event_key='case_finalized'").fetchone() == (2,)
    assert source_snapshot(fictional_project) == before


def test_hot_rollback_journal_recovers_committed_rows_without_modifying_sources(preservation, fictional_project, tmp_path):
    source = fictional_project.project / "data" / "rollback.sqlite"
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE fictional_records (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        connection.executemany("INSERT INTO fictional_records VALUES (?, ?)",
                               [(number, "COMMITTED-" + "x" * 3000) for number in range(300)])
        connection.commit()
    finally:
        connection.close()
    writer = """
import os
import sqlite3
import sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA journal_mode=DELETE')
connection.execute('PRAGMA synchronous=FULL')
connection.execute('PRAGMA cache_size=2')
connection.execute('PRAGMA cache_spill=ON')
connection.execute('BEGIN IMMEDIATE')
connection.execute('UPDATE fictional_records SET payload=?', ('UNCOMMITTED-' + 'y' * 3000,))
os._exit(77)
"""
    result = subprocess.run([sys.executable, "-B", "-c", writer, str(source)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 77, result.stderr
    journal = Path(str(source) + "-journal")
    assert journal.read_bytes()[:8] == bytes.fromhex("d9d505f920a163d7"), "Fixture must contain a genuinely hot journal"
    main_only = tmp_path / "rollback-main-only.sqlite"
    shutil.copy2(source, main_only)
    connection = sqlite3.connect(main_only)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fictional_records WHERE payload LIKE 'UNCOMMITTED-%'").fetchone()[0] > 0
    finally:
        connection.close()
    before = source_snapshot(fictional_project)
    apply(preservation, fictional_project)
    destination = tmp_path / "restored-rollback"
    preservation.restore_archive(fictional_project.output, destination, smoke=False)
    connection = sqlite3.connect(destination / "databases" / "data" / "rollback.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM fictional_records").fetchone() == (300,)
        assert connection.execute("SELECT COUNT(*) FROM fictional_records WHERE payload LIKE 'COMMITTED-%'").fetchone() == (300,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("change", ["tamper", "missing", "extra", "incomplete"])
def test_archive_corruption_is_rejected_before_restore(preservation, fictional_project, tmp_path, change):
    apply(preservation, fictional_project)
    if change == "tamper":
        member = first_payload(fictional_project.output)
        member.write_bytes(member.read_bytes() + b"\nTAMPERED")
    elif change == "missing":
        first_payload(fictional_project.output).unlink()
    elif change == "extra":
        (fictional_project.output / "unmanifested.txt").write_text("unexpected member")
    else:
        (fictional_project.output / "COMPLETE.json").unlink()
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)
    destination = tmp_path / "must-not-be-restored"
    with pytest.raises(preservation.PreservationError):
        preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert not destination.exists()


@pytest.mark.parametrize("unsafe", ["../escape.txt", "/tmp/preservation-absolute-path-escape", "payload/project/../../escape.txt"])
def test_resigned_manifest_rejects_unsafe_paths(preservation, fictional_project, unsafe):
    apply(preservation, fictional_project)
    rewrite_manifest(fictional_project.output, lambda manifest: manifest["entries"][0].update(path=unsafe))
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)


def test_resigned_manifest_rejects_duplicate_paths(preservation, fictional_project):
    apply(preservation, fictional_project)
    rewrite_manifest(fictional_project.output, lambda manifest: manifest["entries"].append(dict(manifest["entries"][0])))
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)


def test_resigned_manifest_cannot_omit_a_captured_database(preservation, fictional_project, tmp_path):
    relative = "data/extra.sqlite"
    connection = sqlite3.connect(fictional_project.project / relative)
    try:
        connection.execute("CREATE TABLE fictional_records (name TEXT NOT NULL)")
        connection.execute("INSERT INTO fictional_records VALUES ('Luma Vesper')")
        connection.commit()
    finally:
        connection.close()
    before = source_snapshot(fictional_project)
    apply(preservation, fictional_project)
    normalized = "databases/" + relative
    (fictional_project.output / normalized).unlink()

    def omit_database(manifest):
        manifest["entries"] = [entry for entry in manifest["entries"] if entry["path"] != normalized]
        manifest["database_paths"].remove(relative)
        del manifest["sidecars"][relative]

    rewrite_manifest(fictional_project.output, omit_database)
    with pytest.raises(preservation.PreservationError, match="[Dd]atabase membership"):
        preservation.verify_archive(fictional_project.output)
    destination = tmp_path / "must-not-restore-omitted-database"
    with pytest.raises(preservation.PreservationError):
        preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert not destination.exists()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_archive_member_cannot_reference_an_external_inode(preservation, fictional_project, tmp_path, link_kind):
    apply(preservation, fictional_project)
    member = first_payload(fictional_project.output)
    outside = tmp_path / "outside-copy"
    shutil.copy2(member, outside)
    original = outside.read_bytes()
    member.unlink()
    if link_kind == "symlink":
        member.symlink_to(outside)
    else:
        os.link(outside, member)
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)
    assert outside.read_bytes() == original


def test_restore_never_overwrites_an_existing_destination(preservation, fictional_project, tmp_path):
    apply(preservation, fictional_project)
    destination = tmp_path / "existing-restore"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_bytes(b"keep existing destination")
    with pytest.raises(preservation.PreservationError):
        preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert sentinel.read_bytes() == b"keep existing destination"
    assert list(destination.iterdir()) == [sentinel]


def test_restore_cannot_nest_inside_archive(preservation, fictional_project):
    apply(preservation, fictional_project)
    archived = archive_snapshot(fictional_project.output)
    destination = fictional_project.output / "restore"
    with pytest.raises(preservation.PreservationError):
        preservation.restore_archive(fictional_project.output, destination, smoke=False)
    assert not destination.exists()
    assert archive_snapshot(fictional_project.output) == archived


def test_fsync_failure_never_produces_complete_archive(preservation, fictional_project, monkeypatch):
    before = source_snapshot(fictional_project)
    attempts = 0

    def disk_failure(_descriptor):
        nonlocal attempts
        attempts += 1
        raise OSError(28, "No space left on device (fictional test)")

    monkeypatch.setattr(preservation.os, "fsync", disk_failure)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert attempts > 0
    assert not (fictional_project.output / "COMPLETE.json").exists()
    assert source_snapshot(fictional_project) == before


def test_copy_failure_never_produces_complete_archive(preservation, fictional_project, monkeypatch):
    before = source_snapshot(fictional_project)
    actual_copy = preservation._copy_file
    copies = 0

    def fail_after_one_copy(source, target, expected=None):
        nonlocal copies
        copies += 1
        if copies == 2:
            raise OSError(28, "Copy exhausted disk space (fictional test)")
        return actual_copy(source, target, expected)

    monkeypatch.setattr(preservation, "_copy_file", fail_after_one_copy)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert copies == 2
    assert not (fictional_project.output / "COMPLETE.json").exists()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("mutation", ["source_bytes", "sidecar_membership"])
def test_source_change_during_capture_prevents_completion(preservation, fictional_project, monkeypatch, mutation):
    actual_copy = preservation._copy_file
    changed = False

    def change_after_copy(source, target, expected=None):
        nonlocal changed
        actual_copy(source, target, expected)
        if expected is not None and not changed:
            changed = True
            if mutation == "source_bytes":
                source.write_bytes(source.read_bytes() + b"\nconcurrent fictional change")
            else:
                (fictional_project.workspace / "cases.sqlite-wal").write_bytes(b"new fictional sidecar")

    monkeypatch.setattr(preservation, "_copy_file", change_after_copy)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert changed
    assert not (fictional_project.output / "COMPLETE.json").exists()


def test_insufficient_space_is_rejected_before_output_creation(preservation, fictional_project, monkeypatch):
    actual = shutil.disk_usage(fictional_project.project)
    monkeypatch.setattr(preservation.shutil, "disk_usage", lambda path: type(actual)(actual.total, actual.used, 0))
    before = source_snapshot(fictional_project)
    for operation in (preservation.preflight, preservation.apply_archive):
        with pytest.raises(preservation.PreservationError, match="[Ss]pace"):
            operation(fictional_project.project, fictional_project.workspace, fictional_project.output,
                      include_runtime=False)
        assert not fictional_project.output.exists()
        assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("stage", ["backup", "last_directory_fsync", "lock_recheck"])
def test_late_failure_never_leaves_a_valid_completion_marker(preservation, fictional_project, monkeypatch, stage):
    before = source_snapshot(fictional_project)
    injected = False
    if stage == "backup":
        actual = preservation._backup_databases

        def fail_backup(*args, **kwargs):
            nonlocal injected
            actual(*args, **kwargs)
            injected = True
            raise sqlite3.OperationalError("Fictional failed backup finalization")

        monkeypatch.setattr(preservation, "_backup_databases", fail_backup)
    elif stage == "last_directory_fsync":
        actual = preservation._fsync_dir

        def fail_fsync(path):
            nonlocal injected
            if path == fictional_project.output.parent and (fictional_project.output / "COMPLETE.json").exists():
                injected = True
                raise OSError(5, "Fictional final directory sync failure")
            return actual(path)

        monkeypatch.setattr(preservation, "_fsync_dir", fail_fsync)
    else:
        actual = preservation._metadata

        def fail_lock_recheck(path):
            nonlocal injected
            value = actual(path)
            if path == fictional_project.workspace / "writer.lock" and (fictional_project.output / "COMPLETE.json").exists():
                injected = True
                return {**value, "ctime_ns": value["ctime_ns"] + 1}
            return value

        monkeypatch.setattr(preservation, "_metadata", fail_lock_recheck)
    with pytest.raises(preservation.PreservationError):
        apply(preservation, fictional_project)
    assert injected
    assert not (fictional_project.output / "COMPLETE.json").exists()
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("changes", [{"kind": "executable"}, {"category": "python-framework"}, {"size": True}])
def test_resigned_manifest_rejects_wrong_member_types(preservation, fictional_project, changes):
    apply(preservation, fictional_project)

    def change(manifest):
        entry = next(entry for entry in manifest["entries"] if entry["kind"] == "file")
        entry.update(changes)

    rewrite_manifest(fictional_project.output, change)
    with pytest.raises(preservation.PreservationError):
        preservation.verify_archive(fictional_project.output)


@pytest.mark.parametrize("damage", ["packet", "submission", "audit", "missing_checkpoint_parent", "typed_pickle", "extension_outside_interrupt"])
def test_logically_corrupt_store_is_not_archived_as_verified(preservation, fictional_project, damage):
    checkpoint = damage in {"missing_checkpoint_parent", "typed_pickle", "extension_outside_interrupt"}
    path = fictional_project.workspace / ("checkpoints.sqlite" if checkpoint else "cases.sqlite")
    connection = sqlite3.connect(path)
    try:
        if damage == "packet":
            connection.execute("UPDATE review_packets SET sha256=?", ("0" * 64,))
        elif damage == "submission":
            connection.execute("UPDATE review_submissions SET sha256=?", ("0" * 64,))
        elif damage == "audit":
            connection.execute("UPDATE audit_events SET payload_json='{}' WHERE event_key='case_finalized'")
        elif damage == "missing_checkpoint_parent":
            connection.execute("UPDATE checkpoints SET parent_checkpoint_id='missing-checkpoint' WHERE checkpoint_id=(SELECT MAX(checkpoint_id) FROM checkpoints)")
        elif damage == "typed_pickle":
            connection.execute("UPDATE checkpoints SET type='pickle', checkpoint=? WHERE checkpoint_id=(SELECT MAX(checkpoint_id) FROM checkpoints)", (b"\x80\x04N.",))
        else:
            assert connection.execute("SELECT COUNT(*) FROM writes WHERE channel='__interrupt__'").fetchone()[0] > 0
            connection.execute("UPDATE writes SET channel='fictional_other_channel' WHERE channel='__interrupt__'")
        connection.commit()
    finally:
        connection.close()
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError, match="logical verification"):
        apply(preservation, fictional_project)
    assert not (fictional_project.output / "COMPLETE.json").exists()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("table, omitted", [
    ("cases", " UNIQUE"),
    ("audit_events", " REFERENCES cases(audit_id)"),
    ("audit_events", "PRIMARY KEY(audit_id, sequence),"),
])
def test_missing_schema_constraints_are_rejected_even_with_valid_rows(preservation, fictional_project, table, omitted):
    connection = sqlite3.connect(fictional_project.workspace / "cases.sqlite")
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        schema = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        assert omitted in schema
        rows = connection.execute(f'SELECT * FROM "{table}"').fetchall()
        connection.execute(f'DROP TABLE "{table}"')
        connection.execute(schema.replace(omitted, "", 1))
        placeholders = ",".join("?" for _ in rows[0])
        connection.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
        connection.commit()
    finally:
        connection.close()
    before = source_snapshot(fictional_project)
    with pytest.raises(preservation.PreservationError, match="logical verification"):
        apply(preservation, fictional_project)
    assert not (fictional_project.output / "COMPLETE.json").exists()
    assert source_snapshot(fictional_project) == before


@pytest.mark.parametrize("blob", [
    b"\xc1", b"\xd9\x03a", b"\xc0\xc0", b"\x82\xa1a\x01\xa1a\x02",
    b"\xcb" + struct.pack(">d", float("nan")), b"\x91" * 66 + b"\xc0",
])
def test_checkpoint_decoder_rejects_malformed_or_unbounded_data(preservation, blob):
    with pytest.raises(preservation.PreservationError):
        preservation._pv1_decode("msgpack", blob, "fictional checkpoint")


@pytest.mark.parametrize("kind", ["pickle", "bytes", "bytearray", "unknown"])
def test_checkpoint_decoder_rejects_unsupported_serialization(preservation, kind):
    with pytest.raises(preservation.PreservationError):
        preservation._pv1_decode(kind, b"\x80\x04N.", "fictional checkpoint")


def interrupt_blob(payload, extension_code=2):
    encoded = ormsgpack.packb(payload)
    return b"\x91\xc9" + struct.pack(">I", len(encoded)) + bytes([extension_code]) + encoded


@pytest.mark.parametrize("attack", ["wrong_code", "constructor", "wrong_shape", "missing_field", "response_schema", "outside_interrupt"])
def test_checkpoint_decoder_rejects_unapproved_extension_shapes(preservation, attack):
    fields = {"value": {"fictional": "data"}, "id": "fixture-interrupt", "response_schema": None}
    payload = ["langgraph.types", "Interrupt", fields]
    extension_code = 2
    allow_interrupt = True
    if attack == "wrong_code":
        extension_code = 3
    elif attack == "constructor":
        payload[:2] = ["os", "system"]
    elif attack == "wrong_shape":
        payload = {"module": "langgraph.types", "constructor": "Interrupt", "fields": fields}
    elif attack == "missing_field":
        del fields["id"]
    elif attack == "response_schema":
        fields["response_schema"] = {"type": "object"}
    else:
        allow_interrupt = False
    with pytest.raises(preservation.PreservationError):
        preservation._pv1_decode("msgpack", interrupt_blob(payload, extension_code), "fictional control write",
                                 allow_interrupt=allow_interrupt)


def utility_command(fixture, *arguments):
    """Pin every CLI test to its fictional temporary project."""
    capture_options = ["--without-runtime"] if "--dry-run" in arguments or "--apply" in arguments else []
    return [sys.executable, "-B", str(UTILITY), "--project", str(fixture.project),
            "--workspace", "data/review", "--output", "data/review-archives/v1",
            *capture_options, *arguments]


def test_cli_dry_run_and_conflicting_actions(preservation, fictional_project):
    before = source_snapshot(fictional_project)
    dry_run = subprocess.run(utility_command(fictional_project, "--dry-run"), capture_output=True, text=True, timeout=30)
    assert dry_run.returncode == 0, dry_run.stderr
    assert json.loads(dry_run.stdout)["status"] == "ready"
    conflict = subprocess.run(utility_command(fictional_project, "--dry-run", "--apply"),
                              capture_output=True, text=True, timeout=10)
    assert conflict.returncode == 2
    assert not fictional_project.output.exists()
    assert source_snapshot(fictional_project) == before


def test_cli_apply_verify_and_restore(preservation, fictional_project, tmp_path):
    before = source_snapshot(fictional_project)
    destination = tmp_path / "cli-restored"
    for arguments in (("--apply",), ("--verify",), ("--restore", "--restore-to", str(destination))):
        result = subprocess.run(utility_command(fictional_project, *arguments), capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "verified"
    assert (destination / "RESTORE-COMPLETE.json").is_file()
    assert source_snapshot(fictional_project) == before
