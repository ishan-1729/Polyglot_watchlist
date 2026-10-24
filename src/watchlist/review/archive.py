"""Read-only inspection of the frozen Step 00 preservation-v1 archive format.

The path/member contract is deliberately frozen from the reviewed Step 00
utility. This module never imports that executable script or archived Python,
never extracts a payload, and never resolves recorded recipes against live paths.
Current execution fingerprints are informational; this reader cannot resume a
workflow. Use ``python -B -m watchlist.review`` to suppress interpreter bytecode.
"""
from __future__ import annotations

from datetime import datetime
from email.parser import BytesHeaderParser
from importlib import metadata as distribution_metadata
import functools
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import unicodedata
from typing import Any, Callable

from watchlist.review.compat_v1 import ArchiveError, read_v1

SCHEMA = "polyglot-preservation-v1"
SIDECARS = ("-wal", "-shm", "-journal")
CHUNK = 1024 * 1024
_EXECUTION_PACKAGES = ("langgraph", "langgraph-checkpoint", "langgraph-checkpoint-sqlite", "ormsgpack")
_EXECUTION_BASE_FILES = ("normalize.py", "embeddings.py", "matching_embeddings.py", "entities.py", "database.py")
RESEARCH_NOTICE = ("Possible record matches for research and human review only. "
                   "Stored similarity is not identity probability; annotations do not establish identity or wrongdoing. "
                   "A local reviewer label is not proof of human authentication.")


def _reader_errors(function: Callable) -> Callable:
    """Expose a consistent reader error without hiding unsupported evidence."""
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ArchiveError:
            raise
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
            raise ArchiveError(f"{function.__name__}: {exc}") from exc
    return wrapped


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArchiveError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _json_read(path: Path, *, expected_sha256: str | None = None) -> dict:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ArchiveError(f"Oversized JSON manifest: {path.name}")
    raw = path.read_bytes()
    if expected_sha256 is not None and digest_bytes(raw) != expected_sha256:
        raise ArchiveError(f"JSON bytes changed after verification: {path.name}")
    value = json.loads(raw, object_pairs_hook=_unique_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(ArchiveError(f"Nonfinite JSON: {value}")))
    if not isinstance(value, dict):
        raise ArchiveError(f"Expected a JSON object: {path.name}")
    return value


def _safe_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArchiveError("Invalid manifest path")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(p in ("", ".", "..") for p in path.parts):
        raise ArchiveError(f"Unsafe manifest path: {value!r}")
    return path


def _absolute_path(value: Path | str) -> Path:
    """Reject traversal before lexical containment or filesystem access."""
    path = Path(value)
    if ".." in path.parts:
        raise ArchiveError("Parent traversal is unsupported in filesystem paths")
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
            raise ArchiveError(f"Symlink path component is unsupported: {parent}")


def _metadata(path: Path) -> dict:
    st = path.lstat()
    return {"device": st.st_dev, "inode": st.st_ino, "size": st.st_size,
            "mode": stat.S_IMODE(st.st_mode), "mtime_ns": st.st_mtime_ns,
            "ctime_ns": st.st_ctime_ns, "nlink": st.st_nlink}


def _regular(path: Path, *, single_link: bool = True) -> dict:
    _no_symlinks(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or (single_link and st.st_nlink != 1):
        raise ArchiveError(f"Expected independent regular file: {path}")
    return _metadata(path)


def _hash(path: Path) -> str:
    before = _regular(path, single_link=False)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino) != (before["device"], before["inode"]):
            raise ArchiveError(f"File replaced while reading: {path}")
        h = hashlib.sha256()
        while block := os.read(fd, CHUNK):
            h.update(block)
        if _metadata(path) != before:
            raise ArchiveError(f"File changed while reading: {path}")
        return h.hexdigest()
    finally:
        os.close(fd)


def _all_disk_members(root: Path) -> dict[str, str]:
    result = {}
    def fail_walk(error: OSError) -> None:
        raise error
    for base, directories, files in os.walk(root, followlinks=False, onerror=fail_walk):
        for name in sorted(directories + files):
            path = Path(base) / name
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise ArchiveError("Archive contains a symlink or special file")
            if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
                raise ArchiveError("Archive contains a hardlink")
            expected_mode = 0o700 if stat.S_ISDIR(st.st_mode) else 0o600
            if stat.S_IMODE(st.st_mode) != expected_mode:
                raise ArchiveError(f"Archive permissions are not private: {path.relative_to(root)}")
            result[str(path.relative_to(root))] = "directory" if stat.S_ISDIR(st.st_mode) else "file"
    return result


def _fields(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ArchiveError(f"Invalid {label} fields")


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _register_member(members: dict[str, str], relative: PurePosixPath, kind: str) -> None:
    key = str(relative)
    if members.get(key, kind) != kind:
        raise ArchiveError("Manifest file/directory/link collision")
    members[key] = kind
    for parent in relative.parents:
        if str(parent) != ".":
            if members.get(str(parent), "directory") != "directory":
                raise ArchiveError("Manifest member has a nondirectory parent")
            members[str(parent)] = "directory"


def _link_destination(item: dict, runtime: dict) -> PurePosixPath:
    """Validate runtime links; absolute framework links remain same-host dependencies."""
    raw = item["target"]
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        raise ArchiveError("Invalid preserved link target")
    relative = PurePosixPath(_restore_relative(item).as_posix())
    link = PurePosixPath(raw)
    if link.is_absolute():
        framework = PurePosixPath(runtime["framework_root"])
        if ".." in link.parts or str(link) != raw or not link.is_relative_to(framework):
            raise ArchiveError("Unexpected external runtime link")
        return PurePosixPath("python-framework") / link.relative_to(framework)
    result = relative.parent / link
    permitted = PurePosixPath("project/.venv" if item["category"] == "environment" else "python-framework")
    if not PurePosixPath(os.path.normpath(str(result))).is_relative_to(permitted):
        raise ArchiveError("Runtime link would escape its declared tree")
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
            raise ArchiveError("Runtime link resolution exceeded its component limit")
        part = pending.pop()
        if current.parts and members.get(str(current)) != "directory":
            available = False
        if part == ".":
            continue
        if part == "..":
            if current in roots or not current.parts:
                raise ArchiveError("Runtime link would escape its declared tree")
            current = current.parent
            continue
        candidate = current / part
        if not any(candidate.is_relative_to(root) or root.is_relative_to(candidate) for root in roots):
            raise ArchiveError("Runtime link would escape its declared tree")
        target = targets.get(str(candidate))
        if target is not None:
            expansions += 1
            if expansions > 64:
                raise ArchiveError("Cyclic or excessively deep runtime links are unsupported")
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
                raise ArchiveError("Runtime link target_exists must be a boolean")
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
                raise ArchiveError("Runtime link target presence differs from captured members")
            missing += not exists
    return missing


def _validate_manifest(manifest: dict) -> None:
    """Validate all paths and restore mappings before any archive-driven writes."""
    _fields(manifest, {"schema", "captured_at", "entries", "runtime", "workspace_relative",
                      "database_paths", "sidecars", "exclusions", "source_root", "atime_preserved",
                      "origin_attributions"}, "manifest")
    if manifest["schema"] != SCHEMA or manifest["atime_preserved"] is not False:
        raise ArchiveError("Unknown preservation schema or access-time contract")
    if not isinstance(manifest["captured_at"], str) or datetime.fromisoformat(manifest["captured_at"]).tzinfo is None:
        raise ArchiveError("Invalid capture timestamp")
    source = manifest["source_root"]
    if not isinstance(source, str) or not Path(source).is_absolute() or str(_absolute_path(source)) != source:
        raise ArchiveError("Invalid original project root")
    workspace = _safe_relative(manifest["workspace_relative"])
    if not isinstance(manifest["exclusions"], list) or any(not isinstance(v, str) for v in manifest["exclusions"]):
        raise ArchiveError("Invalid exclusion receipt")
    if not isinstance(manifest["origin_attributions"], list) or any(not isinstance(v, dict) for v in manifest["origin_attributions"]):
        raise ArchiveError("Invalid external origin attribution")
    runtime = manifest["runtime"]
    if not isinstance(runtime, dict) or type(runtime.get("included")) is not bool:
        raise ArchiveError("Invalid runtime manifest")
    if runtime["included"]:
        _fields(runtime, {"included", "framework_root", "environment_relative", "python_relative",
                          "site_packages_relative", "python_version", "platform", "same_host_only",
                          "creation_configuration"}, "runtime")
        if (runtime["framework_root"] != "/Library/Frameworks/Python.framework/Versions/3.14"
                or runtime["environment_relative"] != ".venv" or runtime["python_relative"] != ".venv/bin/python"
                or runtime["same_host_only"] is not True):
            raise ArchiveError("Unsupported same-host runtime contract")
        site = _safe_relative(runtime["site_packages_relative"])
        if len(site.parts) != 4 or site.parts[:2] != (".venv", "lib") or site.parts[-1] != "site-packages":
            raise ArchiveError("Invalid runtime package path")
        if any(not isinstance(runtime[key], str) or not runtime[key] for key in ("python_version", "platform")):
            raise ArchiveError("Invalid runtime version information")
        cfg = runtime["creation_configuration"]
        if not isinstance(cfg, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in cfg.items()):
            raise ArchiveError("Invalid runtime creation configuration")
    else:
        _fields(runtime, {"included"}, "excluded runtime")
    entries = manifest["entries"]
    if not isinstance(entries, list):
        raise ArchiveError("Manifest entries must be a list")
    by_path, restored, explicit_restored = {}, {}, set()
    for item in entries:
        if not isinstance(item, dict):
            raise ArchiveError("Manifest entry must be an object")
        relative = _safe_relative(item.get("path"))
        kind, category = item.get("kind"), item.get("category")
        if str(relative) in by_path or kind not in ("file", "directory", "link"):
            raise ArchiveError("Duplicate path or unsupported manifest member")
        if relative.parts[0] == "databases":
            if len(relative.parts) < 2 or category != "database" or kind != "file":
                raise ArchiveError("Invalid normalized database member")
        elif len(relative.parts) < 3 or relative.parts[:2] != ("payload", category) or category not in ("project", "environment", "python-framework"):
            raise ArchiveError("Invalid payload category/path mapping")
        if category in ("environment", "python-framework") and not runtime["included"]:
            raise ArchiveError("Runtime payload exists without a declared runtime")
        if kind == "link" and category not in ("environment", "python-framework"):
            raise ArchiveError("Only runtime links may be recorded")
        fields = {"path", "category", "kind", "mode"}
        if category != "database":
            fields.add("metadata")
        if kind == "file":
            fields.update(("size", "sha256"))
        elif kind == "link":
            fields.update(("target", "target_exists"))
        _fields(item, fields, "manifest entry")
        if type(item["mode"]) is not int or not 0 <= item["mode"] <= 0o7777:
            raise ArchiveError("Invalid captured file mode")
        if kind == "file" and (type(item["size"]) is not int or item["size"] < 0 or not _sha256(item["sha256"])):
            raise ArchiveError("Invalid captured file size/hash")
        if category != "database":
            metadata_fields = {"device", "inode", "mode"} if kind == "directory" else {"device", "inode", "size", "mode", "mtime_ns", "ctime_ns", "nlink"}
            _fields(item["metadata"], metadata_fields, "source metadata")
            if any(type(v) is not int for v in item["metadata"].values()) or item["metadata"]["mode"] != item["mode"]:
                raise ArchiveError("Invalid source metadata values")
            if kind == "file" and item["metadata"]["size"] != item["size"]:
                raise ArchiveError("Source metadata/file size mismatch")
        restored_path = PurePosixPath(_restore_relative(item).as_posix())
        if str(restored_path) in explicit_restored:
            raise ArchiveError("Multiple archive entries map to the same restore destination")
        explicit_restored.add(str(restored_path))
        _register_member(restored, restored_path, kind)
        by_path[str(relative)] = item
    _validate_runtime_links(entries, runtime)
    paths = manifest["database_paths"]
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths) or len(set(paths)) != len(paths):
        raise ArchiveError("Invalid database path list")
    expected_databases = set()
    for relative in paths:
        _safe_relative(relative)
        raw, normalized = by_path.get("payload/project/" + relative), by_path.get("databases/" + relative)
        if not relative.endswith(".sqlite") or raw is None or raw["kind"] != "file" or normalized is None:
            raise ArchiveError("Database lacks matching raw/normalized members")
        expected_databases.add("databases/" + relative)
    if {p for p in by_path if p.startswith("databases/")} != expected_databases:
        raise ArchiveError("Unexpected normalized database member")
    if {p.removeprefix("payload/project/") for p, item in by_path.items()
            if p.startswith("payload/project/") and p.endswith(".sqlite") and item["kind"] == "file"} != set(paths):
        raise ArchiveError("Raw database membership differs from database path list")
    if not {str(workspace / "cases.sqlite"), str(workspace / "checkpoints.sqlite")} <= set(paths):
        raise ArchiveError("Established review database pair is absent")
    _fields(manifest["sidecars"], set(paths), "sidecar receipt")
    for relative, statuses in manifest["sidecars"].items():
        _fields(statuses, set(SIDECARS), "database sidecars")
        for suffix, present in statuses.items():
            member = by_path.get("payload/project/" + relative + suffix)
            if type(present) is not bool or present != (member is not None) or (member is not None and member["kind"] != "file"):
                raise ArchiveError("Sidecar membership/receipt mismatch")


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
                raise ArchiveError(f"Archive hash/size mismatch: {relative}")
    if _all_disk_members(output) != expected:
        raise ArchiveError("Archive membership differs from manifest")


def _restore_relative(item: dict) -> Path:
    relative = _safe_relative(item["path"])
    if relative.parts[0] == "databases":
        return Path(*relative.parts)
    if len(relative.parts) < 3 or relative.parts[0] != "payload":
        raise ArchiveError("Invalid payload layout")
    category = relative.parts[1]
    prefix = {"project": Path("project"), "environment": Path("project/.venv"),
              "python-framework": Path("python-framework")}.get(category)
    if prefix is None:
        raise ArchiveError("Unknown restore category")
    return prefix / Path(*relative.parts[2:])


def _snapshot(root: Path) -> dict[str, dict]:
    """Detect replacement or mutation throughout a read, ignoring access time."""
    members = _all_disk_members(root)
    return {".": _metadata(root), **{name: _metadata(root / name) for name in members}}


def _execution_sources(root: Path) -> dict[str, str]:
    """Mirror the v1 execution fingerprint file set without importing code."""
    agent = root / "agent"
    paths = sorted(agent.glob("*.py")) + sorted(agent.glob("*.sql"))
    if not paths:
        raise ArchiveError("Execution source files were not captured")
    paths += [root / name for name in _EXECUTION_BASE_FILES]
    return {str(path.relative_to(root)): _hash(path) for path in paths}


def _current_execution_manifest() -> dict:
    """Compare live source/dependencies; absence never invalidates old evidence."""
    try:
        files = _execution_sources(Path(__file__).absolute().parents[1])
        packages = {name: distribution_metadata.version(name) for name in _EXECUTION_PACKAGES}
        return {"status": "available", "sha256": digest_bytes(canonical_bytes(
                    {"files": files, "packages": packages})),
                "file_count": len(files), "packages": packages}
    except (OSError, ArchiveError, distribution_metadata.PackageNotFoundError) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def _captured_execution_manifest(output: Path, manifest: dict) -> dict:
    """Hash captured source and parse captured package headers as inert bytes."""
    prefix = "payload/project/src/watchlist/"
    names = {entry["path"] for entry in manifest["entries"] if entry["kind"] == "file"}
    required = {prefix + name for name in _EXECUTION_BASE_FILES}
    if not required <= names:
        return {"status": "not_captured", "reason": "execution source subset absent"}
    files = _execution_sources(output / prefix)
    if any(prefix + name not in names for name in files):
        raise ArchiveError("Execution source is not a manifest-listed file")
    result = {"source_files": {"status": "verified", "count": len(files)}}
    if not manifest["runtime"]["included"]:
        return {**result, "status": "not_captured", "reason": "execution package metadata absent"}
    site = PurePosixPath(manifest["runtime"]["site_packages_relative"])
    metadata_prefix = str(PurePosixPath("payload/environment") / PurePosixPath(*site.parts[1:])) + "/"
    packages = {}
    for name in sorted(names):
        if (not name.startswith(metadata_prefix) or not name.endswith(".dist-info/METADATA")
                or len(PurePosixPath(name.removeprefix(metadata_prefix)).parts) != 2):
            continue
        headers = BytesHeaderParser().parsebytes((output / name).read_bytes())
        raw_names = headers.get_all("Name", [])
        normalized = [re.sub(r"[-_.]+", "-", str(v)).lower() for v in raw_names]
        relevant = set(normalized) & set(_EXECUTION_PACKAGES)
        # Distribution directory names also identify malformed missing headers.
        folder_name = PurePosixPath(name).parent.name.removesuffix(".dist-info").rsplit("-", 1)[0]
        folder_name = re.sub(r"[-_.]+", "-", folder_name).lower()
        if not relevant and folder_name not in _EXECUTION_PACKAGES:
            continue
        versions = headers.get_all("Version", [])
        if len(raw_names) != 1 or len(versions) != 1 or not str(versions[0]).strip() or len(relevant) != 1:
            raise ArchiveError("Malformed captured execution package metadata")
        package = next(iter(relevant))
        if folder_name != package:
            raise ArchiveError("Captured execution package directory/name disagreement")
        if package in packages:
            raise ArchiveError("Duplicate captured execution package metadata")
        packages[package] = str(versions[0])
    if set(packages) != set(_EXECUTION_PACKAGES):
        raise ArchiveError("Captured runtime lacks required execution package metadata")
    return {**result, "status": "verified", "sha256": digest_bytes(canonical_bytes(
                {"files": files, "packages": packages})), "packages": packages}


def _read_archive(path: Path | str) -> tuple[dict, dict]:
    """Validate all archive bytes before exposing decoded historical evidence."""
    output = _absolute_path(path)
    _no_symlinks(output)
    if not output.is_dir() or stat.S_IMODE(output.stat().st_mode) != 0o700:
        raise ArchiveError("Expected a private archive directory")
    before = _snapshot(output)
    for name in ("COMPLETE.json", "manifest.json", "verification.json"):
        _regular(output / name)
    marker = _json_read(output / "COMPLETE.json")
    _fields(marker, {"schema", "manifest_sha256", "verification_sha256"}, "completion marker")
    if marker["schema"] != SCHEMA or not all(_sha256(marker[key]) for key in ("manifest_sha256", "verification_sha256")):
        raise ArchiveError("Unknown or invalid archive completion marker")
    manifest = _json_read(output / "manifest.json", expected_sha256=marker["manifest_sha256"])
    saved = _json_read(output / "verification.json", expected_sha256=marker["verification_sha256"])
    _check_payload(output, manifest, complete=True)
    receipt, details = read_v1(output / "payload/project", manifest["workspace_relative"], output / "databases")
    if canonical_bytes(receipt) != canonical_bytes(saved):
        raise ArchiveError("Logical database receipt changed")
    if canonical_bytes(manifest["origin_attributions"]) != canonical_bytes(receipt["external_origin_attributions"]):
        raise ArchiveError("External attribution disagrees with verified evidence")
    historical = _captured_execution_manifest(output, manifest)
    current = _current_execution_manifest()
    catalogue = []
    recipes = {}
    for summary in receipt["cases"]:
        identifier = summary["audit_id"]
        detail = details[identifier]
        stored = summary["workflow_sha256"]
        if historical["status"] == "verified" and historical["sha256"] != stored:
            raise ArchiveError("Captured execution manifest disagrees with stored workflow hash")
        compatibility = {
            "stored_workflow_sha256": stored,
            "captured_execution_match": historical.get("sha256") == stored if "sha256" in historical else None,
            "current_workflow_sha256": current.get("sha256"),
            "current_execution_match": current.get("sha256") == stored if "sha256" in current else None,
            "execution_allowed": False,
        }
        recipe = detail["initial"]["recipe"]
        retrieval = detail["packet"]["retrieval"] if detail["packet"] else None
        recipe_key = digest_bytes(canonical_bytes([recipe, retrieval]))
        if recipe_key not in recipes:
            recipes[recipe_key] = recipe_contract(
                recipe, output / "payload/project", manifest["source_root"],
                manifest["entries"], retrieval=retrieval)
        recipe_checks = recipes[recipe_key]
        contracts = {
            "case_schema": {"status": "verified", "version": summary["schema_version"]},
            "packet_schema": {"status": "verified" if detail["packet"] else "not_present",
                              "contract": "inferred-legacy-review-v1", "independently_stored_version": False},
            "execution_manifest": historical,
            "source_snapshot": recipe_checks.get("source_snapshot", {"status": "recorded_only"}),
            "model_recipe": recipe_checks,
        }
        row = {"case_id": identifier, "thread_id": summary["thread_id"], "state": summary["status"],
               "audit_event_count": summary["audit_count"], "annotation_origin": summary["annotation_origin"],
               "versions": {"case_schema": summary["schema_version"], "workflow": summary["workflow_version"]},
               "compatibility": compatibility, "contracts": contracts}
        catalogue.append(row)
        details[identifier] = {**detail, **row, "state": detail["latest_state"] or detail["initial"]}
    result = {
        "status": "verified", "archive_format": SCHEMA, "execution_allowed": False,
        "verification": {"scope": "historical_integrity_and_v1_protocol",
                         "archive_manifest_sha256": marker["manifest_sha256"],
                         "files_verified": sum(e["kind"] == "file" for e in manifest["entries"]),
                         "databases_verified": len(receipt["databases"]), "case_count": len(catalogue),
                         "independent_authentication": False},
        "cases": catalogue,
        "contracts": {"archive": SCHEMA, "historical_execution": historical, "current_execution": current},
        "execution": {"allowed": False, "reason": "Archive inspection never authorizes workflow execution"},
        "research_notice": RESEARCH_NOTICE,
    }
    if before != _snapshot(output):
        raise ArchiveError("Archive changed during inspection")
    return result, details


@_reader_errors
def verify_archive(path: Path | str) -> dict[str, Any]:
    """Verify an archive and return a catalogue without queries/reviewer notes."""
    return _read_archive(path)[0]


@_reader_errors
def inspect_case(path: Path | str, case_id: str) -> dict[str, Any]:
    """Verify the entire archive and explicitly expose one saved case's evidence."""
    if not isinstance(case_id, str) or not case_id or len(case_id) > 128:
        raise ArchiveError("Expected a nonempty case identifier of at most 128 characters")
    result, details = _read_archive(path)
    matches = [detail for identifier, detail in details.items()
               if case_id in (identifier, detail["thread_id"])]
    if len(matches) != 1:
        raise ArchiveError("Case identifier is unknown or ambiguous")
    result.pop("cases")
    result["case"] = matches[0]
    return result


# Frozen, primitive reconstruction of captured recipe evidence.
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_JSON_LIMIT = 8 * 1024 * 1024
_MODEL_LIMIT = 600_000_000
_MODEL_ID = "intfloat/multilingual-e5-small"
_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
_MODEL_FILES = {
    "1_Pooling/config.json", "README.md", "config.json", "model.safetensors",
    "modules.json", "sentence_bert_config.json", "sentencepiece.bpe.model",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
}
_PACKAGES = {"numpy", "torch", "transformers", "sentence-transformers", "tokenizers"}


def _finite_json(value: object) -> str:
    """Require finite primitive JSON, bounded before canonical serialization."""
    remaining, characters = 100_000, 0

    def visit(item: object, depth: int) -> None:
        nonlocal remaining, characters
        remaining -= 1
        if remaining < 0 or depth > 32:
            raise ValueError("recipe JSON exceeds structural limits")
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ValueError("recipe JSON keys must be strings")
            characters += sum(len(k) for k in item)
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("recipe JSON contains a nonfinite number")
        elif type(item) is str:
            characters += len(item)
        elif type(item) not in (str, int, bool, type(None)):
            raise ValueError("recipe JSON contains a nonprimitive value")
        if characters > _JSON_LIMIT:
            raise ValueError("recipe JSON exceeds text limit")

    visit(value, 0)
    text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
    if len(text.encode("utf-8")) > _JSON_LIMIT:
        raise ValueError("recipe JSON exceeds byte limit")
    return text


def _digest(value: object) -> str:
    return hashlib.sha256(_finite_json(value).encode("utf-8")).hexdigest()


def _sha(value: object) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("invalid recorded SHA-256")
    return value


def _text(value: object, limit: int = 4096) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError("invalid or overlong recipe text")
    return value


def _path(value: object) -> PurePosixPath:
    """Parse without resolving, expanding, or touching the recorded location."""
    text = _text(value)
    if "\\" in text or "\x00" in text or ":" in text:
        raise ValueError("unsupported recorded path")
    parts = text[1:].split("/") if text.startswith("/") else text.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("noncanonical or traversing recorded path")
    return PurePosixPath(text)


def _relative(value: object, source_root: str) -> str | None:
    path, origin = _path(value), _path(source_root)
    if not origin.is_absolute():
        raise ValueError("recorded source root must be absolute")
    if path.is_absolute():
        if not path.is_relative_to(origin):
            return None
        path = path.relative_to(origin)
    if not path.parts:
        raise ValueError("recorded path names the project root")
    return str(path)


class _CapturedFiles:
    """Access only listed files beneath the supplied capture, with no symlinks."""

    def __init__(self, project: Path, entries: list[dict]):
        if type(entries) is not list or len(entries) > 100_000:
            raise ValueError("invalid capture file inventory")
        self.project = project
        self.files, self.databases = {}, set()
        for entry in entries:
            if type(entry) is not dict:
                raise ValueError("invalid capture entry")
            category = entry.get("category")
            if category not in ("project", "database") or entry.get("kind") != "file":
                continue
            path = _text(entry.get("path"))
            prefix = "payload/project/" if category == "project" else "databases/"
            if not path.startswith(prefix):
                raise ValueError("invalid capture member path")
            parsed = _path(path.removeprefix(prefix))
            if parsed.is_absolute():
                raise ValueError("capture-relative path required")
            relative = str(parsed)
            inventory = self.files if category == "project" else self.databases
            if relative in inventory or type(entry.get("size")) is not int or entry["size"] < 0:
                raise ValueError("duplicate or invalid captured file")
            _sha(entry.get("sha256"))
            if category == "project":
                self.files[relative] = entry
            else:
                self.databases.add(relative)

    def read(self, relative: str, limit: int, *, keep: bool = True) -> bytes | None:
        entry = self.files.get(relative)
        if entry is None:
            return None
        if entry["size"] > limit:
            raise ValueError("captured recipe file exceeds byte limit")
        parts = _path(relative).parts
        if PurePosixPath(relative).is_absolute():
            raise ValueError("capture-relative path required")
        directory = descriptor = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            directory = os.open(self.project, flags)
            for component in parts[:-1]:
                child = os.open(component, flags, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size != entry["size"]:
                raise ValueError("captured recipe member type or size changed")
            digest, chunks, received = hashlib.sha256(), [], 0
            while chunk := os.read(descriptor, min(1024 * 1024, limit - received + 1)):
                received += len(chunk)
                if received > limit:
                    raise ValueError("captured recipe file grew beyond limit")
                digest.update(chunk)
                if keep:
                    chunks.append(chunk)
            after = os.fstat(descriptor)
            if (received != entry["size"] or digest.hexdigest() != entry["sha256"]
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError("captured recipe member differs from inventory")
            return b"".join(chunks) if keep else b""
        except OSError as exc:
            raise ValueError("listed recipe member is missing or unsafe") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)

    def json(self, relative: str) -> object | None:
        data = self.read(relative, _JSON_LIMIT)
        if data is None:
            return None

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate captured JSON key")
                result[key] = value
            return result

        try:
            value = json.loads(data, object_pairs_hook=unique)
            _finite_json(value)
            return value
        except (UnicodeError, RecursionError) as exc:
            raise ValueError("invalid captured recipe JSON") from exc


def _normalized(name: object) -> str:
    text = _text(name, 200)
    normalized = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    normalized = " ".join(normalized.split())
    if not normalized or len(normalized) > 200:
        raise ValueError("invalid captured fictional name")
    return normalized


def _fictional_entities(raw: object) -> list[dict]:
    """Reproduce v1 dataclass JSON/order without importing its loader/classes."""
    if type(raw) is not list or len(raw) > 4096:
        raise ValueError("invalid captured fictional entity collection")
    entities, entity_ids, alias_ids = [], set(), set()
    for row in raw:
        if type(row) is not dict:
            raise ValueError("invalid captured fictional entity")
        eid = _text(row.get("entity_id"))
        if eid != eid.strip() or eid in entity_ids:
            raise ValueError("invalid captured fictional entity ID")
        entity_ids.add(eid)
        if row.get("synthetic") is not True or row.get("source") != "fictional-synthetic-v1":
            raise ValueError("captured fictional source marker mismatch")
        if row.get("entity_type") not in ("person", "organisation"):
            raise ValueError("invalid captured fictional entity type")
        name = _normalized(row.get("name"))
        aliases, normalized = [], set()
        values = row.get("aliases")
        if type(values) is not list or not 1 <= len(values) <= 1024:
            raise ValueError("invalid captured fictional aliases")
        for value in values:
            if type(value) is not dict:
                raise ValueError("invalid captured fictional alias")
            aid, spelling = _text(value.get("alias_id")), _normalized(value.get("name"))
            if aid != aid.strip() or aid in alias_ids or spelling in normalized:
                raise ValueError("duplicate captured fictional alias")
            alias_ids.add(aid)
            normalized.add(spelling)
            aliases.append({"alias_id": aid, "name": value["name"]})
        if name not in normalized:
            raise ValueError("captured canonical name missing from aliases")
        entities.append({"entity_id": eid, "name": row["name"], "entity_type": row["entity_type"],
                         "aliases": aliases, "synthetic": True, "source": row["source"], "provenance": None})
    return entities


def recipe_contract(recipe: dict, project: Path, source_root: str, file_entries: list[dict],
                    *, retrieval: dict | None = None) -> dict:
    """Verify legacy recipe artifacts; absence is distinct from a present mismatch.

    Raw file reads are capped at 8 MiB per JSON and 600 MB across E5 artifacts.
    Source DBs are never opened. Five retrieval package versions remain recorded
    values; reconstruct the separate four-package workflow guard elsewhere.
    """
    if type(recipe) is not dict:
        raise ValueError("recipe must be an object")
    _finite_json(recipe)
    fields = {"config", "db", "reference_sha256", "model_receipt_sha256", "packages"}
    if not fields.intersection(recipe):
        return {"kind": "opaque_legacy_recipe", "status": "recorded_only", "resume_authorized": False}
    if set(recipe) != fields or type(recipe["config"]) is not dict:
        raise ValueError("malformed legacy E5 recipe")
    _sha(recipe["reference_sha256"])
    _sha(recipe["model_receipt_sha256"])
    packages = recipe["packages"]
    if type(packages) is not dict or set(packages) != _PACKAGES:
        raise ValueError("malformed recorded retrieval package versions")
    for value in packages.values():
        _text(value, 256)
    model = recipe["config"].get("model")
    if type(model) is not dict:
        raise ValueError("model configuration must be an object")
    _text(model.get("model_id"), 256)
    _text(model.get("revision"), 256)
    encoder_files = None
    if retrieval is not None:
        if type(retrieval) is not dict:
            raise ValueError("saved retrieval evidence must be an object")
        _finite_json(retrieval)
        encoder = retrieval.get("encoder")
        if (type(encoder) is not dict or type(encoder.get("files")) is not dict
                or _digest(encoder.get("config")) != _digest(model)
                or _digest(encoder.get("packages")) != _digest(packages)
                or _sha(retrieval.get("reference_sha256")) != recipe["reference_sha256"]):
            raise ValueError("saved retrieval evidence differs from recipe")
        encoder_files = encoder["files"]
    captured = _CapturedFiles(project, file_entries)
    model_root = _relative(model.get("model_path"), source_root)
    _relative(recipe["config"].get("cache_path"), source_root)  # Validate; never open/create a cache.
    result = {"kind": "legacy_e5_v1", "resume_authorized": False,
              "retrieval_packages": {"status": "recorded_only", "versions": dict(packages)}}
    if recipe["db"] is None:
        relative = "src/watchlist/data/synthetic_entities.json"
        raw = captured.json(relative)
        if relative not in captured.files:
            result["source_snapshot"] = {"status": "not_captured", "kind": "fictional"}
        elif _digest(_fictional_entities(raw)) != recipe["reference_sha256"]:
            raise ValueError("captured fictional reference differs from recipe")
        else:
            result["source_snapshot"] = {"status": "verified", "kind": "fictional"}
    else:
        db = _relative(recipe["db"], source_root)
        listed = db is not None and (db in captured.files or db in captured.databases)
        result["source_snapshot"] = {"status": "recorded_only" if listed else "not_captured",
                                     "kind": "database", "original_recipe_database_opened": False,
                                     "reference_digest_reconstructed": False}
    result["model_receipt"] = {"status": "not_captured"}
    result["model_files"] = {"status": "not_captured", "weights_status": "not_captured",
                             "expected_files": len(_MODEL_FILES), "verified_files": 0}
    if model_root is not None:
        receipt_path = model_root + "/acquisition.json"
        receipt = captured.json(receipt_path)
        if receipt_path in captured.files:
            if (type(receipt) is not dict or _digest(receipt) != recipe["model_receipt_sha256"]
                    or receipt.get("model_id") != model["model_id"] or receipt.get("revision") != model["revision"]):
                raise ValueError("captured model receipt differs from recipe")
            if encoder_files is not None and _digest(receipt.get("files")) != _digest(encoder_files):
                raise ValueError("captured model receipt differs from saved retrieval files")
            result["model_receipt"] = {"status": "verified", "digest_kind": "canonical_json_sha256"}
            if model["model_id"] != _MODEL_ID or model["revision"] != _REVISION:
                result["model_files"] = {"status": "recorded_only", "weights_status": "not_verified",
                                         "reason": "unsupported_model_contract"}
                statuses = [result[key]["status"] for key in ("source_snapshot", "model_receipt", "model_files")]
                result["status"] = "not_captured" if "not_captured" in statuses else "recorded_only"
                return result
            members = receipt.get("files")
            if type(members) is not dict or set(members) != _MODEL_FILES:
                raise ValueError("unsupported captured E5 receipt file set")
            total, verified = 0, []
            for name, info in sorted(members.items()):
                if type(info) is not dict or type(info.get("bytes")) is not int or info["bytes"] < 0:
                    raise ValueError("invalid captured model file receipt")
                total += info["bytes"]
                if total > _MODEL_LIMIT:
                    raise ValueError("captured model artifact budget exceeded")
                expected = _sha(info.get("sha256"))
                relative = model_root + "/" + name
                entry = captured.files.get(relative)
                if entry is None:
                    continue
                if entry["size"] != info["bytes"] or entry["sha256"] != expected:
                    raise ValueError("captured model file inventory differs from receipt")
                captured.read(relative, _MODEL_LIMIT, keep=False)
                verified.append(name)
            result["model_files"] = {"status": "verified" if len(verified) == len(members) else "not_captured",
                                     "weights_status": "verified" if "model.safetensors" in verified else "not_captured",
                                     "expected_files": len(members), "verified_files": len(verified)}
    statuses = [result[key]["status"] for key in ("source_snapshot", "model_receipt", "model_files")]
    result["status"] = "not_captured" if "not_captured" in statuses else "recorded_only" if "recorded_only" in statuses else "verified"
    return result
