"""Prepare stable entity-group partitions; no benchmark or training is run."""

import argparse
from collections.abc import Sequence
import hashlib
import json
from pathlib import Path
import sqlite3

from watchlist.database import connect_database, load_database
from watchlist.ingest.deduplicate import reference_groups

PARTITIONS = ((50, "train"), (65, "development"), (75, "calibration_fit"),
              (85, "threshold_selection"), (100, "test"))
PARTITION_NAMES = frozenset(name for _, name in PARTITIONS)


def validate_seed(seed: object) -> int:
    """Require an integer seed; retain the existing meaning of negative integers."""
    if type(seed) is not int:
        raise ValueError("split seed must be an integer, not a boolean or coerced value")
    return seed


def _identifier(value: object, label: str) -> str:
    """Reject blank, padded or non-Unicode IDs instead of changing their meaning."""
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank string without surrounding whitespace")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must contain valid Unicode text") from exc
    return value


def validate_assignments(entity_ids: Sequence[str], assignments: dict) -> None:
    """Check exact ID coverage and one partition per explicit provider group.

Partitions describe data use, not whether a target is present or a label is
ambiguous. Those independent labels belong to queries. This validates supplied
group ownership; ``assign_groups`` constructs groups from provider links before
assignment, and evaluation additionally binds this mapping to its source view.
    """
    if isinstance(entity_ids, (str, bytes)) or not isinstance(entity_ids, Sequence):
        raise ValueError("entity IDs must be a sequence of strings")
    ids = [_identifier(value, "entity ID") for value in entity_ids]
    if len(ids) != len(set(ids)):
        raise ValueError("partition coverage or duplicate entity ID error")
    if type(assignments) is not dict:
        raise ValueError("partition assignments must be an object")
    for key in assignments:
        _identifier(key, "assignment entity ID")
    if set(ids) != set(assignments):
        raise ValueError("partition coverage or duplicate entity ID error")
    groups: dict[str, set[str]] = {}
    for item in assignments.values():
        if type(item) is not dict or set(item) != {"group_id", "partition"}:
            raise ValueError("partition assignment must contain only group_id and partition")
        group = _identifier(item["group_id"], "group ID")
        partition = item["partition"]
        if not isinstance(partition, str) or partition not in PARTITION_NAMES:
            raise ValueError("invalid partition; presence and ambiguity are separate query labels")
        groups.setdefault(group, set()).add(partition)
    if any(len(partitions) != 1 for partitions in groups.values()):
        raise ValueError("entity group leakage across partitions")


def assign_groups(records: list[dict], seed: int = 42) -> dict[str, dict[str, str]]:
    """Hash explicit provider-linked groups into fixed percentage buckets.

    Hashing makes membership independent of input order. Percentages are target
    proportions, not guaranteed counts, especially for a 20-record sample.
    """
    seed = validate_seed(seed)
    if type(records) is not list:
        raise ValueError("source records must be a list of objects")
    ids = []
    for record in records:
        if type(record) is not dict:
            raise ValueError("each source record must be an object")
        entity_id = _identifier(record.get("id"), "source record ID")
        ids.append(entity_id)
        referents = record.get("referents", [])
        if type(referents) is not list:
            raise ValueError(f"{entity_id}: referents must be a list of strings")
        for value in referents:
            _identifier(value, f"{entity_id}: referent")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate IDs must be resolved before splitting")
    groups = reference_groups(records)
    assignments = {}
    for entity_id, group in sorted(groups.items()):
        digest = hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()
        bucket = int(digest, 16) % 100
        partition = next(name for upper, name in PARTITIONS if bucket < upper)
        assignments[entity_id] = {"group_id": group, "partition": partition}
    validate_assignments(ids, assignments)
    return assignments


def create_manifest(db_path: Path, seed: int = 42) -> dict:
    """Bind assignments to an exact snapshot and flag shared normalized names."""
    seed = validate_seed(seed)
    _, provenance, _ = load_database(db_path)
    connection = connect_database(db_path, readonly=True)
    try:
        records = [{"id": row["entity_id"],
                    "referents": [*json.loads(row["referents_json"]), row["group_id"]]}
                   for row in connection.execute("SELECT entity_id, referents_json, group_id FROM entities")]
        assignments = assign_groups(records, seed)
        names: dict[str, set[str]] = {}
        for row in connection.execute(
            "SELECT entity_id, normalized_name FROM aliases WHERE unsearchable_reason IS NULL"
        ):
            names.setdefault(row["normalized_name"], set()).add(row["entity_id"])
        collisions = [{"normalized_name": name, "entity_ids": sorted(ids)}
                      for name, ids in sorted(names.items()) if len(ids) > 1]
    finally:
        connection.close()
    counts = {name: sum(a["partition"] == name for a in assignments.values())
              for _, name in PARTITIONS}
    return {
        "snapshot_id": provenance.snapshot_id, "raw_sha256": provenance.raw_sha256,
        "algorithm": "sha256-provider-group-v1", "seed": seed,
        "assignments": assignments, "entity_counts": counts,
        "shared_normalized_names": collisions,
        "limitations": "Tiny teaching sample; no performance estimate. Shared names are not identity links.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = create_manifest(args.db, args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest["entity_counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
