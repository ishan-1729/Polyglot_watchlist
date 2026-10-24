"""Verify or inspect archived review evidence without running its workflow."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    """Define only the approved archive operations and their required inputs."""
    parser = argparse.ArgumentParser(
        prog="python -B -m watchlist.review",
        description=__doc__,
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser(
        "archive", help="read preserved evidence without permitting execution",
        allow_abbrev=False,
    )
    actions = archive.add_subparsers(dest="archive_action", required=True)
    verify = actions.add_parser(
        "verify", help="verify an archive and list its case identifiers",
        allow_abbrev=False,
    )
    verify.add_argument("--archive", type=Path, required=True, metavar="PATH")
    inspect = actions.add_parser(
        "inspect", help="verify an archive and display one saved case",
        allow_abbrev=False,
    )
    inspect.add_argument("--archive", type=Path, required=True, metavar="PATH")
    inspect.add_argument("--case-id", required=True, metavar="AUDIT_ID")
    return parser


def _error(message: str) -> int:
    """Keep expected failures on stderr, with terminal controls escaped."""
    print(json.dumps({"error": message}, ensure_ascii=True), file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Print a finite JSON result; use exit 1 for expected archive failures.

    Argument parsing happens before importing the reader. Argparse retains its
    standard exit 2 for invalid syntax and exit 0 for help. Neither path opens
    an archive. Reader failures do not print a partial success result.
    """
    args = _parser().parse_args(argv)

    from .archive import inspect_case, verify_archive
    from .compat_v1 import ArchiveError

    try:
        if args.archive_action == "verify":
            result = verify_archive(args.archive)
        else:
            result = inspect_case(args.archive, args.case_id)
    except (ArchiveError, OSError) as exc:
        return _error(str(exc))

    if not isinstance(result, dict):
        return _error("archive reader did not return a JSON object")
    try:
        output = json.dumps(result, sort_keys=True, indent=2,
                            ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        return _error("archive reader returned a value outside the finite JSON contract")
    print(output)
    return 0
