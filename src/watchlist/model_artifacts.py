"""Hash-bound derived-model artifacts that cannot masquerade as pretrained weights.

An artifact directory is immutable once ``manifest.json`` exists. The manifest
lists every payload file with its size and SHA-256, the training config, the
training-data manifest digest, code/environment fingerprints and metrics.
Loading always verifies first. Only this standard-library module touches the
manifest, so verification never requires torch.

The self-digest detects accidental corruption and careless edits. It is not a
signature: anyone who can write the directory can reseal an altered manifest, so
it does not stop deliberate tampering.
"""

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import sys
import tempfile

ARTIFACT_VERSION = "derived-model-artifact-v1"
MANIFEST = "manifest.json"
REQUIRED = (
    "artifact_version",
    "artifact_kind",
    "is_pretrained_original",
    "derived_from",
    "files",
    "config",
    "data_manifest_digest",
    "metrics",
    "code",
    "environment",
    "evidence",
    "manifest_digest",
)
# Source files whose bytes define the derived artifact's training recipe.
CODE_FILES = (
    "training.py",
    "training_losses.py",
    "training_data.py",
    "model_artifacts.py",
)


class ArtifactError(ValueError):
    """Explicit refusal for missing, altered, partial or overwriting artifacts."""


def file_sha256(path: Path) -> str:
    """Stream a file hash in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    """SHA-256 of sorted, compact JSON; stable across processes and platforms."""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write to a sibling temporary file, fsync, then rename over the target.

    ``os.replace`` is atomic on the same volume on Windows and POSIX, so readers
    see either the old complete file or the new complete file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".partial", dir=path.parent
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: object) -> None:
    """Deterministic UTF-8 JSON with LF newlines, written atomically."""
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_bytes(path, text.encode("utf-8"))


def _safe_payload_name(name: object) -> bool:
    """A plain relative name inside the artifact on both Windows and POSIX."""
    if not isinstance(name, str) or not name or name != name.strip():
        return False
    posix, windows = PurePosixPath(name), PureWindowsPath(name)
    return not (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or windows.root
        or ".." in posix.parts
        or ".." in windows.parts
    )


def code_fingerprint() -> dict[str, str]:
    """Hash the exact training source bytes used to produce an artifact."""
    root = Path(__file__).parent
    return {
        name: file_sha256(root / name) for name in CODE_FILES if (root / name).exists()
    }


def environment_summary(packages: Mapping[str, str] | None = None) -> dict:
    """Interpreter/platform plus caller-supplied package versions (e.g. torch)."""
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": dict(sorted((packages or {}).items())),
    }


def _is_sealed_manifest(path: Path) -> bool:
    """Only a manifest declaring this artifact format marks a frozen directory."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return path.exists()
    return not isinstance(value, dict) or "artifact_version" in value


def is_protected_directory(path: Path) -> bool:
    """True for pretrained receipts or frozen artifacts at or above ``path``."""
    resolved = Path(path).resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "acquisition.json").exists() or _is_sealed_manifest(
            candidate / MANIFEST
        ):
            return True
    return False


def write_artifact(
    directory: Path,
    *,
    payload_files: list[str],
    config: Mapping,
    data_manifest_digest: str,
    metrics: Mapping,
    derived_from: Mapping,
    packages: Mapping[str, str] | None = None,
    evidence: str = "fictional/synthetic regression-only evidence",
) -> dict:
    """Seal already-written payload files under a self-digested manifest.

    The manifest is written last and atomically: a crash before that leaves an
    unsealed directory that ``verify_artifact`` refuses. Existing manifests and
    directories that hold pretrained acquisition receipts are never overwritten.
    """
    directory = Path(directory)
    if (directory / MANIFEST).exists():
        raise ArtifactError(
            "artifact is already sealed; refusing to overwrite a frozen artifact"
        )
    if any(
        (parent / "acquisition.json").exists()
        for parent in (directory.resolve(), *directory.resolve().parents)
    ):
        raise ArtifactError(
            "refusing to write a derived artifact inside original pretrained weights"
        )
    if not isinstance(data_manifest_digest, str) or len(data_manifest_digest) != 64:
        raise ArtifactError("a 64-character training-data manifest digest is required")
    if not payload_files:
        raise ArtifactError("an artifact must contain at least one payload file")
    files = {}
    for name in sorted(payload_files):
        path = directory / name
        if not _safe_payload_name(name) or not path.is_file():
            raise ArtifactError(
                f"payload file is missing or outside the artifact: {name}"
            )
        files[name] = {"bytes": path.stat().st_size, "sha256": file_sha256(path)}
    body = {
        "artifact_version": ARTIFACT_VERSION,
        "artifact_kind": "derived-trained-model",
        "is_pretrained_original": False,
        "derived_from": dict(derived_from),
        "files": files,
        "config": json.loads(json.dumps(config)),
        "data_manifest_digest": data_manifest_digest,
        "metrics": json.loads(json.dumps(metrics)),
        "code": code_fingerprint(),
        "environment": environment_summary(packages),
        "evidence": evidence,
    }
    manifest = {**body, "manifest_digest": canonical_digest(body)}
    atomic_write_json(directory / MANIFEST, manifest)
    return manifest


def verify_artifact(directory: Path) -> dict:
    """Validate manifest structure, self-digest and every payload hash before use."""
    path = Path(directory) / MANIFEST
    if not path.is_file():
        raise ArtifactError("artifact manifest is missing; the artifact is incomplete")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("artifact manifest is not valid JSON") from exc
    if type(manifest) is not dict or set(manifest) != set(REQUIRED):
        raise ArtifactError("artifact manifest fields differ from the required schema")
    if (
        manifest["artifact_version"] != ARTIFACT_VERSION
        or manifest["is_pretrained_original"] is not False
    ):
        raise ArtifactError(
            "unsupported artifact version or a claimed pretrained original"
        )
    body = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if canonical_digest(body) != manifest["manifest_digest"]:
        raise ArtifactError("artifact manifest digest mismatch")
    if type(manifest["files"]) is not dict or not manifest["files"]:
        raise ArtifactError("artifact manifest lists no payload files")
    for name, info in manifest["files"].items():
        if not _safe_payload_name(name) or type(info) is not dict:
            raise ArtifactError(
                f"artifact payload name is not a plain relative path: {name}"
            )
        payload = Path(directory) / name
        if not payload.is_file():
            raise ArtifactError(f"artifact payload is missing: {name}")
        if (
            payload.stat().st_size != info["bytes"]
            or file_sha256(payload) != info["sha256"]
        ):
            raise ArtifactError(f"artifact payload checksum mismatch: {name}")
    return manifest
