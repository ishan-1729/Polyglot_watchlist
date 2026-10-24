"""Offline parsing of a small organisation-only FollowTheMoney snapshot."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from watchlist.entities import Alias, Entity
from watchlist.ingest.deduplicate import NAME_PROPERTIES, deduplicate_records, reference_groups
from watchlist.normalize import normalize_name

PARSER_VERSION = "opensanctions-un-organisations-v1"
ORGANISATION_SCHEMAS = {"Organization", "Company", "LegalEntity"}


@dataclass(frozen=True)
class StoredAlias:
    """Original name evidence, including names unsuitable for this baseline."""

    alias_id: str
    name: str
    property_name: str
    normalized: str | None
    unsearchable_reason: str | None


@dataclass(frozen=True)
class ParsedEntity:
    """The matcher view plus original source evidence needed by the database."""

    entity: Entity
    schema: str
    referents: tuple[str, ...]
    aliases: tuple[StoredAlias, ...]
    raw_records: tuple[str, ...]
    group_id: str


def read_records(path: Path) -> list[dict]:
    """Read one JSON object per line and report malformed line numbers."""
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: record must be an object")
            records.append(record)
    return records


def parse_records(
    records: list[dict], *, synthetic: bool, limit: int = 20
) -> tuple[list[ParsedEntity], dict]:
    """Select at most 20 named organisation targets, retaining every name form.

    Weak aliases are retained as evidence but excluded from retrieval. Invalid
    or overlong names are preserved with reasons; records with no usable names
    are excluded and counted. Missing optional fields are not fabricated.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")
    unique, duplicate_count = deduplicate_records(records)
    # Resolve links before selecting 20 records, including links through a
    # record outside that selection. Names never participate in grouping.
    groups = reference_groups(unique)
    originals: dict[str, list[str]] = {}
    for record in records:
        originals.setdefault(record["id"], []).append(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
        )
    report = {
        "input_records": len(records), "duplicate_id_records": duplicate_count,
        "excluded": [], "unsearchable_names": [], "duplicate_alias_values": 0,
        "normalized_collisions": [], "eligible_entities": 0, "selected_entities": 0,
    }
    eligible: list[ParsedEntity] = []
    for record in unique:
        entity_id = record["id"]
        schema = record.get("schema")
        props = record["properties"]
        if schema not in ORGANISATION_SCHEMAS:
            report["excluded"].append({"id": entity_id, "reason": "unsupported_schema"})
            continue
        topics = props.get("topics", [])
        if not isinstance(topics, list) or not all(isinstance(value, str) for value in topics):
            raise ValueError(f"{entity_id}: topics must be a list of strings")
        if "sanction" not in topics:
            report["excluded"].append({"id": entity_id, "reason": "not_tagged_sanction"})
            continue
        datasets = record.get("datasets", [])
        if (not isinstance(datasets, list)
            or not all(isinstance(value, str) for value in datasets)
            or "un_sc_sanctions" not in datasets):
            raise ValueError(f"{entity_id}: missing approved dataset membership")
        referents = record.get("referents", [])
        if not isinstance(referents, list) or not all(
            isinstance(value, str) and value.strip() for value in referents
        ):
            raise ValueError(f"{entity_id}: invalid referents")
        stored: list[StoredAlias] = []
        seen_originals: set[tuple[str, str]] = set()
        seen_normalized: dict[str, str] = {}
        for key in NAME_PROPERTIES:
            for name in props.get(key, []):
                if (key, name) in seen_originals:
                    report["duplicate_alias_values"] += 1
                    continue
                seen_originals.add((key, name))
                digest = hashlib.sha256(
                    json.dumps([entity_id, key, name], ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                normalized, reason = None, None
                try:
                    normalized = normalize_name(name)
                except ValueError as exc:
                    reason = str(exc)
                if key == "weakAlias":
                    reason = "weak alias excluded from baseline retrieval"
                if reason:
                    report["unsearchable_names"].append(
                        {"id": entity_id, "alias_id": digest, "reason": reason}
                    )
                elif normalized in seen_normalized and seen_normalized[normalized] != name:
                    report["normalized_collisions"].append(
                        {"id": entity_id, "alias_id": digest}
                    )
                if normalized is not None:
                    seen_normalized[normalized] = name
                stored.append(StoredAlias(digest, name, key, normalized, reason))
        usable = sorted(
            (alias for alias in stored if alias.unsearchable_reason is None),
            key=lambda alias: alias.alias_id,
        )
        if not usable:
            report["excluded"].append({"id": entity_id, "reason": "no_usable_names"})
            continue
        caption = record.get("caption")
        display = caption if isinstance(caption, str) and caption.strip() else usable[0].name
        entity = Entity(
            entity_id, display, "legal_entity" if schema == "LegalEntity" else "organisation",
            tuple(Alias(alias.alias_id, alias.name) for alias in usable),
            synthetic, "fictional-ftm-v1" if synthetic else "opensanctions:un_sc_sanctions",
        )
        eligible.append(ParsedEntity(
            entity, schema, tuple(sorted(set(referents))), tuple(stored),
            tuple(originals[entity_id]), groups[entity_id],
        ))
    selected = eligible[:limit]
    report["eligible_entities"] = len(eligible)
    report["selected_entities"] = len(selected)
    report["excluded_by_limit"] = len(eligible) - len(selected)
    report["selected_ids"] = [item.entity.entity_id for item in selected]
    return selected, report
