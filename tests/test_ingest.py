"""Offline parser and bounded downloader tests using authored records only."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import stat
import sys

import pytest

from watchlist.ingest import fetch_source
from watchlist.ingest.deduplicate import deduplicate_records
from watchlist.ingest.import_source import import_snapshot
from watchlist.ingest.parse_opensanctions import parse_records, read_records

FIXTURE = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
METADATA = FIXTURE.with_name("opensanctions_synthetic.metadata.json")


def file_tree_snapshot(root: Path) -> dict:
    """Include file bytes and directory metadata while ignoring read access time."""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_mode, info.st_ino, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
            path.read_bytes() if stat.S_ISREG(info.st_mode) else None,
        )
    return result


def organisation() -> dict:
    return deepcopy(read_records(FIXTURE)[0])


def test_fixture_selection_preserves_names_and_reports_exclusions() -> None:
    selected, report = parse_records(read_records(FIXTURE), synthetic=True)
    assert [r.entity.entity_id for r in selected] == ["fixture-001", "fixture-002", "fixture-003"]
    assert selected[1].entity.entity_type == "legal_entity"
    first = selected[0]
    assert {a.name for a in first.entity.aliases} >= {"Moonberry Loom", "MOONBERRY LOOM", "مونبيري لوم"}
    assert "Loom" not in {a.name for a in first.entity.aliases}
    assert any(a.name == "Loom" and a.unsearchable_reason for a in first.aliases)
    assert report["duplicate_alias_values"] == 1
    assert len(report["normalized_collisions"]) == 1
    assert {item["reason"] for item in report["excluded"]} == {
        "unsupported_schema", "not_tagged_sanction", "no_usable_names"
    }
    assert all(record.entity.synthetic for record in selected)


def test_duplicate_id_unions_names_but_keeps_original_evidence() -> None:
    first = organisation()
    second = deepcopy(first)
    second["properties"]["alias"] = ["Moonberry Textile Studio"]
    selected, report = parse_records([first, second], synthetic=True)
    assert len(selected) == 1 and report["duplicate_id_records"] == 1
    assert "Moonberry Textile Studio" in {a.name for a in selected[0].entity.aliases}
    assert len(selected[0].raw_records) == 2
    assert first["properties"]["alias"] == ["Moonberry Loom Studio", "مونبيري لوم"]


def test_repeated_id_conflict_is_not_silently_overwritten() -> None:
    first, second = organisation(), organisation()
    second["caption"] = "Different alleged entity"
    with pytest.raises(ValueError, match="conflicting"):
        deduplicate_records([first, second])


def test_same_name_different_ids_remain_separate() -> None:
    first, second = organisation(), organisation()
    second["id"] = "fixture-other"
    second["referents"] = []
    selected, _ = parse_records([second, first], synthetic=True)
    assert len(selected) == 2
    assert len({r.group_id for r in selected}) == 2


def test_missing_caption_and_optional_fields_have_explicit_fallback() -> None:
    record = organisation()
    del record["caption"], record["referents"]
    selected, _ = parse_records([record], synthetic=True)
    assert selected[0].entity.name in record["properties"]["name"] + record["properties"]["alias"]
    assert selected[0].referents == ()


def test_overlong_and_blank_aliases_are_retained_but_not_searched() -> None:
    record = organisation()
    record["properties"]["alias"] += ["x" * 201, " "]
    selected, report = parse_records([record], synthetic=True)
    assert {"x" * 201, " "} <= {a.name for a in selected[0].aliases}
    assert not {"x" * 201, " "} & {a.name for a in selected[0].entity.aliases}
    assert len(report["unsearchable_names"]) == 3  # also the weak alias


@pytest.mark.parametrize("change, message", [
    ({"id": None}, "id"), ({"schema": None}, "schema"),
    ({"properties": []}, "properties"), ({"referents": "wrong"}, "referents"),
    ({"datasets": []}, "dataset"),
])
def test_invalid_source_fields(change: dict, message: str) -> None:
    record = organisation()
    record.update(change)
    with pytest.raises(ValueError, match=message):
        parse_records([record], synthetic=True)


@pytest.mark.parametrize("field,value", [("name", "text"), ("alias", [1]), ("topics", "sanction")])
def test_invalid_property_types(field: str, value: object) -> None:
    record = organisation()
    record["properties"][field] = value
    with pytest.raises(ValueError, match=field):
        parse_records([record], synthetic=True)


@pytest.mark.parametrize("limit", [0, 21, True, 1.5])
def test_selection_cap(limit: object) -> None:
    with pytest.raises(ValueError, match="limit"):
        parse_records([], synthetic=True, limit=limit)


def test_selection_is_order_independent_and_grouping_precedes_limit() -> None:
    records = []
    for entity_id, refs in [("a", ["link-1"]), ("b", ["link-2"]), ("z", ["link-1", "link-2"])]:
        record = organisation()
        record.update(id=entity_id, referents=refs)
        records.append(record)
    selected, _ = parse_records(records, synthetic=True, limit=2)
    reversed_selection, _ = parse_records(list(reversed(records)), synthetic=True, limit=2)
    assert selected == reversed_selection
    assert [r.entity.entity_id for r in selected] == ["a", "b"]
    assert selected[0].group_id == selected[1].group_id


@pytest.mark.parametrize("text", ["{bad json}", "[]"])
def test_line_errors_identify_location(tmp_path: Path, text: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text("\n" + text, encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        read_records(path)


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, length: str | None = None):
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": length}

    def geturl(self) -> str:
        return fetch_source.BASE_URL + "/index.json"


@pytest.mark.parametrize("length", [None, "100"])
def test_download_cap_without_network(monkeypatch: pytest.MonkeyPatch, length: str | None) -> None:
    monkeypatch.setattr(fetch_source, "urlopen", lambda *a, **k: FakeResponse(b"123456", length))
    with pytest.raises(ValueError, match="byte limit"):
        fetch_source.read_bounded(fetch_source.BASE_URL, 5)


def mock_download(monkeypatch: pytest.MonkeyPatch, *, wrong_checksum: bool = False) -> None:
    payload = FIXTURE.read_bytes()
    metadata = {
        "name": "un_sc_sanctions", "version": "fictional-download-test",
        "resources": [{"name": "entities.ftm.json", "checksum":
                       "bad" if wrong_checksum else hashlib.sha1(payload).hexdigest()}],
    }

    def response(request, timeout):
        data = json.dumps(metadata).encode() if request.full_url.endswith("index.json") else payload
        return FakeResponse(data)

    monkeypatch.setattr(fetch_source, "urlopen", response)


def test_mocked_acquisition_and_public_branch_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_download(monkeypatch)
    receipt = fetch_source.fetch_snapshot(tmp_path)
    assert receipt["raw_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    result = import_snapshot(
        tmp_path / "raw/un_sc_sanctions/entities.ftm.json",
        tmp_path / "raw/un_sc_sanctions/index.json", tmp_path / "public-test.sqlite",
        receipt_path=tmp_path / "manifests/source.json",
    )
    assert result["selected_entities"] == 3
    with pytest.raises(ValueError, match="already exist"):
        fetch_source.fetch_snapshot(tmp_path)


def test_mismatched_remote_checksum_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_download(monkeypatch, wrong_checksum=True)
    with pytest.raises(ValueError, match="checksum"):
        fetch_source.fetch_snapshot(tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("filename", ["entities.ftm.json", "index.json"])
def test_tampered_input_receipt_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    mock_download(monkeypatch)
    fetch_source.fetch_snapshot(tmp_path)
    path = tmp_path / "raw/un_sc_sanctions" / filename
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum"):
        import_snapshot(
            tmp_path / "raw/un_sc_sanctions/entities.ftm.json",
            tmp_path / "raw/un_sc_sanctions/index.json", tmp_path / "db.sqlite",
            receipt_path=tmp_path / "manifests/source.json",
        )
    assert not (tmp_path / "db.sqlite").exists()


def test_sample_requires_fictional_marker(tmp_path: Path) -> None:
    metadata = tmp_path / "meta.json"
    metadata.write_text('{"name":"un_sc_sanctions"}')
    with pytest.raises(ValueError, match="fictional"):
        import_snapshot(FIXTURE, metadata, tmp_path / "db.sqlite", sample=True)


@pytest.mark.parametrize("exports", ["intact", "missing", "changed"])
def test_true_public_repeat_does_not_rewrite_side_exports(tmp_path, monkeypatch, exports):
    """Public-mode wiring uses only authored bytes returned by a fake download."""
    mock_download(monkeypatch)
    fetch_source.fetch_snapshot(tmp_path)
    arguments = (
        tmp_path / "raw/un_sc_sanctions/entities.ftm.json",
        tmp_path / "raw/un_sc_sanctions/index.json", tmp_path / "public-test.sqlite",
    )
    receipt = tmp_path / "manifests/source.json"
    assert import_snapshot(*arguments, receipt_path=receipt)["created"] is True
    for path in (tmp_path / "samples/un-organisations.ftm.json", tmp_path / "manifests/ingestion-report.json"):
        if exports == "missing":
            path.unlink()
        elif exports == "changed":
            path.write_text("Fictional independently edited export")
    before = file_tree_snapshot(tmp_path)
    assert import_snapshot(*arguments, receipt_path=receipt)["created"] is False
    assert file_tree_snapshot(tmp_path) == before


@pytest.mark.parametrize("evidence", ["metadata", "receipt"])
@pytest.mark.parametrize("invalid,diagnostic", [
    ('{"probe":1,"probe":2}', "duplicate JSON key"),
    ('{"nested":{"probe":1,"probe":2}}', "duplicate JSON key"),
    ('{"probe":NaN}', "nonfinite"),
    ('{"probe":Infinity}', "nonfinite"),
    ('{"probe":-Infinity}', "nonfinite"),
    ('{"probe":1e999}', "nonfinite"),
    ('[]', "must be an object"),
])
def test_ambiguous_or_nonfinite_evidence_is_rejected_unchanged(tmp_path, monkeypatch, evidence, invalid, diagnostic):
    mock_download(monkeypatch)
    fetch_source.fetch_snapshot(tmp_path)
    metadata = tmp_path / "raw/un_sc_sanctions/index.json"
    receipt = tmp_path / "manifests/source.json"
    (metadata if evidence == "metadata" else receipt).write_text(invalid)
    before = file_tree_snapshot(tmp_path)
    with pytest.raises(ValueError, match=diagnostic):
        import_snapshot(tmp_path / "raw/un_sc_sanctions/entities.ftm.json", metadata,
                        tmp_path / "must-not-exist.sqlite", receipt_path=receipt)
    assert file_tree_snapshot(tmp_path) == before


def test_deeply_nested_raw_evidence_is_a_clean_validation_failure(tmp_path, monkeypatch):
    mock_download(monkeypatch)
    fetch_source.fetch_snapshot(tmp_path)
    raw = tmp_path / "raw/un_sc_sanctions/entities.ftm.json"
    metadata = tmp_path / "raw/un_sc_sanctions/index.json"
    receipt = tmp_path / "manifests/source.json"
    depth = sys.getrecursionlimit() + 100
    raw.write_text("\n" + json.dumps(organisation())[:-1] + ',"nested":' + "[" * depth + "0" + "]" * depth + "}")
    value = json.loads(receipt.read_text())
    value.update(raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), bytes=raw.stat().st_size)
    receipt.write_text(json.dumps(value))
    before = file_tree_snapshot(tmp_path)
    with pytest.raises(ValueError, match="nesting|finite JSON"):
        import_snapshot(raw, metadata, tmp_path / "must-not-exist.sqlite", receipt_path=receipt)
    assert file_tree_snapshot(tmp_path) == before


def test_valid_json_that_exceeds_record_copy_depth_fails_cleanly(tmp_path):
    """A valid JSON decoder result can still exceed the parser's copy depth."""
    depth = sys.getrecursionlimit() // 2 + 100
    text = json.dumps(organisation())[:-1] + ',"nested":' + "[" * depth + "0" + "]" * depth + "}"
    assert isinstance(json.loads(text), dict)
    raw, metadata = tmp_path / "raw.jsonl", tmp_path / "metadata.json"
    raw.write_text(text)
    metadata.write_bytes(METADATA.read_bytes())
    before = file_tree_snapshot(tmp_path)
    with pytest.raises(ValueError, match="nesting"):
        import_snapshot(raw, metadata, tmp_path / "must-not-exist.sqlite", sample=True)
    assert file_tree_snapshot(tmp_path) == before


@pytest.mark.parametrize("field", ["bytes", "metadata_bytes"])
@pytest.mark.parametrize("value", [True, "123", -1])
def test_receipt_sizes_must_match_the_exact_saved_buffers(tmp_path, monkeypatch, field, value):
    mock_download(monkeypatch)
    fetch_source.fetch_snapshot(tmp_path)
    receipt = tmp_path / "manifests/source.json"
    metadata = tmp_path / "raw/un_sc_sanctions/index.json"
    saved = json.loads(receipt.read_text())
    saved[field] = value
    receipt.write_text(json.dumps(saved))
    before = file_tree_snapshot(tmp_path)
    with pytest.raises(ValueError, match=f"acquisition receipt {field} differs"):
        import_snapshot(tmp_path / "raw/un_sc_sanctions/entities.ftm.json", metadata,
                        tmp_path / "must-not-exist.sqlite", receipt_path=receipt)
    assert file_tree_snapshot(tmp_path) == before
