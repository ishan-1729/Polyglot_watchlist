"""Offline C1 readiness queues: source assertions and restrictions, never labels.

The final manifest is a no-replace completion marker, not corpus acceptance.
Validation regenerates content from externally pinned source evidence. Run the
CLI under resource_guard.supervise_command for sampled process-group enforcement;
its own guard provides cooperative checks. No model or network client is used.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Callable
import uuid

from watchlist import corpus
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import (
    ResourceGuard,
    ResourceStop,
    _artifact_size,
    system_snapshot,
)
from watchlist.normalize import normalize_name

SCOPE = "08B-C1-offline-readiness"
ARTIFACT_KIND = "readiness_preparation"
MAX_BYTES = 64 * 1024**2
LIMITS = {
    "max_new_artifact_bytes": MAX_BYTES,
    "max_records": 20_000,
    "max_names": 100_000,
    "max_pairs": 100_000,
    "max_witnesses": 1_000_000,
    "max_total_name_characters": 10_000_000,
    "max_name_characters": 100_000,
    "session_seconds": 3600,
}
RESTRICTIONS = {
    "network_allowed": False,
    "human_review_execution_allowed": False,
    "identity_merge_allowed": False,
    "accepted_corpus_release_allowed": False,
    "training_allowed": False,
    "step09_allowed": False,
    "publication_allowed": False,
    "fresh_final_eligible": False,
}
COUNT_KEYS = frozenset(
    {
        "observations",
        "organizations",
        "vessels",
        "name_entries",
        "candidate_pairs",
        "exact_pairs",
        "normalized_only_pairs",
        "review_components",
        "collision_records",
        "weak_name_entries",
        "weak_records",
        "overlength_name_entries",
        "overlength_records",
        "flagged_records",
        "unknown_language_entries",
    }
)
PAYLOAD_NAMES = frozenset(
    {
        "input-manifest.json",
        "observations.jsonl",
        "nominations.jsonl",
        "components.jsonl",
        "quarantine.jsonl",
        "summary.json",
    }
)


class ReadinessError(ValueError):
    """A preparation boundary failed; no source-derived text is required."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json(payload: bytes) -> dict:
    try:
        return corpus._json_object(payload, "readiness object")
    except (ValueError, UnicodeError, TypeError):
        raise ReadinessError("invalid_readiness_json") from None


def _fields(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ReadinessError("unexpected_readiness_fields")
    return value


def _relative(value: object) -> str:
    try:
        return corpus._relative(value)
    except (ValueError, TypeError):
        raise ReadinessError("unsafe_relative_path") from None


def _path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if ".." in path.parts or not path.is_relative_to(root):
        raise ReadinessError("path_outside_project")
    return path


def _reference(root: Path, value: dict, *, maximum: int) -> bytes:
    _fields(value, {"path", "sha256"})
    relative = _relative(value["path"])
    corpus._digest(value["sha256"], "readiness reference")
    payload = corpus._read_saved(root / relative, maximum, "readiness input")
    if _sha(payload) != value["sha256"]:
        raise ReadinessError("readiness_input_digest_mismatch")
    return payload


def _load_config(path: Path, root: Path) -> tuple[dict, bytes]:
    raw = corpus._read_saved(path, 2_000_000, "readiness config")
    config = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "receipt",
            "output_path",
            "artifact_roots",
            "normalized_inputs",
            "expected_counts",
            "limits",
            "permissions",
            "versions",
            "entity_types",
        },
    )
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["scope"] != SCOPE
    ):
        raise ReadinessError("unapproved_readiness_scope")
    if config["limits"] != LIMITS or any(
        type(v) is not int for v in config["limits"].values()
    ):
        raise ReadinessError("unapproved_readiness_limits")
    if config["permissions"] != RESTRICTIONS or any(
        type(v) is not bool for v in config["permissions"].values()
    ):
        raise ReadinessError("unapproved_readiness_permissions")
    if config["versions"] != {
        "normalization": links.READINESS_NORMALIZATION_VERSION,
        "nomination": links.READINESS_NOMINATION_VERSION,
        "unicode": links.READINESS_UNICODE_VERSION,
    }:
        raise ReadinessError("unapproved_readiness_versions")
    if config["entity_types"] != ["organization", "vessel"]:
        raise ReadinessError("unapproved_entity_types")
    counts = _fields(config["expected_counts"], COUNT_KEYS)
    if any(type(v) is not int or v < 0 for v in counts.values()):
        raise ReadinessError("invalid_expected_counts")
    output = root / _relative(config["output_path"])
    roots = config["artifact_roots"]
    if (
        type(roots) is not list
        or not 1 <= len(roots) <= 8
        or any(type(item) is not str for item in roots)
        or len(set(roots)) != len(roots)
    ):
        raise ReadinessError("invalid_artifact_roots")
    for item in roots:
        descriptor = corpus._open_directory(root / _relative(item))
        os.close(descriptor)
    if output.parent.relative_to(root).as_posix() not in roots:
        raise ReadinessError("output_root_not_monitored")
    normalized = config["normalized_inputs"]
    if type(normalized) is not list or not 1 <= len(normalized) <= 16:
        raise ReadinessError("invalid_normalized_inputs")
    paths = [
        _relative(_fields(item, {"path", "sha256"})["path"]) for item in normalized
    ]
    if len(paths) != len(set(paths)):
        raise ReadinessError("duplicate_normalized_reservation")
    _fields(config["receipt"], {"path", "sha256"})
    _relative(config["receipt"]["path"])
    corpus._digest(config["receipt"]["sha256"], "receipt")
    return config, raw


def _checkpoint(guard: ResourceGuard) -> Callable[[], None]:
    last = time.monotonic()

    def check() -> None:
        nonlocal last
        now = time.monotonic()
        if now - last >= 0.25:
            guard.check()
            last = now

    return check


def _resource_guard(
    root: Path, config: dict, guard: ResourceGuard | None
) -> ResourceGuard:
    roots = tuple(root / relative for relative in config["artifact_roots"])
    if guard is None:
        guard = ResourceGuard(
            probe=lambda: system_snapshot(roots[0], additional_artifact_roots=roots[1:])
        )
    if not isinstance(guard, ResourceGuard):
        raise ReadinessError("resource_guard_required")
    if not guard.admitted:
        guard.admit()
    else:
        guard.check()
    normalized = 0
    for reference in config["normalized_inputs"]:
        normalized += len(_reference(root, reference, maximum=100_000_000))
        guard.check()
    new_root_bytes = _artifact_size(
        (root / config["output_path"]).parent, required=True
    )
    if new_root_bytes > MAX_BYTES:
        raise ReadinessError("new_preparation_artifact_limit")
    # Conservatively charge existing C1 evidence/logs as well as retained selections.
    normalized += new_root_bytes
    if guard.normalized_bytes < normalized:
        guard.normalized_bytes = normalized
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")
    return guard


def _json_lines(values: list[dict], checkpoint: Callable[[], None]) -> bytes:
    chunks = []
    size = 0
    for value in values:
        checkpoint()
        chunk = _canonical(value)
        size += len(chunk)
        if size > MAX_BYTES:
            raise ReadinessError("readiness_output_byte_limit")
        chunks.append(chunk)
    return b"".join(chunks)


def assemble_readiness(
    preparation: corpus.ContinuationPreparation,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, bytes]:
    """Derive deterministic unreviewed queues; never establish human identity.

    I/O entry points obtain this typed object only by strict source admission.
    Original evidence values/qualifiers remain intact; order is canonicalized.
    """
    checkpoint = checkpoint or (lambda: None)
    if not isinstance(preparation, corpus.ContinuationPreparation):
        raise ReadinessError("continuation_preparation_required")
    if _sha(preparation.input_manifest_bytes) != preparation.input_manifest_sha256:
        raise ReadinessError("preparation_manifest_digest_mismatch")
    observations = sorted(
        preparation.observations, key=lambda item: item.observation_id
    )
    if not 1 <= len(observations) <= LIMITS["max_records"]:
        raise ReadinessError("readiness_record_limit")
    if len({item.observation_id for item in observations}) != len(observations):
        raise ReadinessError("duplicate_observation_id")
    record_rows = []
    link_rows = []
    names = {}
    weak = {}
    overlength = {}
    unknown = 0
    total_chars = 0
    multiple_usable = set()
    for observation in observations:
        checkpoint()
        if observation.source_record_key != (
            observation.source_id,
            observation.provider_id,
        ):
            raise ReadinessError("source_key_mismatch")
        if observation.entity_type not in {"organization", "vessel"}:
            raise ReadinessError("unapproved_entity_type")
        record = asdict(observation)
        record["aliases"] = sorted(
            record["aliases"], key=lambda item: item["evidence_id"]
        )
        record_rows.append(record)
        alias_refs = []
        usable_keys = set()
        for alias in sorted(observation.aliases, key=lambda item: item.evidence_id):
            total_chars += len(alias.value)
            if (
                len(alias.value) > LIMITS["max_name_characters"]
                or total_chars > LIMITS["max_total_name_characters"]
            ):
                raise ReadinessError("readiness_name_character_limit")
            if alias.evidence_id in names or len(names) >= LIMITS["max_names"]:
                raise ReadinessError("invalid_or_excess_name_evidence")
            names[alias.evidence_id] = observation.observation_id
            alias_refs.append(links.LinkName(alias.evidence_id, alias.value))
            unknown += alias.language is None
            attrs = dict(alias.attributes)
            isweak = (
                observation.source_id == "ofac_sdn"
                and attrs.get("category", "").casefold() == "weak"
            ) or (
                observation.source_id == "opensanctions_un"
                and alias.field == "properties.weakAlias"
            )
            if isweak:
                weak[alias.evidence_id] = observation.observation_id
            try:
                normalize_name(alias.value)
            except ValueError:
                # Preserve originals; no name repair or limit relaxation.
                overlength[alias.evidence_id] = observation.observation_id
            else:
                if not isweak:
                    usable_keys.add(links.readiness_name_key(alias.value))
        if len(usable_keys) >= 2:
            multiple_usable.add(observation.observation_id)
        link_rows.append(
            links.LinkRecord(
                observation.observation_id,
                observation.source_record_key,
                observation.snapshot_id,
                tuple(alias_refs),
            )
        )
    nominations = links.nominate_readiness_links(
        tuple(link_rows),
        preparation_input_sha256=preparation.input_manifest_sha256,
        checkpoint=checkpoint,
        **{
            k: LIMITS[k]
            for k in (
                "max_records",
                "max_names",
                "max_pairs",
                "max_witnesses",
                "max_total_name_characters",
                "max_name_characters",
            )
        },
    )
    adjacent = defaultdict(set)
    for nomination in nominations:
        adjacent[nomination.left].add(nomination.right)
        adjacent[nomination.right].add(nomination.left)
    remaining = set(adjacent)
    components = []
    component_for = {}
    while remaining:
        checkpoint()
        first = min(remaining)
        remaining.remove(first)
        members = {first}
        todo = [first]
        while todo:
            checkpoint()
            for neighbor in sorted(adjacent[todo.pop()] & remaining):
                remaining.remove(neighbor)
                members.add(neighbor)
                todo.append(neighbor)
        ordered = sorted(members)
        cid = "readiness-component-" + _sha(
            _canonical([preparation.input_manifest_sha256, ordered])
        )
        components.append(
            {
                "component_id": cid,
                "observation_ids": ordered,
                "reason": "unresolved_duplicate_candidate",
                "identity_confirmed": False,
                "preparation_input_sha256": preparation.input_manifest_sha256,
            }
        )
        component_for.update({member: cid for member in members})
    restrictions = defaultdict(list)
    for evidence_id in sorted(set(weak) | set(overlength)):
        reasons = []
        if evidence_id in weak:
            reasons.append("explicit_source_weak_name")
        if evidence_id in overlength:
            reasons.append("normalization_contract_rejected")
        restrictions[names[evidence_id]].append(
            {
                "evidence_id": evidence_id,
                "reasons": reasons,
                "excluded_from": [
                    "positive_label_use",
                    "negative_mining",
                    "final_query_use",
                ]
                + (["matcher_input"] if evidence_id in overlength else []),
                "original_preserved": True,
            }
        )
    quarantine = []
    for oid in sorted(set(component_for) | set(restrictions)):
        checkpoint()
        quarantine.append(
            {
                "observation_id": oid,
                "component_id": component_for.get(oid),
                "group_reasons": ["unresolved_duplicate_candidate"]
                if oid in component_for
                else [],
                "name_restrictions": restrictions.get(oid, []),
                "valid_sibling_names_discarded": False,
                "human_resolution": None,
                "identity_confirmed": False,
            }
        )
    exact = sum("exact_name" in nomination.methods for nomination in nominations)
    counts = {
        "observations": len(observations),
        "organizations": sum(o.entity_type == "organization" for o in observations),
        "vessels": sum(o.entity_type == "vessel" for o in observations),
        "name_entries": len(names),
        "candidate_pairs": len(nominations),
        "exact_pairs": exact,
        "normalized_only_pairs": len(nominations) - exact,
        "review_components": len(components),
        "collision_records": len(component_for),
        "weak_name_entries": len(weak),
        "weak_records": len(set(weak.values())),
        "overlength_name_entries": len(overlength),
        "overlength_records": len(set(overlength.values())),
        "flagged_records": len(quarantine),
        "unknown_language_entries": unknown,
    }
    source_counts = {
        source: {
            "observations": sum(o.source_id == source for o in observations),
            "name_entries": sum(
                len(o.aliases) for o in observations if o.source_id == source
            ),
        }
        for source in sorted({o.source_id for o in observations})
    }
    duplicate_ids = set(component_for)
    weak_ids = set(weak.values())
    long_ids = set(overlength.values())
    intersections = {
        "duplicate_and_weak_records": len(duplicate_ids & weak_ids),
        "duplicate_and_overlength_records": len(duplicate_ids & long_ids),
        "weak_and_overlength_records": len(weak_ids & long_ids),
        "all_three_records": len(duplicate_ids & weak_ids & long_ids),
        "no_listed_flag_records": len(observations) - len(quarantine),
    }
    all_ids = {item.observation_id for item in observations}
    flagged_ids = duplicate_ids | weak_ids | long_ids

    def group_counts(ids: set[str]) -> dict:
        selected = [item for item in observations if item.observation_id in ids]
        return {
            "groups": len(selected),
            "organizations": sum(
                item.entity_type == "organization" for item in selected
            ),
            "vessels": sum(item.entity_type == "vessel" for item in selected),
            "by_source": dict(
                sorted(Counter(item.source_id for item in selected).items())
            ),
        }

    diagnostics = {
        "collision_involved": group_counts(duplicate_ids),
        "explicit_weak_name_groups": group_counts(weak_ids),
        "normalizer_rejected_name_groups": group_counts(long_ids),
        "any_of_three_flags": group_counts(flagged_ids),
        "collision_and_weak": group_counts(duplicate_ids & weak_ids),
        "collision_and_overlength": group_counts(duplicate_ids & long_ids),
        "no_listed_flag": group_counts(all_ids - flagged_ids),
        "at_least_two_distinct_normalized_nonweak_accepted_names": group_counts(
            multiple_usable
        ),
        "two_names_and_no_listed_flag": group_counts(multiple_usable - flagged_ids),
        "component_size_histogram": dict(
            sorted(Counter(len(c["observation_ids"]) for c in components).items())
        ),
    }
    sources_by_id = {item.observation_id: item.source_id for item in observations}
    within_source = sum(
        sources_by_id[n.left] == sources_by_id[n.right] for n in nominations
    )
    summary = {
        "schema_version": 1,
        "artifact_kind": ARTIFACT_KIND,
        "status": "unreviewed_preparation",
        "counts": counts,
        "flag_intersections": intersections,
        "readiness_diagnostics": diagnostics,
        "pair_scope": {
            "within_source": within_source,
            "cross_source": len(nominations) - within_source,
        },
        "by_source": source_counts,
        "permissions": RESTRICTIONS,
        "human_decisions": 0,
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "referent_nominations": "not_generated_no_namespace_inference",
        "normalization_version": links.READINESS_NORMALIZATION_VERSION,
        "nomination_version": links.READINESS_NOMINATION_VERSION,
        "preparation_input_sha256": preparation.input_manifest_sha256,
    }
    result = {
        "input-manifest.json": preparation.input_manifest_bytes,
        "observations.jsonl": _json_lines(record_rows, checkpoint),
        "nominations.jsonl": _json_lines([asdict(n) for n in nominations], checkpoint),
        "components.jsonl": _json_lines(
            sorted(components, key=lambda c: c["component_id"]), checkpoint
        ),
        "quarantine.jsonl": _json_lines(quarantine, checkpoint),
        "summary.json": _canonical(summary),
    }
    if sum(map(len, result.values())) > MAX_BYTES:
        raise ReadinessError("readiness_output_byte_limit")
    return result


def _payloads(config: dict, root: Path, guard: ResourceGuard) -> dict[str, bytes]:
    check = _checkpoint(guard)
    preparation = corpus.prepare_continuation_sources(
        root / config["receipt"]["path"],
        expected_receipt_sha256=config["receipt"]["sha256"],
        evidence_root=root,
        checkpoint=check,
    )
    payloads = assemble_readiness(preparation, checkpoint=check)
    if _json(payloads["summary.json"])["counts"] != config["expected_counts"]:
        raise ReadinessError("measured_counts_differ_from_approved_inputs")
    guard.check()
    return payloads


def _recheck_inputs(
    root: Path, payloads: dict[str, bytes], guard: ResourceGuard
) -> None:
    """Recheck pinned inputs before commit/validation completion without reparsing."""
    manifest = _json(payloads["input-manifest.json"])
    references = [manifest["receipt"], *manifest["evidence"]]
    for source in manifest["sources"]:
        references.extend((source["selection"], source["permission"]))
    seen = set()
    for reference in references:
        if reference["path"] in seen:
            continue
        seen.add(reference["path"])
        guard.check()
        _reference(root, reference, maximum=corpus.MAX_TOTAL_INPUT_BYTES)


def _manifest(
    payloads: dict[str, bytes], config_path: Path, config_bytes: bytes, root: Path
) -> bytes:
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "artifact_kind": ARTIFACT_KIND,
            "status": "complete_unreviewed_preparation",
            "configuration": {
                "path": config_path.relative_to(root).as_posix(),
                "sha256": _sha(config_bytes),
            },
            "files": {
                name: {"sha256": _sha(payload), "bytes": len(payload)}
                for name, payload in sorted(payloads.items())
            },
            "permissions": RESTRICTIONS,
            "human_decisions": 0,
            "accepted_corpus_release": False,
        }
    )


def _same_directory(path: Path, pinned: int) -> None:
    reopened = corpus._open_directory(path)
    try:
        a, b = os.fstat(reopened), os.fstat(pinned)
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
            raise ReadinessError("output_directory_changed")
    finally:
        os.close(reopened)


def _write_payload(directory_fd: int, name: str, payload: bytes) -> None:
    """Write and fsync a private file; commit by exclusive hard link, never rename."""
    temporary = ".readiness-" + uuid.uuid4().hex + ".tmp"
    fd = os.open(
        temporary,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        view = memoryview(payload)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("readiness_write_stalled")
            view = view[n:]
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        hasher = hashlib.sha256()
        count = 0
        while block := os.read(fd, 65536):
            hasher.update(block)
            count += len(block)
        if count != len(payload) or hasher.hexdigest() != _sha(payload):
            raise ReadinessError("readiness_staging_corrupted")
        before = os.fstat(fd)
        entry = os.stat(temporary, dir_fd=directory_fd, follow_symlinks=False)
        if corpus._fingerprint(before) != corpus._fingerprint(entry):
            raise ReadinessError("readiness_staging_replaced")
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        os.link(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        os.fsync(directory_fd)
    finally:
        os.close(fd)
        os.unlink(temporary, dir_fd=directory_fd)


def _check_saved_files(
    directory: Path, payloads: dict[str, bytes], guard: ResourceGuard
) -> None:
    for name, expected in payloads.items():
        guard.check()
        actual = corpus._read_saved(directory / name, MAX_BYTES, "readiness artifact")
        if actual != expected:
            raise ReadinessError("readiness_content_mismatch")
        if stat.S_IMODE((directory / name).stat(follow_symlinks=False).st_mode) & 0o077:
            raise ReadinessError("readiness_file_not_private")


def prepare_readiness(
    config_path: Path,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Write new private queues, with manifest completion only after data verification."""
    root = Path(project_root).absolute()
    config_path = _path(root, config_path)
    output = _path(root, output)
    config, raw = _load_config(config_path, root)
    if output != root / config["output_path"]:
        raise ReadinessError("unapproved_output_path")
    parent = corpus._open_directory(output.parent)
    directory = None
    try:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("readiness_output_exists")
        guard = _resource_guard(root, config, guard)
        payloads = _payloads(config, root, guard)
        manifest = _manifest(payloads, config_path, raw, root)
        # Per-file staging is released before the next write; its bytes are still reserved conservatively.
        total = sum(map(len, payloads.values())) + len(manifest)
        new_root_bytes = _artifact_size(output.parent, required=True)
        if new_root_bytes + total + max(map(len, payloads.values())) > MAX_BYTES:
            raise ReadinessError("new_preparation_artifact_limit")
        guard.reserve_artifact(
            total + max(map(len, payloads.values())), normalized=True
        )
        _same_directory(output.parent, parent)
        os.mkdir(output.name, 0o700, dir_fd=parent)
        directory = os.open(
            output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.fsync(parent)
        for name, payload in sorted(payloads.items()):
            guard.check()
            _same_directory(output, directory)
            _write_payload(directory, name, payload)
        _check_saved_files(output, payloads, guard)
        if set(os.listdir(directory)) != PAYLOAD_NAMES:
            raise ReadinessError("unexpected_preparation_files")
        if corpus._read_saved(config_path, 2_000_000, "readiness config") != raw:
            raise ReadinessError("configuration_changed_during_preparation")
        _recheck_inputs(root, payloads, guard)
        guard.check()
        _same_directory(output, directory)
        _write_payload(directory, "manifest.json", manifest)
        return _json(payloads["summary.json"])
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def validate_readiness(
    input_path: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
    config_path: Path | None = None,
) -> dict:
    """Re-admit trusted inputs and regenerate queues; editable self-hashes are insufficient."""
    root = Path(project_root).absolute()
    input_path = _path(root, input_path)
    config_path = _path(root, config_path or "config/corpus-readiness-v1.json")
    config, raw = _load_config(config_path, root)
    if input_path != root / config["output_path"]:
        raise ReadinessError("unapproved_input_path")
    directory = corpus._open_directory(input_path)
    try:
        if stat.S_IMODE(os.fstat(directory).st_mode) & 0o077:
            raise ReadinessError("readiness_directory_not_private")
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise ReadinessError("incomplete_or_unexpected_preparation_files")
        manifest = corpus._read_saved(
            input_path / "manifest.json", 2_000_000, "readiness manifest"
        )
        _json(manifest)
        guard = _resource_guard(root, config, guard)
        payloads = _payloads(config, root, guard)
        if manifest != _manifest(payloads, config_path, raw, root):
            raise ReadinessError("readiness_manifest_mismatch")
        _check_saved_files(input_path, {**payloads, "manifest.json": manifest}, guard)
        _recheck_inputs(root, payloads, guard)
        if corpus._read_saved(config_path, 2_000_000, "readiness config") != raw:
            raise ReadinessError("configuration_changed_during_validation")
        _same_directory(input_path, directory)
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise ReadinessError("artifact_changed_during_validation")
        return _json(payloads["summary.json"])
    finally:
        os.close(directory)


def deny_network(event: str, arguments: tuple) -> None:
    """CLI audit hook: fail before socket operations; not an OS sandbox claim."""
    if event.startswith("socket."):
        raise ReadinessError("readiness_network_forbidden")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument(
        "--config", type=Path, default=Path("config/corpus-readiness-v1.json")
    )
    args = parser.parse_args(argv)
    sys.addaudithook(deny_network)
    try:
        if args.command == "prepare":
            result = prepare_readiness(
                args.config, args.output, project_root=Path.cwd()
            )
        else:
            result = validate_readiness(
                args.input, project_root=Path.cwd(), config_path=args.config
            )
    except (
        ReadinessError,
        corpus.CorpusValidationError,
        ResourceStop,
        OSError,
        ValueError,
    ):
        # Deliberately no exception/source text: supervisor and private partial files retain context.
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "readiness_validation_or_resource_failure",
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
