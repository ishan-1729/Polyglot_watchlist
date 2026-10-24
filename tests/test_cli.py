"""CLI integration through the same Python interpreter used by pytest."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from watchlist import cli


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "watchlist", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )


def test_cli_json_from_another_working_directory(tmp_path: Path) -> None:
    result = run_cli("--name", "  LUMA   VESPER  ", "--top-k", "3", cwd=tmp_path)
    assert result.returncode == 0 and result.stderr == ""
    output = json.loads(result.stdout)
    assert output["query"] == "  LUMA   VESPER  "
    assert output["normalized_query"] == "luma vesper"
    assert output["top_k"] == 3
    assert output["scorer"] == "rapidfuzz.normalized_levenshtein_similarity_x100"
    assert [c["rank"] for c in output["candidates"]] == [1, 2, 3]
    assert [c["entity_id"] for c in output["candidates"][:2]] == ["syn-001", "syn-012"]
    first = output["candidates"][0]
    assert first["matched_alias"] == first["display_name"] == "Luma Vesper"
    assert first["matched_alias_id"] == "syn-001-a1"
    assert first["similarity_score"] == 100
    assert first["synthetic"] is True and first["source"] == "fictional-synthetic-v1"
    assert "probability" not in first and "decision" not in output
    assert "not identity confirmation" in output["notice"]
    assert "scores are not probabilities" in output["notice"]


def test_cli_defaults_and_unicode_display() -> None:
    result = run_cli("--name", "سيرا لومين")
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["top_k"] == len(output["candidates"]) == 5
    assert output["candidates"][0]["entity_id"] == "syn-007"
    assert "سيرا لومين" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], "required"),
        (["--name", "   "], "blank"),
        (["--name", "x" * 201], "at most 200"),
        (["--name", "Luma", "--top-k", "0"], "positive integer"),
        (["--name", "Luma", "--top-k", "-1"], "positive integer"),
        (["--name", "Luma", "--top-k", "abc"], "invalid int value"),
    ],
)
def test_cli_validation_errors(arguments: list[str], message: str) -> None:
    result = run_cli(*arguments)
    assert result.returncode == 2
    assert result.stdout == ""
    assert message in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_reports_broken_fixture(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken_loader() -> None:
        raise ValueError("malformed fictional fixture")

    monkeypatch.setattr(cli, "load_entities", broken_loader)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--name", "Luma"])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == "" and "malformed fictional fixture" in output.err


def test_cli_help() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "fictional" in result.stdout


def test_database_cli_uses_fictional_fixture_outside_checkout(tmp_path: Path) -> None:
    from watchlist.ingest.import_source import import_snapshot

    fixture = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
    db = tmp_path / "sample.sqlite"
    import_snapshot(fixture, fixture.with_name("opensanctions_synthetic.metadata.json"), db, sample=True)
    result = run_cli("--db", str(db), "--name", "Moonberry Loom", "--top-k", "2", cwd=tmp_path)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert [c["entity_id"] for c in output["candidates"]] == ["fixture-001", "fixture-003"]
    assert output["snapshot"]["dataset"] == "fictional-ftm-v1"
    assert "All reference records are fictional" in output["notice"]


def test_public_mode_notice_with_authored_records_only(tmp_path: Path) -> None:
    import hashlib
    from watchlist.ingest.import_source import import_snapshot
    from watchlist.ingest.fetch_source import LICENSE_URL

    fixture = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
    metadata = tmp_path / "index.json"
    metadata.write_text('{"name":"un_sc_sanctions","version":"test-only"}')
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "dataset": "un_sc_sanctions", "synthetic": False,
        "license_url": LICENSE_URL, "raw_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "metadata_sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
        "provider": "Authored test provider", "publisher": "Authored test publisher",
        "source_url": "https://example.invalid/fixture", "download_url": "",
        "retrieved_at": "test-only; no real download",
    }))
    db = tmp_path / "public-branch.sqlite"
    import_snapshot(fixture, metadata, db, receipt_path=receipt)
    result = run_cli("--db", str(db), "--name", "Moonberry Loom", "--top-k", "1")
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["candidates"][0]["synthetic"] is False
    assert output["candidates"][0]["provenance"] == output["snapshot"]
    assert "All reference records are fictional" not in output["notice"]
    assert "limited public-data snapshot" in output["notice"]
    assert "neither identity nor wrongdoing" in output["notice"]


@pytest.mark.parametrize("bad_file", [False, True])
def test_database_error_is_clear_and_never_creates_a_missing_file(tmp_path: Path, bad_file: bool) -> None:
    path = tmp_path / "bad.sqlite"
    if bad_file:
        path.write_text("not a SQLite database")
    result = run_cli("--db", str(path), "--name", "Moonberry Loom")
    assert result.returncode == 2 and result.stdout == ""
    assert "Traceback" not in result.stderr
    assert path.exists() == bad_file
