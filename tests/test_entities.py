"""Dataset integrity and malformed-input cases."""

import json
from pathlib import Path

import pytest

from watchlist.entities import SYNTHETIC_SOURCE, load_entities
from watchlist.normalize import normalize_name


def fictional_record() -> dict:
    """Return a fresh small record so each corruption test is independent."""
    return {
        "entity_id": "syn-test",
        "name": "Luma Vesper",
        "entity_type": "person",
        "synthetic": True,
        "source": SYNTHETIC_SOURCE,
        "aliases": [
            {"alias_id": "syn-test-a1", "name": "Luma Vesper"},
            {"alias_id": "syn-test-a2", "name": "L. Vesper"},
        ],
    }


def write_data(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "fictional.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_packaged_fixture_contract() -> None:
    entities = load_entities()
    assert [e.entity_id for e in entities] == [f"syn-{i:03d}" for i in range(1, 13)]
    assert sum(len(e.aliases) for e in entities) == 24
    assert {e.entity_type for e in entities} == {"person", "organisation"}
    alias_ids = [a.alias_id for e in entities for a in e.aliases]
    assert len(set(alias_ids)) == len(alias_ids)
    for entity in entities:
        assert 2 <= len(entity.aliases) <= 3
        assert entity.synthetic is True and entity.source == SYNTHETIC_SOURCE
        normalized = {normalize_name(a.name) for a in entity.aliases}
        assert len(normalized) == len(entity.aliases)
    assert entities[0].name == entities[-1].name == "Luma Vesper"
    names = {a.name for e in entities for a in e.aliases}
    assert {"Élo Nivara", "Мира Велуне", "سيرا لومين"} <= names


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("entity_id", " ", "entity_id"),
        ("entity_id", " syn-test ", "whitespace-padded"),
        ("name", 123, "name"),
        ("name", "x" * 201, "at most 200"),
        ("entity_type", "unknown", "entity_type"),
        ("synthetic", False, "synthetic"),
        ("synthetic", 1, "synthetic"),
        ("source", "unapproved-source", "source"),
        ("aliases", [], "nonempty list"),
        ("aliases", {}, "nonempty list"),
        ("aliases", [42], "alias must be a JSON object"),
        ("aliases", [{"alias_id": "a1", "name": " "}], "name"),
        ("aliases", [{"alias_id": "a1", "name": "Another Name"}], "canonical name"),
    ],
)
def test_malformed_fields(tmp_path: Path, field: str, value: object, message: str) -> None:
    record = fictional_record()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        load_entities(write_data(tmp_path, [record]))


def test_missing_field(tmp_path: Path) -> None:
    record = fictional_record()
    del record["entity_id"]
    with pytest.raises(ValueError, match="entity_id"):
        load_entities(write_data(tmp_path, [record]))


@pytest.mark.parametrize("data", [{}, [None]])
def test_wrong_json_structure(tmp_path: Path, data: object) -> None:
    with pytest.raises(ValueError, match="JSON"):
        load_entities(write_data(tmp_path, data))


def test_broken_json_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("[", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_entities(path)
    with pytest.raises(FileNotFoundError):
        load_entities(tmp_path / "missing.json")


def test_duplicate_entity_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate.*entity_id"):
        load_entities(write_data(tmp_path, [fictional_record(), fictional_record()]))


def test_duplicate_alias_id_across_entities(tmp_path: Path) -> None:
    second = fictional_record()
    second["entity_id"] = "syn-other"
    with pytest.raises(ValueError, match="duplicate.*alias_id"):
        load_entities(write_data(tmp_path, [fictional_record(), second]))


def test_normalized_alias_collision(tmp_path: Path) -> None:
    record = fictional_record()
    record["aliases"][1]["name"] = "  LUMA   VESPER "
    with pytest.raises(ValueError, match="duplicate normalized alias"):
        load_entities(write_data(tmp_path, [record]))


def test_empty_corpus(tmp_path: Path) -> None:
    assert load_entities(write_data(tmp_path, [])) == ()
