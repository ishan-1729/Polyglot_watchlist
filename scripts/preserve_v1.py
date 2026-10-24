"""Preserve the established v1 project without opening its original SQLite files.

This is a local, quiescent, same-host preservation tool, not an archive importer
for untrusted downloads or a portable Python installer. It uses only the standard
library; the optional restored-runtime smoke imports already preserved packages.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterator

SCHEMA = "polyglot-preservation-v1"
ROOT_FILES = ("AGENTS.md", "README.md", "pyproject.toml", "uv.lock", ".gitignore", ".codex/config.toml")
ROOT_TREES = ("src", "tests", "scripts", "docs", "config", "eval", "data")
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXCLUDED = {"data/review-archives", "docs/releases/v1-manifest.json", "docs/progress/completion-00.md"}
SIDECARS = ("-wal", "-shm", "-journal")
CHUNK = 1024 * 1024


class PreservationError(RuntimeError):
    """Preservation cannot establish its required safety or integrity contract."""


def _public_errors(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PreservationError:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            raise PreservationError(f"{function.__name__}: {exc}") from exc
    return wrapped


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PreservationError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _json_read(path: Path, *, expected_sha256: str | None = None) -> dict:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise PreservationError(f"Oversized JSON manifest: {path.name}")
    raw = path.read_bytes()
    if expected_sha256 is not None and digest_bytes(raw) != expected_sha256:
        raise PreservationError(f"JSON bytes changed after verification: {path.name}")
    value = json.loads(raw, object_pairs_hook=_unique_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(PreservationError(f"Nonfinite JSON: {value}")))
    if not isinstance(value, dict):
        raise PreservationError(f"Expected a JSON object: {path.name}")
    return value


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise PreservationError("Invalid manifest path")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in ("", ".", "..") for p in path.parts):
        raise PreservationError(f"Unsafe manifest path: {value!r}")
    return path


def _absolute_path(value: Path | str) -> Path:
    """Reject traversal before lexical containment or filesystem access."""
    path = Path(value)
    if ".." in path.parts:
        raise PreservationError("Parent traversal is unsupported in filesystem paths")
    return path.absolute()


def _no_symlinks(path: Path) -> None:
    """Check every existing path component without silently resolving links."""
    path = _absolute_path(path)
    for parent in (*reversed(path.parents), path):
        try:
            metadata = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise PreservationError(f"Symlink path component is unsupported: {parent}")


def _metadata(path: Path) -> dict:
    st = path.lstat()
    return {"device": st.st_dev, "inode": st.st_ino, "size": st.st_size,
            "mode": stat.S_IMODE(st.st_mode), "mtime_ns": st.st_mtime_ns,
            "ctime_ns": st.st_ctime_ns, "nlink": st.st_nlink}


def _regular(path: Path, *, single_link: bool = True) -> dict:
    _no_symlinks(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or (single_link and st.st_nlink != 1):
        raise PreservationError(f"Expected independent regular file: {path}")
    return _metadata(path)


def _hash(path: Path) -> str:
    before = _regular(path, single_link=False)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != (before["device"], before["inode"]):
            raise PreservationError(f"File replaced while reading: {path}")
        h = hashlib.sha256()
        while block := os.read(fd, CHUNK):
            h.update(block)
        if _metadata(path) != before:
            raise PreservationError(f"File changed while reading: {path}")
        return h.hexdigest()
    finally:
        os.close(fd)


def _private_mkdir(path: Path) -> None:
    _no_symlinks(path)
    if path.exists():
        if not path.is_dir():
            raise PreservationError(f"Not a directory: {path}")
        return
    _private_mkdir(path.parent)
    path.mkdir(mode=0o700)  # Exclusive, including when another creator races us.


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_json(path: Path, value: dict) -> None:
    _private_mkdir(path.parent)
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(canonical_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _remove_owned_marker(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if (metadata.st_dev, metadata.st_ino) != identity or not stat.S_ISREG(metadata.st_mode):
        raise PreservationError("Completion marker was replaced during rollback")
    path.unlink()
    _fsync_dir(path.parent)


def _publish_json(path: Path, value: dict) -> tuple[int, int]:
    """Install a complete JSON marker atomically without replacing a destination."""
    _private_mkdir(path.parent)
    fd, filename = tempfile.mkstemp(prefix=".publication-", dir=path.parent)
    temporary = Path(filename)
    identity = None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        metadata = temporary.lstat()
        os.link(temporary, path, follow_symlinks=False)
        identity = (metadata.st_dev, metadata.st_ino)
        temporary.unlink()
        _fsync_dir(path.parent)
        return identity
    except BaseException:
        _remove_owned_marker(path, identity)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def _copy_file(source: Path, target: Path, expected: dict | None = None) -> None:
    """Copy through no-follow descriptors; never create a shared inode."""
    before = _regular(source, single_link=False)
    if expected is not None and before != expected:
        raise PreservationError(f"Source changed before copying: {source}")
    _private_mkdir(target.parent)
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(source_fd)
        if (st.st_dev, st.st_ino) != (before["device"], before["inode"]):
            raise PreservationError(f"Source replaced: {source}")
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            while block := os.read(source_fd, CHUNK):
                view = memoryview(block)
                while view:
                    count = os.write(target_fd, view)
                    if count <= 0:
                        raise PreservationError("Copy made no progress")
                    view = view[count:]
            os.fsync(target_fd)
        finally:
            os.close(target_fd)
        if _metadata(source) != before:
            raise PreservationError(f"Source changed while copying: {source}")
    finally:
        os.close(source_fd)


def _runtime(project: Path, include: bool) -> dict:
    if not include:
        return {"included": False}
    environment = project / ".venv"
    _no_symlinks(environment)
    if not environment.is_dir():
        raise PreservationError("Missing established .venv; runtime preservation requested")
    cfg = dict(line.split(" = ", 1) for line in (environment / "pyvenv.cfg").read_text().splitlines() if " = " in line)
    framework = Path(cfg["home"]).parent.absolute()
    _no_symlinks(framework)
    if "Python.framework/Versions/" not in str(framework) or not framework.is_dir():
        raise PreservationError("This recovery recipe requires the established macOS Python framework")
    site_packages = list(environment.glob("lib/python*/site-packages"))
    if len(site_packages) != 1:
        raise PreservationError("Expected one established site-packages directory")
    return {"included": True, "framework_root": str(framework), "environment_relative": ".venv",
            "python_relative": ".venv/bin/python",
            "site_packages_relative": str(site_packages[0].relative_to(project)),
            "python_version": platform.python_version(), "platform": platform.platform(),
            "same_host_only": True, "creation_configuration": cfg}


def _excluded(relative: Path) -> bool:
    return (any(part in SKIP_PARTS for part in relative.parts) or relative.suffix in (".pyc", ".pyo")
            or any(str(relative) == entry or str(relative).startswith(entry + "/") for entry in EXCLUDED))


def _inventory(project: Path, runtime: dict, *, hashes: bool = True) -> list[dict]:
    entries = []
    def visit(path: Path, relative: Path, category: str, root: Path):
        if _excluded(relative):
            return
        st = path.lstat()
        item = {"path": f"payload/{category}/{relative.as_posix()}", "category": category,
                "mode": stat.S_IMODE(st.st_mode), "source": str(path)}
        if stat.S_ISLNK(st.st_mode):
            if category == "project":
                raise PreservationError(f"Project symlink unsupported: {path}")
            try:
                resolved = path.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                raise PreservationError(f"Cannot resolve runtime link: {path}") from exc
            permitted = [root]
            if category == "environment":
                permitted.append(Path(runtime["framework_root"]))
            if not any(resolved.is_relative_to(base) for base in permitted):
                raise PreservationError(f"External runtime link unsupported: {path}")
            item.update(kind="link", target=os.readlink(path), target_exists=path.exists(), metadata=_metadata(path))
        elif stat.S_ISDIR(st.st_mode):
            item.update(kind="directory", metadata={key: _metadata(path)[key] for key in ("device", "inode", "mode")})
        elif stat.S_ISREG(st.st_mode):
            if category == "project" and st.st_nlink != 1:
                raise PreservationError(f"Project hardlink unsupported: {path}")
            item.update(kind="file", size=st.st_size, metadata=_metadata(path))
            if hashes:
                item["sha256"] = _hash(path)
        else:
            raise PreservationError(f"Unsupported source type: {path}")
        entries.append(item)
        if item["kind"] == "directory":
            for child in sorted(path.iterdir()):
                visit(child, relative / child.name, category, root)
    for name in ROOT_FILES:
        path = project / name
        if path.exists() or path.is_symlink():
            visit(path, Path(name), "project", project)
    for name in ROOT_TREES:
        path = project / name
        if path.exists() or path.is_symlink():
            visit(path, Path(name), "project", project)
    if runtime["included"]:
        for category, root in (("environment", project / ".venv"), ("python-framework", Path(runtime["framework_root"]))):
            for child in sorted(root.iterdir()):
                visit(child, Path(child.name), category, root)
        _validate_runtime_links(entries, runtime)
    return sorted(entries, key=lambda item: item["path"])


def _paths(project: Path, workspace: Path, output: Path) -> tuple[Path, Path, Path]:
    project, workspace, output = (_absolute_path(p) for p in (project, workspace, output))
    for path in (project, workspace, output):
        _no_symlinks(path)
    if not project.is_dir() or not workspace.is_dir() or not workspace.is_relative_to(project):
        raise PreservationError("Workspace must be an established directory inside the project")
    if output.exists() or output.is_symlink():
        raise PreservationError("Destination already exists; choose a fresh destination")
    if output.is_relative_to(project) and not output.is_relative_to(project / "data/review-archives"):
        raise PreservationError("An in-project destination must be inside data/review-archives")
    if project.is_relative_to(output) or output.is_relative_to(workspace):
        raise PreservationError("Destination overlaps source inputs")
    for name in ("writer.lock", "cases.sqlite", "checkpoints.sqlite"):
        _regular(workspace / name)
    return project, workspace, output


def _database_files(project: Path, entries: list[dict]) -> list[Path]:
    result = [Path(item["source"]) for item in entries
              if item["category"] == "project" and item["kind"] == "file" and item["path"].endswith(".sqlite")]
    for db in result:
        for candidate in db.parent.glob(db.name + "-*"):
            if candidate.name[len(db.name):] not in SIDECARS:
                raise PreservationError(f"Unknown SQLite sidecar: {candidate}")
            _regular(candidate)
    return sorted(result)


def _lsof(paths: list[Path], lock_fd: int) -> None:
    executable = shutil.which("lsof")
    if not executable:
        raise PreservationError("lsof is required to check for other open database users")
    run = subprocess.run([executable, "-nP", "-Fpf", "--", *(str(path) for path in paths)],
                         capture_output=True, text=True, timeout=20)
    if run.returncode not in (0, 1) or run.stderr.strip():
        raise PreservationError(f"Cannot establish quiescence with lsof: {run.stderr.strip()}")
    pid = None
    saw_own = False
    for line in run.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("f"):
            if pid == os.getpid() and line[1:] == str(lock_fd):
                saw_own = True
            else:
                raise PreservationError("Database or lock is open by another descriptor; stop all review/database processes")
        elif line:
            raise PreservationError("Unexpected lsof output; cannot establish quiescence")
    if not saw_own:
        raise PreservationError("lsof did not confirm the utility's lock descriptor")


@contextmanager
def _locked(workspace: Path) -> Iterator[int]:
    path = workspace / "writer.lock"
    before = _regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before["device"], before["inode"]):
            raise PreservationError("Lock changed during acquisition")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PreservationError("Review workspace is busy") from exc
        yield fd
        if _metadata(path) != before:
            raise PreservationError("Original lock metadata changed")
    finally:
        os.close(fd)


def _open_files(workspace: Path, databases: list[Path]) -> list[Path]:
    paths = [workspace / "writer.lock"]
    for db in databases:
        paths.append(db)
        paths.extend(Path(str(db) + suffix) for suffix in SIDECARS if Path(str(db) + suffix).exists())
    return paths


def _space(output: Path, entries: list[dict], database_bytes: int) -> dict:
    total = sum(item.get("size", 0) for item in entries)
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    required = total * 2 + database_bytes * 4 + 256 * 1024 * 1024
    if free < required:
        raise PreservationError(f"Insufficient space: need {required} free bytes for archive and restore; have {free}")
    return {"captured_regular_bytes": total, "required_free_bytes": required, "available_free_bytes": free}


@_public_errors
def preflight(project: Path, workspace: Path, output: Path, *, include_runtime: bool = True) -> dict:
    """Inspect inputs and acquire the existing lock; create/chmod/open no databases."""
    project, workspace, output = _paths(project, workspace, output)
    with _locked(workspace) as fd:
        runtime = _runtime(project, include_runtime)
        entries = _inventory(project, runtime, hashes=False)
        databases = _database_files(project, entries)
        _lsof(_open_files(workspace, databases), fd)
        space = _space(output, entries, sum(db.stat().st_size for db in databases))
    return {"status": "ready", "schema": SCHEMA, "file_count": sum(e["kind"] == "file" for e in entries),
            "database_count": len(databases), "runtime_included": include_runtime, **space,
            "missing_runtime_link_count": sum(e["kind"] == "link" and not e["target_exists"] for e in entries),
            "precondition": "Keep all review and source-database processes stopped until capture finishes."}


def _backup_databases(raw_project: Path, database_paths: list[str], destination: Path) -> None:
    """Recover complete copied file sets, then use SQLite backup on copies only."""
    with tempfile.TemporaryDirectory(prefix="polyglot-db-working-") as temporary:
        working = Path(temporary).resolve()
        os.chmod(working, 0o700)
        for relative in database_paths:
            source = raw_project / relative
            copied = working / relative
            _copy_file(source, copied)
            for suffix in SIDECARS:
                sidecar = Path(str(source) + suffix)
                if sidecar.exists():
                    _copy_file(sidecar, Path(str(copied) + suffix))
            target = destination / relative
            _private_mkdir(target.parent)
            target.touch(mode=0o600, exist_ok=False)
            with closing(sqlite3.connect(copied, timeout=2)) as connection:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("SELECT count(*) FROM sqlite_master").fetchone()  # Trigger journal recovery only here.
                with closing(sqlite3.connect(target, timeout=2)) as backup:
                    connection.backup(backup, pages=256)
                    backup.execute("PRAGMA journal_mode=DELETE").fetchone()
            if target.stat().st_size == 0:
                raise PreservationError("SQLite backup produced an empty database")
            with target.open("rb") as stream:
                os.fsync(stream.fileno())


def _sidecar_receipt(project: Path, paths: list[Path]) -> dict:
    return {str(db.relative_to(project)): {suffix: Path(str(db) + suffix).exists() for suffix in SIDECARS} for db in paths}


def _manifest_entry(item: dict) -> dict:
    return {key: value for key, value in item.items() if key != "source"}


def _all_disk_members(root: Path) -> dict[str, str]:
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(base) / name
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise PreservationError("Archive contains a symlink or special file")
            if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
                raise PreservationError("Archive contains a hardlink")
            expected_mode = 0o700 if stat.S_ISDIR(st.st_mode) else 0o600
            if stat.S_IMODE(st.st_mode) != expected_mode:
                raise PreservationError(f"Archive permissions are not private: {path.relative_to(root)}")
            result[str(path.relative_to(root))] = "directory" if stat.S_ISDIR(st.st_mode) else "file"
    return result


def _fields(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise PreservationError(f"Invalid {label} fields")


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _register_member(members: dict[str, str], relative: PurePosixPath, kind: str) -> None:
    key = str(relative)
    if members.get(key, kind) != kind:
        raise PreservationError("Manifest file/directory/link collision")
    members[key] = kind
    for parent in relative.parents:
        if str(parent) != ".":
            if members.get(str(parent), "directory") != "directory":
                raise PreservationError("Manifest member has a nondirectory parent")
            members[str(parent)] = "directory"


def _link_destination(item: dict, runtime: dict) -> PurePosixPath:
    """Validate runtime links; absolute framework links remain same-host dependencies."""
    raw = item["target"]
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise PreservationError("Invalid preserved link target")
    relative = PurePosixPath(_restore_relative(item).as_posix())
    link = PurePosixPath(raw)
    if link.is_absolute():
        framework = PurePosixPath(runtime["framework_root"])
        if ".." in link.parts or str(link) != raw or not link.is_relative_to(framework):
            raise PreservationError("Unexpected external runtime link")
        return PurePosixPath("python-framework") / link.relative_to(framework)
    result = relative.parent / link
    permitted = PurePosixPath("project/.venv" if item["category"] == "environment" else "python-framework")
    if not PurePosixPath(os.path.normpath(str(result))).is_relative_to(permitted):
        raise PreservationError("Runtime link would escape its declared tree")
    return result


def _resolve_runtime_member(relative: PurePosixPath, members: dict[str, str],
                            targets: dict[str, tuple[str, ...]]) -> bool:
    """Resolve virtual path components with bounded work and no host access."""
    roots = (PurePosixPath("project/.venv"), PurePosixPath("python-framework"))
    pending = list(reversed(relative.parts))
    current = PurePosixPath()
    available, expansions, steps = True, 0, 0
    while pending:
        steps += 1
        if steps > 8192:
            raise PreservationError("Runtime link resolution exceeded its component limit")
        part = pending.pop()
        if current.parts and members.get(str(current)) != "directory":
            available = False
        if part == ".":
            continue
        if part == "..":
            if current in roots or not current.parts:
                raise PreservationError("Runtime link would escape its declared tree")
            current = current.parent
            continue
        candidate = current / part
        if not any(candidate.is_relative_to(root) or root.is_relative_to(candidate) for root in roots):
            raise PreservationError("Runtime link would escape its declared tree")
        target = targets.get(str(candidate))
        if target is not None:
            expansions += 1
            if expansions > 64:
                raise PreservationError("Cyclic or excessively deep runtime links are unsupported")
            pending.extend(reversed(target))
            current = PurePosixPath()
        else:
            current = candidate
            if str(current) not in members:
                available = False
    return available and str(current) in members


def _validate_runtime_links(entries: list[dict], runtime: dict) -> int:
    """Check each link's declared target presence against the captured tree."""
    members, targets = {}, {}
    for item in entries:
        relative = PurePosixPath(_restore_relative(item).as_posix())
        _register_member(members, relative, item["kind"])
        if item["kind"] == "link":
            if type(item.get("target_exists")) is not bool:
                raise PreservationError("Runtime link target_exists must be a boolean")
            target = _link_destination(item, runtime).parts
            if item["target"].endswith(("/", "/.")):
                target += (".",)
            targets[str(relative)] = target
    missing = 0
    for item in entries:
        if item["kind"] == "link":
            relative = PurePosixPath(_restore_relative(item).as_posix())
            exists = _resolve_runtime_member(relative, members, targets)
            if exists != item["target_exists"]:
                raise PreservationError("Runtime link target presence differs from captured members")
            missing += not exists
    return missing


def _validate_manifest(manifest: dict) -> None:
    """Validate all paths and restore mappings before any archive-driven writes."""
    _fields(manifest, {"schema", "captured_at", "entries", "runtime", "workspace_relative",
                      "database_paths", "sidecars", "exclusions", "source_root", "atime_preserved",
                      "origin_attributions"}, "manifest")
    if manifest["schema"] != SCHEMA or manifest["atime_preserved"] is not False:
        raise PreservationError("Unknown preservation schema or access-time contract")
    if not isinstance(manifest["captured_at"], str) or datetime.fromisoformat(manifest["captured_at"]).tzinfo is None:
        raise PreservationError("Invalid capture timestamp")
    source = manifest["source_root"]
    if not isinstance(source, str) or not Path(source).is_absolute() or str(_absolute_path(source)) != source:
        raise PreservationError("Invalid original project root")
    workspace = _safe_relative(manifest["workspace_relative"])
    if not isinstance(manifest["exclusions"], list) or any(not isinstance(v, str) for v in manifest["exclusions"]):
        raise PreservationError("Invalid exclusion receipt")
    if not isinstance(manifest["origin_attributions"], list) or any(not isinstance(v, dict) for v in manifest["origin_attributions"]):
        raise PreservationError("Invalid external origin attribution")
    runtime = manifest["runtime"]
    if not isinstance(runtime, dict) or type(runtime.get("included")) is not bool:
        raise PreservationError("Invalid runtime manifest")
    if runtime["included"]:
        _fields(runtime, {"included", "framework_root", "environment_relative", "python_relative",
                          "site_packages_relative", "python_version", "platform", "same_host_only",
                          "creation_configuration"}, "runtime")
        if (runtime["framework_root"] != "/Library/Frameworks/Python.framework/Versions/3.14"
                or runtime["environment_relative"] != ".venv" or runtime["python_relative"] != ".venv/bin/python"
                or runtime["same_host_only"] is not True):
            raise PreservationError("Unsupported same-host runtime contract")
        site = _safe_relative(runtime["site_packages_relative"])
        if len(site.parts) != 4 or site.parts[:2] != (".venv", "lib") or site.parts[-1] != "site-packages":
            raise PreservationError("Invalid runtime package path")
        if any(not isinstance(runtime[key], str) or not runtime[key] for key in ("python_version", "platform")):
            raise PreservationError("Invalid runtime version information")
        cfg = runtime["creation_configuration"]
        if not isinstance(cfg, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in cfg.items()):
            raise PreservationError("Invalid runtime creation configuration")
    else:
        _fields(runtime, {"included"}, "excluded runtime")
    entries = manifest["entries"]
    if not isinstance(entries, list):
        raise PreservationError("Manifest entries must be a list")
    by_path, restored, explicit_restored = {}, {}, set()
    for item in entries:
        if not isinstance(item, dict):
            raise PreservationError("Manifest entry must be an object")
        relative = _safe_relative(item.get("path"))
        kind, category = item.get("kind"), item.get("category")
        if str(relative) in by_path or kind not in ("file", "directory", "link"):
            raise PreservationError("Duplicate path or unsupported manifest member")
        if relative.parts[0] == "databases":
            if len(relative.parts) < 2 or category != "database" or kind != "file":
                raise PreservationError("Invalid normalized database member")
        elif len(relative.parts) < 3 or relative.parts[:2] != ("payload", category) or category not in ("project", "environment", "python-framework"):
            raise PreservationError("Invalid payload category/path mapping")
        if category in ("environment", "python-framework") and not runtime["included"]:
            raise PreservationError("Runtime payload exists without a declared runtime")
        if kind == "link" and category not in ("environment", "python-framework"):
            raise PreservationError("Only runtime links may be recorded")
        fields = {"path", "category", "kind", "mode"}
        if category != "database":
            fields.add("metadata")
        if kind == "file":
            fields.update(("size", "sha256"))
        elif kind == "link":
            fields.update(("target", "target_exists"))
        _fields(item, fields, "manifest entry")
        if type(item["mode"]) is not int or not 0 <= item["mode"] <= 0o7777:
            raise PreservationError("Invalid captured file mode")
        if kind == "file" and (type(item["size"]) is not int or item["size"] < 0 or not _sha256(item["sha256"])):
            raise PreservationError("Invalid captured file size/hash")
        if category != "database":
            metadata_fields = {"device", "inode", "mode"} if kind == "directory" else {"device", "inode", "size", "mode", "mtime_ns", "ctime_ns", "nlink"}
            _fields(item["metadata"], metadata_fields, "source metadata")
            if any(type(v) is not int for v in item["metadata"].values()) or item["metadata"]["mode"] != item["mode"]:
                raise PreservationError("Invalid source metadata values")
            if kind == "file" and item["metadata"]["size"] != item["size"]:
                raise PreservationError("Source metadata/file size mismatch")
        restored_path = PurePosixPath(_restore_relative(item).as_posix())
        if str(restored_path) in explicit_restored:
            raise PreservationError("Multiple archive entries map to the same restore destination")
        explicit_restored.add(str(restored_path))
        _register_member(restored, restored_path, kind)
        by_path[str(relative)] = item
    _validate_runtime_links(entries, runtime)
    paths = manifest["database_paths"]
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths) or len(set(paths)) != len(paths):
        raise PreservationError("Invalid database path list")
    expected_databases = set()
    for relative in paths:
        _safe_relative(relative)
        raw, normalized = by_path.get("payload/project/" + relative), by_path.get("databases/" + relative)
        if not relative.endswith(".sqlite") or raw is None or raw["kind"] != "file" or normalized is None:
            raise PreservationError("Database lacks matching raw/normalized members")
        expected_databases.add("databases/" + relative)
    if {p for p in by_path if p.startswith("databases/")} != expected_databases:
        raise PreservationError("Unexpected normalized database member")
    if {p.removeprefix("payload/project/") for p, item in by_path.items()
            if p.startswith("payload/project/") and p.endswith(".sqlite") and item["kind"] == "file"} != set(paths):
        raise PreservationError("Raw database membership differs from database path list")
    if not {str(workspace / "cases.sqlite"), str(workspace / "checkpoints.sqlite")} <= set(paths):
        raise PreservationError("Established review database pair is absent")
    _fields(manifest["sidecars"], set(paths), "sidecar receipt")
    for relative, statuses in manifest["sidecars"].items():
        _fields(statuses, set(SIDECARS), "database sidecars")
        for suffix, present in statuses.items():
            member = by_path.get("payload/project/" + relative + suffix)
            if type(present) is not bool or present != (member is not None) or (member is not None and member["kind"] != "file"):
                raise PreservationError("Sidecar membership/receipt mismatch")


def _check_payload(output: Path, manifest: dict, *, complete: bool) -> None:
    """Verify exact membership and file bytes, including zero extra payload files."""
    _validate_manifest(manifest)
    expected = {"manifest.json": "file", "verification.json": "file"}
    if complete:
        expected["COMPLETE.json"] = "file"
    virtual = {}
    for item in manifest["entries"]:
        relative = _safe_relative(item["path"])
        kind = item["kind"]
        _register_member(virtual, relative, kind)
        if kind != "link":
            _register_member(expected, relative, kind)
        for parent in relative.parents:
            if str(parent) != ".":
                _register_member(expected, parent, "directory")
        if kind == "file":
            file = output / relative
            if _regular(file)["size"] != item["size"] or _hash(file) != item["sha256"]:
                raise PreservationError(f"Archive hash/size mismatch: {relative}")
    if _all_disk_members(output) != expected:
        raise PreservationError("Archive membership differs from manifest")


@_public_errors
def apply_archive(project: Path, workspace: Path, output: Path, *, include_runtime: bool = True) -> dict:
    """Capture originals, verify derivative databases, publish COMPLETE.json last."""
    project, workspace, output = _paths(project, workspace, output)
    marker_identity = None
    try:
        with _locked(workspace) as fd:
            runtime = _runtime(project, include_runtime)
            initial = _inventory(project, runtime)
            databases = _database_files(project, initial)
            _lsof(_open_files(workspace, databases), fd)
            _space(output, initial, sum(db.stat().st_size for db in databases))
            sidecars = _sidecar_receipt(project, databases)
            _private_mkdir(output.parent)
            output.mkdir(mode=0o700)  # Deliberately never rename over a possibly raced destination.
            for item in initial:
                target = output / item["path"]
                if item["kind"] == "directory":
                    _private_mkdir(target)
                elif item["kind"] == "link":
                    _private_mkdir(target.parent)  # Targets remain inert manifest metadata in archive.
                else:
                    _copy_file(Path(item["source"]), target, item["metadata"])
                    if _hash(target) != item["sha256"]:
                        raise PreservationError("Copy hash differs from original")
            if _inventory(project, runtime) != initial or _sidecar_receipt(project, databases) != sidecars:
                raise PreservationError("Source bytes, metadata or membership changed during capture")
            _lsof(_open_files(workspace, databases), fd)
            database_paths = [str(db.relative_to(project)) for db in databases]
            _backup_databases(output / "payload/project", database_paths, output / "databases")
            entries = [_manifest_entry(item) for item in initial]
            for relative in database_paths:
                target = output / "databases" / relative
                entries.append({"path": "databases/" + relative, "category": "database", "kind": "file",
                                "size": target.stat().st_size, "mode": 0o600, "sha256": _hash(target)})
            receipt = logical_verification(output / "payload/project", str(workspace.relative_to(project)), output / "databases")
            manifest = {"schema": SCHEMA, "captured_at": datetime.now(timezone.utc).isoformat(),
                        "entries": sorted(entries, key=lambda item: item["path"]), "runtime": runtime,
                        "workspace_relative": str(workspace.relative_to(project)), "database_paths": database_paths,
                        "sidecars": sidecars, "exclusions": sorted(EXCLUDED | SKIP_PARTS | {"*.pyc", "*.pyo", "unlisted root files"}),
                        "source_root": str(project), "atime_preserved": False,
                        "origin_attributions": receipt.get("external_origin_attributions", [])}
            _write_json(output / "manifest.json", manifest)
            _write_json(output / "verification.json", receipt)
            _check_payload(output, manifest, complete=False)
            for root, _, _ in os.walk(output, topdown=False):
                _fsync_dir(Path(root))
            if _inventory(project, runtime) != initial or _sidecar_receipt(project, databases) != sidecars:
                raise PreservationError("Source changed before archive publication")
            _lsof(_open_files(workspace, databases), fd)
            marker = {"schema": SCHEMA, "manifest_sha256": _hash(output / "manifest.json"),
                      "verification_sha256": _hash(output / "verification.json")}
            marker_identity = _publish_json(output / "COMPLETE.json", marker)
            _fsync_dir(output.parent)
    except BaseException:
        # This also covers the lock context's final source-metadata check.
        _remove_owned_marker(output / "COMPLETE.json", marker_identity)
        raise
    return {"status": "verified", "schema": SCHEMA, "file_count": sum(e["kind"] == "file" for e in entries),
            "database_count": len(databases), "manifest_sha256": marker["manifest_sha256"],
            "missing_runtime_link_count": sum(e["kind"] == "link" and not e["target_exists"] for e in entries),
            "original_bytes_and_modes_unchanged": True}


@_public_errors
def verify_archive(output: Path) -> dict:
    """Verify complete archive bytes and independently repeat its SQL checks."""
    output = _absolute_path(output)
    _no_symlinks(output)
    if not output.is_dir() or stat.S_IMODE(output.stat().st_mode) != 0o700:
        raise PreservationError("Expected a private archive directory")
    for name in ("COMPLETE.json", "manifest.json", "verification.json"):
        _regular(output / name)
    marker = _json_read(output / "COMPLETE.json")
    _fields(marker, {"schema", "manifest_sha256", "verification_sha256"}, "completion marker")
    if marker.get("schema") != SCHEMA or marker.get("manifest_sha256") != _hash(output / "manifest.json") or marker.get("verification_sha256") != _hash(output / "verification.json"):
        raise PreservationError("Incomplete archive or receipt hash mismatch")
    manifest = _json_read(output / "manifest.json")
    _check_payload(output, manifest, complete=True)
    _safe_relative(manifest["workspace_relative"])
    # The archive itself is never opened with SQLite, even for verification.
    with tempfile.TemporaryDirectory(prefix="polyglot-verify-") as temporary:
        staged = Path(temporary).resolve()
        for relative in manifest["database_paths"]:
            _safe_relative(relative)
            _copy_file(output / "databases" / relative, staged / relative)
        receipt = logical_verification(output / "payload/project", manifest["workspace_relative"], staged)
    if canonical_bytes(receipt) != canonical_bytes(_json_read(output / "verification.json")):
        raise PreservationError("Logical database receipt changed")
    return {"status": "verified", "manifest_sha256": marker["manifest_sha256"],
            "file_count": sum(e["kind"] == "file" for e in manifest["entries"]),
            "missing_runtime_link_count": sum(e["kind"] == "link" and not e["target_exists"] for e in manifest["entries"]),
            "database_count": len(manifest["database_paths"])}


def _restore_relative(item: dict) -> Path:
    relative = _safe_relative(item["path"])
    if relative.parts[0] == "databases":
        return Path(*relative.parts)
    if len(relative.parts) < 3 or relative.parts[0] != "payload":
        raise PreservationError("Invalid payload layout")
    category = relative.parts[1]
    prefix = {"project": Path("project"), "environment": Path("project/.venv"),
              "python-framework": Path("python-framework")}.get(category)
    if prefix is None:
        raise PreservationError("Unknown restore category")
    return prefix / Path(*relative.parts[2:])


def _restore_link(destination: Path, item: dict, manifest: dict) -> None:
    target = destination / _restore_relative(item)
    raw_target = item["target"]
    if item["category"] not in ("environment", "python-framework"):
        raise PreservationError("Only declared runtime links can be restored")
    _link_destination(item, manifest["runtime"])
    _private_mkdir(target.parent)
    target.symlink_to(raw_target)


def _check_restored_payload(destination: Path, manifest: dict) -> None:
    """Verify restored membership, bytes, modes and inert or live link targets."""
    _no_symlinks(destination)
    root = destination.lstat()
    if not stat.S_ISDIR(root.st_mode) or stat.S_IMODE(root.st_mode) != 0o700:
        raise PreservationError("Restore root is not a private directory")
    expected, explicit = {}, {}
    for item in manifest["entries"]:
        relative = PurePosixPath(_restore_relative(item).as_posix())
        _register_member(expected, relative, item["kind"])
        explicit[str(relative)] = item
    actual = {}
    def walk_error(error: OSError) -> None:
        raise error
    for base, directories, files in os.walk(destination, followlinks=False, onerror=walk_error):
        for name in directories + files:
            path = Path(base) / name
            relative = path.relative_to(destination).as_posix()
            metadata = path.lstat()
            kind = ("link" if stat.S_ISLNK(metadata.st_mode) else
                    "directory" if stat.S_ISDIR(metadata.st_mode) else
                    "file" if stat.S_ISREG(metadata.st_mode) else "special")
            if expected.get(relative) != kind:
                raise PreservationError(f"Unexpected restored member/type: {relative}")
            actual[relative] = kind
            item = explicit.get(relative)
            if kind == "link":
                if item is None or metadata.st_nlink != 1 or os.readlink(path) != item["target"]:
                    raise PreservationError(f"Restored link changed: {relative}")
            else:
                mode = item["mode"] & 0o777 if item is not None else 0o700
                if stat.S_IMODE(metadata.st_mode) != mode:
                    raise PreservationError(f"Restored permissions changed: {relative}")
                if kind == "file" and (item is None or metadata.st_nlink != 1
                        or metadata.st_size != item["size"] or _hash(path) != item["sha256"]):
                    raise PreservationError(f"Restored file bytes or independent inode changed: {relative}")
    if actual != expected:
        raise PreservationError("Restored membership differs from manifest")


@_public_errors
def restore_archive(output: Path, destination: Path, *, smoke: bool = False) -> dict:
    """Restore into an exclusive new private directory; leave the archive untouched."""
    output, destination = _absolute_path(output), _absolute_path(destination)
    verification = verify_archive(output)
    _no_symlinks(destination)
    if destination.exists() or destination.is_symlink() or destination.is_relative_to(output) or output.is_relative_to(destination):
        raise PreservationError("Restore requires a fresh non-overlapping destination")
    manifest = _json_read(output / "manifest.json", expected_sha256=verification["manifest_sha256"])
    _validate_manifest(manifest)
    if destination.is_relative_to(Path(manifest["source_root"])) and not destination.is_relative_to(Path(manifest["source_root"]) / "data/review-archives"):
        raise PreservationError("Restore destination overlaps original project inputs")
    required = sum(item.get("size", 0) for item in manifest["entries"]) + 128 * 1024 * 1024
    parent = destination.parent
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < required:
        raise PreservationError("Insufficient restore space")
    _private_mkdir(destination.parent)
    destination.mkdir(mode=0o700)
    for item in manifest["entries"]:
        target = destination / _restore_relative(item)
        if item["kind"] == "directory":
            _private_mkdir(target)
        elif item["kind"] == "file":
            _copy_file(output / item["path"], target)
            target.chmod(item["mode"] & 0o777)
            if _hash(target) != item["sha256"] or target.stat().st_size != item["size"]:
                raise PreservationError("Restored file hash differs")
    for item in manifest["entries"]:
        if item["kind"] == "link":
            _restore_link(destination, item, manifest)
    for item in sorted(manifest["entries"], key=lambda e: len(PurePosixPath(e["path"]).parts), reverse=True):
        if item["kind"] == "directory":
            (destination / _restore_relative(item)).chmod(item["mode"] & 0o777)
    _check_restored_payload(destination, manifest)
    # Re-derive from restored raw DB+sidecars, not merely copied normalized backups.
    with tempfile.TemporaryDirectory(prefix="polyglot-restore-check-") as temporary:
        staged = Path(temporary).resolve()
        _backup_databases(destination / "project", manifest["database_paths"], staged)
        receipt = logical_verification(destination / "project", manifest["workspace_relative"], staged)
    if canonical_bytes(receipt) != canonical_bytes(_json_read(output / "verification.json")):
        raise PreservationError("Restored logical evidence differs")
    _check_restored_payload(destination, manifest)
    runtime_receipt = {"status": "not_requested"}
    if smoke:
        try:
            runtime_receipt = restored_runtime_smoke(destination, manifest)
        finally:
            _check_restored_payload(destination, manifest)
        if not isinstance(runtime_receipt, dict) or runtime_receipt.get("ok") is not True:
            raise PreservationError("Restored runtime smoke failed: " + canonical_bytes(runtime_receipt).decode("utf-8"))
    if verify_archive(output) != verification:
        raise PreservationError("Archive changed during restoration")
    result = {"schema": SCHEMA, "status": "verified", "archive_manifest_sha256": verification["manifest_sha256"],
              "raw_bytes_verified": True, "logical_evidence_verified": True, "archive_unchanged": True,
              "missing_runtime_link_count": verification["missing_runtime_link_count"],
              "runtime_smoke": runtime_receipt}
    _publish_json(destination / "RESTORE-COMPLETE.json", result)
    return result


# Logical verification and isolated-runtime helpers follow. They do not import
# the live application or call ReviewService / SqliteSaver.


import hashlib
import json
import math
from pathlib import Path
import sqlite3
import struct
import unicodedata
from uuid import UUID


def _pv1_fail(message):
    raise PreservationError("logical verification: " + message)


def _pv1_canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _pv1_fail("unsupported canonical JSON value: " + type(exc).__name__)


def _pv1_digest(value):
    return hashlib.sha256(_pv1_canonical(value)).hexdigest()


def _pv1_file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _pv1_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _pv1_fail("duplicate JSON object key")
        result[key] = value
    return result


def _pv1_json(raw, label, *, canonical=False):
    if not isinstance(raw, (str, bytes)) or len(raw) > 16 * 1024 * 1024:
        _pv1_fail(label + ": missing or oversized JSON")
    try:
        value = json.loads(raw, object_pairs_hook=_pv1_pairs,
                           parse_constant=lambda token: _pv1_fail("nonfinite JSON number"))
        encoded = _pv1_canonical(value)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        _pv1_fail(label + ": invalid JSON: " + type(exc).__name__)
    if canonical and encoded != (raw.encode("utf-8") if isinstance(raw, str) else raw):
        _pv1_fail(label + ": noncanonical JSON")
    return value


class _PV1Extension:
    """Opaque MessagePack bytes, never an imported or constructed application class."""
    __slots__ = ("code", "payload", "decoded")

    def __init__(self, code, payload):
        self.code, self.payload = code, payload
        self.decoded = None


class _PV1MessagePack:
    """Bounded inert decoder for the pinned v1 primitive checkpoint format."""
    def __init__(self, raw):
        if not isinstance(raw, bytes) or len(raw) > 16 * 1024 * 1024:
            _pv1_fail("missing or oversized MessagePack blob")
        self.raw, self.position, self.nodes = raw, 0, 0

    def take(self, size):
        if size < 0 or self.position + size > len(self.raw):
            _pv1_fail("truncated MessagePack blob")
        start = self.position
        self.position += size
        return self.raw[start:self.position]

    def number(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def length(self, size):
        return self.number({1: ">B", 2: ">H", 4: ">I"}[size])

    def string(self, size):
        try:
            return self.take(size).decode("utf-8")
        except UnicodeError:
            _pv1_fail("invalid MessagePack UTF-8")

    def array(self, size, depth):
        if size > 100000:
            _pv1_fail("MessagePack array exceeds item limit")
        return [self.value(depth + 1) for _ in range(size)]

    def mapping(self, size, depth):
        if size > 100000:
            _pv1_fail("MessagePack map exceeds item limit")
        result = {}
        for _ in range(size):
            key = self.value(depth + 1)
            if type(key) not in (str, int, bool, bytes) or key in result:
                _pv1_fail("unsupported or duplicate MessagePack map key")
            result[key] = self.value(depth + 1)
        return result

    def value(self, depth=0):
        self.nodes += 1
        if depth > 64 or self.nodes > 200000:
            _pv1_fail("MessagePack nesting or node budget exceeded")
        code = self.number(">B")
        if code <= 0x7f:
            return code
        if code >= 0xe0:
            return code - 256
        if 0xa0 <= code <= 0xbf:
            return self.string(code & 31)
        if 0x90 <= code <= 0x9f:
            return self.array(code & 15, depth)
        if 0x80 <= code <= 0x8f:
            return self.mapping(code & 15, depth)
        if code == 0xc0:
            return None
        if code in (0xc2, 0xc3):
            return code == 0xc3
        formats = {0xca: ">f", 0xcb: ">d", 0xcc: ">B", 0xcd: ">H",
                   0xce: ">I", 0xcf: ">Q", 0xd0: ">b", 0xd1: ">h",
                   0xd2: ">i", 0xd3: ">q"}
        if code in formats:
            value = self.number(formats[code])
            if isinstance(value, float) and not math.isfinite(value):
                _pv1_fail("nonfinite MessagePack number")
            return value
        if code in (0xc4, 0xc5, 0xc6):
            return self.take(self.length({0xc4: 1, 0xc5: 2, 0xc6: 4}[code]))
        if code in (0xd9, 0xda, 0xdb):
            return self.string(self.length({0xd9: 1, 0xda: 2, 0xdb: 4}[code]))
        if code in (0xdc, 0xdd):
            return self.array(self.length(2 if code == 0xdc else 4), depth)
        if code in (0xde, 0xdf):
            return self.mapping(self.length(2 if code == 0xde else 4), depth)
        if code in (0xc7, 0xc8, 0xc9, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8):
            fixed = {0xd4: 1, 0xd5: 2, 0xd6: 4, 0xd7: 8, 0xd8: 16}
            size = fixed[code] if code in fixed else self.length({0xc7: 1, 0xc8: 2, 0xc9: 4}[code])
            extension_code = self.number(">b")
            return _PV1Extension(extension_code, self.take(size))
        _pv1_fail("unsupported MessagePack opcode")

    def decode(self):
        result = self.value()
        if self.position != len(self.raw):
            _pv1_fail("trailing bytes in MessagePack blob")
        return result


def _pv1_inert_shape(value, label, *, allow_interrupt=False, depth=0):
    """Accept JSON primitives and one pinned interrupt data shape, never classes."""
    if depth > 64:
        _pv1_fail(label + ": inert value nesting limit")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _pv1_inert_shape(item, label, allow_interrupt=allow_interrupt, depth=depth + 1)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            _pv1_fail(label + ": non-string key outside the pinned JSON state contract")
        for item in value.values():
            _pv1_inert_shape(item, label, allow_interrupt=allow_interrupt, depth=depth + 1)
        return
    if isinstance(value, _PV1Extension) and allow_interrupt and value.code == 2:
        payload = _PV1MessagePack(value.payload).decode()
        if (not isinstance(payload, list) or len(payload) != 3
                or payload[:2] != ["langgraph.types", "Interrupt"]):
            _pv1_fail(label + ": unknown MessagePack extension constructor shape")
        fields = payload[2]
        if not isinstance(fields, dict) or set(fields) != {"value", "id", "response_schema"}:
            _pv1_fail(label + ": unsupported pinned interrupt fields")
        if fields["response_schema"] is not None:
            _pv1_fail(label + ": v1 interrupt has unexpected response schema")
        _pv1_text(fields["id"], "interrupt ID", 128)
        _pv1_inert_shape(fields["value"], label + " interrupt value", depth=depth + 1)
        value.decoded = fields
        return
    _pv1_fail(label + ": unsupported bytes, extension, or non-JSON value")


def _pv1_decode(kind, raw, label, *, allow_interrupt=False):
    if not isinstance(raw, bytes):
        _pv1_fail(label + ": serialized value is not bytes")
    if kind == "msgpack":
        value = _PV1MessagePack(raw).decode()
    elif kind == "json":
        value = _pv1_json(raw, label)
    elif kind == "null" and raw == b"":
        value = None
    else:
        _pv1_fail(label + ": unsupported serialization type " + repr(kind))
    _pv1_inert_shape(value, label, allow_interrupt=allow_interrupt)
    return value


_PV1_STATE = ("schema_version", "workflow_version", "workflow_sha256", "thread_id",
              "audit_id", "parent_audit_id", "created_at", "query", "normalized_query",
              "recipe", "candidates", "evidence", "retrieval", "evidence_sha256",
              "review_revision", "review_status", "reviewer_decision", "explanation",
              "error", "audit_status", "audit_event_id", "audit_head_sha256")
_PV1_PACKET = ("schema_version", "workflow_version", "workflow_sha256", "thread_id", "audit_id",
               "query", "normalized_query", "recipe", "candidates", "evidence", "retrieval", "review_revision")
_PV1_REVIEW = ("submission_id", "review_revision", "evidence_sha256", "expected_checkpoint_id",
               "outcome", "candidate_entity_id", "reviewer_id", "reason", "submitted_at")
_PV1_HEADER = ("schema_version", "workflow_version", "workflow_sha256", "thread_id", "audit_id",
               "parent_audit_id", "created_at", "query", "recipe")
_PV1_FINAL = ("evidence_sha256", "reviewer_decision", "explanation", "error")


def _pv1_text(value, label, maximum=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _pv1_fail(label + ": invalid bounded text")


def _pv1_hex(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        _pv1_fail(label + ": invalid SHA-256")


def _pv1_packet(value, initial):
    if not isinstance(value, dict) or set(value) != set(_PV1_PACKET):
        _pv1_fail("packet fields differ from review-v1")
    for key in set(_PV1_HEADER) & set(_PV1_PACKET):
        if value[key] != initial[key]:
            _pv1_fail("packet/header mismatch: " + key)
    query = value["query"]
    if not isinstance(query, str) or len(query) > 200:
        _pv1_fail("packet query violates v1 normalization envelope")
    normalized = " ".join(unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", query).casefold()).split())
    if not normalized or len(normalized) > 200 or value["normalized_query"] != normalized:
        _pv1_fail("packet normalization mismatch")
    if type(value["review_revision"]) is not int or value["review_revision"] != 1:
        _pv1_fail("unsupported packet revision")
    candidates, evidence = value["candidates"], value["evidence"]
    if not isinstance(candidates, list) or len(candidates) > 5 or not isinstance(evidence, list) or len(evidence) > 10000:
        _pv1_fail("invalid candidate/evidence lists")
    evidence_fields = {"evidence_id", "entity_id", "alias_id", "original_text", "source", "synthetic", "provenance", "attribution"}
    candidate_fields = {"entity_id", "display_name", "entity_type", "rank", "matched_alias_id", "matched_alias", "evidence_ids", "similarity_score", "score_kind"}
    provenance_fields = {"snapshot_id", "dataset", "provider", "publisher", "source_url", "download_url", "retrieved_at", "source_updated_at", "export_version", "raw_sha256", "license_url"}
    by_id = {}
    for item in evidence:
        if not isinstance(item, dict) or set(item) != evidence_fields:
            _pv1_fail("invalid evidence fields")
        for key in evidence_fields - {"synthetic", "provenance"}:
            _pv1_text(item[key], "evidence " + key)
        if type(item["synthetic"]) is not bool or (not item["synthetic"] and not isinstance(item["provenance"], dict)):
            _pv1_fail("invalid evidence provenance/origin")
        provenance = item["provenance"]
        if provenance is not None:
            if not isinstance(provenance, dict) or set(provenance) != provenance_fields:
                _pv1_fail("invalid provenance fields")
            for key in provenance_fields - {"source_updated_at", "export_version"}:
                _pv1_text(provenance[key], "provenance " + key)
        if item["evidence_id"] in by_id:
            _pv1_fail("duplicate evidence ID")
        by_id[item["evidence_id"]] = item
    seen, used = set(), set()
    for rank, item in enumerate(candidates, 1):
        if not isinstance(item, dict) or set(item) != candidate_fields:
            _pv1_fail("invalid candidate fields")
        for key in ("entity_id", "display_name", "entity_type", "matched_alias_id", "matched_alias"):
            _pv1_text(item[key], "candidate " + key)
        if item["entity_id"] in seen or type(item["rank"]) is not int or item["rank"] != rank:
            _pv1_fail("duplicate candidate or invalid rank")
        seen.add(item["entity_id"])
        score = item["similarity_score"]
        if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1 or item["score_kind"] != "cosine_similarity":
            _pv1_fail("invalid candidate score")
        refs = item["evidence_ids"]
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
            _pv1_fail("invalid candidate evidence references")
        linked = [by_id.get(ref) for ref in refs]
        if any(e is None or e["entity_id"] != item["entity_id"] for e in linked):
            _pv1_fail("cross-entity/missing evidence reference")
        if not any(e["alias_id"] == item["matched_alias_id"] and e["original_text"] == item["matched_alias"] for e in linked):
            _pv1_fail("winning alias missing from packet")
        used.update(refs)
    if used != set(by_id):
        _pv1_fail("orphan evidence")
    if not isinstance(value["retrieval"], dict) or value["retrieval"].get("reranker") != "disabled" or value["retrieval"].get("top_k") != 5:
        _pv1_fail("unsupported v1 retrieval manifest")
    return _pv1_digest(value)


def _pv1_submission(value, packet, packet_hash):
    if not isinstance(value, dict) or set(value) != set(_PV1_REVIEW):
        _pv1_fail("submission fields differ from review-v1")
    for key in ("submission_id", "evidence_sha256", "expected_checkpoint_id", "reviewer_id", "reason", "submitted_at"):
        _pv1_text(value[key], "submission " + key, 1000)
    try:
        UUID(value["submission_id"])
    except (ValueError, TypeError, AttributeError):
        _pv1_fail("submission ID is not a UUID")
    if type(value["review_revision"]) is not int or value["review_revision"] != 1 or value["evidence_sha256"] != packet_hash:
        _pv1_fail("submission packet/revision mismatch")
    if value["outcome"] == "candidate_for_follow_up":
        if value["candidate_entity_id"] not in {c["entity_id"] for c in packet["candidates"]}:
            _pv1_fail("submission selected a record outside its packet")
    elif value["outcome"] in ("none_selected", "unresolved"):
        if value["candidate_entity_id"] is not None:
            _pv1_fail("unselected review has a candidate ID")
    else:
        _pv1_fail("unknown review outcome")


def _pv1_quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _pv1_rows(db, query, parameters=(), maximum=100000):
    result = db.execute(query, parameters).fetchmany(maximum + 1)
    if len(result) > maximum:
        _pv1_fail("SQL row budget exceeded")
    return result


def _pv1_database(path, relative):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        _pv1_fail("missing, symlinked, or oversized normalized database: " + relative)
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        _pv1_fail("normalized database still has journal/sidecar files: " + relative)
    before = _pv1_file_hash(path)
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        if [row[0] for row in _pv1_rows(db, "PRAGMA integrity_check")] != ["ok"]:
            _pv1_fail("SQLite integrity failure: " + relative)
        if _pv1_rows(db, "PRAGMA foreign_key_check"):
            _pv1_fail("SQLite foreign-key failure: " + relative)
        schema = [dict(row) for row in _pv1_rows(db, "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables = {}
        for row in schema:
            if row["type"] != "table":
                continue
            if "VIRTUAL TABLE" in (row["sql"] or "").upper():
                _pv1_fail("unsupported virtual table: " + relative)
            name = row["name"]
            tables[name] = {"row_count": db.execute("SELECT COUNT(*) FROM " + _pv1_quote(name)).fetchone()[0],
                            "columns": [dict(r) for r in db.execute("PRAGMA table_info(" + _pv1_quote(name) + ")")],
                            "foreign_keys": [dict(r) for r in db.execute("PRAGMA foreign_key_list(" + _pv1_quote(name) + ")")]}
        receipt = {"path": relative, "sha256": before, "bytes": path.stat().st_size,
                   "user_version": db.execute("PRAGMA user_version").fetchone()[0],
                   "schema_sha256": _pv1_digest(schema), "schema": schema, "tables": tables,
                   "integrity_check": "ok", "foreign_key_check": "ok"}
        return db, receipt
    except BaseException:
        db.close()
        raise


def _pv1_expect_schema(receipt, expected, version=None):
    if version is not None and receipt["user_version"] != version:
        _pv1_fail("unsupported database version: " + receipt["path"])
    if set(receipt["tables"]) != set(expected):
        _pv1_fail("unexpected table set: " + receipt["path"])
    if any(row["type"] in ("trigger", "view") for row in receipt["schema"]):
        _pv1_fail("unexpected trigger/view in v1 review store")
    for table, columns in expected.items():
        if tuple(column["name"] for column in receipt["tables"][table]["columns"]) != columns:
            _pv1_fail("unexpected v1 columns: " + table)
        integer_columns = {"revision", "sequence", "idx"}
        blob_columns = {"checkpoint", "metadata", "value"}
        nullable = {"cases": {"audit_id", "parent_audit_id"},
                    "review_submissions": {"submission_id"},
                    "checkpoints": {"parent_checkpoint_id", "type", "checkpoint", "metadata"},
                    "writes": {"type", "value"}}.get(table, set())
        for column in receipt["tables"][table]["columns"]:
            name = column["name"]
            declared = "INTEGER" if name in integer_columns else "BLOB" if name in blob_columns else "TEXT"
            default = "''" if name in ("checkpoint_ns", "task_path") else None
            if (column["type"].upper() != declared or column["notnull"] != int(name not in nullable)
                    or column["dflt_value"] != default):
                _pv1_fail("unexpected v1 column declaration: " + table + "." + name)


def _pv1_constraints(db, receipt, primary_keys, foreign_keys, extra_unique):
    """Check declared keys too: valid rows alone do not prove the v1 schema."""
    for table, wanted in primary_keys.items():
        columns = receipt["tables"][table]["columns"]
        actual = tuple(column["name"] for column in sorted(columns, key=lambda c: c["pk"]) if column["pk"])
        if actual != wanted:
            _pv1_fail("unexpected primary key: " + table)
        groups = {}
        for row in receipt["tables"][table]["foreign_keys"]:
            if row["on_update"] != "NO ACTION" or row["on_delete"] != "NO ACTION":
                _pv1_fail("unexpected foreign-key action: " + table)
            groups.setdefault(row["id"], []).append(row)
        actual_fks = set()
        for group in groups.values():
            ordered = sorted(group, key=lambda row: row["seq"])
            actual_fks.add((ordered[0]["table"], tuple(row["from"] for row in ordered), tuple(row["to"] for row in ordered)))
        if actual_fks != set(foreign_keys.get(table, ())):
            _pv1_fail("unexpected declared foreign keys: " + table)
        unique = set()
        for index in db.execute("PRAGMA index_list(" + _pv1_quote(table) + ")"):
            if index["unique"] and not index["partial"]:
                unique.add(tuple(row["name"] for row in db.execute("PRAGMA index_info(" + _pv1_quote(index["name"]) + ")")))
        if not set(extra_unique.get(table, ())).issubset(unique):
            _pv1_fail("missing v1 unique constraint: " + table)


def _pv1_review_pair(ledger, checkpoint_db, ledger_receipt, checkpoint_receipt):
    _pv1_expect_schema(ledger_receipt, {
        "cases": ("audit_id", "thread_id", "initial_json", "parent_audit_id"),
        "review_packets": ("audit_id", "revision", "packet_json", "sha256"),
        "review_submissions": ("submission_id", "audit_id", "revision", "payload_json", "sha256"),
        "audit_events": ("audit_id", "sequence", "event_key", "payload_json", "created_at", "previous_sha256", "event_sha256")}, 1)
    _pv1_expect_schema(checkpoint_receipt, {
        "checkpoints": ("thread_id", "checkpoint_ns", "checkpoint_id", "parent_checkpoint_id", "type", "checkpoint", "metadata"),
        "writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "task_path", "idx", "channel", "type", "value")}, 0)
    _pv1_constraints(ledger, ledger_receipt,
        {"cases": ("audit_id",), "review_packets": ("audit_id", "revision"),
         "review_submissions": ("submission_id",), "audit_events": ("audit_id", "sequence")},
        {"cases": {("cases", ("parent_audit_id",), ("audit_id",))},
         "review_packets": {("cases", ("audit_id",), ("audit_id",))},
         "review_submissions": {("review_packets", ("audit_id", "revision"), ("audit_id", "revision"))},
         "audit_events": {("cases", ("audit_id",), ("audit_id",))}},
        {"cases": {("thread_id",)}, "review_submissions": {("audit_id", "revision")},
         "audit_events": {("audit_id", "event_key")}})
    _pv1_constraints(checkpoint_db, checkpoint_receipt,
        {"checkpoints": ("thread_id", "checkpoint_ns", "checkpoint_id"),
         "writes": ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx")}, {}, {})
    packet_sql = next(row["sql"] for row in ledger_receipt["schema"] if row["name"] == "review_packets")
    if "check(revision=1)" not in "".join(packet_sql.lower().split()):
        _pv1_fail("missing v1 fixed packet-revision constraint")
    cases = _pv1_rows(ledger, "SELECT * FROM cases ORDER BY audit_id", maximum=1000)
    case_by_thread = {row["thread_id"]: row for row in cases}
    if len(case_by_thread) != len(cases):
        _pv1_fail("duplicate case thread")
    checkpoints, by_thread = {}, {}
    for row in _pv1_rows(checkpoint_db, "SELECT * FROM checkpoints ORDER BY thread_id,checkpoint_ns,checkpoint_id"):
        key = (row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"])
        if row["thread_id"] not in case_by_thread or row["checkpoint_ns"] != "" or key in checkpoints:
            _pv1_fail("orphan, duplicate, or unsupported checkpoint namespace")
        value = _pv1_decode(row["type"], row["checkpoint"], "checkpoint")
        if not isinstance(value, dict) or value.get("id") != row["checkpoint_id"] or not isinstance(value.get("channel_values"), dict):
            _pv1_fail("checkpoint row/blob identity mismatch")
        for field in ("channel_versions", "versions_seen"):
            if not isinstance(value.get(field), dict):
                _pv1_fail("missing checkpoint scheduling metadata")
        metadata = _pv1_json(row["metadata"], "checkpoint metadata") if row["metadata"] is not None else {}
        if not isinstance(metadata, dict):
            _pv1_fail("checkpoint metadata is not an object")
        item = {"row": dict(row), "value": value, "metadata": metadata}
        checkpoints[key] = item
        by_thread.setdefault(row["thread_id"], []).append(item)
    for key, item in checkpoints.items():
        parent = item["row"]["parent_checkpoint_id"]
        # Pinned checkpoint IDs increase monotonically. A strict decrease on
        # every parent edge proves acyclicity without a quadratic chain walk.
        if parent is not None and ((key[0], key[1], parent) not in checkpoints or parent >= key[2]):
            _pv1_fail("missing or nonmonotonic/cyclic checkpoint parent")
    writes = {}
    write_receipts = []
    for row in _pv1_rows(checkpoint_db, "SELECT * FROM writes ORDER BY thread_id,checkpoint_ns,checkpoint_id,task_id,idx"):
        key = (row["thread_id"], row["checkpoint_ns"], row["checkpoint_id"])
        if key not in checkpoints:
            _pv1_fail("orphan checkpoint write")
        write_value = _pv1_decode(row["type"], row["value"], "checkpoint write",
                                  allow_interrupt=row["channel"] == "__interrupt__")
        if row["channel"] == "__interrupt__":
            if (not isinstance(write_value, list) or len(write_value) != 1
                    or not isinstance(write_value[0], _PV1Extension)):
                _pv1_fail("unexpected v1 interrupt control-write shape")
            interrupt = write_value[0].decoded["value"]
            fields = {"thread_id", "audit_id", "review_revision", "evidence_sha256", "message"}
            if not isinstance(interrupt, dict) or set(interrupt) != fields:
                _pv1_fail("unexpected v1 human-review interrupt payload")
            channels = checkpoints[key]["value"]["channel_values"]
            for field in fields - {"message"}:
                if interrupt[field] != channels.get(field):
                    _pv1_fail("interrupt payload differs from its checkpoint: " + field)
            _pv1_text(interrupt["message"], "interrupt message", 5000)
        writes.setdefault(key, []).append(row["channel"])
        write_receipts.append({k: row[k] for k in ("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "task_path", "idx", "channel", "type")} | {"value_sha256": hashlib.sha256(row["value"]).hexdigest()})
    results, states = [], {}
    for case in cases:
        aid, thread = case["audit_id"], case["thread_id"]
        initial = _pv1_json(case["initial_json"], "case initial", canonical=True)
        if not isinstance(initial, dict) or set(initial) != set(_PV1_STATE):
            _pv1_fail("initial fields differ from review-v1")
        if initial["audit_id"] != aid or initial["thread_id"] != thread or initial["parent_audit_id"] != case["parent_audit_id"]:
            _pv1_fail("case row/header identity mismatch")
        if initial["schema_version"] != "review-v1" or initial["workflow_version"] != "phase-07a-v1":
            _pv1_fail("unsupported case schema/workflow")
        _pv1_hex(initial["workflow_sha256"], "workflow digest")
        events, previous, ordered = {}, "", []
        for count, row in enumerate(_pv1_rows(ledger, "SELECT * FROM audit_events WHERE audit_id=? ORDER BY sequence", (aid,)), 1):
            envelope = {k: row[k] for k in ("audit_id", "sequence", "event_key", "payload_json", "created_at", "previous_sha256")}
            if row["sequence"] != count or row["previous_sha256"] != previous or _pv1_digest(envelope) != row["event_sha256"]:
                _pv1_fail("audit chain failure for " + aid)
            if row["event_key"] in events:
                _pv1_fail("duplicate audit event key")
            payload = _pv1_json(row["payload_json"], "audit payload", canonical=True)
            events[row["event_key"]] = {"row": dict(row), "payload": payload}
            ordered.append(row["event_key"])
            previous = row["event_sha256"]
        if not ordered or ordered[0] != "request_created" or events["request_created"]["payload"] != initial:
            _pv1_fail("missing/mismatched case creation event")
        semantic = [key for key in ordered if not key.startswith("attempt:")]
        if any(key not in ("request_created", "suggestions_ready", "review_submitted", "case_finalized") for key in semantic):
            _pv1_fail("unknown v1 semantic audit event")
        if semantic != sorted(semantic, key=("request_created", "suggestions_ready", "review_submitted", "case_finalized").index):
            _pv1_fail("invalid semantic audit event order")
        packet_rows = _pv1_rows(ledger, "SELECT * FROM review_packets WHERE audit_id=?", (aid,))
        submission_rows = _pv1_rows(ledger, "SELECT * FROM review_submissions WHERE audit_id=?", (aid,))
        if len(packet_rows) > 1 or len(submission_rows) > 1:
            _pv1_fail("multiple v1 packet/submission revisions")
        packet, packet_hash, submission, submission_hash = None, None, None, None
        if packet_rows:
            row = packet_rows[0]
            packet = _pv1_json(row["packet_json"], "saved packet", canonical=True)
            packet_hash = _pv1_packet(packet, initial)
            if row["revision"] != 1 or row["sha256"] != packet_hash or events.get("suggestions_ready", {}).get("payload") != {"packet_sha256": packet_hash}:
                _pv1_fail("packet row/event digest mismatch")
        elif "suggestions_ready" in events:
            _pv1_fail("missing saved packet")
        if submission_rows:
            row = submission_rows[0]
            submission = _pv1_json(row["payload_json"], "saved submission", canonical=True)
            if packet is None:
                _pv1_fail("submission has no packet")
            _pv1_submission(submission, packet, packet_hash)
            submission_hash = _pv1_digest(submission)
            if row["revision"] != 1 or row["submission_id"] != submission["submission_id"] or row["sha256"] != submission_hash or events.get("review_submitted", {}).get("payload") != {"submission": submission}:
                _pv1_fail("submission row/event identity mismatch")
        elif "review_submitted" in events:
            _pv1_fail("missing saved submission")
        final = events.get("case_finalized")
        if final:
            payload = final["payload"]
            if not isinstance(payload, dict) or set(payload) != set(_PV1_FINAL) or payload["evidence_sha256"] != packet_hash or payload["reviewer_decision"] != submission:
                _pv1_fail("final audit payload differs from packet/submission")
            if not payload["error"] and submission is None:
                _pv1_fail("successful finalization lacks a review")
            if payload["error"] and (packet is not None or submission is not None):
                _pv1_fail("unsupported v1 error finalization after review")
        snapshots = by_thread.get(thread, [])
        state_by_checkpoint = {}
        for item in snapshots:
            channels = item["value"]["channel_values"]
            if set(_PV1_STATE).issubset(channels):
                state = {key: channels[key] for key in _PV1_STATE}
                _pv1_canonical(state)  # rejects opaque extension/byte objects in application state
                for key in _PV1_HEADER:
                    if state[key] != initial[key]:
                        _pv1_fail("checkpoint/header mismatch: " + key)
                if state["evidence_sha256"] is not None:
                    checkpoint_packet = {key: state[key] for key in _PV1_PACKET}
                    actual = _pv1_packet(checkpoint_packet, initial)
                    if actual != state["evidence_sha256"] or (packet is not None and checkpoint_packet != packet):
                        _pv1_fail("checkpoint/saved packet mismatch")
                if state["reviewer_decision"] is not None and state["reviewer_decision"] != submission:
                    _pv1_fail("checkpoint/saved submission mismatch")
                if state["audit_status"] == "committed":
                    if not final or {key: state[key] for key in _PV1_FINAL} != final["payload"]:
                        _pv1_fail("committed checkpoint lacks matching final audit")
                    if state["audit_event_id"] != aid + ":" + str(final["row"]["sequence"]) or state["audit_head_sha256"] != final["row"]["event_sha256"]:
                        _pv1_fail("committed checkpoint receipt mismatch")
                state_by_checkpoint[item["row"]["checkpoint_id"]] = state
            elif channels.get("__start__") != initial:
                _pv1_fail("unsupported partial checkpoint application state")
        if submission is not None:
            reviewed_id = submission["expected_checkpoint_id"]
            reviewed = state_by_checkpoint.get(reviewed_id)
            if reviewed is None or reviewed["evidence_sha256"] != packet_hash or reviewed["review_status"] != "pending":
                _pv1_fail("submission expected checkpoint is missing/foreign/not pending")
        latest = snapshots[-1] if snapshots else None
        latest_id = latest["row"]["checkpoint_id"] if latest else None
        state = state_by_checkpoint.get(latest_id)
        completed = bool(state and state["audit_status"] == "committed")
        if latest is None and (packet is not None or submission is not None or final is not None):
            _pv1_fail("durable review evidence exists but checkpoint history is missing")
        if final and (state is None or {key: state[key] for key in _PV1_FINAL} != final["payload"]):
            _pv1_fail("final audit disagrees with latest checkpoint evidence")
        if completed and any(channel in ("__interrupt__", "__error__", "__resume__", "__tasks__") for channel in writes.get((thread, "", latest_id), [])):
            _pv1_fail("completed checkpoint has unexpected pending control writes")
        if submission and latest:
            ancestors, cursor = set(), latest_id
            while cursor is not None:
                ancestors.add(cursor)
                cursor = checkpoints[(thread, "", cursor)]["row"]["parent_checkpoint_id"]
            if submission["expected_checkpoint_id"] not in ancestors:
                _pv1_fail("reviewed checkpoint is not an ancestor of latest state")
        status = ("completed_audit_checkpoint" if completed else "final_audit_pending_checkpoint" if final else
                  "submission_accepted_pending_completion" if submission else "packet_saved_pending_review" if packet else
                  "checkpoint_before_packet" if latest else "created_before_first_checkpoint")
        checkpoint_summaries = [{"checkpoint_id": item["row"]["checkpoint_id"],
                                 "parent_checkpoint_id": item["row"]["parent_checkpoint_id"],
                                 "type": item["row"]["type"],
                                 "blob_sha256": hashlib.sha256(item["row"]["checkpoint"]).hexdigest(),
                                 "metadata_sha256": _pv1_digest(item["metadata"])} for item in snapshots]
        result = {"audit_id": aid, "thread_id": thread, "schema_version": initial["schema_version"],
                  "workflow_version": initial["workflow_version"], "workflow_sha256": initial["workflow_sha256"],
                  "initial_sha256": _pv1_digest(initial), "packet_sha256": packet_hash,
                  "submission_id": submission["submission_id"] if submission else None,
                  "submission_sha256": submission_hash, "audit_count": len(ordered), "audit_head_sha256": previous,
                  "event_keys": ordered, "final_event_sha256": final["row"]["event_sha256"] if final else None,
                  "latest_checkpoint_id": latest_id, "latest_state_sha256": _pv1_digest(state) if state else None,
                  "status": status, "completed_audit_checkpoint": completed, "checkpoints": checkpoint_summaries,
                  "annotation_origin": "unknown"}
        results.append(result)
        states[aid] = {"initial": initial, "packet": packet, "submission": submission,
                       "latest_state": state, "states": state_by_checkpoint, "receipt": result}
    # The ledger's own FKs cover these relationships; retain explicit checks for altered schemas.
    for table in ("review_packets", "review_submissions", "audit_events"):
        if ledger.execute("SELECT COUNT(*) FROM " + table + " x LEFT JOIN cases c ON c.audit_id=x.audit_id WHERE c.audit_id IS NULL").fetchone()[0]:
            _pv1_fail("orphan ledger rows: " + table)
    return results, states, {"checkpoint_rows": len(checkpoints), "write_rows": len(write_receipts),
                            "writes_manifest_sha256": _pv1_digest(write_receipts),
                            "decoder": "bounded-inert-stdlib-msgpack-v1", "graph_executed": False}


def _pv1_saved_demo(project, workspace_relative, states):
    directory = project / workspace_relative / "verification"
    names = ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review-form.json",
             "demo-review.json", "demo-recover.json", "demo-audit-verify.json")
    exists = [(directory / name).exists() for name in names]
    if not any(exists):
        return {"present": False, "verified": False}, []
    if not all(exists):
        _pv1_fail("saved demo artifact set is incomplete")
    docs, evidence = {}, []
    for name in names:
        path = directory / name
        if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
            _pv1_fail("symlinked or oversized demo artifact")
        docs[name] = _pv1_json(path.read_bytes(), name)
        evidence.append({"path": path.relative_to(project).as_posix(), "sha256": _pv1_file_hash(path)})
    start, done = docs["demo-start.json"], docs["demo-review.json"]
    aid = "e449b466-466d-4b81-9a29-cb3c9d957823"
    thread = "446f2137-621a-4426-8f95-9c82e07bcacf"
    final_id = "1f1ce0fc-cda5-66e0-8007-f6f0502a7876"
    pending_id = "1f1ce0fa-af59-63b4-8004-4f329c922484"
    head = "b62fc08e60b609a5c56e6cd4a4710f60e15b5a43c352ed76cc9220a7f1848a9e"
    actual = states.get(aid)
    if actual is None or done.get("thread_id") != thread or done.get("audit_id") != aid:
        _pv1_fail("known demo case identity mismatch")
    receipt = actual["receipt"]
    if receipt["audit_count"] != 4 or receipt["audit_head_sha256"] != head or receipt["latest_checkpoint_id"] != final_id or not receipt["completed_audit_checkpoint"]:
        _pv1_fail("known demo audit/checkpoint anchor mismatch")
    if done.get("state") != actual["latest_state"] or done.get("checkpoint_id") != final_id or done.get("completed") is not True or done.get("pending_interrupt") is not False or done.get("next") != []:
        _pv1_fail("completed demo transcript differs from restored checkpoint")
    if start.get("audit_id") != aid or start.get("thread_id") != thread or start.get("state") != actual["states"].get(pending_id) or start.get("checkpoint_id") != pending_id or start.get("pending_interrupt") is not True or start.get("completed") is not False or start.get("next") != ["human_review"]:
        _pv1_fail("pending demo transcript differs from reviewed checkpoint")
    pending_audit = {"audit_id": aid, "count": 2,
                     "head_sha256": "f42547719eecbddc2d95876bf373df3ec3aeb3e713d404a164b1d1ce9b4f7e45"}
    if start.get("audit") != pending_audit:
        _pv1_fail("saved pending demo audit anchor mismatch")
    if start != docs["demo-status.json"] or start != docs["demo-recover-pending.json"] or done != docs["demo-recover.json"]:
        _pv1_fail("saved demo restart transcripts disagree")
    expected_audit = {"audit_id": aid, "count": 4, "head_sha256": head}
    if done.get("audit") != expected_audit or docs["demo-audit-verify.json"] != {"audit": expected_audit, "completed": True}:
        _pv1_fail("saved demo audit transcript mismatch")
    submission = actual["submission"]
    if docs["demo-review-form.json"] != {key: value for key, value in submission.items() if key not in ("reviewer_id", "submitted_at")}:
        _pv1_fail("saved demo form differs from durable submission")
    if not submission["reason"].startswith("Simulated fictional demo annotation by the assistant:") or "This is not a real analyst identity decision." not in submission["reason"]:
        _pv1_fail("known demo lacks explicit simulation attribution")
    for name in ("demo-start.json", "demo-status.json", "demo-recover-pending.json", "demo-review.json", "demo-recover.json"):
        if {key: docs[name]["state"][key] for key in _PV1_PACKET} != actual["packet"]:
            _pv1_fail("demo transcript packet differs from durable packet")
    report = project / "docs/progress/phase-07a.md"
    if report.exists():
        if report.is_symlink() or report.stat().st_size > 2 * 1024 * 1024:
            _pv1_fail("invalid historical report file")
        if "Simulated fictional demo annotation by the assistant" not in report.read_text(encoding="utf-8"):
            _pv1_fail("historical report no longer corroborates demo origin")
        evidence.append({"path": "docs/progress/phase-07a.md", "sha256": _pv1_file_hash(report)})
    receipt["annotation_origin"] = "simulated_demo"
    attribution = {"audit_id": aid, "thread_id": thread, "submission_id": submission["submission_id"],
                   "origin": "simulated_demo", "basis": "explicit_saved_simulation_statement",
                   "packet_sha256": receipt["packet_sha256"], "audit_head_sha256": head,
                   "evidence": evidence, "original_record_modified": False,
                   "local_actor_label_is_not_human_authentication": True,
                   "independent_trusted_anchor": False}
    return {"present": True, "verified": True, "audit_id": aid,
            "pending_checkpoint_id": pending_id, "final_checkpoint_id": final_id,
            "evidence": evidence}, [attribution]


def logical_verification(project: Path, workspace_relative: str, database_root: Path) -> dict:
    """Verify normalized COPIES and return a private receipt; perform no mutation.

    ``project`` must be the raw copied project. ``database_root`` must contain
    normalized databases at the same relative paths, without WAL/SHM journals.
    This helper intentionally never follows database paths from saved recipes.
    """
    project, database_root = Path(project).resolve(), Path(database_root).resolve()
    relative = Path(workspace_relative)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _pv1_fail("review workspace must be a safe project-relative path")
    if project == database_root or not project.is_dir() or not database_root.is_dir():
        _pv1_fail("require distinct copied-project and normalized-database roots")
    ledger_relative = (relative / "cases.sqlite").as_posix()
    checkpoint_relative = (relative / "checkpoints.sqlite").as_posix()
    databases = {}
    connections = []
    paths = {}
    try:
        for path in sorted(database_root.rglob("*")):
            if path.is_symlink():
                _pv1_fail("symlink in normalized database tree")
            if not path.is_file():
                continue
            with path.open("rb") as source:
                header = source.read(16)
            if header != b"SQLite format 3\x00" and path.suffix.lower() not in (".sqlite", ".sqlite3", ".db"):
                continue
            name = path.relative_to(database_root).as_posix()
            db, receipt = _pv1_database(path, name)
            connections.append(db)
            databases[name] = (db, receipt)
            paths[name] = path
        if ledger_relative not in databases or checkpoint_relative not in databases:
            _pv1_fail("normalized review database pair is missing")
        ledger, ledger_receipt = databases[ledger_relative]
        checkpoints, checkpoint_receipt = databases[checkpoint_relative]
        cases, states, checkpoint_summary = _pv1_review_pair(ledger, checkpoints, ledger_receipt, checkpoint_receipt)
        demo, attribution = _pv1_saved_demo(project, relative, states)
        result = {"verifier": "step00-v1-logical-verification-v1", "read_only": True,
                  "workspace_relative": relative.as_posix(), "databases": [databases[key][1] for key in sorted(databases)],
                  "case_count": len(cases), "cases": cases, "checkpoint_store": checkpoint_summary,
                  "saved_demo": demo, "external_origin_attributions": attribution,
                  "scope": "structural case/checkpoint coherence; no graph execution or general archive viewer",
                  "provenance": {"inputs": "normalized derivatives and copied saved transcripts",
                                 "original_databases_opened": False, "runtime_class_revival": False,
                                 "raw_queries_or_notes_in_receipt": False}}
        _pv1_canonical(result)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        _pv1_fail(type(exc).__name__ + " while reading normalized copies: " + str(exc))
    finally:
        for db in connections:
            db.close()
    for name, (_, receipt) in databases.items():
        if _pv1_file_hash(paths[name]) != receipt["sha256"]:
            _pv1_fail("normalized database changed during verification: " + name)
        if any(Path(str(paths[name]) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            _pv1_fail("verification created a SQLite sidecar")
    return result


import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any


_RESULT_PREFIX = "POLYGLOT_STEP00_RUNTIME_JSON="
_TIMEOUT_SECONDS = 120
_OUTPUT_LIMIT = 64_000

_SMOKE_CHILD = r'''
import importlib
import importlib.metadata
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import sysconfig
import traceback

RESULT_PREFIX = "POLYGLOT_STEP00_RUNTIME_JSON="

def inside(path, root):
    try:
        Path(path).resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False

def run():
    project = Path(sys.argv[1]).resolve(strict=True)
    site_packages = Path(sys.argv[2]).resolve(strict=True)
    expected_framework = Path(sys.argv[3]).resolve(strict=True)
    scratch = Path(sys.argv[4]).resolve(strict=True)
    source = (project / "src").resolve(strict=True)
    if not inside(source, project) or not inside(site_packages, project):
        raise RuntimeError("restored source or site-packages escapes restored project")
    if not sys.flags.isolated or not sys.flags.no_site or not sys.dont_write_bytecode:
        raise RuntimeError("required -B -I -S interpreter flags are missing")
    if Path(sys.base_prefix).resolve() != expected_framework:
        raise RuntimeError("running interpreter framework differs from preservation manifest")
    if inside(scratch, project) or inside(project, scratch) or not scratch.is_dir():
        raise RuntimeError("scratch must be a separate private directory")
    if scratch.stat().st_mode & 0o077:
        raise RuntimeError("scratch directory must be private to its owner")
    if Path(os.environ.get("TMPDIR", "")).resolve() != scratch:
        raise RuntimeError("TMPDIR differs from the designated private scratch")

    # -S prevents execution of the preserved editable .pth and site startup hooks.
    # Retain only the interpreter's isolated standard-library paths, then add the
    # two restored import roots explicitly.  Never use site.addsitedir here.
    inherited_paths = list(sys.path)
    if any("site-packages" in Path(p).parts for p in inherited_paths if p):
        raise RuntimeError("isolated no-site interpreter unexpectedly has site-packages")
    sys.path[:0] = [str(source), str(site_packages)]

    denied_events = []
    scratch_mutation_count = 0
    model_root = project / "data" / "models"

    def deny(event, detail):
        denied_events.append({"event": event, "detail": str(detail)})
        raise PermissionError("runtime smoke prohibits " + event)

    def fd_path(descriptor):
        # This helper intentionally targets the preserved macOS runtime.  F_GETPATH
        # resolves directory-relative cleanup operations without trusting a raw fd.
        if sys.platform != "darwin":
            deny("unresolved_file_descriptor", descriptor)
        raw = fcntl.fcntl(descriptor, getattr(fcntl, "F_GETPATH", 50), bytes(1024))
        return Path(os.fsdecode(raw.split(b"\0", 1)[0]))

    def mutation_path(value, dir_fd=None):
        if isinstance(value, int):
            return fd_path(value).resolve()
        path = Path(os.fsdecode(value))
        if not path.is_absolute() and dir_fd not in (None, -1):
            path = fd_path(dir_fd) / path
        return path.resolve()

    def allow_scratch_mutation(event, value, dir_fd=None):
        nonlocal scratch_mutation_count
        path = mutation_path(value, dir_fd)
        if not inside(path, scratch):
            deny(event, str(path))
        scratch_mutation_count += 1

    def audit(event, args):
        if event in {"sqlite3.connect", "sqlite3.connect/handle"}:
            deny("database_open", "SQLite connections are prohibited")
        if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                     "socket.gethostbyname", "socket.gethostbyaddr",
                     "socket.sendto", "socket.sendmsg"}:
            deny("network_access", event)
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            raw_path = os.fsdecode(args[0])
            path = Path(raw_path)
            if inside(path, model_root) or path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".safetensors"}:
                deny("model_or_database_file_open", raw_path)
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+"))
            writing = writing or (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writing:
                allow_scratch_mutation("file_write", raw_path)
        elif event == "open" and args and isinstance(args[0], int):
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            if ((isinstance(mode, str) and any(c in mode for c in "wax+")) or
                (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))):
                allow_scratch_mutation("file_write", args[0])
        if event in {"os.mkdir", "os.chmod"}:
            allow_scratch_mutation(event, args[0], args[2] if len(args) > 2 else None)
        elif event in {"os.remove", "os.rmdir"}:
            allow_scratch_mutation(event, args[0], args[1] if len(args) > 1 else None)
        elif event in {"os.rename", "os.link"}:
            allow_scratch_mutation(event, args[0], args[2] if len(args) > 2 else None)
            allow_scratch_mutation(event, args[1], args[3] if len(args) > 3 else None)
        elif event == "os.symlink":
            # No imported package needs to create symlinks for this smoke.  Reject
            # them rather than let a scratch link redirect a later native write.
            deny("symlink_creation", event)
        elif event in {"os.chown", "os.utime"}:
            allow_scratch_mutation(event, args[0], args[3] if len(args) > 3 else None)
        elif event == "os.truncate":
            allow_scratch_mutation(event, args[0])

    sys.addaudithook(audit)

    requested = ("watchlist", "rapidfuzz", "numpy", "torch", "transformers",
                 "sentence_transformers", "langgraph", "langgraph.checkpoint.sqlite")
    imports = {}
    for name in requested:
        expected_root = source if name == "watchlist" else site_packages
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise RuntimeError("missing restored module: " + name)
        locations = list(spec.submodule_search_locations or [])
        if spec.origin and spec.origin not in {"built-in", "frozen"}:
            locations.append(spec.origin)
        if not locations or any(not inside(p, expected_root) for p in locations):
            raise RuntimeError("module would load outside its restored import root: " + name)
        module = importlib.import_module(name)
        actual = []
        module_file = getattr(module, "__file__", None)
        if module_file:
            actual.append(module_file)
        actual.extend(list(getattr(module, "__path__", [])))
        if not actual or any(not inside(p, expected_root) for p in actual):
            raise RuntimeError("module loaded outside its restored import root: " + name)
        imports[name] = {"paths": [str(Path(p).resolve()) for p in actual],
                         "verified_restored_origin": True}

    # Check transitive native/Python imports too.  The original interpreter's
    # standard library is the one permitted external import dependency.
    unexpected = []
    synthetic_origins = []
    checked_file_origins = 0
    torch_namespaces = {
        "torch.classes": ("torch._classes", "_Classes", "classes", "_classes.py"),
        "torch.ops": ("torch._ops", "_Ops", "ops", "_ops.py"),
    }
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and filename not in {"built-in", "frozen"}:
            if not Path(filename).is_absolute():
                # Torch registers these two synthetic module objects with a
                # placeholder __file__.  Verify the exact object, type, and
                # defining source instead of exempting arbitrary relative paths.
                definition = torch_namespaces.get(name)
                if definition is not None:
                    owner_name, class_name, attribute, placeholder = definition
                    owner = sys.modules.get(owner_name)
                    torch_module = sys.modules.get("torch")
                    owner_file = vars(owner).get("__file__") if owner is not None else None
                    expected_owner_file = site_packages / "torch" / placeholder
                    if (filename == placeholder and owner_file is not None and
                        Path(owner_file).is_absolute() and
                        Path(owner_file).resolve() == expected_owner_file.resolve() and
                        inside(owner_file, site_packages) and
                        type(module) is vars(owner).get(class_name) and
                        type(module).__module__ == owner_name and
                        vars(owner).get(attribute) is module and
                        torch_module is not None and
                        vars(torch_module).get(attribute) is module):
                        synthetic_origins.append({"module": name, "placeholder": filename,
                                                  "defining_module": owner_name,
                                                  "defining_file": str(Path(owner_file).resolve()),
                                                  "identity_and_type_verified": True})
                        continue
                unexpected.append({"module": name, "file": str(filename)})
                continue
            from_restored = any(inside(filename, allowed) for allowed in (source, site_packages))
            from_framework_stdlib = inside(filename, expected_framework) and "site-packages" not in Path(filename).parts
            if not (from_restored or from_framework_stdlib):
                unexpected.append({"module": name, "file": str(filename)})
            else:
                checked_file_origins += 1
    if unexpected:
        raise RuntimeError("unexpected import origins: " + json.dumps(unexpected))

    distributions = []
    for dist in importlib.metadata.distributions(path=[str(site_packages)]):
        distributions.append({"name": dist.metadata.get("Name"), "version": dist.version})
    distributions.sort(key=lambda d: ((d["name"] or "").casefold(), d["version"]))
    if not distributions or any(not d["name"] for d in distributions):
        raise RuntimeError("restored distribution metadata is empty or invalid")

    return {"ok": True,
            "python": {"version": sys.version, "executable": sys.executable,
                       "base_executable": getattr(sys, "_base_executable", None),
                       "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                       "stdlib": sysconfig.get_path("stdlib"),
                       "isolated": bool(sys.flags.isolated), "no_site": bool(sys.flags.no_site),
                       "dont_write_bytecode": sys.dont_write_bytecode},
            "host": {"platform": platform.platform(), "machine": platform.machine()},
            "imports": imports,
            "transitive_origins": {"verified_file_count": checked_file_origins,
                                   "verified_synthetic_modules": synthetic_origins},
            "distribution_count": len(distributions), "distributions": distributions,
            "sqlite_version": sqlite3.sqlite_version,
            "denied_events": denied_events,
            "scratch": {"path": str(scratch), "audited_mutation_count": scratch_mutation_count,
                        "writes_restricted_to_private_scratch": True},
            "checks": {"restored_source_imported": True,
                       "restored_dependency_origins_verified": True,
                       "editable_pth_processed": False,
                       "model_loaded": False, "model_inference_run": False,
                       "database_connection_opened": False},
            "external_dependencies": [str(expected_framework), "compatible macOS system libraries/frameworks"],
            "claim": "Same-host restored-package import smoke using the original installed Python framework; not a portable rebuild or independently relocated interpreter."}

try:
    result = run()
except Exception as exc:
    result = {"ok": False, "error_type": type(exc).__name__, "error": str(exc),
              "traceback": traceback.format_exc()}
print(RESULT_PREFIX + json.dumps(result, sort_keys=True))
sys.exit(0 if result["ok"] else 1)
'''


def _relative_path(root: Path, value: Any, field: str) -> Path:
    """Accept a manifest-relative path without allowing parent traversal."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"runtime.{field} must be a nonempty relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"runtime.{field} must remain inside the restored project")
    return root / relative


def _bounded_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    return text[:_OUTPUT_LIMIT]


def restored_runtime_smoke(destination: Path, manifest: dict) -> dict:
    """Import restored source/dependencies without model, DB, or network use.

    Returns a failed receipt on validation errors, import errors or timeout.
    The destination is never modified.  Import-time caches may use a separate
    private temporary directory, removed afterward.  The original absolute
    framework symlink is deliberately retained and disclosed.
    """
    receipt: dict[str, Any] = {
        "ok": False,
        "mode": "same-host-restored-packages-original-framework",
        "timeout_seconds": _TIMEOUT_SECONDS,
        "child_script_sha256": hashlib.sha256(_SMOKE_CHILD.encode("utf-8")).hexdigest(),
        "portable_rebuild_proven": False,
        "relocated_framework_execution_proven": False,
    }
    try:
        destination = Path(destination).resolve(strict=True)
        project = (destination / "project").resolve(strict=True)
        project.relative_to(destination)
        if not project.is_dir():
            raise ValueError("restored project is not a directory")
        runtime = manifest.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("manifest.runtime must be an object")
        environment = _relative_path(project, runtime.get("environment_relative", ".venv"), "environment_relative")
        python = _relative_path(project, runtime.get("python_relative", ".venv/bin/python"), "python_relative")
        site_packages = _relative_path(project, runtime.get("site_packages_relative", ".venv/lib/python3.14/site-packages"), "site_packages_relative")
        environment.resolve(strict=True).relative_to(project)
        site_packages.resolve(strict=True).relative_to(environment.resolve(strict=True))
        python.parent.resolve(strict=True).relative_to(environment.resolve(strict=True))
        framework_text = runtime.get("framework_root")
        if not isinstance(framework_text, str) or not Path(framework_text).is_absolute():
            raise ValueError("runtime.framework_root must be the original absolute framework path")
        framework = Path(framework_text).resolve(strict=True)
        python.resolve(strict=True).relative_to(framework)
        if not (project / "src" / "watchlist").is_dir():
            raise ValueError("restored watchlist source is missing")

        archived_framework = destination / "python-framework"
        if archived_framework.exists() or archived_framework.is_symlink():
            archived_framework.resolve(strict=True).relative_to(destination)
            if not archived_framework.is_dir():
                raise ValueError("preserved framework path is not a directory")
        receipt.update({
            "restored_project": str(project),
            "restored_environment": str(environment),
            "restored_site_packages": str(site_packages),
            "python_path": str(python),
            "python_symlink_target": os.readlink(python) if python.is_symlink() else None,
            "original_framework_root": str(framework),
            "archived_framework": {"path": str(archived_framework),
                                   "exists": archived_framework.is_dir(), "executed": False,
                                   "bytes_verified_by_this_smoke": False,
                                   "verification_scope": "Framework archive integrity is checked separately by archive restoration."},
        })

        offline_flags = {
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1",
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
            "TOKENIZERS_PARALLELISM": "false", "WANDB_MODE": "disabled",
        }
        child_environment = os.environ.copy()
        child_environment.update(offline_flags)
        for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            child_environment.pop(key, None)
        receipt["offline_flags"] = offline_flags
        scratch_path = None
        try:
            with tempfile.TemporaryDirectory(prefix="polyglot-runtime-smoke-") as scratch_text:
                scratch_path = Path(scratch_text).resolve(strict=True)
                child_environment.update({"TMPDIR": str(scratch_path), "TMP": str(scratch_path),
                                          "TEMP": str(scratch_path),
                                          "TORCHINDUCTOR_CACHE_DIR": str(scratch_path / "torchinductor"),
                                          "TORCH_HOME": str(scratch_path / "torch"),
                                          "HF_HOME": str(scratch_path / "huggingface"),
                                          "XDG_CACHE_HOME": str(scratch_path / "cache")})
                receipt["scratch"] = {"path": str(scratch_path), "removed_after_smoke": False}
                args = [str(python), "-B", "-I", "-S", "-c", _SMOKE_CHILD,
                        str(project), str(site_packages), str(framework), str(scratch_path)]
                receipt["command_outline"] = [str(python), "-B", "-I", "-S", "-c",
                                              "<embedded smoke script identified by child_script_sha256>",
                                              str(project), str(site_packages), str(framework), str(scratch_path)]
                completed = subprocess.run(args, cwd=project, env=child_environment,
                                           capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
                                           check=False)
        finally:
            if scratch_path is not None:
                receipt["scratch"]["removed_after_smoke"] = not scratch_path.exists()
        receipt["returncode"] = completed.returncode
        receipt["stderr"] = _bounded_text(completed.stderr)
        result_lines = [line for line in completed.stdout.splitlines() if line.startswith(_RESULT_PREFIX)]
        if len(result_lines) != 1:
            receipt["stdout"] = _bounded_text(completed.stdout)
            raise RuntimeError("runtime child did not emit exactly one structured result")
        child = json.loads(result_lines[0][len(_RESULT_PREFIX):])
        receipt["child"] = child
        receipt["stdout_other"] = _bounded_text("\n".join(
            line for line in completed.stdout.splitlines() if not line.startswith(_RESULT_PREFIX)))
        receipt["ok"] = completed.returncode == 0 and isinstance(child, dict) and child.get("ok") is True
    except subprocess.TimeoutExpired as exc:
        receipt.update({"error_type": "TimeoutExpired", "error": "runtime smoke exceeded 120 seconds",
                        "stdout": _bounded_text(exc.stdout), "stderr": _bounded_text(exc.stderr)})
    except Exception as exc:
        receipt.update({"error_type": type(exc).__name__, "error": str(exc)})
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace", type=Path, default=Path("data/review"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restore-to", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--without-runtime", action="store_true", help="For isolated fixtures; not a full runtime backup")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if (args.restore_to is not None or args.smoke) and not args.restore:
        parser.error("--restore-to and --smoke require --restore")
    if args.without_runtime and (args.verify or args.restore):
        parser.error("--without-runtime is only supported with --dry-run or --apply")
    workspace = args.workspace if args.workspace.is_absolute() else args.project / args.workspace
    output = args.output if args.output.is_absolute() else args.project / args.output
    try:
        if args.restore:
            if args.restore_to is None:
                raise PreservationError("--restore requires --restore-to")
            result = restore_archive(output, args.restore_to, smoke=args.smoke)
        elif args.verify:
            result = verify_archive(output)
        else:
            operation = preflight if args.dry_run else apply_archive
            result = operation(args.project, workspace, output, include_runtime=not args.without_runtime)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except PreservationError as exc:
        print(f"Preservation stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
