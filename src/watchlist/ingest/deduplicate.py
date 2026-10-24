"""Conservative consolidation using provider IDs, never similar names."""

from copy import deepcopy

NAME_PROPERTIES = ("name", "alias", "weakAlias")


def deduplicate_records(records: list[dict]) -> tuple[list[dict], int]:
    """Union name lists for repeated IDs only when all other metadata agrees.

    Non-name differences are ambiguous in a frozen snapshot, so fail explicitly
    instead of picking whichever record happened to be read last.
    """
    by_id: dict[str, dict] = {}
    duplicate_count = 0
    for record in records:
        entity_id = record.get("id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("every source record requires a nonblank string id")
        if entity_id != entity_id.strip():
            raise ValueError("source IDs must not have surrounding whitespace")
        properties = record.get("properties")
        if not isinstance(record.get("schema"), str) or not record["schema"].strip():
            raise ValueError(f"{entity_id}: schema must be a nonblank string")
        if not isinstance(properties, dict):
            raise ValueError(f"{entity_id}: properties must be an object")
        for key in NAME_PROPERTIES:
            values = properties.get(key, [])
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError(f"{entity_id}: {key} must be a list of strings")
        if entity_id not in by_id:
            by_id[entity_id] = deepcopy(record)
            continue
        previous = by_id[entity_id]
        old_metadata = deepcopy(previous)
        new_metadata = deepcopy(record)
        for data in (old_metadata, new_metadata):
            for key in NAME_PROPERTIES:
                data["properties"].pop(key, None)
        if old_metadata != new_metadata:
            raise ValueError(f"{entity_id}: conflicting repeated-ID metadata")
        for key in NAME_PROPERTIES:
            values = previous["properties"].get(key, []) + properties.get(key, [])
            if values:
                previous["properties"][key] = sorted(set(values))
        duplicate_count += 1
    return [by_id[key] for key in sorted(by_id)], duplicate_count


def reference_groups(records: list[dict]) -> dict[str, str]:
    """Group explicit provider id/referent links; never infer links from names."""
    parent = {record["id"]: record["id"] for record in records}

    def root(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    owner: dict[str, str] = {}
    for record in sorted(records, key=lambda item: item["id"]):
        entity_id = record["id"]
        referents = record.get("referents", [])
        if not isinstance(referents, list) or not all(
            isinstance(value, str) and value.strip() for value in referents
        ):
            raise ValueError(f"{entity_id}: referents must be nonblank strings")
        for reference in [entity_id, *referents]:
            if reference in owner:
                left, right = sorted((root(entity_id), root(owner[reference])))
                parent[right] = left
            else:
                owner[reference] = entity_id
    return {entity_id: root(entity_id) for entity_id in parent}
