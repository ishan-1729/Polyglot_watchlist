"""Verify legacy source evidence offline and rebuild only into a new database."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from watchlist.database import compare_legacy_snapshot, verify_snapshot, write_snapshot
from watchlist.ingest.import_source import PreparedSnapshot, prepare_snapshot


TRUST_LIMIT = (
    "Checks establish consistency with supplied local source bytes and receipt; "
    "they do not independently authenticate a provider or resist replacement "
    "of all supplied evidence together."
)


def _compare(legacy_path: Path, prepared: PreparedSnapshot) -> dict:
    """Compare every retained v2 field with independently reconstructed inputs."""
    return compare_legacy_snapshot(
        legacy_path, prepared.provenance, prepared.records,
        receipt=prepared.receipt, selection=prepared.selection,
        report=prepared.report, source_metadata=prepared.source_metadata,
    )


def _new_output_path(path: Path) -> Path:
    """Require an absent destination below existing real directory ancestors."""
    if ".." in path.parts:
        raise ValueError("output path must not contain parent traversal")
    absolute = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(absolute.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError as exc:
            raise ValueError("output parent must already exist") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("output ancestors must be real directories, not symlinks")
    if os.path.lexists(absolute):
        raise ValueError("output already exists; choose a new database path")
    if any(os.path.lexists(f"{absolute}{suffix}") for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("output has SQLite sidecars; choose a new database path")
    return absolute


def verify_legacy(
    legacy_path: Path, input_path: Path, metadata_path: Path, *,
    limit: int = 20, sample: bool = False, receipt_path: Path | None = None,
) -> dict:
    """Read and compare v2 evidence without upgrading it or creating exports.

    The original raw export, metadata and acquisition receipt are required for
    public-source mode. Explicit sample mode accepts only fictional metadata.
    A successful result does not make a v2 database loadable as a v3 database.
    """
    prepared = prepare_snapshot(
        input_path, metadata_path, limit=limit, sample=sample, receipt_path=receipt_path,
    )
    compared = _compare(legacy_path, prepared)
    return {
        **compared, "status": "verified", "legacy_schema_version": 2,
        "verification_basis": "legacy content matches independently reconstructed supplied inputs",
        "trust_limit": TRUST_LIMIT,
    }


def rebuild_legacy(
    legacy_path: Path, input_path: Path, metadata_path: Path, output_path: Path, *,
    limit: int = 20, sample: bool = False, receipt_path: Path | None = None,
) -> dict:
    """Compare v2, then publish a separately verified v3 file without overwrite.

    Staging stays in a private directory under the existing output parent. The
    final hard link succeeds only if the output is still absent. Failure before
    publication removes staging and leaves all supplied originals untouched.
    """
    output = _new_output_path(output_path)
    prepared = prepare_snapshot(
        input_path, metadata_path, limit=limit, sample=sample, receipt_path=receipt_path,
    )
    compared = _compare(legacy_path, prepared)
    staged_identity: tuple[int, int] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=".watchlist-source-migration-", dir=output.parent) as temporary:
            staged = Path(temporary) / "rebuilt.sqlite"
            created = write_snapshot(
                staged, prepared.provenance, prepared.records,
                receipt=prepared.receipt, selection=prepared.selection,
                report=prepared.report, source_metadata=prepared.source_metadata,
            )
            if created is not True:
                raise ValueError("migration staging did not create a new source database")
            verified = verify_snapshot(staged)
            if verified.get("status") != "verified" or verified.get("snapshot_id") != compared["snapshot_id"]:
                raise ValueError("rebuilt source verification did not confirm the expected snapshot")
            _new_output_path(output)
            info = staged.stat()
            staged_identity = (info.st_dev, info.st_ino)
            # Unlike replace/rename, link cannot overwrite a file created after
            # the absence check. Context cleanup removes the private stage link.
            os.link(staged, output, follow_symlinks=False)
    except BaseException:
        # A publication/cleanup failure may occur after the link was created.
        # Remove only our own inode, never an independently created destination.
        if staged_identity is not None:
            try:
                info = output.lstat()
            except FileNotFoundError:
                pass
            else:
                if (info.st_dev, info.st_ino) == staged_identity:
                    output.unlink()
        raise
    return {
        **verified, "status": "rebuilt", "legacy_schema_version": 2,
        "source_metadata_retained": True,
        "verification_basis": "legacy compared with supplied inputs; new v3 content verified before publication",
        "trust_limit": TRUST_LIMIT,
    }


def main() -> int:
    """Expose explicit verify/rebuild operations with no acquisition behavior."""
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("verify", "rebuild"):
        command = actions.add_parser(action)
        command.add_argument("--legacy", type=Path, required=True, help="Preserved legacy v2 source database")
        command.add_argument("--input", type=Path, required=True, help="Original saved JSON-lines export")
        command.add_argument("--metadata", type=Path, required=True, help="Original saved provider metadata")
        command.add_argument("--receipt", type=Path, help="Original saved acquisition receipt; required outside sample mode")
        command.add_argument("--limit", type=int, default=20, help="Original selection limit (1 to 20)")
        command.add_argument("--sample", action="store_true", help="Explicitly fictional original input and metadata")
        if action == "rebuild":
            command.add_argument("--output", type=Path, required=True, help="Absent v3 output below an existing directory")
    args = parser.parse_args()
    if not args.sample and args.receipt is None:
        parser.error("public mode requires --receipt")
    if args.sample and args.receipt is not None:
        parser.error("sample mode reconstructs its fictional receipt; do not supply --receipt")
    options = {"limit": args.limit, "sample": args.sample, "receipt_path": args.receipt}
    try:
        if args.action == "verify":
            result = verify_legacy(args.legacy, args.input, args.metadata, **options)
        else:
            result = rebuild_legacy(args.legacy, args.input, args.metadata, args.output, **options)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
