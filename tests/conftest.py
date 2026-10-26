"""Shared test hooks.

Some Step 08 tests read the owner's private permission evidence under
``data/eval-comparisons/``. The public checkout does not contain it, so a
missing private evidence file is reported as a skip with its path rather than
as a failure. Any other error still fails. Set
``WATCHLIST_REQUIRE_PRIVATE_EVIDENCE=1`` in the private checkout to make a
missing file fail as before.
"""

import os
from pathlib import Path

import pytest

PRIVATE_EVIDENCE_ROOT = (
    Path(__file__).resolve().parents[1] / "data" / "eval-comparisons"
)


def _missing_private_evidence(excinfo) -> str | None:
    """Return the missing private path when that is the whole cause of an error."""
    if excinfo is None or not isinstance(excinfo.value, FileNotFoundError):
        return None
    filename = excinfo.value.filename
    if not filename:
        return None
    path = Path(os.fspath(filename))
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path.resolve().relative_to(PRIVATE_EVIDENCE_ROOT)
    except ValueError:
        return None
    return None if path.exists() else str(path)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.failed or os.environ.get("WATCHLIST_REQUIRE_PRIVATE_EVIDENCE") == "1":
        return
    missing = _missing_private_evidence(call.excinfo)
    if missing is None:
        return
    report.outcome = "skipped"
    report.longrepr = (
        str(item.path),
        item.location[1] or 0,
        f"Skipped: private Step 08 evidence is not in this checkout: {missing}",
    )
