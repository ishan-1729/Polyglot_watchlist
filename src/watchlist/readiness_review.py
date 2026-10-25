"""Private C2 development packets and a fictional-only append-only review ledger.

Pins detect changes relative to separately retained expected bytes. They do not
authenticate a reviewer, prove independence, or protect against an administrator
replacing code and every trusted pin. Source wrappers must run under the existing
resource supervisor. This module never merges identities or exports labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Callable, Iterator

from watchlist import corpus, corpus_readiness as readiness
from watchlist.ingest import link_records as links
from watchlist.ingest.resource_guard import (
    ResourceGuard,
    ResourceStop,
    _artifact_size,
    system_snapshot,
)
from watchlist.normalize import normalize_name
from watchlist.scripts import script_set

SCOPE = "08B-C2-offline-review"
PACKET_VERSION = "readiness-review-packets-v1"
LEDGER_VERSION = "readiness-review-ledger-v1"
PROTOCOL_VERSION = "two-reviewers-independent-adjudicator-v1"
MAX_BYTES = 16_000_000
LIMITS = {
    "max_new_artifact_bytes": MAX_BYTES,
    "max_cases": 40_000,
    "max_events": 100_000,
    "session_seconds": 3600,
}
RESTRICTIONS = dict(readiness.RESTRICTIONS)
KINDS = ("duplicate", "flagged", "proposed_positive", "negative_candidate")
PAYLOAD_NAMES = frozenset({*(kind + ".jsonl" for kind in KINDS), "summary.json"})
OUTCOMES = frozenset(
    {"supported_same", "supported_distinct", "insufficient_evidence", "ineligible"}
)
RELATIONSHIPS = frozenset(
    {
        "translation",
        "transliteration",
        "spelling",
        "abbreviation",
        "historic",
        "other",
        "unresolved",
    }
)
QUESTIONS = {
    "duplicate": "What relationship, if any, does the cited evidence support between these records?",
    "flagged": "What restrictions or unresolved evidence issues apply to this record?",
    "proposed_positive": "What relationship, if any, does the evidence support between these two name forms?",
    "negative_candidate": "Does independent evidence support the same entity, distinct entities, or neither?",
}
FIXTURE_METADATA = {
    "created_at": "2000-01-01T00:00:00+00:00",
    "creator": "codex-offline-preparation",
    "approval_ref": "user-approved-08B-C2",
}


class ReviewError(ValueError):
    """An offline review boundary failed, without exposing source text."""


def _canonical(value: object) -> bytes:
    return readiness._canonical(value)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fields(value: object, expected: set | frozenset) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ReviewError("unexpected_review_fields")
    return value


def _json(payload: bytes) -> dict:
    try:
        return corpus._json_object(payload, "review object")
    except (ValueError, UnicodeError, TypeError):
        raise ReviewError("invalid_review_json") from None


def _hash(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ReviewError("invalid_review_digest")
    return value


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise ReviewError("invalid_review_text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ReviewError("invalid_review_text") from None
    return value


def _strings(value: object, *, nonempty: bool = False) -> list[str]:
    if type(value) is not list or (nonempty and not value):
        raise ReviewError("invalid_review_string_list")
    for item in value:
        _text(item)
    if len(value) != len(set(value)):
        raise ReviewError("duplicate_review_reference")
    return value


def _time(value: object) -> datetime:
    _text(value, maximum=64)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ReviewError("invalid_review_timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReviewError("review_timestamp_timezone_required")
    return parsed


def _metadata(value: object) -> dict:
    value = _fields(value, {"created_at", "creator", "approval_ref"})
    _time(value["created_at"])
    if (
        value["creator"] != FIXTURE_METADATA["creator"]
        or value["approval_ref"] != FIXTURE_METADATA["approval_ref"]
    ):
        raise ReviewError("invalid_preparation_attribution")
    return value


def _rows(payload: bytes, maximum: int) -> list[dict]:
    if type(payload) is not bytes or len(payload) > readiness.MAX_BYTES:
        raise ReviewError("review_input_byte_limit")
    lines = payload.splitlines()
    if len(lines) > maximum or any(not line for line in lines):
        raise ReviewError("review_input_row_limit")
    return [_json(line) for line in lines]


def _encode_queues(queues: dict[str, list[dict]], summary: dict) -> dict[str, bytes]:
    """Bound accumulated serialized bytes before any large concatenation."""
    result = {"summary.json": _canonical(summary)}
    total = len(result["summary.json"])
    for kind in KINDS:
        chunks = []
        for case in sorted(queues[kind], key=lambda c: c["case_id"]):
            chunk = _canonical(case)
            total += len(chunk)
            if total > MAX_BYTES:
                raise ReviewError("review_output_byte_limit")
            chunks.append(chunk)
        result[kind + ".jsonl"] = b"".join(chunks)
    return result


def _c1_payloads(
    value: object, pin: str, checkpoint: Callable[[], None]
) -> dict[str, bytes]:
    """Check C1 pins and reconstruct its derived queues, not source authenticity."""
    _hash(pin)
    if type(value) is not dict or set(value) != readiness.PAYLOAD_NAMES | {
        "manifest.json"
    }:
        raise ReviewError("complete_c1_payloads_required")
    if (
        any(type(item) is not bytes for item in value.values())
        or sum(map(len, value.values())) > readiness.MAX_BYTES
    ):
        raise ReviewError("c1_payload_byte_limit")
    if _sha(value["manifest.json"]) != pin:
        raise ReviewError("c1_manifest_pin_mismatch")
    manifest = _fields(
        _json(value["manifest.json"]),
        {
            "schema_version",
            "scope",
            "artifact_kind",
            "status",
            "configuration",
            "files",
            "permissions",
            "human_decisions",
            "accepted_corpus_release",
        },
    )
    if (
        type(manifest["schema_version"]) is not int
        or manifest["schema_version"] != 1
        or manifest["scope"] != readiness.SCOPE
        or manifest["artifact_kind"] != readiness.ARTIFACT_KIND
        or manifest["status"] != "complete_unreviewed_preparation"
        or manifest["permissions"] != RESTRICTIONS
        or type(manifest["human_decisions"]) is not int
        or manifest["human_decisions"] != 0
        or manifest["accepted_corpus_release"] is not False
    ):
        raise ReviewError("invalid_c1_preparation_boundary")
    _fields(manifest["files"], readiness.PAYLOAD_NAMES)
    for name in readiness.PAYLOAD_NAMES:
        checkpoint()
        reference = _fields(manifest["files"][name], {"sha256", "bytes"})
        if (
            reference != {"sha256": _sha(value[name]), "bytes": len(value[name])}
            or type(reference["bytes"]) is not int
        ):
            raise ReviewError("c1_file_pin_mismatch")
    try:
        observations = []
        for row in _rows(value["observations.jsonl"], readiness.LIMITS["max_records"]):
            checkpoint()
            aliases = tuple(
                corpus.CandidateNameEvidence(
                    **{**a, "attributes": tuple(tuple(p) for p in a["attributes"])}
                )
                for a in row["aliases"]
            )
            observations.append(
                corpus.CandidateObservation(
                    **{
                        **row,
                        "aliases": aliases,
                        "source_record_key": tuple(row["source_record_key"]),
                        "referents": tuple(row["referents"]),
                        "provider_datasets": tuple(row["provider_datasets"]),
                        "provider_topics": tuple(row["provider_topics"]),
                    }
                )
            )
        rebuilt = readiness.assemble_readiness(
            corpus.ContinuationPreparation(
                receipt_sha256="",
                receipt_bytes=b"",
                input_manifest_bytes=value["input-manifest.json"],
                input_manifest_sha256=_sha(value["input-manifest.json"]),
                evidence=(),
                sources=(),
                observations=tuple(observations),
            ),
            checkpoint=checkpoint,
        )
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ReviewError("invalid_c1_structured_evidence") from None
    if any(rebuilt[name] != value[name] for name in readiness.PAYLOAD_NAMES):
        raise ReviewError("c1_derived_content_mismatch")
    return value


def assemble_review_packets(
    c1_payloads: dict[str, bytes],
    *,
    c1_manifest_sha256: str,
    fictional: bool = False,
    fictional_identity_evidence: dict[str, list[str]] | None = None,
    metadata: dict | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, bytes]:
    """Build deterministic blank queues; hypotheses never become correct labels.

    The source wrapper independently re-admits C1. This pure function checks C1
    byte pins and internal derivation. Explicit fictional evidence is available
    only to authored fixtures whose source IDs all begin ``fictional_``.
    """
    check = checkpoint or (lambda: None)
    if type(fictional) is not bool:
        raise ReviewError("fictional_mode_must_be_boolean")
    c1 = _c1_payloads(c1_payloads, c1_manifest_sha256, check)
    metadata = _metadata(metadata or dict(FIXTURE_METADATA))
    observations = {
        r["observation_id"]: r
        for r in _rows(c1["observations.jsonl"], readiness.LIMITS["max_records"])
    }
    if fictional and any(
        not o["source_id"].startswith("fictional_")
        or not o["observation_id"].startswith("fictional-")
        or any(not a["evidence_id"].startswith("fictional-") for a in o["aliases"])
        for o in observations.values()
    ):
        raise ReviewError("fictional_source_namespace_required")
    identities = fictional_identity_evidence or {}
    if (
        type(identities) is not dict
        or identities
        and not fictional
        or not set(identities) <= observations.keys()
    ):
        raise ReviewError("fictional_identity_evidence_only")
    seen_identity = set()
    for oid, refs in identities.items():
        _strings(refs, nonempty=True)
        for ref in refs:
            if not ref.startswith("fictional-identity-") or ref in seen_identity:
                raise ReviewError("invalid_fictional_identity_reference")
            seen_identity.add(ref)
    flags = {
        r["observation_id"]: r
        for r in _rows(c1["quarantine.jsonl"], readiness.LIMITS["max_records"])
    }
    components = {
        oid: r["component_id"]
        for r in _rows(c1["components.jsonl"], readiness.LIMITS["max_records"])
        for oid in r["observation_ids"]
    }
    nominations = _rows(c1["nominations.jsonl"], readiness.LIMITS["max_pairs"])
    evidence = {
        a["evidence_id"]: a for o in observations.values() for a in o["aliases"]
    }
    excluded = {
        r["evidence_id"] for flag in flags.values() for r in flag["name_restrictions"]
    }
    queues: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    case_count = 0

    def add(
        kind: str, ids: list[str], refs: list[str], nomination: str | None = None
    ) -> None:
        nonlocal case_count
        check()
        if case_count >= LIMITS["max_cases"]:
            raise ReviewError("review_case_limit")
        case_count += 1
        ids, refs = sorted(set(ids)), sorted(set(refs))
        identity = {oid: sorted(identities[oid]) for oid in ids if oid in identities}
        scripts = sorted(
            {s for ref in refs for s in script_set(evidence[ref]["value"])}
        )
        case = {
            "case_id": ("fictional-review-" if fictional else "review-")
            + _sha(
                _canonical(
                    [PACKET_VERSION, c1_manifest_sha256, kind, ids, refs, nomination]
                )
            ),
            "kind": kind,
            "observation_ids": ids,
            "evidence_refs": sorted(
                refs + [r for values in identity.values() for r in values]
            ),
            "identity_evidence_refs": identity,
            "component_ids": sorted(
                {components[oid] for oid in ids if oid in components}
            ),
            "nomination_id": nomination,
            "flagged_observation_ids": [oid for oid in ids if oid in flags],
            "required_competencies": [
                "record_review",
                *("script:" + s for s in scripts),
            ],
            "status": "blocked_unresolved",
            "outcome": None,
        }
        queues[kind].append(case)

    for nomination in nominations:
        ids = [nomination["left"], nomination["right"]]
        # Complete witnesses remain in pinned C1. Cases cite their evidence IDs.
        refs = sorted(
            {
                w[key]
                for w in nomination["witnesses"]
                for key in ("left_evidence_id", "right_evidence_id")
            }
        )
        add("duplicate", ids, refs, nomination["nomination_id"])
        add("negative_candidate", ids, refs, nomination["nomination_id"])
    for oid in sorted(flags):
        add("flagged", [oid], [a["evidence_id"] for a in observations[oid]["aliases"]])
    for oid, observation in sorted(observations.items()):
        usable = {}
        for alias in sorted(observation["aliases"], key=lambda a: a["evidence_id"]):
            if alias["evidence_id"] in excluded:
                continue
            try:
                normalize_name(alias["value"])
            except ValueError:
                continue
            usable.setdefault(
                links.readiness_name_key(alias["value"]), alias["evidence_id"]
            )
        if len(usable) >= 2:
            add("proposed_positive", [oid], [usable[key] for key in sorted(usable)[:2]])
    counts = {kind: len(queues[kind]) for kind in KINDS}
    counts["total"] = sum(counts.values())
    if counts["total"] > LIMITS["max_cases"]:
        raise ReviewError("review_case_limit")
    summary = {
        "schema_version": 1,
        "scope": SCOPE,
        "artifact_kind": "blank_review_packets",
        "mode": "fictional_fixture" if fictional else "development_blank",
        "custody": "development",
        "packet_version": PACKET_VERSION,
        "ledger_version": LEDGER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "metadata": metadata,
        "c1_manifest_sha256": c1_manifest_sha256,
        "preparation_input_sha256": _sha(c1["input-manifest.json"]),
        "counts": counts,
        "permissions": RESTRICTIONS,
        "human_decisions": 0,
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "real_actor_registry": [],
        "questions": QUESTIONS,
        "sampling": {
            "duplicate": "all_c1_equality_nominations",
            "flagged": "all_c1_flagged_observations",
            "proposed_positive": "one_pair_per_observation_first_two_distinct_normalized_nonweak_accepted_keys_then_evidence_id",
            "negative_candidate": "same_existing_equality_pairs_as_duplicate_queue_unresolved_hypotheses",
            "duplicate_negative_overlap_pairs": len(nominations),
            "distinct_cross_record_pairs": len(nominations),
            "label_review_counts": "zero_no_queue_count_is_an_accepted_label_count",
        },
        "normalization_version": links.READINESS_NORMALIZATION_VERSION,
        "nomination_version": links.READINESS_NOMINATION_VERSION,
        "unknown_language_entries": sum(
            a["language"] is None for a in evidence.values()
        ),
        "script_counts": dict(
            sorted(
                Counter(
                    s for a in evidence.values() for s in script_set(a["value"])
                ).items()
            )
        ),
        "scripts_are_not_languages": True,
        "relationship_annotations": sorted(RELATIONSHIPS),
        "integrity_limitation": "hashes_and_actor_declarations_do_not_authenticate_humans_or_independent_custody",
    }
    return _encode_queues(queues, summary)


def _load_config(path: Path, root: Path) -> tuple[dict, bytes]:
    raw = corpus._read_saved(path, 2_000_000, "review config")
    config = _fields(
        _json(raw),
        {
            "schema_version",
            "scope",
            "c1",
            "output_path",
            "ledger_path",
            "artifact_roots",
            "normalized_inputs",
            "expected_counts",
            "limits",
            "permissions",
            "versions",
            "actors",
            "metadata",
            "protocol_version",
        },
    )
    if (
        type(config["schema_version"]) is not int
        or config["schema_version"] != 1
        or config["scope"] != SCOPE
        or config["protocol_version"] != PROTOCOL_VERSION
    ):
        raise ReviewError("unapproved_review_scope")
    if config["limits"] != LIMITS or any(
        type(v) is not int for v in config["limits"].values()
    ):
        raise ReviewError("unapproved_review_limits")
    if (
        config["permissions"] != RESTRICTIONS
        or any(type(v) is not bool for v in config["permissions"].values())
        or config["actors"] != []
    ):
        raise ReviewError("real_review_execution_disabled")
    if config["versions"] != {"packet": PACKET_VERSION, "ledger": LEDGER_VERSION}:
        raise ReviewError("unapproved_review_versions")
    _metadata(config["metadata"])
    counts = _fields(config["expected_counts"], {*KINDS, "total"})
    if (
        any(type(v) is not int or v < 0 for v in counts.values())
        or counts["total"] != sum(counts[k] for k in KINDS)
        or counts["total"] > LIMITS["max_cases"]
    ):
        raise ReviewError("invalid_review_expected_counts")
    _fields(config["c1"], {"configuration", "manifest"})
    for ref in config["c1"].values():
        _fields(ref, {"path", "sha256"})
        readiness._relative(ref["path"])
        _hash(ref["sha256"])
    output, ledger = (
        root / readiness._relative(config[key])
        for key in ("output_path", "ledger_path")
    )
    roots = _strings(config["artifact_roots"], nonempty=True)
    if (
        len(roots) > 8
        or output.parent != ledger.parent
        or output == ledger
        or output.parent.relative_to(root).as_posix() not in roots
    ):
        raise ReviewError("invalid_review_output_roots")
    for relative in roots:
        fd = corpus._open_directory(root / readiness._relative(relative))
        os.close(fd)
    refs = config["normalized_inputs"]
    if type(refs) is not list or not 1 <= len(refs) <= 32:
        raise ReviewError("invalid_review_normalized_inputs")
    paths = []
    for ref in refs:
        _fields(ref, {"path", "sha256"})
        paths.append(readiness._relative(ref["path"]))
        _hash(ref["sha256"])
    if len(paths) != len(set(paths)):
        raise ReviewError("duplicate_normalized_reservation")
    return config, raw


def _guard(
    root: Path, artifact_roots: list[str], new_root: Path, guard: ResourceGuard | None
) -> ResourceGuard:
    roots = tuple(root / relative for relative in artifact_roots)
    if guard is None:
        guard = ResourceGuard(
            probe=lambda: system_snapshot(roots[0], additional_artifact_roots=roots[1:])
        )
    if not isinstance(guard, ResourceGuard):
        raise ReviewError("resource_guard_required")
    if guard.admitted:
        guard.check()
    else:
        guard.admit()
    if _artifact_size(new_root, required=True) > MAX_BYTES:
        raise ReviewError("new_review_artifact_limit")
    return guard


def _reserve(new_root: Path, amount: int, guard: ResourceGuard) -> None:
    if _artifact_size(new_root, required=True) + amount > MAX_BYTES:
        raise ReviewError("new_review_artifact_limit")
    guard.reserve_artifact(amount, normalized=True)


def _account_inputs(
    root: Path, config: dict, guard: ResourceGuard
) -> tuple[bytes, bytes]:
    """Charge retained material on every public I/O path without resetting a guard."""
    c1config = readiness._reference(
        root, config["c1"]["configuration"], maximum=2_000_000
    )
    manifest = readiness._reference(root, config["c1"]["manifest"], maximum=2_000_000)
    directory = (root / config["c1"]["manifest"]["path"]).parent
    parsed = _json(manifest)
    if parsed["configuration"] != config["c1"]["configuration"]:
        raise ReviewError("c1_configuration_pin_mismatch")
    # Require historical reservations from pinned C1 plus every C1 file, so a
    # smaller edited C2 list cannot silently forget existing normalized bytes.
    required = {
        ref["path"]: ref["sha256"] for ref in _json(c1config)["normalized_inputs"]
    }
    for name, item in parsed["files"].items():
        required[(directory / name).relative_to(root).as_posix()] = item["sha256"]
    required[config["c1"]["manifest"]["path"]] = config["c1"]["manifest"]["sha256"]
    provided = {ref["path"]: ref["sha256"] for ref in config["normalized_inputs"]}
    if not required.items() <= provided.items():
        raise ReviewError("normalized_input_coverage_missing")
    total = sum(
        len(readiness._reference(root, ref, maximum=100_000_000))
        for ref in config["normalized_inputs"]
    )
    total += _artifact_size((root / config["output_path"]).parent, required=True)
    guard.normalized_bytes = max(guard.normalized_bytes, total)
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")
    return c1config, manifest


def _admit_c1(root: Path, config: dict, guard: ResourceGuard) -> dict[str, bytes]:
    c1config, manifest = _account_inputs(root, config, guard)
    directory = (root / config["c1"]["manifest"]["path"]).parent
    readiness.validate_readiness(
        directory,
        project_root=root,
        guard=guard,
        config_path=root / config["c1"]["configuration"]["path"],
    )
    payloads = {
        name: corpus._read_saved(directory / name, readiness.MAX_BYTES, "C1 payload")
        for name in readiness.PAYLOAD_NAMES | {"manifest.json"}
    }
    if (
        payloads["manifest.json"] != manifest
        or corpus._read_saved(
            root / config["c1"]["configuration"]["path"], 2_000_000, "C1 config"
        )
        != c1config
    ):
        raise ReviewError("c1_changed_during_admission")
    return payloads


def _manifest(
    payloads: dict[str, bytes], configuration: dict | None, *, c1: dict | None
) -> bytes:
    summary = _json(payloads["summary.json"])
    return _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "artifact_kind": "blank_review_packets",
            "status": "complete_unreviewed_preparation",
            "mode": summary["mode"],
            "configuration": configuration,
            "c1": c1,
            "files": {
                name: {"sha256": _sha(payload), "bytes": len(payload)}
                for name, payload in sorted(payloads.items())
            },
            "permissions": RESTRICTIONS,
            "human_decisions": 0,
            "accepted_labels": 0,
            "identity_merges": 0,
            "accepted_corpus_release": False,
        }
    )


def _write_payload(directory_fd: int, name: str, payload: bytes) -> None:
    """Publish through the existing exclusive, fsynced private-file primitive."""
    readiness._write_payload(directory_fd, name, payload)


def _private(path: Path, *, directory: bool = False) -> None:
    info = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode)
    ) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ReviewError("review_artifact_not_private")


def _write_packet(
    output: Path,
    payloads: dict[str, bytes],
    manifest: bytes,
    guard: ResourceGuard,
    recheck: Callable[[], None],
) -> None:
    parent = corpus._open_directory(output.parent)
    directory = None
    try:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("review_output_exists")
        _reserve(
            output.parent,
            sum(map(len, payloads.values()))
            + len(manifest)
            + max(map(len, payloads.values())),
            guard,
        )
        readiness._same_directory(output.parent, parent)
        os.mkdir(output.name, 0o700, dir_fd=parent)
        directory = os.open(
            output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.fsync(parent)
        for name, payload in sorted(payloads.items()):
            guard.check()
            readiness._same_directory(output, directory)
            _write_payload(directory, name, payload)
        for name, expected in payloads.items():
            if (
                corpus._read_saved(output / name, MAX_BYTES, "review payload")
                != expected
            ):
                raise ReviewError("review_written_content_mismatch")
        recheck()
        guard.check()
        readiness._same_directory(output, directory)
        if set(os.listdir(directory)) != PAYLOAD_NAMES:
            raise ReviewError("unexpected_review_packet_files")
        _write_payload(directory, "manifest.json", manifest)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)


def _recheck_c1(
    root: Path,
    config_path: Path,
    raw: bytes,
    config: dict,
    c1: dict[str, bytes],
    guard: ResourceGuard,
) -> None:
    if corpus._read_saved(config_path, 2_000_000, "review config") != raw:
        raise ReviewError("review_configuration_changed")
    directory = (root / config["c1"]["manifest"]["path"]).parent
    for name, expected in c1.items():
        guard.check()
        if (
            corpus._read_saved(directory / name, readiness.MAX_BYTES, "C1 evidence")
            != expected
        ):
            raise ReviewError("c1_evidence_changed")
    readiness._reference(root, config["c1"]["configuration"], maximum=2_000_000)
    readiness._recheck_inputs(root, c1, guard)


def prepare_review(
    config_path: Path,
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Admit pinned C1 and write new private blank packets, never real decisions."""
    root = Path(project_root).absolute()
    config_path, output = (
        readiness._path(root, config_path),
        readiness._path(root, output),
    )
    config, raw = _load_config(config_path, root)
    if output != root / config["output_path"]:
        raise ReviewError("unapproved_review_output_path")
    if output.exists() or output.is_symlink():
        raise FileExistsError("review_output_exists")
    guard = _guard(root, config["artifact_roots"], output.parent, guard)
    c1 = _admit_c1(root, config, guard)
    payloads = assemble_review_packets(
        c1,
        c1_manifest_sha256=config["c1"]["manifest"]["sha256"],
        metadata=config["metadata"],
        checkpoint=readiness._checkpoint(guard),
    )
    summary = _json(payloads["summary.json"])
    if summary["counts"] != config["expected_counts"]:
        raise ReviewError("review_counts_differ_from_approval")
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
        c1=config["c1"],
    )
    _write_packet(
        output,
        payloads,
        manifest,
        guard,
        lambda: _recheck_c1(root, config_path, raw, config, c1, guard),
    )
    return summary


def validate_review(
    input_path: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
    config_path: Path | None = None,
) -> dict:
    """Independently regenerate C2 from trusted config and re-admitted C1 evidence."""
    root = Path(project_root).absolute()
    config_path = readiness._path(root, config_path or "config/corpus-review-v1.json")
    input_path = readiness._path(root, input_path)
    config, raw = _load_config(config_path, root)
    if input_path != root / config["output_path"]:
        raise ReviewError("unapproved_review_input_path")
    guard = _guard(root, config["artifact_roots"], input_path.parent, guard)
    c1 = _admit_c1(root, config, guard)
    payloads = assemble_review_packets(
        c1,
        c1_manifest_sha256=config["c1"]["manifest"]["sha256"],
        metadata=config["metadata"],
        checkpoint=readiness._checkpoint(guard),
    )
    manifest = _manifest(
        payloads,
        {"path": config_path.relative_to(root).as_posix(), "sha256": _sha(raw)},
        c1=config["c1"],
    )
    actual, _, _ = _load_packet(input_path, _sha(manifest), guard)
    if (
        actual != payloads
        or _json(payloads["summary.json"])["counts"] != config["expected_counts"]
    ):
        raise ReviewError("review_content_mismatch")
    _recheck_c1(root, config_path, raw, config, c1, guard)
    return _json(payloads["summary.json"])


def write_fictional_packet(
    payloads: dict[str, bytes],
    output: Path,
    *,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Publish authored fictional packet bytes for local tests; never mode-switch real C2."""
    if (
        type(payloads) is not dict
        or set(payloads) != PAYLOAD_NAMES
        or _json(payloads["summary.json"])["mode"] != "fictional_fixture"
    ):
        raise ReviewError("fictional_packet_required")
    root = Path(project_root).absolute()
    output = readiness._path(root, output)
    guard = _guard(
        root, [output.parent.relative_to(root).as_posix()], output.parent, guard
    )
    manifest = _manifest(payloads, None, c1=None)
    _validate_packet_content(payloads, _json(manifest))
    _write_packet(output, payloads, manifest, guard, lambda: None)
    return _sha(manifest)


def _validate_packet_content(
    payloads: dict[str, bytes], manifest: dict
) -> tuple[dict, dict[str, dict]]:
    summary = _json(payloads["summary.json"])
    if (
        summary.get("scope") != SCOPE
        or summary.get("mode") not in {"development_blank", "fictional_fixture"}
        or summary.get("mode") != manifest.get("mode")
        or summary.get("packet_version") != PACKET_VERSION
        or summary.get("ledger_version") != LEDGER_VERSION
        or summary.get("protocol_version") != PROTOCOL_VERSION
        or summary.get("custody") != "development"
        or summary.get("permissions") != RESTRICTIONS
        or summary.get("real_actor_registry") != []
    ):
        raise ReviewError("invalid_review_packet_boundary")
    if (
        any(
            type(summary.get(key)) is not int or summary[key] != 0
            for key in ("human_decisions", "accepted_labels", "identity_merges")
        )
        or summary.get("accepted_corpus_release") is not False
    ):
        raise ReviewError("review_packet_contains_decisions")
    _metadata(summary["metadata"])
    _hash(summary["c1_manifest_sha256"])
    cases = {}
    counts = {}
    for kind in KINDS:
        rows = _rows(payloads[kind + ".jsonl"], LIMITS["max_cases"])
        counts[kind] = len(rows)
        for case in rows:
            _fields(
                case,
                {
                    "case_id",
                    "kind",
                    "observation_ids",
                    "evidence_refs",
                    "identity_evidence_refs",
                    "component_ids",
                    "nomination_id",
                    "flagged_observation_ids",
                    "required_competencies",
                    "status",
                    "outcome",
                },
            )
            _text(case["case_id"])
            if (
                case["case_id"] in cases
                or case["kind"] != kind
                or case["status"] != "blocked_unresolved"
                or case["outcome"] is not None
            ):
                raise ReviewError("invalid_or_nonblank_review_case")
            ids = _strings(case["observation_ids"], nonempty=True)
            refs = _strings(case["evidence_refs"], nonempty=True)
            if summary["mode"] == "fictional_fixture" and (
                not case["case_id"].startswith("fictional-review-")
                or any(not value.startswith("fictional-") for value in [*ids, *refs])
            ):
                raise ReviewError("fictional_reference_namespace_required")
            _strings(case["component_ids"])
            _strings(case["required_competencies"], nonempty=True)
            if not set(_strings(case["flagged_observation_ids"])) <= set(ids) or len(
                ids
            ) != (2 if kind in {"duplicate", "negative_candidate"} else 1):
                raise ReviewError("invalid_case_observation_links")
            identity = case["identity_evidence_refs"]
            if (
                type(identity) is not dict
                or not set(identity) <= set(ids)
                or identity
                and summary["mode"] != "fictional_fixture"
            ):
                raise ReviewError("invalid_identity_evidence_scope")
            for values in identity.values():
                if not set(_strings(values, nonempty=True)) <= set(refs) or any(
                    not r.startswith("fictional-identity-") for r in values
                ):
                    raise ReviewError("invalid_identity_evidence_reference")
            plain_refs = sorted(
                set(refs) - {r for values in identity.values() for r in values}
            )
            prefix = (
                "fictional-review-"
                if summary["mode"] == "fictional_fixture"
                else "review-"
            )
            expected_id = prefix + _sha(
                _canonical(
                    [
                        PACKET_VERSION,
                        summary["c1_manifest_sha256"],
                        kind,
                        sorted(ids),
                        plain_refs,
                        case["nomination_id"],
                    ]
                )
            )
            if case["case_id"] != expected_id:
                raise ReviewError("review_case_identity_mismatch")
            if kind in {"duplicate", "negative_candidate"}:
                _text(case["nomination_id"])
            elif case["nomination_id"] is not None:
                raise ReviewError("unexpected_nomination_reference")
            cases[case["case_id"]] = case
    counts["total"] = sum(counts.values())
    if counts != summary["counts"] or counts["total"] > LIMITS["max_cases"]:
        raise ReviewError("review_packet_count_mismatch")
    return summary, cases


def _load_packet(
    path: Path, expected_sha256: str, guard: ResourceGuard
) -> tuple[dict[str, bytes], dict, dict[str, dict]]:
    _hash(expected_sha256)
    directory = corpus._open_directory(path)
    try:
        _private(path, directory=True)
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise ReviewError("incomplete_or_extra_packet_files")
        raw = corpus._read_saved(path / "manifest.json", 2_000_000, "review manifest")
        if _sha(raw) != expected_sha256:
            raise ReviewError("review_packet_pin_mismatch")
        manifest = _fields(
            _json(raw),
            {
                "schema_version",
                "scope",
                "artifact_kind",
                "status",
                "mode",
                "configuration",
                "c1",
                "files",
                "permissions",
                "human_decisions",
                "accepted_labels",
                "identity_merges",
                "accepted_corpus_release",
            },
        )
        if (
            type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != 1
            or manifest["scope"] != SCOPE
            or manifest["artifact_kind"] != "blank_review_packets"
            or manifest["status"] != "complete_unreviewed_preparation"
            or manifest["permissions"] != RESTRICTIONS
            or any(
                type(manifest[k]) is not int or manifest[k] != 0
                for k in ("human_decisions", "accepted_labels", "identity_merges")
            )
            or manifest["accepted_corpus_release"] is not False
        ):
            raise ReviewError("invalid_review_manifest_boundary")
        _fields(manifest["files"], PAYLOAD_NAMES)
        payloads = {}
        for name, ref in manifest["files"].items():
            guard.check()
            _fields(ref, {"sha256", "bytes"})
            _private(path / name)
            payload = corpus._read_saved(path / name, MAX_BYTES, "review packet")
            if (
                ref != {"sha256": _sha(payload), "bytes": len(payload)}
                or type(ref["bytes"]) is not int
            ):
                raise ReviewError("review_packet_content_pin_mismatch")
            payloads[name] = payload
        _private(path / "manifest.json")
        if sum(map(len, payloads.values())) + len(raw) > MAX_BYTES:
            raise ReviewError("review_packet_byte_limit")
        summary, cases = _validate_packet_content(payloads, manifest)
        readiness._same_directory(path, directory)
        _verify_packet_saved(path, expected_sha256, payloads)
        return payloads, summary, cases
    finally:
        os.close(directory)


def _verify_packet_saved(path: Path, pin: str, payloads: dict[str, bytes]) -> None:
    """Recheck the pinned packet immediately before a ledger commit or return."""
    directory = corpus._open_directory(path)
    try:
        _private(path, directory=True)
        if set(os.listdir(directory)) != PAYLOAD_NAMES | {"manifest.json"}:
            raise ReviewError("packet_changed_during_ledger_operation")
        if (
            _sha(corpus._read_saved(path / "manifest.json", 2_000_000, "packet pin"))
            != pin
        ):
            raise ReviewError("packet_changed_during_ledger_operation")
        _private(path / "manifest.json")
        for name, expected in payloads.items():
            _private(path / name)
            if (
                corpus._read_saved(path / name, MAX_BYTES, "packet evidence")
                != expected
            ):
                raise ReviewError("packet_changed_during_ledger_operation")
        readiness._same_directory(path, directory)
    finally:
        os.close(directory)


def _actors(actors: object, mode: str) -> list[dict]:
    if type(actors) is not tuple or len(actors) > 1000:
        raise ReviewError("actor_registry_must_be_tuple")
    if mode != "fictional_fixture" and actors:
        raise ReviewError("real_actor_registry_must_be_empty")
    result = []
    seen = set()
    for actor in actors:
        actor = _fields(
            actor,
            {
                "actor_id",
                "principal_id",
                "independence_group",
                "kind",
                "authorization_ref",
                "competencies",
                "roles",
            },
        )
        if (
            actor["kind"] != "fictional_human"
            or not _text(actor["actor_id"]).startswith("fictional-")
            or not _text(actor["authorization_ref"]).startswith("fictional-")
            or not _text(actor["principal_id"]).startswith("fictional-")
            or not _text(actor["independence_group"]).startswith("fictional-")
            or actor["actor_id"] in seen
        ):
            raise ReviewError("invalid_fictional_actor")
        _strings(actor["competencies"], nonempty=True)
        roles = _strings(actor["roles"], nonempty=True)
        if not set(roles) <= {"review", "adjudicate"}:
            raise ReviewError("invalid_actor_roles")
        seen.add(actor["actor_id"])
        result.append(
            {
                **actor,
                "roles": sorted(roles),
                "competencies": sorted(actor["competencies"]),
            }
        )
    return sorted(result, key=lambda item: item["actor_id"])


def _ledger_context(
    ledger_path: Path,
    packet_path: Path,
    project_root: Path,
    guard: ResourceGuard | None,
    expected_packet_sha256: str,
) -> tuple[Path, Path, ResourceGuard]:
    root = Path(project_root).absolute()
    ledger, packet = (
        readiness._path(root, ledger_path),
        readiness._path(root, packet_path),
    )
    if ledger == packet or ledger.parent != packet.parent:
        raise ReviewError("ledger_must_be_separate_packet_sibling")
    raw = corpus._read_saved(packet / "manifest.json", 2_000_000, "review manifest")
    if _sha(raw) != _hash(expected_packet_sha256):
        raise ReviewError("review_packet_pin_mismatch")
    manifest = _json(raw)
    if manifest.get("mode") == "development_blank":
        reference = _fields(manifest.get("configuration"), {"path", "sha256"})
        config_path = root / readiness._relative(reference["path"])
        config, config_bytes = _load_config(config_path, root)
        if (
            _sha(config_bytes) != _hash(reference["sha256"])
            or packet != root / config["output_path"]
            or ledger != root / config["ledger_path"]
            or manifest.get("c1") != config["c1"]
        ):
            raise ReviewError("ledger_configuration_pin_or_path_mismatch")
        guard = _guard(root, config["artifact_roots"], packet.parent, guard)
        _account_inputs(root, config, guard)
    elif manifest.get("mode") == "fictional_fixture":
        if manifest.get("configuration") is not None or manifest.get("c1") is not None:
            raise ReviewError("fictional_packet_cannot_claim_real_configuration")
        guard = _guard(
            root, [packet.parent.relative_to(root).as_posix()], packet.parent, guard
        )
        guard.normalized_bytes = max(
            guard.normalized_bytes, _artifact_size(packet.parent, required=True)
        )
        if guard.normalized_bytes > guard.limits.max_normalized_bytes:
            raise ResourceStop("normalized_byte_limit")
    else:
        raise ReviewError("invalid_ledger_packet_mode")
    return ledger, packet, guard


def create_ledger(
    packet_path: Path,
    ledger_path: Path,
    *,
    expected_packet_sha256: str,
    actors: tuple[dict, ...] = (),
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Create an empty private ledger; retain the returned genesis outside it."""
    ledger, packet, guard = _ledger_context(
        ledger_path, packet_path, project_root, guard, expected_packet_sha256
    )
    packet_bytes, summary, _ = _load_packet(packet, expected_packet_sha256, guard)
    registry = _actors(actors, summary["mode"])
    header = _canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "ledger_version": LEDGER_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "packet_sha256": expected_packet_sha256,
            "mode": summary["mode"],
            "actors": registry,
            "created_at": summary["metadata"]["created_at"],
            "permissions": RESTRICTIONS,
            "accepted_labels": 0,
            "identity_merges": 0,
            "accepted_corpus_release": False,
        }
    )
    parent = corpus._open_directory(ledger.parent)
    directory = None
    try:
        _reserve(ledger.parent, 2 * len(header), guard)
        os.mkdir(ledger.name, 0o700, dir_fd=parent)
        directory = os.open(
            ledger.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.mkdir("events", 0o700, dir_fd=directory)
        lockfd = os.open(
            ".lock",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.fsync(lockfd)
        os.close(lockfd)
        os.fsync(directory)
        guard.check()
        readiness._same_directory(ledger, directory)
        _verify_packet_saved(packet, expected_packet_sha256, packet_bytes)
        _write_payload(directory, "header.json", header)
        os.fsync(parent)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return _sha(header)


@contextmanager
def _locked(ledger: Path) -> Iterator[tuple[int, int, Callable[[], None]]]:
    """Serialize replay plus append using a retained inode, never a replaced lock."""
    directory = corpus._open_directory(ledger)
    lockfd = eventfd = None
    try:
        _private(ledger, directory=True)
        if set(os.listdir(directory)) != {"header.json", ".lock", "events"}:
            raise ReviewError("incomplete_or_extra_ledger_files")
        _private(ledger / ".lock")
        lockfd = os.open(
            ".lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        info = os.fstat(lockfd)
        if not stat.S_ISREG(info.st_mode) or info.st_size or info.st_nlink != 1:
            raise ReviewError("invalid_ledger_lock")
        try:
            fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ReviewError("ledger_busy") from None
        current = os.stat(".lock", dir_fd=directory, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ReviewError("ledger_lock_changed")
        _private(ledger / "events", directory=True)
        eventfd = os.open(
            "events", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
        )

        def check_lock() -> None:
            readiness._same_directory(ledger, directory)
            readiness._same_directory(ledger / "events", eventfd)
            current = os.stat(".lock", dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise ReviewError("ledger_lock_changed")

        yield directory, eventfd, check_lock
        check_lock()
    finally:
        if eventfd is not None:
            os.close(eventfd)
        if lockfd is not None:
            os.close(lockfd)
        os.close(directory)


def _event_payload(
    raw: object,
    kind: str,
    cases: dict[str, dict],
    registry: dict[str, dict],
    packet_sha256: str,
) -> dict:
    identifier = "submission_id" if kind == "submission" else "adjudication_id"
    base = {
        identifier,
        "packet_sha256",
        "case_id",
        "actor_id",
        "outcome",
        "rationale",
        "evidence_refs",
        "created_at",
        "origin",
        "uncertain",
        "conflict_declared",
    }
    if kind == "adjudication":
        base.add("submission_ids")
    if (
        type(raw) is not dict
        or not base <= raw.keys()
        or not set(raw) <= base | {"relationship_annotation", "direction"}
    ):
        raise ReviewError("invalid_review_event_fields")
    value = {
        **raw,
        "relationship_annotation": raw.get("relationship_annotation", "unresolved"),
        "direction": raw.get(
            "direction",
            {
                "query_evidence_id": None,
                "reference_evidence_id": None,
                "adequacy": "unresolved",
            },
        ),
    }
    for key in (identifier, "case_id", "actor_id", "rationale"):
        _text(value[key])
    _time(value["created_at"])
    if value["packet_sha256"] != packet_sha256 or value["case_id"] not in cases:
        raise ReviewError("stale_or_unknown_review_case")
    if (
        value["outcome"] not in OUTCOMES
        or value["origin"] != "fictional_human"
        or type(value["uncertain"]) is not bool
        or type(value["conflict_declared"]) is not bool
    ):
        raise ReviewError("invalid_review_outcome_or_origin")
    if (
        value["conflict_declared"]
        or value["uncertain"]
        and value["outcome"].startswith("supported_")
    ):
        raise ReviewError("conflicted_or_uncertain_supported_outcome")
    case = cases[value["case_id"]]
    actor = registry.get(value["actor_id"])
    role = "review" if kind == "submission" else "adjudicate"
    if (
        actor is None
        or role not in actor["roles"]
        or not set(case["required_competencies"]) <= set(actor["competencies"])
    ):
        raise ReviewError("unauthorized_or_unqualified_actor")
    refs = set(_strings(value["evidence_refs"], nonempty=True))
    if not refs <= set(case["evidence_refs"]):
        raise ReviewError("unknown_or_cross_case_evidence")
    if value["outcome"].startswith("supported_"):
        if case["kind"] == "flagged":
            raise ReviewError("flag_case_cannot_decide_identity")
        if len(case["observation_ids"]) == 2 and any(
            not refs.intersection(case["identity_evidence_refs"].get(oid, []))
            for oid in case["observation_ids"]
        ):
            raise ReviewError("independent_identity_evidence_required")
        if (
            case["kind"] == "proposed_positive"
            and len(
                refs
                - {
                    r
                    for values in case["identity_evidence_refs"].values()
                    for r in values
                }
            )
            < 2
        ):
            raise ReviewError("both_name_forms_required")
    if value["relationship_annotation"] not in RELATIONSHIPS:
        raise ReviewError("invalid_relationship_annotation")
    direction = _fields(
        value["direction"], {"query_evidence_id", "reference_evidence_id", "adequacy"}
    )
    if direction["adequacy"] not in {"unresolved", "adequate", "inadequate"}:
        raise ReviewError("invalid_direction_adequacy")
    q, r = direction["query_evidence_id"], direction["reference_evidence_id"]
    if q is None or r is None:
        if q is not None or r is not None or direction["adequacy"] != "unresolved":
            raise ReviewError("incomplete_direction_evidence")
    elif (
        q == r
        or q not in refs
        or r not in refs
        or q
        in {
            item
            for values in case["identity_evidence_refs"].values()
            for item in values
        }
        or r
        in {
            item
            for values in case["identity_evidence_refs"].values()
            for item in values
        }
    ):
        raise ReviewError("invalid_direction_evidence")
    if kind == "adjudication":
        _strings(value["submission_ids"], nonempty=True)
    return value


def _apply_event(
    kind: str,
    value: dict,
    states: dict[str, dict],
    submissions: dict[str, dict],
    ids: set[str],
    pair_outcomes: dict[tuple[str, ...], str],
    cases: dict[str, dict],
    registry: dict[str, dict],
) -> None:
    identifier = value["submission_id" if kind == "submission" else "adjudication_id"]
    if identifier in ids:
        raise ReviewError("duplicate_or_replayed_event")
    state = states[value["case_id"]]
    reviews = [s for s in submissions.values() if s["case_id"] == value["case_id"]]
    actor = registry[value["actor_id"]]

    def related(review: dict) -> bool:
        other = registry[review["actor_id"]]
        return any(
            actor[key] == other[key]
            for key in ("actor_id", "principal_id", "independence_group")
        )

    if state["adjudication_id"] is not None:
        raise ReviewError("case_already_adjudicated")
    if kind == "submission":
        if len(reviews) >= 2 or any(related(r) for r in reviews):
            raise ReviewError("duplicate_reviewer_or_review_limit")
        submissions[identifier] = value
        reviews.append(value)
        state["review_count"] = len(reviews)
        state["status"] = (
            "awaiting_second_review"
            if len(reviews) == 1
            else (
                "agreement_pending_adjudication"
                if reviews[0]["outcome"] == reviews[1]["outcome"]
                else "disagreement_pending_adjudication"
            )
        )
    else:
        if len(reviews) != 2 or set(value["submission_ids"]) != {
            r["submission_id"] for r in reviews
        }:
            raise ReviewError("adjudication_requires_exact_two_reviews")
        if any(related(r) for r in reviews):
            raise ReviewError("independent_adjudicator_required")
        if any(_time(r["created_at"]) > _time(value["created_at"]) for r in reviews):
            raise ReviewError("adjudication_predates_review")
        case = cases[value["case_id"]]
        if len(case["observation_ids"]) == 2 and value["outcome"].startswith(
            "supported_"
        ):
            pair = tuple(sorted(case["observation_ids"]))
            if pair in pair_outcomes and pair_outcomes[pair] != value["outcome"]:
                raise ReviewError("incompatible_pair_adjudications")
            pair_outcomes[pair] = value["outcome"]
        state.update(
            status="adjudicated_unresolved"
            if value["outcome"] in {"insufficient_evidence", "ineligible"}
            or value["uncertain"]
            else "adjudicated_fixture",
            outcome=value["outcome"],
            adjudication_id=identifier,
        )
    ids.add(identifier)


def _replay(
    ledger: Path,
    eventfd: int,
    *,
    expected_packet_sha256: str,
    expected_head: str,
    summary: dict,
    cases: dict[str, dict],
    actors: tuple[dict, ...],
    guard: ResourceGuard,
) -> tuple[dict, dict, set, dict, list[tuple[str, bytes]]]:
    _hash(expected_head)
    _private(ledger / "header.json")
    header_bytes = corpus._read_saved(
        ledger / "header.json", 2_000_000, "ledger header"
    )
    header = _fields(
        _json(header_bytes),
        {
            "schema_version",
            "scope",
            "ledger_version",
            "protocol_version",
            "packet_sha256",
            "mode",
            "actors",
            "created_at",
            "permissions",
            "accepted_labels",
            "identity_merges",
            "accepted_corpus_release",
        },
    )
    registry = _actors(actors, summary["mode"])
    expected = {
        "schema_version": 1,
        "scope": SCOPE,
        "ledger_version": LEDGER_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "packet_sha256": expected_packet_sha256,
        "mode": summary["mode"],
        "actors": registry,
        "created_at": summary["metadata"]["created_at"],
        "permissions": RESTRICTIONS,
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
    }
    if header_bytes != _canonical(expected) or header != expected:
        raise ReviewError("ledger_header_or_actor_registry_mismatch")
    filenames = sorted(os.listdir(eventfd))
    if len(filenames) > LIMITS["max_events"] or filenames != [
        f"{n:012d}.json" for n in range(1, len(filenames) + 1)
    ]:
        raise ReviewError("ledger_event_gap_or_unexpected_file")
    if summary["mode"] != "fictional_fixture" and filenames:
        raise ReviewError("real_review_execution_disabled")
    states = {
        cid: {
            "status": "unreviewed",
            "review_count": 0,
            "outcome": None,
            "adjudication_id": None,
            "release_blocked": True,
        }
        for cid in cases
    }
    submissions, ids, pair_outcomes = {}, set(), {}
    head, previous_time = _sha(header_bytes), _time(header["created_at"])
    saved = [("header.json", header_bytes)]
    for sequence, filename in enumerate(filenames, 1):
        guard.check()
        _private(ledger / "events" / filename)
        raw = corpus._read_saved(ledger / "events" / filename, 65536, "ledger event")
        event = _fields(
            _json(raw),
            {
                "schema_version",
                "sequence",
                "previous_sha256",
                "kind",
                "payload",
                "event_sha256",
            },
        )
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        if (
            type(event["schema_version"]) is not int
            or event["schema_version"] != 1
            or type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["previous_sha256"] != head
            or event["kind"] not in {"submission", "adjudication"}
            or event["event_sha256"] != _sha(_canonical(body))
            or raw != _canonical(event)
        ):
            raise ReviewError("corrupt_ledger_chain")
        value = _event_payload(
            event["payload"],
            event["kind"],
            cases,
            {a["actor_id"]: a for a in registry},
            expected_packet_sha256,
        )
        if value != event["payload"] or _time(value["created_at"]) < previous_time:
            raise ReviewError("noncanonical_or_backdated_event")
        previous_time = _time(value["created_at"])
        _apply_event(
            event["kind"],
            value,
            states,
            submissions,
            ids,
            pair_outcomes,
            cases,
            {a["actor_id"]: a for a in registry},
        )
        head = event["event_sha256"]
        saved.append(("events/" + filename, raw))
    if head != expected_head:
        raise ReviewError("ledger_head_mismatch_or_truncation")
    result = {
        "event_count": len(filenames),
        "head_sha256": head,
        "submission_count": len(submissions),
        "adjudication_count": sum(
            s["adjudication_id"] is not None for s in states.values()
        ),
        "accepted_labels": 0,
        "identity_merges": 0,
        "accepted_corpus_release": False,
        "case_states": states,
    }
    return result, submissions, ids, pair_outcomes, saved


def _verify_saved_ledger(
    ledger: Path, eventfd: int, saved: list[tuple[str, bytes]]
) -> None:
    if set(os.listdir(eventfd)) != {
        name.split("/", 1)[1] for name, _ in saved if name.startswith("events/")
    }:
        raise ReviewError("ledger_changed_during_operation")
    for name, payload in saved:
        if (
            corpus._read_saved(ledger / name, max(len(payload), 1), "ledger evidence")
            != payload
        ):
            raise ReviewError("ledger_changed_during_operation")


def replay_ledger(
    ledger_path: Path,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    actors: tuple[dict, ...] = (),
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Rebuild state only against an independent expected head, detecting truncation."""
    ledger, packet, guard = _ledger_context(
        ledger_path, packet_path, project_root, guard, expected_packet_sha256
    )
    packet_bytes, summary, cases = _load_packet(packet, expected_packet_sha256, guard)
    with _locked(ledger) as (_, eventfd, check_lock):
        result, _, _, _, saved = _replay(
            ledger,
            eventfd,
            expected_packet_sha256=expected_packet_sha256,
            expected_head=expected_head,
            summary=summary,
            cases=cases,
            actors=actors,
            guard=guard,
        )
        _verify_saved_ledger(ledger, eventfd, saved)
        _verify_packet_saved(packet, expected_packet_sha256, packet_bytes)
        check_lock()
        return result


def _append(
    ledger_path: Path,
    raw: dict,
    kind: str,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    actors: tuple[dict, ...],
    project_root: Path,
    guard: ResourceGuard | None,
) -> str:
    ledger, packet, guard = _ledger_context(
        ledger_path, packet_path, project_root, guard, expected_packet_sha256
    )
    packet_bytes, summary, cases = _load_packet(packet, expected_packet_sha256, guard)
    # Hardcoded execution boundary: neither config flags nor actor entries can
    # authorize a submission against a real development packet.
    if summary["mode"] != "fictional_fixture":
        raise ReviewError("real_review_execution_disabled")
    registry = _actors(actors, summary["mode"])
    with _locked(ledger) as (_, eventfd, check_lock):
        state, submissions, ids, pairs, saved = _replay(
            ledger,
            eventfd,
            expected_packet_sha256=expected_packet_sha256,
            expected_head=expected_head,
            summary=summary,
            cases=cases,
            actors=actors,
            guard=guard,
        )
        value = _event_payload(
            raw,
            kind,
            cases,
            {a["actor_id"]: a for a in registry},
            expected_packet_sha256,
        )
        previous = _json(saved[-1][1])
        previous_time = (
            previous["payload"]["created_at"]
            if "payload" in previous
            else previous["created_at"]
        )
        if _time(value["created_at"]) < _time(previous_time):
            raise ReviewError("backdated_review_event")
        _apply_event(
            kind,
            value,
            state["case_states"],
            submissions,
            ids,
            pairs,
            cases,
            {a["actor_id"]: a for a in registry},
        )
        sequence = state["event_count"] + 1
        if sequence > LIMITS["max_events"]:
            raise ReviewError("ledger_event_limit")
        body = {
            "schema_version": 1,
            "sequence": sequence,
            "previous_sha256": expected_head,
            "kind": kind,
            "payload": value,
        }
        head = _sha(_canonical(body))
        event_bytes = _canonical({**body, "event_sha256": head})
        if len(event_bytes) > 65536:
            raise ReviewError("ledger_event_byte_limit")
        _reserve(ledger.parent, 2 * len(event_bytes), guard)
        guard.check()
        _verify_saved_ledger(ledger, eventfd, saved)
        _verify_packet_saved(packet, expected_packet_sha256, packet_bytes)
        check_lock()
        _write_payload(eventfd, f"{sequence:012d}.json", event_bytes)
        return head


def append_submission(
    ledger_path: Path,
    submission: dict,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    actors: tuple[dict, ...] = (),
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Append one fictional declaration; duplicate or stale retries fail safely."""
    return _append(
        ledger_path,
        submission,
        "submission",
        packet_path=packet_path,
        expected_packet_sha256=expected_packet_sha256,
        expected_head=expected_head,
        actors=actors,
        project_root=project_root,
        guard=guard,
    )


def append_adjudication(
    ledger_path: Path,
    adjudication: dict,
    *,
    packet_path: Path,
    expected_packet_sha256: str,
    expected_head: str,
    actors: tuple[dict, ...] = (),
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Append a separate fictional adjudicator's declaration, never release a label."""
    return _append(
        ledger_path,
        adjudication,
        "adjudication",
        packet_path=packet_path,
        expected_packet_sha256=expected_packet_sha256,
        expected_head=expected_head,
        actors=actors,
        project_root=project_root,
        guard=guard,
    )


def resolve_evidence(
    packet_path: Path,
    case_id: str,
    *,
    expected_packet_sha256: str,
    project_root: Path,
    config_path: Path | None = None,
    guard: ResourceGuard | None = None,
) -> dict:
    """Resolve one case to original C1 evidence after full trusted-source validation.

    Returned strings are untrusted data for local human inspection, never code,
    prompts, identity facts or implicit approval. This is not a network/UI service.
    """
    root = Path(project_root).absolute()
    config_path = readiness._path(root, config_path or "config/corpus-review-v1.json")
    config, _ = _load_config(config_path, root)
    packet_path = readiness._path(root, packet_path)
    guard = _guard(root, config["artifact_roots"], packet_path.parent, guard)
    validate_review(
        packet_path, project_root=root, guard=guard, config_path=config_path
    )
    _, _, cases = _load_packet(packet_path, expected_packet_sha256, guard)
    if case_id not in cases:
        raise ReviewError("unknown_review_case")
    case = cases[case_id]
    directory = (root / config["c1"]["manifest"]["path"]).parent
    manifest = _json(
        readiness._reference(root, config["c1"]["manifest"], maximum=2_000_000)
    )
    payloads = {}
    for name in ("observations.jsonl", "nominations.jsonl", "quarantine.jsonl"):
        payload = corpus._read_saved(
            directory / name, readiness.MAX_BYTES, "C1 resolution"
        )
        if _sha(payload) != manifest["files"][name]["sha256"]:
            raise ReviewError("c1_resolution_pin_mismatch")
        payloads[name] = payload
    observations = [
        row
        for row in _rows(
            payloads["observations.jsonl"], readiness.LIMITS["max_records"]
        )
        if row["observation_id"] in case["observation_ids"]
    ]
    return {
        "case": case,
        "observations": observations,
        "nomination": next(
            (
                n
                for n in _rows(
                    payloads["nominations.jsonl"], readiness.LIMITS["max_pairs"]
                )
                if n["nomination_id"] == case["nomination_id"]
            ),
            None,
        ),
        "restrictions": [
            r
            for r in _rows(
                payloads["quarantine.jsonl"], readiness.LIMITS["max_records"]
            )
            if r["observation_id"] in case["observation_ids"]
        ],
        "source_text_is_untrusted": True,
        "identity_confirmed": False,
    }


def deny_network(event: str, arguments: tuple) -> None:
    """Deny process-local socket operations; not an operating-system sandbox."""
    if event.startswith("socket."):
        raise ReviewError("review_network_forbidden")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--config", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument(
        "--config", type=Path, default=Path("config/corpus-review-v1.json")
    )
    args = parser.parse_args(argv)
    sys.addaudithook(deny_network)
    try:
        if args.command == "prepare":
            result = prepare_review(args.config, args.output, project_root=Path.cwd())
        else:
            result = validate_review(
                args.input, project_root=Path.cwd(), config_path=args.config
            )
    except (
        ReviewError,
        readiness.ReadinessError,
        corpus.CorpusValidationError,
        ResourceStop,
        OSError,
        ValueError,
        TypeError,
        KeyError,
    ):
        print(
            json.dumps(
                {"status": "failed", "reason": "review_validation_or_resource_failure"}
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
