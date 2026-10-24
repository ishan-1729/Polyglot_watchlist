"""Shared matching records and the deliberately strict fictional JSON loader."""

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path

from watchlist.normalize import normalize_name

SYNTHETIC_SOURCE = "fictional-synthetic-v1"


@dataclass(frozen=True)
class Alias:
    """One display spelling and its stable identifier."""

    alias_id: str
    name: str


@dataclass(frozen=True)
class Provenance:
    """A frozen research snapshot, distinct from the entity's name or identity."""

    snapshot_id: str
    dataset: str
    provider: str
    publisher: str
    source_url: str
    download_url: str
    retrieved_at: str
    source_updated_at: str | None
    export_version: str | None
    raw_sha256: str
    license_url: str


@dataclass(frozen=True)
class Entity:
    """One reference record; a shared name does not establish shared identity."""

    entity_id: str
    name: str
    entity_type: str
    aliases: tuple[Alias, ...]
    synthetic: bool
    source: str
    provenance: Provenance | None = None


def _text(record: dict[str, object], key: str) -> str:
    """Require a nonblank string field while preserving its original spelling."""
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonblank string")
    return value


def load_entities(path: Path | None = None) -> tuple[Entity, ...]:
    """Read and validate fictional JSON records, defaulting to packaged data.

    The optional path supports local test fixtures, not public-data ingestion.
    Entity IDs and alias IDs must be globally unique. Within one entity,
    normalized aliases must differ. Across entities, shared names are allowed.
    An empty list is a valid empty corpus; broken records are explicit errors.
    """
    if path is None:
        text = (
            files("watchlist")
            .joinpath("data", "synthetic_entities.json")
            .read_text(encoding="utf-8")
        )
    else:
        text = path.read_text(encoding="utf-8")
    records = json.loads(text)
    if not isinstance(records, list):
        raise ValueError("dataset must be a JSON list")

    entities: list[Entity] = []
    entity_ids: set[str] = set()
    alias_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each entity must be a JSON object")
        entity_id = _text(record, "entity_id")
        if entity_id != entity_id.strip() or entity_id in entity_ids:
            raise ValueError(f"duplicate or whitespace-padded entity_id: {entity_id}")
        entity_ids.add(entity_id)
        name = _text(record, "name")
        normalized_name = normalize_name(name)
        entity_type = _text(record, "entity_type")
        if entity_type not in {"person", "organisation"}:
            raise ValueError("entity_type must be person or organisation")
        if record.get("synthetic") is not True:
            raise ValueError("every entity must declare synthetic: true")
        if record.get("source") != SYNTHETIC_SOURCE:
            raise ValueError(f"source must be {SYNTHETIC_SOURCE}")

        raw_aliases = record.get("aliases")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            raise ValueError(f"{entity_id}: aliases must be a nonempty list")
        aliases: list[Alias] = []
        normalized_aliases: set[str] = set()
        for raw_alias in raw_aliases:
            if not isinstance(raw_alias, dict):
                raise ValueError("each alias must be a JSON object")
            alias_id = _text(raw_alias, "alias_id")
            if alias_id != alias_id.strip() or alias_id in alias_ids:
                raise ValueError(f"duplicate or whitespace-padded alias_id: {alias_id}")
            alias_ids.add(alias_id)
            alias_name = _text(raw_alias, "name")
            normalized_alias = normalize_name(alias_name)
            if normalized_alias in normalized_aliases:
                raise ValueError(f"{entity_id}: duplicate normalized alias")
            normalized_aliases.add(normalized_alias)
            aliases.append(Alias(alias_id=alias_id, name=alias_name))
        if normalized_name not in normalized_aliases:
            raise ValueError(f"{entity_id}: aliases must include the canonical name")
        entities.append(
            Entity(
                entity_id=entity_id,
                name=name,
                entity_type=entity_type,
                aliases=tuple(aliases),
                synthetic=True,
                source=SYNTHETIC_SOURCE,
            )
        )
    return tuple(entities)
