"""Offline, immutable *candidate* preparation from permission-bound selections.

This module makes no network requests and supplies no labels, identity merges,
partitions or training rights. A successful preparation checks evidence bytes
and mechanical consistency; it does not authenticate reviewers, establish legal
permission, replay discarded raw responses or certify independent entities.

The purpose-permission v1 contract is deliberately narrow. It binds one receipt
and selection, requires both retention/preparation operations, and enumerates
record/alias fields, entity types and original name fields with attribute keys.
Every declared evidence file is retained in the candidate artifact. Training,
publication and reviewed-corpus acceptance require separate future workflows.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
from importlib.resources import files
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
from typing import Callable, Iterable
from urllib.parse import urlsplit
import uuid

from watchlist.ingest.source_registry import (
    AliasEvidence,
    SOURCE_IDS,
    SourceRecord,
    SourceValidationError,
)
from watchlist.scripts import SCRIPT_METHOD, UNICODE_VERSION, script_set


APPLICATION_ID = 0x50574331
SCHEMA_VERSION = 2
MAX_SELECTION_BYTES = 100_000_000
MAX_METADATA_BYTES = 2_000_000
MAX_EVIDENCE_BYTES = 2_000_000
MAX_TOTAL_INPUT_BYTES = 100_000_000
MAX_RELEASE_BYTES = 256_000_000
MAX_OBSERVATIONS = 100_000
MAX_SNAPSHOTS = 32
MAX_EVIDENCE_FILES = 128
PURPOSE = "local_candidate_corpus_preparation"
SOURCE_RECEIPT = "source-acquisition-v1"
FICTIONAL_FULL_RECEIPT = "fictional-full-acquisition-v1"
REAL_FULL_RECEIPT = "real-full-acquisition-v1"
RECOVERY_SCOPE = "08B-2R-development-candidate-recovery-v1"
CONTINUATION_SCOPE = "08B-2R-development-candidate-continuation-v1"
CONTINUATION_PREPARATION = "continuation-readiness-inputs-v1"
OPERATIONS = frozenset({"retain_selected_names", "prepare_candidate_corpus"})
RECORD_FIELDS = frozenset(
    {
        "source_id",
        "provider_id",
        "entity_type",
        "primary_name",
        "aliases",
        "provider_schema",
        "referents",
        "provider_datasets",
        "provider_topics",
        "classification_basis",
        "qualified_id",
        "source_role",
    }
)
ALIAS_FIELDS = frozenset({"value", "field", "language", "attributes"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "source_id",
        "role",
        "status",
        "requested_url",
        "final_url",
        "permission",
        "permission_evidence",
        "policy_sha256",
        "max_response_body_bytes",
        "request_timeout_seconds",
        "source_deadline_seconds",
        "attempts",
        "bytes_received",
        "complete_body_sha256",
        "complete_body_bytes",
        "normalized_selection_sha256",
        "records_path",
        "raw_retained",
        "attribution",
        "parser_version",
        "source_version",
        "source_version_field",
        "version_fallback",
        "selected_provider_schemas",
        "container_format",
        "container_member",
        "decoded_bytes",
        "decoded_sha256",
        "stats",
    }
)
_RECEIPT_OPTIONAL = frozenset(
    {
        "publisher_snapshot",
        "publisher_checksum_verified",
        "publisher_decoded_checksum_verified",
        "response_version_evidence",
        "final_url_evidence",
        "finished_at",
    }
)
_PERMISSION_FIELDS = frozenset(
    {
        "schema_version",
        "review_id",
        "source_id",
        "status",
        "purpose",
        "operations",
        "receipt_sha256",
        "selection_sha256",
        "record_fields",
        "alias_fields",
        "entity_types",
        "name_fields",
        "evidence",
        "reviewed_at",
        "reviewer",
        "attribution",
        "conditions",
    }
)
_BLOCKERS = (
    "purpose permission covers candidate preparation only",
    "no accepted record equivalence, entity claims or independent leakage families",
    "no human reviews, adjudicated labels or reviewed target counts",
    "no frozen reference/query views, partitions or independent final custody",
)


class CorpusValidationError(ValueError):
    """Saved evidence, permissions or a candidate artifact failed admission."""


@dataclass(frozen=True, slots=True)
class CandidateNameEvidence:
    """One complete source name assertion, with no language/identity inference."""

    evidence_id: str
    value: str
    field: str
    language: str | None
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    """One source-local record in one snapshot; never an independent entity."""

    observation_id: str
    snapshot_id: str
    source_id: str
    provider_id: str
    source_record_key: tuple[str, str]
    entity_type: str
    primary_name: str
    aliases: tuple[CandidateNameEvidence, ...]
    provider_schema: str
    classification_basis: str | None
    referents: tuple[str, ...]
    provider_datasets: tuple[str, ...]
    provider_topics: tuple[str, ...]
    source_role: str


@dataclass(frozen=True, slots=True)
class SavedEvidence:
    """Exact permitted local evidence, identified by relative path and digest."""

    path: str
    sha256: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class PreparedSource:
    """Verified immutable input buffers; publication revalidates every field."""

    snapshot_id: str
    source_id: str
    selection_sha256: str
    receipt_sha256: str
    permission_sha256: str
    selection_bytes: bytes
    receipt_bytes: bytes
    permission_bytes: bytes
    evidence: tuple[SavedEvidence, ...]
    observations: tuple[CandidateObservation, ...]
    receipt_format: str = SOURCE_RECEIPT


@dataclass(frozen=True, slots=True)
class ContinuationSource:
    """Readiness input buffers, deliberately outside the release-source type."""

    snapshot_id: str
    source_id: str
    selection_path: str
    selection_sha256: str
    selection_bytes: bytes
    permission_path: str
    permission_sha256: str
    permission_bytes: bytes
    bound_permission_bytes: bytes
    acquisition_origin: str
    observations: tuple[CandidateObservation, ...]


@dataclass(frozen=True, slots=True)
class ContinuationPreparation:
    """Immutable verified inputs for unreviewed readiness, never a corpus release.

    Receipt, lineage and grants retain their original bytes. The manifest binds
    references only; it grants no decisions, publication or model eligibility.
    """

    receipt_sha256: str
    receipt_bytes: bytes
    input_manifest_bytes: bytes
    input_manifest_sha256: str
    evidence: tuple[SavedEvidence, ...]
    sources: tuple[ContinuationSource, ...]
    observations: tuple[CandidateObservation, ...]

    def input_manifest(self) -> dict:
        """Return a detached input binding without permitting eligibility edits."""
        if _sha(self.input_manifest_bytes) != self.input_manifest_sha256:
            raise CorpusValidationError("continuation input manifest digest differs")
        manifest = _json_object(
            self.input_manifest_bytes, "continuation input manifest"
        )
        if self.input_manifest_bytes != _continuation_manifest(
            manifest.get("receipt", {}).get("path"),
            self.receipt_bytes,
            self.sources,
            self.evidence,
        ) or self.receipt_sha256 != _sha(self.receipt_bytes):
            raise CorpusValidationError(
                "continuation input manifest differs from retained inputs"
            )
        return manifest


@dataclass(frozen=True, slots=True)
class CandidateRelease:
    """A self-contained candidate artifact, explicitly ineligible for ML use."""

    release_id: str
    logical_sha256: str
    artifact_sha256: str
    manifest_bytes: bytes
    sources: tuple[PreparedSource, ...]
    observations: tuple[CandidateObservation, ...]

    def summary(self) -> dict:
        """Return a detached summary; callers cannot change stored eligibility."""
        result = _json_object(self.manifest_bytes, "manifest")
        if self.manifest_bytes != _manifest(
            self.release_id, self.sources, schema_version=result.get("schema_version")
        ) or self.logical_sha256 != _sha(self.manifest_bytes):
            raise CorpusValidationError(
                "candidate summary differs from its preparation manifest"
            )
        result["logical_sha256"] = self.logical_sha256
        result["artifact_sha256"] = self.artifact_sha256
        return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _text(value: object, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise CorpusValidationError(f"invalid {label}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CorpusValidationError(f"invalid {label} SHA-256")
    return value


def _https(value: object, label: str) -> str:
    value = _text(value, label, 16384)
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
        ):
            raise CorpusValidationError(f"invalid {label} HTTPS URL")
    except ValueError as exc:
        raise CorpusValidationError(f"invalid {label} HTTPS URL") from exc
    return value


def _integer(value: object, label: str, minimum: int = 0, maximum: int = 10**12) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CorpusValidationError(f"invalid {label} integer")
    return value


def _object(value: object, required: Iterable[str], label: str, optional=()) -> dict:
    if not isinstance(value, dict) or not set(required) <= set(value) <= (
        set(required) | set(optional)
    ):
        raise CorpusValidationError(f"missing or unsupported {label} fields")
    return value


def _strings(
    value: object, label: str, *, minimum: int = 0, maximum: int = 1024
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise CorpusValidationError(f"invalid {label} array")
    result = tuple(_text(item, label, 1024) for item in value)
    if len(set(result)) != len(result):
        raise CorpusValidationError(f"duplicate {label}")
    return result


def _json_object(raw: bytes, label: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CorpusValidationError(f"duplicate JSON key in {label}")
            result[key] = value
        return result

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise CorpusValidationError(f"nonfinite JSON in {label}")
        return parsed

    try:
        # Explicit UTF-8 prevents json.loads from silently admitting UTF-16/32.
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=finite,
            parse_float=finite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise CorpusValidationError(f"malformed {label} JSON") from exc
    if not isinstance(value, dict):
        raise CorpusValidationError(f"{label} must be a JSON object")
    return value


def _relative(value: object) -> str:
    path = _text(value, "evidence path", 1024)
    parts = PurePosixPath(path)
    if (
        parts.is_absolute()
        or "\\" in path
        or any(p in {"", ".", ".."} for p in path.split("/"))
        or ":" in path
    ):
        raise CorpusValidationError("evidence path must be a contained relative path")
    return path


def _open_directory(path: Path) -> int:
    """Open each directory component without following symlinks."""
    absolute = path.absolute()
    if ".." in absolute.parts:
        raise CorpusValidationError("parent traversal is not permitted")
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _fingerprint(info: os.stat_result) -> tuple:
    return tuple(
        getattr(info, key)
        for key in (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    )


def _read_saved(path: Path, maximum: int, label: str) -> bytes:
    """Read one bounded regular file through descriptors, rejecting replacement."""
    directory = _open_directory(path.parent)
    descriptor = None
    try:
        before = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise CorpusValidationError(f"{label} must be a bounded regular file")
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        opened = os.fstat(descriptor)
        chunks = []
        size = 0
        while chunk := os.read(descriptor, min(65536, maximum + 1 - size)):
            size += len(chunk)
            if size > maximum:
                raise CorpusValidationError(f"{label} exceeds its byte limit")
            chunks.append(chunk)
        finished = os.fstat(descriptor)
        after = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        if any(
            _fingerprint(item) != _fingerprint(before)
            for item in (opened, finished, after)
        ):
            raise CorpusValidationError(f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def _evidence_references(items: object, *, acquisition: bool) -> dict[str, str]:
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_EVIDENCE_FILES:
        raise CorpusValidationError("permission evidence is missing or exceeds bounds")
    result = {}
    for item in items:
        entry = _object(
            item,
            {"path", "sha256"},
            "evidence",
            {"publisher_snapshot"} if acquisition else (),
        )
        path = _relative(entry["path"])
        digest = _digest(entry["sha256"], "evidence")
        if path in result:
            raise CorpusValidationError("duplicate permission evidence path")
        result[path] = digest
    return result


def _permission(
    permission: dict, receipt: dict, receipt_hash: str, selection_hash: str
) -> dict[str, str]:
    _object(permission, _PERMISSION_FIELDS, "purpose permission")
    if (
        type(permission["schema_version"]) is not int
        or permission["schema_version"] != 1
        or permission["status"] != "approved"
        or permission["purpose"] != PURPOSE
        or permission["source_id"] != receipt["source_id"]
        or permission["receipt_sha256"] != receipt_hash
        or permission["selection_sha256"] != selection_hash
    ):
        raise CorpusValidationError(
            "purpose permission does not approve these exact candidate inputs"
        )
    if set(_strings(permission["operations"], "operations")) != OPERATIONS:
        raise CorpusValidationError(
            "candidate preparation requires its exact two operations"
        )
    if set(_strings(permission["record_fields"], "record fields")) != RECORD_FIELDS:
        raise CorpusValidationError(
            "record field permission is incomplete or unsupported"
        )
    if set(_strings(permission["alias_fields"], "alias fields")) != ALIAS_FIELDS:
        raise CorpusValidationError(
            "alias field permission is incomplete or unsupported"
        )
    if not set(_strings(permission["entity_types"], "entity types", minimum=1)) <= {
        "organization",
        "vessel",
    }:
        raise CorpusValidationError(
            "purpose permission allows an unsupported entity type"
        )
    name_fields = permission["name_fields"]
    if not isinstance(name_fields, dict) or not 1 <= len(name_fields) <= 128:
        raise CorpusValidationError("original name-field permissions are required")
    for field, attributes in name_fields.items():
        _text(field, "original name field", 1024)
        _strings(attributes, "attribute keys", maximum=32)
    for key in ("review_id", "reviewer", "reviewed_at", "attribution"):
        _text(permission[key], key)
    try:
        datetime.fromisoformat(permission["reviewed_at"])
    except ValueError as exc:
        raise CorpusValidationError("invalid permission review date") from exc
    _strings(permission["conditions"], "conditions", minimum=1, maximum=128)
    return _evidence_references(permission["evidence"], acquisition=False)


def _receipt(receipt: dict, selection_hash: str) -> dict[str, str]:
    """Check completed transfer accounting; a partial-body digest never suffices."""
    _object(receipt, _RECEIPT_FIELDS, "receipt", _RECEIPT_OPTIONAL)
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["source_id"] not in SOURCE_IDS
        or receipt["status"] != "success"
        or receipt["raw_retained"] is not False
        or receipt["normalized_selection_sha256"] != selection_hash
    ):
        raise CorpusValidationError(
            "receipt does not bind a successful permitted selection"
        )
    expected_role = (
        "supplemental_unlabelled"
        if receipt["source_id"] == "wikidata_orgs"
        else "sanctions_reference"
    )
    if receipt["role"] != expected_role:
        raise CorpusValidationError("receipt source role is inconsistent")
    for key in ("requested_url", "final_url", "attribution", "parser_version"):
        _text(receipt[key], key)
    _https(receipt["requested_url"], "requested URL")
    final_url = _https(receipt["final_url"], "final URL")
    if receipt["source_id"] == "ofac_sdn" and urlsplit(final_url).query:
        raise CorpusValidationError("OFAC signing queries must remain redacted")
    if "final_url_evidence" in receipt:
        url_evidence = _object(
            receipt["final_url_evidence"],
            {"url_sha256", "query_present", "signing_query_redacted"},
            "final URL evidence",
        )
        _digest(url_evidence["url_sha256"], "final URL")
        if (
            type(url_evidence["query_present"]) is not bool
            or type(url_evidence["signing_query_redacted"]) is not bool
        ):
            raise CorpusValidationError("URL evidence flags must be booleans")
        if url_evidence["signing_query_redacted"]:
            if (
                receipt["source_id"] != "ofac_sdn"
                or not url_evidence["query_present"]
                or urlsplit(final_url).query
            ):
                raise CorpusValidationError("invalid signing-query redaction claim")
        elif url_evidence["url_sha256"] != _sha(final_url.encode()) or url_evidence[
            "query_present"
        ] != bool(urlsplit(final_url).query):
            raise CorpusValidationError("final URL evidence differs")
    if "response_version_evidence" in receipt:
        response = _object(
            receipt["response_version_evidence"],
            (),
            "response version",
            {"etag", "last-modified"},
        )
        for value in response.values():
            _text(value, "response version")
    if "finished_at" in receipt:
        _text(receipt["finished_at"], "receipt finish time", 128)
        try:
            datetime.fromisoformat(receipt["finished_at"])
        except ValueError as exc:
            raise CorpusValidationError("invalid receipt finish time") from exc
    if _relative(receipt["records_path"]) != f"{receipt['source_id']}.jsonl":
        raise CorpusValidationError(
            "receipt selection filename does not identify its source"
        )
    _digest(receipt["policy_sha256"], "acquisition policy")
    body_hash = _digest(receipt["complete_body_sha256"], "complete body")
    body_bytes = _integer(receipt["complete_body_bytes"], "complete body bytes", 1)
    maximum = _integer(receipt["max_response_body_bytes"], "response bound", 1)
    total = _integer(receipt["bytes_received"], "received bytes", 1, maximum)
    for key in ("request_timeout_seconds", "source_deadline_seconds"):
        _integer(receipt[key], key, 1)
    if receipt["request_timeout_seconds"] > receipt["source_deadline_seconds"]:
        raise CorpusValidationError("request timeout exceeds source deadline")
    attempts = receipt["attempts"]
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= 32:
        raise CorpusValidationError("receipt lacks bounded transfer attempts")
    summed = 0
    for number, attempt in enumerate(attempts, 1):
        success = number == len(attempts)
        fields = {"attempt", "bytes_received", "status"} | (
            {"complete_body_sha256"}
            if success
            else {"partial_body_sha256", "error_code"}
        )
        _object(attempt, fields, "transfer attempt", {"http_status"})
        if type(attempt["attempt"]) is not int or attempt["attempt"] != number:
            raise CorpusValidationError("transfer attempt order is inconsistent")
        size = _integer(attempt["bytes_received"], "attempt bytes", maximum=maximum)
        summed += size
        if attempt["status"] != ("success" if success else "failed"):
            raise CorpusValidationError("only the final transfer attempt can succeed")
        if success and (
            size != body_bytes or attempt["complete_body_sha256"] != body_hash
        ):
            raise CorpusValidationError("completed transfer evidence is inconsistent")
        if not success:
            _digest(attempt["partial_body_sha256"], "partial body")
            _text(attempt["error_code"], "transfer error")
        if "http_status" in attempt:
            status = _integer(attempt["http_status"], "HTTP status", 100, 599)
            if success and status != 200:
                raise CorpusValidationError(
                    "successful transfer has a non-200 HTTP status"
                )
    if summed != total:
        raise CorpusValidationError(
            "received byte count differs from transfer attempts"
        )
    source_version, field = receipt["source_version"], receipt["source_version_field"]
    if source_version is None:
        if field is not None or receipt["version_fallback"] != "complete_body_sha256":
            raise CorpusValidationError(
                "missing version needs explicit complete-body fallback"
            )
    else:
        _text(source_version, "source version", 1024)
        _text(field, "source version field", 1024)
        if receipt["version_fallback"] is not None:
            raise CorpusValidationError("version and fallback cannot both be claimed")
    acquisition = _object(
        receipt["permission"],
        {
            "status",
            "reviewed_at",
            "license",
            "terms_urls",
            "evidence_paths",
            "rationale",
        },
        "acquisition permission",
    )
    if acquisition["status"] != "approved":
        raise CorpusValidationError("acquisition permission is not approved")
    for key in ("reviewed_at", "license", "rationale"):
        _text(acquisition[key], f"acquisition {key}")
    for url in _strings(acquisition["terms_urls"], "acquisition terms", minimum=1):
        _https(url, "acquisition terms")
    try:
        datetime.fromisoformat(acquisition["reviewed_at"])
    except ValueError as exc:
        raise CorpusValidationError("invalid acquisition review date") from exc
    references = _evidence_references(receipt["permission_evidence"], acquisition=True)
    if set(
        _strings(acquisition["evidence_paths"], "acquisition evidence", minimum=1)
    ) != set(references):
        raise CorpusValidationError("acquisition evidence is incomplete")
    _container(receipt)
    return references


def _container(receipt: dict) -> None:
    values = [
        receipt[key]
        for key in (
            "container_format",
            "container_member",
            "decoded_bytes",
            "decoded_sha256",
        )
    ]
    if any(value is not None for value in values):
        if (
            values[0] != "zip"
            or receipt["source_id"] != "ofac_sdn"
            or values[1] != "SDN.XML"
        ):
            raise CorpusValidationError("unsupported or incomplete container evidence")
        _integer(values[2], "decoded bytes", 1)
        _digest(values[3], "decoded body")
    snapshot = receipt.get("publisher_snapshot")
    recorded = [
        item["publisher_snapshot"]
        for item in receipt["permission_evidence"]
        if "publisher_snapshot" in item
    ]
    if snapshot is None:
        if (
            recorded
            or receipt.get("publisher_checksum_verified") is not None
            or receipt.get("publisher_decoded_checksum_verified") is not None
        ):
            raise CorpusValidationError(
                "publisher verification lacks saved publisher evidence"
            )
        return
    _object(
        snapshot,
        {
            "version",
            "version_field",
            "resource_url",
            "resource_bytes",
            "published_checksum",
            "checksum_comparison",
        },
        "publisher snapshot",
        {
            "publisher_archive_checksum_available",
            "decoded_bytes",
            "decoded_sha256",
            "decoded_hash_field",
            "published_object_path",
        },
    )
    if not recorded or any(item != snapshot for item in recorded):
        raise CorpusValidationError(
            "publisher snapshot differs from permission evidence"
        )
    if (
        snapshot["resource_url"] != receipt["requested_url"]
        or type(snapshot["resource_bytes"]) is not int
        or snapshot["resource_bytes"] != receipt["complete_body_bytes"]
    ):
        raise CorpusValidationError(
            "publisher snapshot does not bind the completed transfer"
        )
    for key in ("version", "version_field"):
        _text(snapshot[key], "publisher " + key)
    if receipt["source_version"] is None:
        raise CorpusValidationError(
            "available publisher version cannot be replaced by fallback"
        )
    if (
        receipt["source_version_field"] == snapshot["version_field"]
        and receipt["source_version"] != snapshot["version"]
    ):
        raise CorpusValidationError("publisher version differs from receipt version")
    checksum, algorithm = (
        snapshot["published_checksum"],
        snapshot["checksum_comparison"],
    )
    if checksum is None:
        if (
            algorithm is not None
            or receipt.get("publisher_checksum_verified") is not None
        ):
            raise CorpusValidationError("absent publisher checksum cannot be verified")
    elif (
        algorithm not in ("sha1", "sha256")
        or not isinstance(checksum, str)
        or re.fullmatch(
            r"[0-9a-f]{" + ("40" if algorithm == "sha1" else "64") + "}", checksum
        )
        is None
        or receipt.get("publisher_checksum_verified") is not True
    ):
        raise CorpusValidationError("publisher checksum claim is incomplete")
    if algorithm == "sha256" and checksum != receipt["complete_body_sha256"]:
        raise CorpusValidationError("publisher complete-body SHA-256 differs")
    decoded_fields = {
        "decoded_sha256",
        "decoded_bytes",
        "decoded_hash_field",
        "published_object_path",
        "publisher_archive_checksum_available",
    }
    if decoded_fields.intersection(snapshot) and not decoded_fields <= set(snapshot):
        raise CorpusValidationError("decoded publisher metadata is incomplete")
    if "decoded_sha256" in snapshot:
        _digest(snapshot["decoded_sha256"], "publisher decoded body")
        _text(snapshot["decoded_hash_field"], "publisher decoded hash field")
        _relative(snapshot["published_object_path"])
        if (
            receipt["container_format"] != "zip"
            or snapshot["decoded_sha256"] != receipt["decoded_sha256"]
            or type(snapshot.get("decoded_bytes")) is not int
            or snapshot["decoded_bytes"] != receipt["decoded_bytes"]
            or receipt.get("publisher_decoded_checksum_verified") is not True
            or snapshot["publisher_archive_checksum_available"] is not False
            or snapshot["published_checksum"] is not None
        ):
            raise CorpusValidationError("decoded publisher checksum evidence differs")
    elif receipt.get("publisher_decoded_checksum_verified") is not None:
        raise CorpusValidationError("decoded checksum claim lacks publisher evidence")


def _nonperson(record: SourceRecord) -> None:
    """Check the supported saved parser profiles, without inventing type evidence."""
    valid = False
    if record.source_id == "opensanctions_un":
        expected = {
            "Organization": "organization",
            "Company": "organization",
            "Vessel": "vessel",
        }.get(record.provider_schema)
        valid = (
            expected == record.entity_type
            and record.classification_basis == "ftm-explicit-schema"
        )
        if record.provider_schema == "LegalEntity":
            valid = (
                record.entity_type == "organization"
                and record.classification_basis == "reviewed-un-entity-mapping"
                and "un_sc_sanctions" in record.provider_datasets
            )
        valid = valid and "sanction" in record.provider_topics
    elif record.source_id == "ofac_sdn":
        prefix = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML#sdnList.sdnEntry:"
        valid = (
            record.provider_schema
            == prefix
            + {"organization": "Entity", "vessel": "Vessel"}[record.entity_type]
        )
    elif record.source_id == "eu_consolidated":
        valid = (
            record.entity_type == "organization"
            and re.fullmatch(
                r"export\.sanctionEntity:code=[^;]+;classificationCode=E",
                record.provider_schema,
            )
            is not None
            and not record.provider_schema.startswith(
                "export.sanctionEntity:code=person;"
            )
            and record.classification_basis == "eu-subjectType-classificationCode-E"
        )
    elif record.source_id == "un_consolidated":
        valid = (
            record.entity_type == "organization"
            and record.provider_schema == "CONSOLIDATED_LIST.ENTITIES.ENTITY"
        )
    elif record.source_id == "wikidata_orgs":
        valid = (
            record.entity_type == "organization"
            and record.provider_schema == "wikidata:P31:Q43229"
        )
    if not valid:
        raise CorpusValidationError(
            "saved provider evidence does not support the non-person type"
        )


def _records(
    raw: bytes,
    receipt: dict,
    permission: dict,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[SourceRecord, ...]:
    if raw and not raw.endswith(b"\n"):
        raise CorpusValidationError(
            "selection has no final newline; completeness is uncertain"
        )
    result = []
    previous = None
    for line in raw.splitlines():
        if checkpoint is not None and len(result) % 128 == 0:
            checkpoint()
        if not line or len(result) >= MAX_OBSERVATIONS:
            raise CorpusValidationError(
                "selection has empty lines or exceeds record bounds"
            )
        item = _object(
            _json_object(line, "selection record"), RECORD_FIELDS, "selection record"
        )
        if (
            item["source_id"] != receipt["source_id"]
            or item["source_role"] != receipt["role"]
            or item["entity_type"] not in permission["entity_types"]
            or item["qualified_id"] != f"{item['source_id']}:{item['provider_id']}"
        ):
            raise CorpusValidationError(
                "record source, role, key or entity-type permission differs"
            )
        aliases = item["aliases"]
        if not isinstance(aliases, list) or not 1 <= len(aliases) <= 128:
            raise CorpusValidationError("invalid alias evidence count")
        converted = []
        for alias in aliases:
            _object(alias, ALIAS_FIELDS, "alias")
            field = _text(alias["field"], "alias field", 1024)
            if field not in permission["name_fields"]:
                raise CorpusValidationError(
                    "original name field lacks purpose permission"
                )
            attributes = alias["attributes"]
            if not isinstance(attributes, list) or len(attributes) > 32:
                raise CorpusValidationError("invalid alias attributes")
            if any(not isinstance(pair, list) or len(pair) != 2 for pair in attributes):
                raise CorpusValidationError("invalid alias attribute pair")
            keys = [_text(pair[0], "attribute key", 128) for pair in attributes]
            if len(set(keys)) != len(keys) or not set(keys) <= set(
                permission["name_fields"][field]
            ):
                raise CorpusValidationError("duplicate or unpermitted alias attributes")
            try:
                converted.append(
                    AliasEvidence(
                        alias["value"],
                        field,
                        alias["language"],
                        tuple(tuple(pair) for pair in attributes),
                    )
                )
            except SourceValidationError as exc:
                raise CorpusValidationError(str(exc)) from exc
        if len(set(converted)) != len(converted):
            raise CorpusValidationError("duplicate complete alias evidence")
        try:
            record = SourceRecord(
                item["source_id"],
                item["provider_id"],
                item["entity_type"],
                item["primary_name"],
                tuple(converted),
                item["provider_schema"],
                _strings(item["referents"], "provider referents"),
                _strings(item["provider_datasets"], "provider datasets", maximum=128),
                _strings(item["provider_topics"], "provider topics", maximum=128),
                item["classification_basis"],
            )
        except SourceValidationError as exc:
            raise CorpusValidationError(str(exc)) from exc
        if previous is not None and record.provider_id <= previous:
            raise CorpusValidationError("selection is not in unique provider-ID order")
        previous = record.provider_id
        _nonperson(record)
        result.append(record)
    return tuple(result)


def _statistics(records: tuple[SourceRecord, ...], receipt: dict) -> None:
    stats = receipt["stats"]
    _object(
        stats,
        {
            "input_records",
            "selected_provider_groups",
            "excluded_person_records",
            "excluded_other_records",
            "excluded_by_limit",
            "alias_evidence_count",
            "unique_name_strings",
            "repeated_name_evidence",
            "same_name_distinct_provider_groups",
            "provider_referents",
            "name_script_counts",
            "name_language_counts",
            "script_count_method",
            "unicode_version",
            "script_count_unit",
            "cross_source_identity_adjudicated",
        },
        "receipt statistics",
    )
    aliases = [alias for record in records for alias in record.aliases]
    names = {alias.value for alias in aliases}
    groups = Counter(
        value
        for record in records
        for value in {alias.value for alias in record.aliases}
    )
    expected = {
        "selected_provider_groups": len(records),
        "alias_evidence_count": len(aliases),
        "unique_name_strings": len(names),
        "repeated_name_evidence": len(aliases) - len(names),
        "same_name_distinct_provider_groups": sum(
            count > 1 for count in groups.values()
        ),
        "provider_referents": sum(len(record.referents) for record in records),
    }
    for key, value in expected.items():
        if _integer(stats[key], key) != value:
            raise CorpusValidationError(f"receipt {key} differs from saved selection")
    accounted = len(records) + sum(
        _integer(stats[key], key)
        for key in (
            "excluded_person_records",
            "excluded_other_records",
            "excluded_by_limit",
        )
    )
    if _integer(stats["input_records"], "input records") != accounted:
        raise CorpusValidationError("receipt input/exclusion accounting is incomplete")
    if stats["cross_source_identity_adjudicated"] is not False:
        raise CorpusValidationError(
            "acquisition statistics cannot assert identity adjudication"
        )
    expected_maps = {
        "name_language_counts": Counter(
            alias.language or "unknown" for alias in aliases
        ),
        "name_script_counts": Counter(
            script
            for alias in aliases
            for script in (script_set(alias.value) or {"NO_SCRIPT_EVIDENCE"})
        ),
    }
    for key, counts in expected_maps.items():
        if not isinstance(stats[key], dict) or stats[key] != dict(counts):
            raise CorpusValidationError(f"receipt {key} differs from source evidence")
        for count in stats[key].values():
            _integer(count, key, 1)
    if (
        stats["script_count_method"] != SCRIPT_METHOD
        or stats["unicode_version"] != UNICODE_VERSION
        or stats["script_count_unit"]
        != "alias evidence; mixed scripts count in each; UNKNOWN is unresolved"
    ):
        raise CorpusValidationError("unsupported script-accounting method/version")
    if _strings(receipt["selected_provider_schemas"], "provider schemas") != tuple(
        sorted({record.provider_schema for record in records})
    ):
        raise CorpusValidationError("selected provider schemas differ from receipt")


def _source_context(
    receipt: dict, selection: bytes, permission: dict, receipt_format: str
) -> tuple[dict, dict[str, str]]:
    """Keep legacy acquisition and explicitly fictional full receipts separate."""
    if receipt_format == SOURCE_RECEIPT:
        return receipt, _receipt(receipt, _sha(selection))
    if receipt_format == REAL_FULL_RECEIPT:
        if receipt.get("scope") == RECOVERY_SCOPE:
            return _recovery_receipt(receipt, selection, permission.get("source_id"))
        return _real_full_receipt(receipt, selection, permission.get("source_id"))
    if receipt_format != FICTIONAL_FULL_RECEIPT:
        raise CorpusValidationError("unsupported source receipt format")
    return _fictional_full_receipt(receipt, selection, permission.get("source_id")), {}


def _reference(value: object, label: str) -> tuple[str, str]:
    entry = _object(value, {"path", "sha256"}, label)
    return _relative(entry["path"]), _digest(entry["sha256"], label)


_FULL_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "input_sha256",
        "input_bytes",
        "body_sha256",
        "bytes_received",
        "input_records",
        "retained_groups",
        "excluded_person_records",
        "excluded_other_records",
        "excluded_by_limit",
        "parser_version",
        "source_version",
        "source_version_field",
        "version_fallback",
        "container_format",
        "container_member",
        "decoded_bytes",
        "decoded_sha256",
        "selection_sha256",
        "selection_bytes",
        "requested_url",
        "final_url",
        "status",
        "complete",
        "http_status",
        "selection_path",
        "transaction_count",
        "permission",
        "publisher_checksum",
    }
)


def _complete_source_content(row: dict, *, recovery: bool = False) -> None:
    """Check completed parser output, source counts and publisher evidence."""
    from watchlist.ingest.resource_guard import STEP08_LIMITS

    key = row["source_id"]
    if _digest(row["input_sha256"], "complete source input") != _digest(
        row["body_sha256"], "complete response body"
    ) or (
        not recovery
        and _integer(row["input_bytes"], "complete input bytes", 1)
        != _integer(row["bytes_received"], "complete received bytes", 1)
    ):
        raise CorpusValidationError(
            "real parser input differs from completed response body"
        )
    _digest(row["selection_sha256"], "selection")
    _integer(
        row["input_bytes"],
        "complete input bytes",
        1,
        STEP08_LIMITS[key].received_bytes,
    )
    _integer(row["selection_bytes"], "selected bytes", maximum=MAX_SELECTION_BYTES)
    retained = _integer(
        row["retained_groups"],
        "retained groups",
        maximum={
            "opensanctions_un": 300,
            "ofac_sdn": 12000,
            "eu_consolidated": 2000,
        }[key],
    )
    if _integer(row["input_records"], "input records", 1) != retained + sum(
        _integer(row[name], name)
        for name in (
            "excluded_person_records",
            "excluded_other_records",
            "excluded_by_limit",
        )
    ):
        raise CorpusValidationError("real source input/exclusion accounting differs")
    _text(row["parser_version"], "parser version")
    if row["source_version"] is None:
        if (
            row["source_version_field"] is not None
            or row["version_fallback"] != "input_sha256"
        ):
            raise CorpusValidationError(
                "real source needs explicit content-hash version fallback"
            )
    else:
        _text(row["source_version"], "source version")
        _text(row["source_version_field"], "source version field")
        if row["version_fallback"] is not None:
            raise CorpusValidationError(
                "real version and fallback cannot both be asserted"
            )
    if key == "ofac_sdn":
        if row["container_format"] != "zip" or row["container_member"] != "SDN.XML":
            raise CorpusValidationError("real OFAC ZIP evidence is incomplete")
        _integer(row["decoded_bytes"], "decoded bytes", 1, 32_000_000)
        _digest(row["decoded_sha256"], "decoded input")
    elif any(
        row[name] is not None
        for name in (
            "container_format",
            "container_member",
            "decoded_bytes",
            "decoded_sha256",
        )
    ):
        raise CorpusValidationError("unexpected real source container evidence")
    pins = _object(
        row["publisher_checksum"],
        {
            "expected_sha256",
            "expected_sha1",
            "expected_bytes",
            "expected_decoded_sha256",
            "verified",
            "hash_verified",
        },
        "publisher pins",
        {"expected_decoded_bytes"} if recovery else (),
    )
    for field, actual in (
        ("expected_sha256", row["input_sha256"]),
        ("expected_decoded_sha256", row["decoded_sha256"]),
    ):
        if pins[field] is not None and _digest(pins[field], field) != actual:
            raise CorpusValidationError(
                "real publisher hash differs from completed input"
            )
    if pins["expected_sha1"] is not None and (
        not isinstance(pins["expected_sha1"], str)
        or re.fullmatch(r"[0-9a-f]{40}", pins["expected_sha1"]) is None
    ):
        raise CorpusValidationError("invalid publisher SHA-1")
    if (
        pins["expected_bytes"] is not None
        and _integer(pins["expected_bytes"], "publisher bytes", 1) != row["input_bytes"]
    ):
        raise CorpusValidationError("real publisher byte count differs")
    has_hash = any(
        pins[name] is not None
        for name in ("expected_sha256", "expected_sha1", "expected_decoded_sha256")
    )
    if (
        pins["verified"] is not (has_hash or pins["expected_bytes"] is not None)
        or pins["hash_verified"] is not has_hash
    ):
        raise CorpusValidationError(
            "real publisher verification flags differ from supplied pins"
        )
    if recovery:
        if "expected_decoded_bytes" not in pins:
            raise CorpusValidationError("recovery decoded size evidence is missing")
        if (
            pins["expected_decoded_bytes"] is not None
            and _integer(
                pins["expected_decoded_bytes"], "publisher decoded bytes", 1, 32_000_000
            )
            != row["decoded_bytes"]
        ):
            raise CorpusValidationError(
                "recovery decoded size differs from publisher pin"
            )


def _real_full_receipt(
    receipt: dict, selection: bytes, source_id: object
) -> tuple[dict, dict[str, str]]:
    """Admit only the completed approved three-source direct-request envelope."""
    from watchlist.ingest.resource_guard import BULK_SOURCES

    _object(
        receipt,
        {
            "schema_version",
            "scope",
            "policy_sha256",
            "status",
            "live_authorized",
            "independent_custody_verified",
            "selection_use",
            "sources",
            "resume_supported",
            "ledger",
            "peak_sampled_rss_bytes",
            "rss_enforcement",
            "execution_policy_path",
            "execution_policy_sha256",
            "approval",
            "permission_grants",
            "evidence",
            "started_at",
            "finished_at",
            "total_body_limit",
        },
        "real full receipt",
    )
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["scope"] != "08B-2-development-candidate-acquisition-v1"
        or receipt["status"] != "passed"
        or receipt["live_authorized"] is not True
        or receipt["independent_custody_verified"] is not False
        or receipt["selection_use"] != "shared-development-candidates-only"
        or receipt["resume_supported"] is not False
        or not isinstance(source_id, str)
        or source_id not in BULK_SOURCES
        or _integer(receipt["total_body_limit"], "real full body limit") != 39_000_000
        or _digest(receipt["policy_sha256"], "real full policy")
        != _digest(receipt["execution_policy_sha256"], "execution policy")
    ):
        raise CorpusValidationError(
            "real full receipt is not complete authorized development preparation"
        )
    _integer(receipt["peak_sampled_rss_bytes"], "sampled RSS", 1, 2 * 1024**3)
    _text(receipt["rss_enforcement"], "RSS enforcement statement")
    try:
        start, finish = (
            datetime.fromisoformat(_text(receipt[name], name, 128))
            for name in ("started_at", "finished_at")
        )
        if (
            start.tzinfo is None
            or finish.tzinfo is None
            or not 0 <= (finish - start).total_seconds() <= 3600
        ):
            raise ValueError("invalid time window")
    except ValueError as exc:
        raise CorpusValidationError(
            "real full receipt has an invalid completion time"
        ) from exc
    grants = receipt["permission_grants"]
    if not isinstance(grants, list) or len(grants) != 3:
        raise CorpusValidationError(
            "real full receipt requires all three permission grants"
        )
    grants_by_source = {}
    for grant in grants:
        _object(grant, {"source_id", "path", "sha256"}, "receipt grant")
        key = _text(grant["source_id"], "grant source")
        if key not in BULK_SOURCES or key in grants_by_source:
            raise CorpusValidationError("duplicate or unsupported receipt grant")
        grants_by_source[key] = {"path": grant["path"], "sha256": grant["sha256"]}
        _reference(grants_by_source[key], "receipt grant")
    rows = receipt["sources"]
    if not isinstance(rows, list) or len(rows) != 3:
        raise CorpusValidationError(
            "real full receipt requires three completed sources"
        )
    indexed = {}
    for row in rows:
        _object(
            row,
            _FULL_SOURCE_FIELDS,
            "real full source",
        )
        key = _text(row["source_id"], "real source ID")
        if key not in BULK_SOURCES or key in indexed:
            raise CorpusValidationError("duplicate or unsupported real full source")
        if (
            row["status"] != "passed"
            or row["complete"] is not True
            or _integer(row["http_status"], "HTTP status") != 200
            or _integer(row["transaction_count"], "source transactions") != 1
            or _https(row["requested_url"], "requested URL")
            != _https(row["final_url"], "final URL")
            or row["selection_path"] != f"{key}.jsonl"
            or row["permission"] != grants_by_source[key]
        ):
            raise CorpusValidationError(
                "real source lacks a complete direct 200 response and grant"
            )
        _complete_source_content(row)
        indexed[key] = row
    if set(indexed) != set(BULK_SOURCES):
        raise CorpusValidationError("real full receipt source coverage is incomplete")
    selected = indexed[source_id]
    if selected["selection_sha256"] != _sha(selection) or selected[
        "selection_bytes"
    ] != len(selection):
        raise CorpusValidationError("real full receipt does not bind saved selection")
    _real_direct_ledger(receipt["ledger"], indexed)
    references = _evidence_references(receipt["evidence"], acquisition=False)
    for reference in (
        receipt["approval"],
        *grants_by_source.values(),
        {
            "path": receipt["execution_policy_path"],
            "sha256": receipt["execution_policy_sha256"],
        },
    ):
        path, digest = _reference(reference, "real admission evidence")
        if references.get(path) != digest:
            raise CorpusValidationError(
                "missing or conflicting real admission evidence"
            )
    return {**selected, "role": "sanctions_reference"}, references


def _real_direct_ledger(ledger: object, sources: dict[str, dict]) -> None:
    """Require the saved 39 MB / three-transaction completed session, not availability."""
    from watchlist.ingest.resource_guard import BULK_SOURCES, STEP08_LIMITS

    _object(
        ledger,
        {
            "schema_version",
            "scope",
            "limits",
            "tranche_bytes",
            "bulk_transaction_limit",
            "allowed_buckets",
            "total_received_bytes",
            "received_bytes",
            "transactions",
            "attempted_sources",
            "active_source",
            "active_request",
            "active_response_reservation",
            "session_deadline_monotonic",
            "stop_reason",
            "resume_supported",
        },
        "real session ledger",
    )
    if (
        type(ledger["schema_version"]) is not int
        or ledger["schema_version"] != 1
        or ledger["scope"] != "step08-single-session-no-resume"
        or _integer(ledger["tranche_bytes"], "tranche bytes") != 39_000_000
        or _integer(ledger["bulk_transaction_limit"], "bulk transaction limit") != 3
        or set(_strings(ledger["allowed_buckets"], "allowed buckets"))
        != set(BULK_SOURCES)
        or set(_strings(ledger["attempted_sources"], "attempted sources"))
        != set(BULK_SOURCES)
        or ledger["active_source"] is not None
        or ledger["active_request"] is not None
        or _integer(ledger["active_response_reservation"], "active reservation") != 0
        or ledger["stop_reason"] is not None
        or ledger["resume_supported"] is not False
    ):
        raise CorpusValidationError(
            "real session is incomplete or exceeds approved scope"
        )
    deadline = ledger["session_deadline_monotonic"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
        or deadline <= 0
    ):
        raise CorpusValidationError("invalid real session deadline")
    for name in ("limits", "received_bytes", "transactions"):
        _object(ledger[name], STEP08_LIMITS, "real ledger " + name)
    total = 0
    for name, ceiling in STEP08_LIMITS.items():
        limits = _object(
            ledger["limits"][name],
            {
                "received_bytes",
                "transactions",
                "response_bytes",
                "request_seconds",
                "source_seconds",
            },
            "real source limits",
        )
        for field, value in limits.items():
            _integer(value, field, 1, getattr(ceiling, field))
        received = _integer(
            ledger["received_bytes"][name],
            "received bytes",
            maximum=limits["received_bytes"],
        )
        transactions = _integer(
            ledger["transactions"][name], "transactions", maximum=limits["transactions"]
        )
        if name in sources:
            if transactions != 1 or received != sources[name]["input_bytes"]:
                raise CorpusValidationError(
                    "real complete response differs from charged direct transfer"
                )
        elif received or transactions:
            raise CorpusValidationError("real session charged an unapproved source")
        total += received
    if (
        _integer(ledger["total_received_bytes"], "received total", maximum=39_000_000)
        != total
    ):
        raise CorpusValidationError("real total received bytes differ")


def _bound_real_permission(
    receipt_bytes: bytes, source_id: str, evidence: tuple[SavedEvidence, ...]
) -> dict:
    """Narrow a prospective grant to one receipt without asserting another review."""
    receipt = _json_object(receipt_bytes, "real full receipt")
    selected = next(row for row in receipt["sources"] if row["source_id"] == source_id)
    saved = {item.path: item.payload for item in evidence}

    def evidence_object(reference, label):
        path, digest = _reference(reference, label)
        if path not in saved or _sha(saved[path]) != digest:
            raise CorpusValidationError(f"missing or changed {label} evidence")
        return _json_object(saved[path], label)

    policy_reference = {
        "path": receipt["execution_policy_path"],
        "sha256": receipt["execution_policy_sha256"],
    }
    policy = evidence_object(policy_reference, "execution policy")
    grant = evidence_object(selected["permission"], "source purpose grant")
    _object(
        policy,
        {
            "schema_version",
            "scope",
            "approval",
            "limits",
            "session_claim_path",
            "sources",
        },
        "execution policy",
    )
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["scope"] != "08B-2-three-source-candidate-acquisition"
        or policy["approval"] != receipt["approval"]
    ):
        raise CorpusValidationError(
            "execution policy scope or approval differs from receipt"
        )
    _relative(policy["session_claim_path"])
    expected_limits = {
        "max_attempts": 1,
        "max_redirects": 0,
        "session_seconds": 3600,
        "total_bytes": 39_000_000,
        "transactions": 3,
    }
    limits = _object(policy["limits"], expected_limits, "execution policy limits")
    for key, expected in expected_limits.items():
        if _integer(limits[key], key) != expected:
            raise CorpusValidationError(
                "execution policy exceeds approved direct-request scope"
            )
    source_policies = policy["sources"]
    if not isinstance(source_policies, list) or len(source_policies) != 3:
        raise CorpusValidationError("execution policy source coverage is incomplete")
    source_rows = {row["source_id"]: row for row in receipt["sources"]}
    seen = set()
    for item in source_policies:
        _object(
            item,
            {
                "source_id",
                "url",
                "allowed_redirects",
                "expected_sha256",
                "expected_sha1",
                "expected_bytes",
                "expected_decoded_sha256",
                "max_groups",
                "received_bytes",
                "decoded_bytes",
                "request_seconds",
                "source_seconds",
                "permission_path",
                "permission_sha256",
            },
            "execution source policy",
        )
        key = _text(item["source_id"], "execution source ID")
        if key not in source_rows or key in seen:
            raise CorpusValidationError("execution source policies differ from receipt")
        seen.add(key)
        row = source_rows[key]
        if (
            item["url"] != row["requested_url"]
            or item["allowed_redirects"] != []
            or row["permission"]
            != {"path": item["permission_path"], "sha256": item["permission_sha256"]}
        ):
            raise CorpusValidationError(
                "source route or purpose grant differs from execution policy"
            )
        if row["retained_groups"] > _integer(
            item["max_groups"],
            "policy retained cap",
            1,
            {"opensanctions_un": 300, "ofac_sdn": 12000, "eu_consolidated": 2000}[key],
        ):
            raise CorpusValidationError("retained source groups exceed policy")
        for field in ("received_bytes", "request_seconds", "source_seconds"):
            if (
                _integer(item[field], field, 1)
                != receipt["ledger"]["limits"][key][field]
            ):
                raise CorpusValidationError(
                    "source resource limits differ from execution policy"
                )
        if key == "ofac_sdn":
            if row["decoded_bytes"] > _integer(
                item["decoded_bytes"], "policy decoded cap", 1, 32_000_000
            ):
                raise CorpusValidationError("decoded source exceeds execution policy")
        elif item["decoded_bytes"] is not None:
            raise CorpusValidationError("unexpected decoded cap in execution policy")
        for field in (
            "expected_sha256",
            "expected_sha1",
            "expected_bytes",
            "expected_decoded_sha256",
        ):
            if row["publisher_checksum"][field] != item[field]:
                raise CorpusValidationError(
                    "publisher pins differ from execution policy"
                )
    grant_fields = (_PERMISSION_FIELDS - {"receipt_sha256", "selection_sha256"}) | {
        "grant_kind",
        "exact_url",
        "license",
        "source_role",
        "approval",
        "development_exposed_only",
        "final_eligible",
        "raw_retention_allowed",
        "transient_full_response_allowed",
        "prospective_binding",
    }
    _object(grant, grant_fields, "prospective source purpose grant")
    if (
        grant["grant_kind"] != "prospective_source_purpose"
        or grant["source_id"] != source_id
        or grant["exact_url"] != selected["requested_url"]
        or grant["source_role"] != "sanctions_reference"
        or grant["approval"] != receipt["approval"]
        or grant["development_exposed_only"] is not True
        or grant["final_eligible"] is not False
        or grant["raw_retention_allowed"] is not False
        or grant["transient_full_response_allowed"] is not True
    ):
        raise CorpusValidationError(
            "prospective source grant does not authorize this development candidate"
        )
    _text(grant["license"], "source license rationale")
    binding = _object(
        grant["prospective_binding"],
        {
            "same_policy",
            "require_complete_direct_200",
            "bind_receipt_sha256",
            "bind_selection_sha256",
            "one_derived_grant_per_source",
            "preserve_review_metadata",
            "new_human_review_asserted",
        },
        "prospective binding",
    )
    if any(
        value is not (key != "new_human_review_asserted")
        for key, value in binding.items()
    ):
        raise CorpusValidationError(
            "prospective grant lacks the exact permitted binding operation"
        )
    references = _evidence_references(grant["evidence"], acquisition=False)
    approval_path, approval_hash = _reference(receipt["approval"], "user approval")
    if references.get(approval_path) != approval_hash:
        raise CorpusValidationError(
            "prospective grant omits its user approval evidence"
        )
    for reference in (policy_reference, receipt["approval"], selected["permission"]):
        path, digest = _reference(reference, "bound purpose evidence")
        if path in references and references[path] != digest:
            raise CorpusValidationError("conflicting bound purpose evidence")
        references[path] = digest
    for path, digest in references.items():
        if path not in saved or _sha(saved[path]) != digest:
            raise CorpusValidationError("bound purpose evidence is missing or changed")
    result = {
        key: grant[key]
        for key in _PERMISSION_FIELDS
        - {"receipt_sha256", "selection_sha256", "evidence"}
    }
    result.update(
        {
            "receipt_sha256": _sha(receipt_bytes),
            "selection_sha256": selected["selection_sha256"],
            "evidence": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(references.items())
            ],
        }
    )
    return result


def _recovery_ledger(
    ledger: object,
    sources: dict[str, dict],
    *,
    historical: bool = False,
    interrupted: bool = False,
    continuation: bool = False,
    failed_recovery: bool = False,
) -> None:
    """Check each completed session independently, without resetting old counters."""
    from watchlist.ingest.resource_guard import BULK_SOURCES, STEP08_LIMITS

    _object(
        ledger,
        {
            "schema_version",
            "scope",
            "limits",
            "tranche_bytes",
            "bulk_transaction_limit",
            "allowed_buckets",
            "total_received_bytes",
            "received_bytes",
            "transactions",
            "attempted_sources",
            "active_source",
            "active_request",
            "active_response_reservation",
            "session_deadline_monotonic",
            "stop_reason",
            "resume_supported",
        },
        "completed session ledger",
    )
    allowed = set(BULK_SOURCES) if historical else {"ofac_sdn", "eu_consolidated"}
    ceiling = 39_000_000 if historical else 30_000_000 if continuation else 34_000_000
    if (
        type(ledger["schema_version"]) is not int
        or ledger["schema_version"] != 1
        or ledger["scope"] != "step08-single-session-no-resume"
        or _integer(ledger["tranche_bytes"], "session limit") != ceiling
        or _integer(ledger["bulk_transaction_limit"], "request limit") != 3
        or set(_strings(ledger["allowed_buckets"], "allowed buckets")) != allowed
        or set(_strings(ledger["attempted_sources"], "attempted sources"))
        != set(sources)
        or (
            not interrupted
            and ledger["active_source"] != ("ofac_sdn" if failed_recovery else None)
        )
        or (not interrupted and ledger["active_request"] is not None)
        or (
            not interrupted
            and _integer(ledger["active_response_reservation"], "active reservation")
            != 0
        )
        or ledger["stop_reason"] is not None
        or ledger["resume_supported"] is not False
    ):
        raise CorpusValidationError("completed session counters or state differ")
    deadline = ledger["session_deadline_monotonic"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
        or deadline <= 0
    ):
        raise CorpusValidationError("invalid completed session deadline")
    for field in ("limits", "received_bytes", "transactions"):
        _object(ledger[field], STEP08_LIMITS, "session " + field)
    total = transactions = 0
    for name, limit in STEP08_LIMITS.items():
        limits = _object(
            ledger["limits"][name],
            {
                "received_bytes",
                "response_bytes",
                "transactions",
                "request_seconds",
                "source_seconds",
            },
            "source limits",
        )
        for field, value in limits.items():
            _integer(value, field, 1, getattr(limit, field))
        received = _integer(
            ledger["received_bytes"][name],
            "received bytes",
            maximum=limits["received_bytes"],
        )
        requests = _integer(
            ledger["transactions"][name], "requests", maximum=limits["transactions"]
        )
        if name in sources:
            row = sources[name]
            if (
                received != row["bytes_received"]
                or requests != row["transaction_count"]
            ):
                raise CorpusValidationError("source and session accounting differ")
        elif received or requests:
            raise CorpusValidationError(
                "unapproved source activity in completed session"
            )
        total += received
        transactions += requests
    if (
        _integer(ledger["total_received_bytes"], "received total", maximum=ceiling)
        != total
        or transactions > 3
    ):
        raise CorpusValidationError("completed session totals differ")
    if interrupted:
        request = _object(
            ledger["active_request"],
            {"bucket", "deadline", "sequence"},
            "interrupted request",
        )
        request_deadline = request["deadline"]
        reservation = _integer(
            ledger["active_response_reservation"], "outstanding response reservation"
        )
        if (
            not historical
            or ledger["active_source"] != "eu_consolidated"
            or request["bucket"] != "eu_consolidated"
            or _integer(request["sequence"], "request sequence") != 3
            or isinstance(request_deadline, bool)
            or not isinstance(request_deadline, (int, float))
            or not math.isfinite(request_deadline)
            or not 0 < request_deadline <= deadline
            or total + reservation > ceiling
            or ledger["received_bytes"]["eu_consolidated"] + reservation > 30_000_000
        ):
            raise CorpusValidationError(
                "interrupted session reservation or request differs"
            )


def _recovery_transactions(row: dict, *, first_sequence: int) -> int:
    """Bind a complete response to bounded requests and query-free redirect evidence."""
    from watchlist.ingest.full_acquire import LIVE_URLS, RECOVERY_OFAC_REDIRECT

    source_id = row["source_id"]
    transactions = row["transactions"]
    maximum = 2 if source_id == "ofac_sdn" else 1
    if not isinstance(transactions, list) or not 1 <= len(transactions) <= maximum:
        raise CorpusValidationError("invalid recovery transaction count")
    total = 0
    for index, tx in enumerate(transactions):
        _object(
            tx,
            {
                "sequence",
                "request_number",
                "requested_url",
                "final_url",
                "signing_query_present",
                "http_status",
                "declared_body_bytes",
                "complete",
                "bytes_received",
                "body_sha256",
                "outcome",
                "stop_reason",
                "redirect_target",
                "unresolved_response_reservation_bytes",
            },
            "recovery transaction",
        )
        final = index == len(transactions) - 1
        route = LIVE_URLS[source_id] if index == 0 else RECOVERY_OFAC_REDIRECT
        if (
            _integer(tx["sequence"], "transaction sequence", 1)
            != first_sequence + index
            or _integer(tx["request_number"], "source request number", 1) != index + 1
            or tx["requested_url"] != route
            or tx["final_url"] != route
            or type(tx["signing_query_present"]) is not bool
            or (index == 0 and tx["signing_query_present"])
            or tx["complete"] is not True
            or tx["stop_reason"] is not None
            or _integer(
                tx["unresolved_response_reservation_bytes"], "unresolved reservation"
            )
            != 0
        ):
            raise CorpusValidationError(
                "recovery transaction is incomplete or has an unapproved route"
            )
        count = _integer(
            tx["bytes_received"],
            "transaction body bytes",
            maximum=4_000_000 if source_id == "ofac_sdn" else 30_000_000,
        )
        _digest(tx["body_sha256"], "transaction body")
        declared = tx["declared_body_bytes"]
        if declared is not None and _integer(declared, "declared bytes") != count:
            raise CorpusValidationError("completed transaction length differs")
        if final:
            if (
                _integer(tx["http_status"], "HTTP status") != 200
                or tx["outcome"] != "complete_200"
                or tx["redirect_target"] is not None
                or _integer(declared, "required successful Content-Length", 1) != count
                or count != row["input_bytes"]
                or tx["body_sha256"] != row["input_sha256"]
                or row["final_url"] != route
            ):
                raise CorpusValidationError(
                    "recovery lacks a complete length-checked 200 body"
                )
        elif (
            source_id != "ofac_sdn"
            or _integer(tx["http_status"], "redirect status")
            not in {301, 302, 303, 307, 308}
            or tx["outcome"] != "approved_redirect"
            or tx["redirect_target"] != RECOVERY_OFAC_REDIRECT
        ):
            raise CorpusValidationError("recovery redirect evidence is not approved")
        total += count
    if (
        row["requested_url"] != LIVE_URLS[source_id]
        or _integer(
            row["bytes_received"],
            "source received bytes",
            maximum=4_000_000 if source_id == "ofac_sdn" else 30_000_000,
        )
        != total
        or _integer(row["transaction_count"], "source requests") != len(transactions)
    ):
        raise CorpusValidationError("recovery source differs from its transactions")
    return len(transactions)


def _recovery_receipt(
    receipt: dict, selection: bytes, source_id: object
) -> tuple[dict, dict[str, str]]:
    """Admit a new complete assembly while preserving its interrupted predecessor."""
    return _completed_session_receipt(receipt, selection, source_id, continuation=False)


def _completed_session_receipt(
    receipt: dict, selection: bytes, source_id: object, *, continuation: bool
) -> tuple[dict, dict[str, str]]:
    """Share complete-source checks while retaining each actual session scope."""
    _object(
        receipt,
        {
            "schema_version",
            "scope",
            "policy_sha256",
            "execution_policy_path",
            "execution_policy_sha256",
            "approval",
            "session_claim",
            "permission_grants",
            "evidence",
            "status",
            "live_authorized",
            "independent_custody_verified",
            "selection_use",
            "sources",
            "resume_supported",
            "total_body_limit",
            "prior_session",
            "prior_session_accounting",
            "recovery_accounting",
            "started_at",
            "finished_at",
            "ledger",
            "peak_sampled_rss_bytes",
            "rss_enforcement",
        }
        | ({"continuation", "tls_preflight"} if continuation else set()),
        "recovery receipt",
    )
    source_ids = {"opensanctions_un", "ofac_sdn", "eu_consolidated"}
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["scope"] != (CONTINUATION_SCOPE if continuation else RECOVERY_SCOPE)
        or receipt["status"] != "passed"
        or receipt["live_authorized"] is not True
        or receipt["independent_custody_verified"] is not False
        or receipt["selection_use"] != "shared-development-candidates-only"
        or receipt["resume_supported"] is not False
        or not isinstance(source_id, str)
        or source_id not in source_ids
        or _integer(receipt["total_body_limit"], "recovery body limit")
        != (30_000_000 if continuation else 34_000_000)
        or _digest(receipt["policy_sha256"], "recovery policy")
        != _digest(receipt["execution_policy_sha256"], "execution policy")
    ):
        raise CorpusValidationError(
            "recovery is not a complete approved development assembly"
        )
    try:
        start, finish = (
            datetime.fromisoformat(_text(receipt[name], name, 128))
            for name in ("started_at", "finished_at")
        )
        if (
            start.tzinfo is None
            or finish.tzinfo is None
            or not 0 <= (finish - start).total_seconds() <= 3600
        ):
            raise ValueError
    except ValueError as exc:
        raise CorpusValidationError("invalid recovery time window") from exc
    _integer(receipt["peak_sampled_rss_bytes"], "sampled RSS", 1, 2 * 1024**3)
    _text(receipt["rss_enforcement"], "RSS enforcement")
    prior = _object(
        receipt["prior_session"],
        {
            "source_id",
            "policy",
            "claim",
            "interruption_assessment",
            "completed_journal",
            "selection",
            "permission",
            "recovery_permission",
        },
        "prior session",
    )
    if prior["source_id"] != "opensanctions_un":
        raise CorpusValidationError(
            "only the completed OpenSanctions source may be reused"
        )
    references = _evidence_references(receipt["evidence"], acquisition=False)
    required = [
        receipt["approval"],
        receipt["session_claim"],
        {
            "path": receipt["execution_policy_path"],
            "sha256": receipt["execution_policy_sha256"],
        },
        *(value for key, value in prior.items() if key != "source_id"),
    ]
    if continuation:
        binding = _continuation_binding(receipt["continuation"])
        required.extend(
            binding[key] for key in ("policy", "receipt", "claim", "tls_ca_bundle")
        )
        tls = receipt["tls_preflight"]
        if tls is not None:
            _object(
                tls,
                {
                    "ca_bundle",
                    "ca_count",
                    "certificate_chain_verification",
                    "client",
                    "hostname_verification",
                },
                "saved TLS preflight",
            )
            if (
                tls["ca_bundle"] != binding["tls_ca_bundle"]
                or tls["certificate_chain_verification"] is not True
                or tls["hostname_verification"] is not True
                or tls["client"]
                != "HTTPTransport/_PinnedHTTPSConnection/ssl.create_default_context"
            ):
                raise CorpusValidationError("continuation TLS evidence differs")
            _integer(tls["ca_count"], "saved trusted CA count", 1)
    grants = receipt["permission_grants"]
    if not isinstance(grants, list) or len(grants) != 3:
        raise CorpusValidationError("recovery requires three purpose grants")
    by_grant = {}
    for grant in grants:
        _object(grant, {"source_id", "path", "sha256"}, "recovery grant reference")
        key = _text(grant["source_id"], "grant source")
        if key not in source_ids or key in by_grant:
            raise CorpusValidationError("invalid recovery grant coverage")
        by_grant[key] = {"path": grant["path"], "sha256": grant["sha256"]}
        required.append(by_grant[key])
    for reference in required:
        path, digest = _reference(reference, "recovery evidence")
        if references.get(path) != digest:
            raise CorpusValidationError("missing or conflicting recovery evidence")
    if by_grant["opensanctions_un"] != prior["recovery_permission"]:
        raise CorpusValidationError("reused source needs its new recovery permission")
    rows = receipt["sources"]
    if not isinstance(rows, list) or len(rows) != 3:
        raise CorpusValidationError("recovery requires three completed selections")
    indexed = {}
    for row in rows:
        _object(
            row,
            _FULL_SOURCE_FIELDS
            | {"acquisition_origin", "origin_evidence", "transactions"},
            "recovered source",
        )
        key = _text(row["source_id"], "recovered source ID")
        if key not in source_ids or key in indexed:
            raise CorpusValidationError("duplicate or unsupported recovered source")
        if (
            row["status"] != "passed"
            or row["complete"] is not True
            or _integer(row["http_status"], "source HTTP status") != 200
            or row["selection_path"] != f"{key}.jsonl"
            or row["permission"] != by_grant[key]
        ):
            raise CorpusValidationError(
                "recovery source lacks complete evidence or permission"
            )
        _complete_source_content(row, recovery=key != "opensanctions_un")
        if key == "opensanctions_un":
            origin = _object(
                row["origin_evidence"],
                {"completed_journal", "source_row"},
                "completed source origin",
            )
            original = _object(
                origin["source_row"], _FULL_SOURCE_FIELDS, "original completed source"
            )
            preserved = {
                key: value for key, value in row.items() if key in _FULL_SOURCE_FIELDS
            }
            preserved["permission"] = prior["permission"]
            if (
                row["acquisition_origin"] != "reused_completed_source"
                or row["transactions"] != []
                or _integer(row["transaction_count"], "historical requests") != 1
                or _https(row["requested_url"], "historical requested URL")
                != _https(row["final_url"], "historical final URL")
                or origin["completed_journal"] != prior["completed_journal"]
                or original != preserved
                or (continuation and _canonical(original) != _canonical(preserved))
                or row["selection_sha256"] != prior["selection"]["sha256"]
            ):
                raise CorpusValidationError(
                    "recovery rewrites completed historical evidence"
                )
        elif (
            row["acquisition_origin"] != "recovery_session"
            or row["origin_evidence"] is not None
        ):
            raise CorpusValidationError(
                "new source incorrectly claims historical completion"
            )
        indexed[key] = row
    sequence = 1
    for key in ("ofac_sdn", "eu_consolidated"):
        sequence += _recovery_transactions(indexed[key], first_sequence=sequence)
    _recovery_ledger(
        receipt["ledger"],
        {key: indexed[key] for key in ("ofac_sdn", "eu_consolidated")},
        continuation=continuation,
    )
    accounting = _object(
        receipt["prior_session_accounting"],
        {
            "persisted_received_body_bytes_lower_bound",
            "conservative_active_response_reservation_bytes",
            "received_plus_reservation_bytes",
        },
        "prior accounting",
    )
    for value in accounting.values():
        _integer(value, "prior body accounting", maximum=39_000_000)
    if (
        accounting["received_plus_reservation_bytes"]
        != accounting["persisted_received_body_bytes_lower_bound"]
        + accounting["conservative_active_response_reservation_bytes"]
    ):
        raise CorpusValidationError("prior conservative accounting differs")
    current = _object(
        receipt["recovery_accounting"],
        {
            "received_body_bytes",
            "unresolved_response_reservation_bytes",
            "received_plus_reservation_bytes",
            "combined_prior_plus_recovery_reserved_bytes",
        }
        | (
            {
                "carried_prior_recovery_reservation_bytes",
                "cumulative_recovery_accounted_bytes",
                "cumulative_recovery_transactions",
            }
            if continuation
            else set()
        ),
        "recovery accounting",
    )
    total = receipt["ledger"]["total_received_bytes"]
    expected = {
        "received_body_bytes": total,
        "unresolved_response_reservation_bytes": 0,
        "received_plus_reservation_bytes": total,
        "combined_prior_plus_recovery_reserved_bytes": accounting[
            "received_plus_reservation_bytes"
        ]
        + total,
    }
    if continuation:
        carried = binding["carried_reservation_bytes"]
        expected["combined_prior_plus_recovery_reserved_bytes"] += carried
        expected.update(
            carried_prior_recovery_reservation_bytes=carried,
            cumulative_recovery_accounted_bytes=carried + total,
            cumulative_recovery_transactions=binding["prior_charged_transactions"]
            + sum(receipt["ledger"]["transactions"].values()),
        )
        if (
            expected["cumulative_recovery_accounted_bytes"]
            > binding["recovery_ceiling_bytes"]
            or expected["cumulative_recovery_transactions"]
            > binding["cumulative_transaction_limit"]
        ):
            raise CorpusValidationError(
                "continuation exceeds cumulative recovery authority"
            )
    if any(_integer(current[key], key) != value for key, value in expected.items()):
        raise CorpusValidationError(
            "recovery accounting resets or changes prior charges"
        )
    selected = indexed[source_id]
    if selected["selection_sha256"] != _sha(selection) or selected[
        "selection_bytes"
    ] != len(selection):
        raise CorpusValidationError("recovery receipt does not bind saved selection")
    return {**selected, "role": "sanctions_reference"}, references


def _bound_recovery_permission(
    receipt_bytes: bytes, source_id: str, evidence: tuple[SavedEvidence, ...]
) -> dict:
    """Retain new recovery authority and the unchanged evidence of both sessions."""
    return _bound_completed_session_permission(
        receipt_bytes, source_id, evidence, continuation=False
    )


def _bound_completed_session_permission(
    receipt_bytes: bytes,
    source_id: str,
    evidence: tuple[SavedEvidence, ...],
    *,
    continuation: bool,
) -> dict:
    """Verify inherited permission without changing grant or receipt bytes."""
    from watchlist.ingest.full_acquire import (
        CONTINUATION_LIMITS,
        CONTINUATION_POLICY_SCOPE,
        FullAcquisitionError,
        LIVE_URLS,
        RECOVERY_LIMITS,
        RECOVERY_OFAC_REDIRECT,
        RECOVERY_POLICY_SCOPE,
        _BINDING,
        _GRANT_FIELDS,
        _SOURCE_POLICY_FIELDS,
        _recovery_permission,
    )

    receipt = _json_object(receipt_bytes, "recovery receipt")
    saved = {item.path: item.payload for item in evidence}

    def payload(reference, label):
        path, digest = _reference(reference, label)
        if path not in saved or _sha(saved[path]) != digest:
            raise CorpusValidationError(f"missing or changed {label}")
        return saved[path]

    def document(reference, label):
        return _json_object(payload(reference, label), label)

    policy_reference = {
        "path": receipt["execution_policy_path"],
        "sha256": receipt["execution_policy_sha256"],
    }
    policy = document(policy_reference, "recovery execution policy")
    _object(
        policy,
        {
            "schema_version",
            "scope",
            "approval",
            "limits",
            "sources",
            "session_claim_path",
            "reuse_completed_source",
        }
        | ({"continuation"} if continuation else set()),
        "recovery policy",
    )
    prior = receipt["prior_session"]
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["scope"]
        != (CONTINUATION_POLICY_SCOPE if continuation else RECOVERY_POLICY_SCOPE)
        or policy["approval"] != receipt["approval"]
        or policy["reuse_completed_source"] != prior
    ):
        raise CorpusValidationError("recovery policy does not authorize this assembly")
    expected_limits = CONTINUATION_LIMITS if continuation else RECOVERY_LIMITS
    _object(policy["limits"], expected_limits, "recovery limits")
    if any(
        _integer(policy["limits"][key], key) != value
        for key, value in expected_limits.items()
    ):
        raise CorpusValidationError("recovery policy limits exceed authorization")
    rows = {row["source_id"]: row for row in receipt["sources"]}
    policies = policy["sources"]
    if (
        not isinstance(policies, list)
        or len(policies) != 2
        or [item.get("source_id") for item in policies if isinstance(item, dict)]
        != ["ofac_sdn", "eu_consolidated"]
    ):
        raise CorpusValidationError("recovery policy source order differs")
    for item in policies:
        _object(
            item,
            _SOURCE_POLICY_FIELDS
            | {"transactions", "content_length_required", "expected_decoded_bytes"},
            "recovery source policy",
        )
        key = item["source_id"]
        row = rows[key]
        if (
            item["url"] != LIVE_URLS[key]
            or item["url"] != row["requested_url"]
            or item["content_length_required"] is not True
            or item["allowed_redirects"]
            != ([RECOVERY_OFAC_REDIRECT] if key == "ofac_sdn" else [])
            or row["permission"]
            != {"path": item["permission_path"], "sha256": item["permission_sha256"]}
        ):
            raise CorpusValidationError(
                "recovery source route, size gate or permission differs"
            )
        expected = {
            "received_bytes": 4_000_000 if key == "ofac_sdn" else 30_000_000,
            "transactions": 2 if key == "ofac_sdn" else 1,
            "request_seconds": 30 if key == "ofac_sdn" else 180,
            "source_seconds": 120 if key == "ofac_sdn" else 240,
            "max_groups": 12000 if key == "ofac_sdn" else 2000,
        }
        for field, value in expected.items():
            if _integer(item[field], field) != value or (
                field != "max_groups"
                and receipt["ledger"]["limits"][key][field] != value
            ):
                raise CorpusValidationError("recovery source limits differ")
        for field in (
            "expected_sha256",
            "expected_sha1",
            "expected_bytes",
            "expected_decoded_sha256",
            "expected_decoded_bytes",
        ):
            if item[field] != row["publisher_checksum"][field]:
                raise CorpusValidationError(
                    "recovery publisher pins differ from policy"
                )
        if key == "ofac_sdn":
            if _integer(item["decoded_bytes"], "decoded cap") != 32_000_000:
                raise CorpusValidationError("recovery decoded cap differs")
            _integer(
                item["expected_decoded_bytes"], "expected decoded bytes", 1, 32_000_000
            )
            _integer(item["expected_bytes"], "expected compressed bytes", 1, 4_000_000)
            _digest(item["expected_decoded_sha256"], "expected decoded body")
        elif any(
            item[field] is not None
            for field in (
                "decoded_bytes",
                "expected_sha256",
                "expected_sha1",
                "expected_bytes",
                "expected_decoded_sha256",
                "expected_decoded_bytes",
            )
        ):
            raise CorpusValidationError("unapproved EU publisher pins")
    original_policy = document(prior["policy"], "original policy")
    _object(
        original_policy,
        {
            "schema_version",
            "scope",
            "approval",
            "limits",
            "sources",
            "session_claim_path",
        },
        "original execution policy",
    )
    old_limits = {
        "max_attempts": 1,
        "max_redirects": 0,
        "session_seconds": 3600,
        "total_bytes": 39_000_000,
        "transactions": 3,
    }
    _object(original_policy["limits"], old_limits, "original execution limits")
    if (
        type(original_policy["schema_version"]) is not int
        or original_policy["schema_version"] != 1
        or any(
            _integer(original_policy["limits"][key], key) != value
            for key, value in old_limits.items()
        )
    ):
        raise CorpusValidationError("original execution policy scope changed")
    claim = document(prior["claim"], "original claim")
    current_claim = document(receipt["session_claim"], "recovery claim")
    claim_fields = {
        "schema_version",
        "scope",
        "policy_sha256",
        "output",
        "claimed_at",
        "maximum_reserved_body_bytes",
        "maximum_transactions",
        "resume_supported",
    }
    _object(claim, claim_fields, "original claim")
    _object(
        current_claim,
        claim_fields | {"prior_claim"} | ({"continuation"} if continuation else set()),
        "recovery claim",
    )
    for value, limit, scope in (
        (claim, 39_000_000, "08B-2-development-candidate-acquisition-v1"),
        (
            current_claim,
            30_000_000 if continuation else 34_000_000,
            CONTINUATION_SCOPE if continuation else RECOVERY_SCOPE,
        ),
    ):
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["scope"] != scope
            or value["resume_supported"] is not False
            or _integer(value["maximum_reserved_body_bytes"], "claim byte limit")
            != limit
            or _integer(value["maximum_transactions"], "claim transaction limit") != 3
            or not Path(_text(value["output"], "claim output")).is_absolute()
        ):
            raise CorpusValidationError(
                "session claim is incomplete or has wider authority"
            )
    if (
        claim["policy_sha256"] != prior["policy"]["sha256"]
        or original_policy.get("scope") != "08B-2-three-source-candidate-acquisition"
        or original_policy.get("session_claim_path") != prior["claim"]["path"]
        or current_claim["policy_sha256"] != receipt["policy_sha256"]
        or current_claim["prior_claim"] != prior["claim"]
        or _relative(policy["session_claim_path"]) != receipt["session_claim"]["path"]
        or receipt["session_claim"]["path"] == prior["claim"]["path"]
        or current_claim["output"] == claim["output"]
    ):
        raise CorpusValidationError(
            "recovery reuses or changes a consumed session claim"
        )
    try:
        old_time, new_time, started = (
            datetime.fromisoformat(value)
            for value in (
                claim["claimed_at"],
                current_claim["claimed_at"],
                receipt["started_at"],
            )
        )
        if (
            any(value.tzinfo is None for value in (old_time, new_time, started))
            or not old_time < new_time <= started
            or (started - new_time).total_seconds() > 3600
        ):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise CorpusValidationError(
            "recovery claim times do not identify a new session"
        ) from exc
    original = rows["opensanctions_un"]["origin_evidence"]["source_row"]
    journal = document(prior["completed_journal"], "completed source journal")
    _object(journal, {"policy_sha256", "ledger", "sources"}, "completed source journal")
    if journal["policy_sha256"] != prior["policy"]["sha256"] or journal["sources"] != [
        original
    ]:
        raise CorpusValidationError(
            "completed source journal belongs to different evidence"
        )
    _recovery_ledger(journal["ledger"], {"opensanctions_un": original}, historical=True)
    selection_bytes = payload(prior["selection"], "original selection")
    if (
        len(selection_bytes) != original["selection_bytes"]
        or _sha(selection_bytes) != original["selection_sha256"]
    ):
        raise CorpusValidationError("original completed selection differs")
    original_parent = Path(prior["selection"]["path"]).parent
    if (
        Path(prior["completed_journal"]["path"]).parent != original_parent
        or Path(prior["policy"]["path"]) != original_parent / "execution-policy.json"
        or not Path(claim["output"])
        .as_posix()
        .endswith("/" + original_parent.as_posix())
    ):
        raise CorpusValidationError(
            "completed source references cross original sessions"
        )
    assessment = document(prior["interruption_assessment"], "interruption assessment")

    def pair(value):
        if not isinstance(value, dict):
            raise CorpusValidationError("invalid assessment evidence")
        reference = {key: value.get(key) for key in ("path", "sha256")}
        _reference(reference, "assessment reference")
        return reference

    try:
        if (
            not isinstance(assessment["sources"], list)
            or len(assessment["sources"]) != 3
        ):
            raise CorpusValidationError("interruption source history is incomplete")
        states = {
            item["source_id"]: item["persisted_row"] for item in assessment["sources"]
        }
        if (
            assessment["scope"] != "08B-2-offline-interruption-assessment-v1"
            or assessment["artifact_kind"]
            != "interruption_assessment_not_acquisition_receipt"
            or assessment["assessment_status"] != "persisted_evidence_consistent"
            or pair(assessment["claim"]["evidence"]) != prior["claim"]
            or assessment["claim"]["persisted_value"] != claim
            or assessment["claim"]["session_consumed"] is not True
            or pair(assessment["policy"]["execution_policy_copy"]) != prior["policy"]
            or assessment["artifact_state"]["final_acquisition_receipt_exists"]
            is not False
            or assessment["artifact_state"]["full_candidate_corpus_accepted"]
            is not False
            or set(states) != {"opensanctions_un", "ofac_sdn", "eu_consolidated"}
            or states["opensanctions_un"] != original
            or states["ofac_sdn"]["status"] != "failed"
            or states["eu_consolidated"]["status"] != "running"
            or states["eu_consolidated"]["complete"] is not False
            or assessment["accounting"]["remaining_authorized_transactions"] != 0
        ):
            raise CorpusValidationError(
                "recovery rewrites the interrupted session history"
            )
        last = document(
            pair(assessment["journals"]["last"]), "last interrupted journal"
        )
        if (
            last["policy_sha256"] != prior["policy"]["sha256"]
            or last["ledger"] != assessment["journals"]["last_ledger"]
            or len(last["sources"]) != 3
            or {row["source_id"]: row for row in last["sources"]} != states
            or last["ledger"]["session_deadline_monotonic"]
            != journal["ledger"]["session_deadline_monotonic"]
        ):
            raise CorpusValidationError(
                "last interrupted journal and assessment differ"
            )
        _recovery_ledger(last["ledger"], states, historical=True, interrupted=True)
        prior_accounting = receipt["prior_session_accounting"]
        if (
            any(
                assessment["accounting"][key] != value
                for key, value in prior_accounting.items()
            )
            or prior_accounting["persisted_received_body_bytes_lower_bound"]
            != last["ledger"]["total_received_bytes"]
            or prior_accounting["conservative_active_response_reservation_bytes"]
            != last["ledger"]["active_response_reservation"]
            or sum(last["ledger"]["transactions"].values()) != 3
        ):
            raise CorpusValidationError(
                "recovery changes consumed historical accounting"
            )
    except (KeyError, TypeError) as exc:
        raise CorpusValidationError("interruption assessment is incomplete") from exc
    original_grant = document(prior["permission"], "original source permission")
    _object(original_grant, _GRANT_FIELDS, "original source purpose")
    original_sources = original_policy.get("sources")
    if not isinstance(original_sources, list):
        raise CorpusValidationError("original source policy is missing")
    old_policies = [
        item
        for item in original_sources
        if isinstance(item, dict) and item.get("source_id") == "opensanctions_un"
    ]
    if (
        len(old_policies) != 1
        or {
            "path": old_policies[0].get("permission_path"),
            "sha256": old_policies[0].get("permission_sha256"),
        }
        != prior["permission"]
        or old_policies[0].get("url") != original["requested_url"]
    ):
        raise CorpusValidationError("original completed source permission differs")
    for field in (
        "expected_sha256",
        "expected_sha1",
        "expected_bytes",
        "expected_decoded_sha256",
    ):
        if old_policies[0].get(field) != original["publisher_checksum"][field]:
            raise CorpusValidationError(
                "original publisher pins differ from completed evidence"
            )
    if (
        original_grant.get("status") != "approved"
        or original_grant.get("purpose") != PURPOSE
        or original_grant.get("source_id") != "opensanctions_un"
        or original_grant.get("approval") != original_policy.get("approval")
        or original_grant.get("exact_url") != original["requested_url"]
        or original_grant["prospective_binding"] != _BINDING
        or original_grant["development_exposed_only"] is not True
        or original_grant["final_eligible"] is not False
    ):
        raise CorpusValidationError("original source purpose is not approved")
    original_references = _evidence_references(
        original_grant.get("evidence"), acquisition=False
    )
    old_approval_path, old_approval_hash = _reference(
        original_policy.get("approval"), "original approval"
    )
    if original_references.get(old_approval_path) != old_approval_hash:
        raise CorpusValidationError(
            "original source permission lacks its approval evidence"
        )
    for path, digest in original_references.items():
        payload({"path": path, "sha256": digest}, "original purpose evidence")
    grants = {}
    for key, row in rows.items():
        grant = document(row["permission"], "new recovery purpose permission")
        try:
            _recovery_permission(
                grant, key, receipt["approval"], reused=key == "opensanctions_un"
            )
        except FullAcquisitionError as exc:
            raise CorpusValidationError(
                "unapproved recovery purpose permission"
            ) from exc
        references = _evidence_references(grant["evidence"], acquisition=False)
        if references.get(receipt["approval"]["path"]) != receipt["approval"]["sha256"]:
            raise CorpusValidationError("recovery purpose omits new approval")
        for path, digest in references.items():
            payload({"path": path, "sha256": digest}, "purpose evidence")
        grants[key] = grant
    recovered_grant = grants["opensanctions_un"]
    expected_binding = {
        "original_policy": prior["policy"],
        "original_claim": prior["claim"],
        "interruption_assessment": prior["interruption_assessment"],
        "completed_journal": prior["completed_journal"],
        "selection": prior["selection"],
        "original_permission": prior["permission"],
        "original_final_receipt_absent": True,
        "original_session_remains_interrupted": True,
        "cross_session_manifest_required": True,
    }
    if recovered_grant["recovery_binding"] != expected_binding:
        raise CorpusValidationError(
            "completed source lacks exact new recovery authority"
        )
    for field in (
        "review_id",
        "reviewer",
        "reviewed_at",
        "operations",
        "record_fields",
        "alias_fields",
        "entity_types",
        "name_fields",
    ):
        if recovered_grant[field] != original_grant.get(field):
            raise CorpusValidationError(
                "recovery changes original review metadata or rights"
            )
    if not set(
        _strings(original_grant.get("conditions"), "original conditions", minimum=1)
    ) <= set(recovered_grant["conditions"]):
        raise CorpusValidationError("recovery removes original source conditions")
    if continuation:
        _continuation_lineage(receipt, policy, current_claim, evidence)
    grant = grants[source_id]
    references = _evidence_references(grant["evidence"], acquisition=False)
    for reference in (policy_reference, rows[source_id]["permission"]):
        path, digest = _reference(reference, "bound recovery evidence")
        if path in references and references[path] != digest:
            raise CorpusValidationError("conflicting recovery purpose evidence")
        references[path] = digest
    result = {
        key: grant[key]
        for key in _PERMISSION_FIELDS
        - {"receipt_sha256", "selection_sha256", "evidence"}
    }
    result.update(
        receipt_sha256=_sha(receipt_bytes),
        selection_sha256=rows[source_id]["selection_sha256"],
        evidence=[
            {"path": path, "sha256": digest}
            for path, digest in sorted(references.items())
        ],
    )
    return result


def _continuation_binding(value: object) -> dict:
    """Require the one approved failed-recovery continuation, with no release right."""
    binding = _object(
        value,
        {
            "policy",
            "receipt",
            "claim",
            "carried_reservation_bytes",
            "prior_charged_transactions",
            "cumulative_transaction_limit",
            "recovery_ceiling_bytes",
            "tls_ca_bundle",
            "release_authorized",
        },
        "continuation binding",
    )
    for key, expected in {
        "carried_reservation_bytes": 4_000_000,
        "prior_charged_transactions": 1,
        "cumulative_transaction_limit": 4,
        "recovery_ceiling_bytes": 34_000_000,
    }.items():
        if _integer(binding[key], key) != expected:
            raise CorpusValidationError(
                "continuation resets prior authority or reservation"
            )
    if binding["release_authorized"] is not False:
        raise CorpusValidationError("continuation release is not authorized")
    for key in ("policy", "receipt", "claim", "tls_ca_bundle"):
        _reference(binding[key], "continuation " + key)
    return binding


def _continuation_lineage(
    receipt: dict,
    policy: dict,
    current_claim: dict,
    evidence: tuple[SavedEvidence, ...],
) -> None:
    """Check the failed middle session as failed, preserving all charged activity.

    This uses retained bytes only. Neither a claim nor a receipt is rewritten into
    a successful recovery, and the prior reservation is never refunded.
    """
    from watchlist.ingest.full_acquire import (
        FullAcquisitionError,
        LIVE_URLS,
        RECOVERY_LIMITS,
        RECOVERY_POLICY_SCOPE,
        _recovery_permission,
    )

    saved = {item.path: item for item in evidence}

    def document(reference: object, label: str) -> dict:
        path, expected = _reference(reference, label)
        item = saved.get(path)
        if item is None or _sha(item.payload) != expected:
            raise CorpusValidationError("missing or changed " + label)
        return _json_object(item.payload, label)

    binding = _continuation_binding(receipt["continuation"])
    if policy["continuation"] != binding or current_claim["continuation"] != binding:
        raise CorpusValidationError("continuation receipt, policy and claim differ")
    old_policy = document(binding["policy"], "failed recovery policy")
    _object(old_policy, set(policy) - {"continuation"}, "failed recovery policy")
    if (
        type(old_policy["schema_version"]) is not int
        or old_policy["schema_version"] != 1
        or old_policy["scope"] != RECOVERY_POLICY_SCOPE
        or old_policy["limits"] != RECOVERY_LIMITS
        or any(type(value) is not int for value in old_policy["limits"].values())
        or old_policy["session_claim_path"] != binding["claim"]["path"]
        or old_policy["session_claim_path"] == policy["session_claim_path"]
    ):
        raise CorpusValidationError("continuation failed recovery policy differs")
    _reference(old_policy["approval"], "failed recovery approval")
    document(old_policy["approval"], "failed recovery approval")
    old_reuse = old_policy["reuse_completed_source"]
    _object(old_reuse, set(policy["reuse_completed_source"]), "failed recovery reuse")
    if _canonical(
        {key: value for key, value in old_reuse.items() if key != "recovery_permission"}
    ) != _canonical(
        {
            key: value
            for key, value in policy["reuse_completed_source"].items()
            if key != "recovery_permission"
        }
    ):
        raise CorpusValidationError("continuation changes original reused source")
    old_sources = old_policy["sources"]
    if not isinstance(old_sources, list) or len(old_sources) != 2:
        raise CorpusValidationError("failed recovery source coverage differs")
    old_grants = {"opensanctions_un": old_reuse["recovery_permission"]}
    for old, new in zip(old_sources, policy["sources"], strict=True):
        _object(old, set(new), "failed recovery source policy")
        if _canonical(
            {
                key: value
                for key, value in old.items()
                if key not in {"permission_path", "permission_sha256"}
            }
        ) != _canonical(
            {
                key: value
                for key, value in new.items()
                if key not in {"permission_path", "permission_sha256"}
            }
        ):
            raise CorpusValidationError(
                "continuation expands failed recovery source contract"
            )
        old_grants[old["source_id"]] = {
            "path": old["permission_path"],
            "sha256": old["permission_sha256"],
        }
    for row in receipt["sources"]:
        source_id = row["source_id"]
        old_grant = document(old_grants[source_id], "failed recovery grant")
        new_grant = document(row["permission"], "continuation grant")
        try:
            _recovery_permission(
                old_grant,
                source_id,
                old_policy["approval"],
                reused=source_id == "opensanctions_un",
            )
        except FullAcquisitionError as exc:
            raise CorpusValidationError(
                "invalid inherited failed recovery grant"
            ) from exc
        if {
            key: value
            for key, value in old_grant.items()
            if key not in {"approval", "evidence"}
        } != {
            key: value
            for key, value in new_grant.items()
            if key not in {"approval", "evidence"}
        }:
            raise CorpusValidationError(
                "continuation changes inherited rights or review metadata"
            )
        old_refs = _evidence_references(old_grant["evidence"], acquisition=False)
        new_refs = _evidence_references(new_grant["evidence"], acquisition=False)
        if old_refs.get(old_policy["approval"]["path"]) != old_policy["approval"][
            "sha256"
        ] or any(
            new_refs.get(path) != digest
            or path not in saved
            or saved[path].sha256 != digest
            for path, digest in old_refs.items()
        ):
            raise CorpusValidationError(
                "continuation omits inherited permission evidence"
            )

    previous = document(binding["receipt"], "failed recovery receipt")
    _object(
        previous,
        (set(receipt) - {"continuation", "tls_preflight"}) | {"stop_reason"},
        "failed recovery receipt",
    )
    expected_grants = [
        {"source_id": key, **old_grants[key]}
        for key in ("opensanctions_un", "ofac_sdn", "eu_consolidated")
    ]
    if (
        type(previous["schema_version"]) is not int
        or previous["schema_version"] != 1
        or previous["scope"] != RECOVERY_SCOPE
        or previous["status"] != "partial"
        or previous["live_authorized"] is not True
        or previous["independent_custody_verified"] is not False
        or previous["selection_use"] != "shared-development-candidates-only"
        or previous["resume_supported"] is not False
        or _integer(previous["total_body_limit"], "failed recovery byte limit")
        != 34_000_000
        or previous["stop_reason"]
        not in {"transport_or_framing_error", "transport_io_failed"}
        or previous["policy_sha256"] != binding["policy"]["sha256"]
        or previous["execution_policy_path"] != binding["policy"]["path"]
        or previous["execution_policy_sha256"] != binding["policy"]["sha256"]
        or previous["session_claim"] != binding["claim"]
        or previous["approval"] != old_policy["approval"]
        or previous["prior_session"] != old_reuse
        or _canonical(previous["prior_session_accounting"])
        != _canonical(receipt["prior_session_accounting"])
        or previous["permission_grants"] != expected_grants
    ):
        raise CorpusValidationError("continuation failed recovery lineage differs")
    _integer(previous["peak_sampled_rss_bytes"], "failed recovery RSS", 1, 2 * 1024**3)
    _text(previous["rss_enforcement"], "failed recovery RSS enforcement")
    previous_refs = _evidence_references(previous["evidence"], acquisition=False)
    for path, expected in previous_refs.items():
        if path not in saved or saved[path].sha256 != expected:
            raise CorpusValidationError("continuation omits failed recovery evidence")
    for reference in [
        binding["policy"],
        binding["claim"],
        old_policy["approval"],
        *old_grants.values(),
        *(value for key, value in old_reuse.items() if key != "source_id"),
    ]:
        path, expected = _reference(reference, "failed recovery evidence")
        if previous_refs.get(path) != expected:
            raise CorpusValidationError("failed recovery evidence is incomplete")
    rows = previous["sources"]
    if not isinstance(rows, list) or len(rows) != 2:
        raise CorpusValidationError(
            "failed recovery must retain exactly its completed and failed sources"
        )
    expected_reused = dict(
        next(
            row for row in receipt["sources"] if row["source_id"] == "opensanctions_un"
        )
    )
    expected_reused["permission"] = old_grants["opensanctions_un"]
    if _canonical(rows[0]) != _canonical(expected_reused):
        raise CorpusValidationError(
            "failed recovery reused source differs from original completion"
        )
    failed = _object(
        rows[1],
        {
            "source_id",
            "status",
            "stop_reason",
            "requested_url",
            "final_url",
            "http_status",
            "complete",
            "bytes_received",
            "body_sha256",
            "transaction_count",
            "permission",
            "acquisition_origin",
            "origin_evidence",
            "transactions",
        },
        "failed recovery source",
    )
    transaction = {
        "sequence": 1,
        "request_number": 1,
        "requested_url": LIVE_URLS["ofac_sdn"],
        "final_url": None,
        "signing_query_present": False,
        "http_status": None,
        "declared_body_bytes": None,
        "complete": False,
        "bytes_received": 0,
        "body_sha256": _sha(b""),
        "outcome": "rejected",
        "stop_reason": previous["stop_reason"],
        "redirect_target": None,
        "unresolved_response_reservation_bytes": 4_000_000,
    }
    expected_failed = {
        "source_id": "ofac_sdn",
        "status": "failed",
        "stop_reason": previous["stop_reason"],
        "requested_url": LIVE_URLS["ofac_sdn"],
        "final_url": None,
        "http_status": None,
        "complete": False,
        "bytes_received": 0,
        "body_sha256": _sha(b""),
        "transaction_count": 1,
        "permission": old_grants["ofac_sdn"],
        "acquisition_origin": "recovery_session",
        "origin_evidence": None,
        "transactions": [transaction],
    }
    # Canonical comparison also rejects booleans posing as integer counters.
    if _canonical(failed) != _canonical(expected_failed):
        raise CorpusValidationError(
            "failed recovery request or unresolved reservation changed"
        )
    _recovery_ledger(previous["ledger"], {"ofac_sdn": failed}, failed_recovery=True)
    if previous["ledger"]["limits"] != receipt["ledger"]["limits"]:
        raise CorpusValidationError("continuation changes inherited request limits")
    expected_accounting = {
        "received_body_bytes": 0,
        "unresolved_response_reservation_bytes": 4_000_000,
        "received_plus_reservation_bytes": 4_000_000,
        "combined_prior_plus_recovery_reserved_bytes": receipt[
            "prior_session_accounting"
        ]["received_plus_reservation_bytes"]
        + 4_000_000,
    }
    if _canonical(previous["recovery_accounting"]) != _canonical(expected_accounting):
        raise CorpusValidationError("failed recovery accounting was reset")
    old_claim = document(binding["claim"], "failed recovery claim")
    _object(old_claim, set(current_claim) - {"continuation"}, "failed recovery claim")
    if (
        type(old_claim["schema_version"]) is not int
        or old_claim["schema_version"] != 1
        or old_claim["scope"] != RECOVERY_SCOPE
        or old_claim["policy_sha256"] != binding["policy"]["sha256"]
        or old_claim["prior_claim"] != receipt["prior_session"]["claim"]
        or old_claim["resume_supported"] is not False
        or _integer(old_claim["maximum_reserved_body_bytes"], "failed claim bytes")
        != 34_000_000
        or _integer(old_claim["maximum_transactions"], "failed claim requests") != 3
        or not Path(_text(old_claim["output"], "failed claim output")).is_absolute()
        or old_claim["output"] == current_claim["output"]
        or binding["claim"]["path"]
        in {receipt["session_claim"]["path"], receipt["prior_session"]["claim"]["path"]}
    ):
        raise CorpusValidationError(
            "continuation reuses or changes failed recovery claim"
        )
    try:
        old_original = document(receipt["prior_session"]["claim"], "original claim")
        times = [
            datetime.fromisoformat(_text(value, "lineage time", 128))
            for value in (
                old_original["claimed_at"],
                old_claim["claimed_at"],
                previous["started_at"],
                previous["finished_at"],
                current_claim["claimed_at"],
                receipt["started_at"],
            )
        ]
        if (
            any(value.tzinfo is None for value in times)
            or not times[0] < times[1] <= times[2] <= times[3] < times[4] <= times[5]
            or (times[3] - times[1]).total_seconds() > 3600
        ):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise CorpusValidationError(
            "continuation chronology does not identify separate consumed sessions"
        ) from exc


def _fictional_full_receipt(receipt: dict, selection: bytes, source_id: object) -> dict:
    """Validate the offline full fixture contract without claiming acquisition rights."""
    from watchlist.ingest.resource_guard import (
        BULK_SOURCES,
        STEP08_LIMITS,
        TRANCHE_BYTES,
    )

    _object(
        receipt,
        {
            "schema_version",
            "scope",
            "policy_sha256",
            "status",
            "live_authorized",
            "independent_custody_verified",
            "selection_use",
            "sources",
            "resume_supported",
            "ledger",
            "peak_sampled_rss_bytes",
            "rss_enforcement",
        },
        "fictional full receipt",
    )
    if (
        type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != 1
        or receipt["scope"] != "08B-0-offline-fictional-only"
        or receipt["status"] != "passed"
        or receipt["live_authorized"] is not False
        or receipt["independent_custody_verified"] is not False
        or receipt["selection_use"] != "fictional-development-only"
        or receipt["resume_supported"] is not False
        or not isinstance(source_id, str)
        or source_id not in BULK_SOURCES
    ):
        raise CorpusValidationError(
            "full receipt must be successful fictional development preparation"
        )
    _digest(receipt["policy_sha256"], "fictional full policy")
    _integer(receipt["peak_sampled_rss_bytes"], "sampled RSS")
    if (
        receipt["rss_enforcement"]
        != "cooperative-checks; use-supervise_command-for-worker-termination"
    ):
        raise CorpusValidationError("unsupported fictional resource enforcement claim")
    rows = receipt["sources"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
        raise CorpusValidationError("fictional full source records are incomplete")
    indexed = {}
    for row in rows:
        _object(
            row,
            {
                "source_id",
                "input_sha256",
                "input_bytes",
                "input_records",
                "retained_groups",
                "excluded_person_records",
                "excluded_other_records",
                "excluded_by_limit",
                "parser_version",
                "source_version",
                "source_version_field",
                "container_format",
                "container_member",
                "decoded_bytes",
                "decoded_sha256",
                "selection_sha256",
                "selection_bytes",
            },
            "fictional full source",
        )
        key = _text(row["source_id"], "fictional source ID")
        if key not in BULK_SOURCES or key in indexed:
            raise CorpusValidationError("unsupported or duplicate fictional source")
        _digest(row["input_sha256"], "fictional complete input")
        _integer(
            row["input_bytes"],
            "fictional complete input bytes",
            1,
            STEP08_LIMITS[key].received_bytes,
        )
        _digest(row["selection_sha256"], "fictional selection")
        _integer(
            row["selection_bytes"],
            "fictional selection bytes",
            maximum=MAX_SELECTION_BYTES,
        )
        retained = _integer(
            row["retained_groups"],
            "fictional retained groups",
            maximum=MAX_OBSERVATIONS,
        )
        accounted = retained + sum(
            _integer(row[name], name)
            for name in (
                "excluded_person_records",
                "excluded_other_records",
                "excluded_by_limit",
            )
        )
        if _integer(row["input_records"], "fictional input records", 1) != accounted:
            raise CorpusValidationError(
                "fictional input/exclusion accounting is incomplete"
            )
        _text(row["parser_version"], "fictional parser version")
        if row["source_version"] is None:
            if row["source_version_field"] is not None:
                raise CorpusValidationError("fictional version evidence is incomplete")
        else:
            _text(row["source_version"], "fictional source version")
            _text(row["source_version_field"], "fictional version field")
        if key == "ofac_sdn":
            if row["container_format"] != "zip" or row["container_member"] != "SDN.XML":
                raise CorpusValidationError(
                    "fictional OFAC container evidence is incomplete"
                )
            _integer(row["decoded_bytes"], "fictional decoded bytes", 1)
            _digest(row["decoded_sha256"], "fictional decoded input")
        elif any(
            row[name] is not None
            for name in (
                "decoded_bytes",
                "decoded_sha256",
                "container_format",
                "container_member",
            )
        ):
            raise CorpusValidationError("unexpected fictional decoded-input evidence")
        indexed[key] = row
    if source_id not in indexed:
        raise CorpusValidationError(
            "purpose source is absent from fictional full receipt"
        )
    selected = indexed[source_id]
    if selected["selection_sha256"] != _sha(selection) or selected[
        "selection_bytes"
    ] != len(selection):
        raise CorpusValidationError(
            "fictional full receipt does not bind the saved selection"
        )
    ledger = _object(
        receipt["ledger"],
        {
            "schema_version",
            "scope",
            "limits",
            "tranche_bytes",
            "total_received_bytes",
            "received_bytes",
            "transactions",
            "attempted_sources",
            "active_source",
            "active_request",
            "active_response_reservation",
            "session_deadline_monotonic",
            "stop_reason",
            "resume_supported",
        },
        "fictional session ledger",
        {"bulk_transaction_limit", "allowed_buckets"},
    )
    if (
        type(ledger["schema_version"]) is not int
        or ledger["schema_version"] != 1
        or ledger["scope"] != "step08-single-session-no-resume"
        or ledger["active_source"] is not None
        or ledger["active_request"] is not None
        or ledger["stop_reason"] is not None
        or ledger["resume_supported"] is not False
        or _integer(ledger["active_response_reservation"], "active reservation") != 0
        or _integer(ledger["tranche_bytes"], "tranche bytes") != TRANCHE_BYTES
    ):
        raise CorpusValidationError(
            "fictional session is unfinished, stopped or unsupported"
        )
    deadline = ledger["session_deadline_monotonic"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
        or deadline <= 0
    ):
        raise CorpusValidationError("invalid fictional session deadline")
    for name in ("limits", "received_bytes", "transactions"):
        _object(ledger[name], STEP08_LIMITS, "fictional ledger " + name)
    attempted = _strings(ledger["attempted_sources"], "attempted sources", minimum=1)
    allowed = (
        set(_strings(ledger["allowed_buckets"], "allowed buckets", minimum=1))
        if "allowed_buckets" in ledger
        else set(STEP08_LIMITS)
    )
    if not set(indexed) <= set(attempted) <= allowed <= set(STEP08_LIMITS):
        raise CorpusValidationError("fictional ledger omits completed sources")
    bulk_limit = _integer(
        ledger.get("bulk_transaction_limit", 9), "bulk transaction limit", 1, 9
    )
    if (
        sum(
            _integer(ledger["transactions"][name], "bulk transactions")
            for name in BULK_SOURCES
        )
        > bulk_limit
    ):
        raise CorpusValidationError("fictional bulk transaction limit exceeded")
    total = 0
    for bucket, ceiling in STEP08_LIMITS.items():
        limit = _object(
            ledger["limits"][bucket],
            {
                "received_bytes",
                "transactions",
                "response_bytes",
                "request_seconds",
                "source_seconds",
            },
            "fictional bucket limits",
        )
        for key, value in limit.items():
            _integer(value, "fictional " + key, 1, getattr(ceiling, key))
        received = _integer(
            ledger["received_bytes"][bucket],
            "fictional received bytes",
            maximum=limit["received_bytes"],
        )
        transactions = _integer(
            ledger["transactions"][bucket],
            "fictional transactions",
            maximum=limit["transactions"],
        )
        if bucket in indexed and (received == 0 or transactions == 0):
            raise CorpusValidationError(
                "completed fictional source lacks transfer accounting"
            )
        if bucket in indexed and indexed[bucket]["input_bytes"] > received:
            raise CorpusValidationError(
                "fictional complete-body bytes exceed charged source bytes"
            )
        if bucket not in attempted and (received or transactions):
            raise CorpusValidationError(
                "unattempted fictional source has charged counters"
            )
        total += received
    if (
        _integer(
            ledger["total_received_bytes"],
            "fictional total bytes",
            maximum=TRANCHE_BYTES,
        )
        != total
    ):
        raise CorpusValidationError("fictional aggregate byte accounting differs")
    # A read-only view for common name/type validation. Original receipt bytes
    # remain unchanged and retain their explicit fictional scope in the store.
    return {**selected, "role": "sanctions_reference"}


def _candidate_observations(
    records: tuple[SourceRecord, ...],
    snapshot_id: str,
    role: str,
    *,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[CandidateObservation, ...]:
    """Keep complete source-name witnesses and stable source-local identifiers."""
    observations = []
    for index, record in enumerate(records):
        if checkpoint is not None and index % 128 == 0:
            checkpoint()
        key = (record.source_id, record.provider_id)
        observation_id = _sha(
            _canonical(["candidate-observation-v1", snapshot_id, key])
        )
        aliases = tuple(
            CandidateNameEvidence(
                _sha(
                    _canonical(
                        [
                            "candidate-name-evidence-v1",
                            observation_id,
                            alias.value,
                            alias.field,
                            alias.language,
                            alias.attributes,
                        ]
                    )
                ),
                alias.value,
                alias.field,
                alias.language,
                alias.attributes,
            )
            for alias in record.aliases
        )
        observations.append(
            CandidateObservation(
                observation_id,
                snapshot_id,
                record.source_id,
                record.provider_id,
                key,
                record.entity_type,
                record.primary_name,
                aliases,
                record.provider_schema,
                record.classification_basis,
                record.referents,
                record.provider_datasets,
                record.provider_topics,
                role,
            )
        )
    return tuple(observations)


def _from_buffers(
    selection: bytes,
    receipt_bytes: bytes,
    permission_bytes: bytes,
    evidence: tuple[SavedEvidence, ...],
    receipt_format: str = SOURCE_RECEIPT,
) -> PreparedSource:
    for payload, limit in (
        (selection, MAX_SELECTION_BYTES),
        (receipt_bytes, MAX_METADATA_BYTES),
        (permission_bytes, MAX_METADATA_BYTES),
    ):
        if type(payload) is not bytes or len(payload) > limit:
            raise CorpusValidationError("input buffer type or byte limit is invalid")
    receipt = _json_object(receipt_bytes, "receipt")
    permission = _json_object(permission_bytes, "purpose permission")
    selection_hash, receipt_hash, permission_hash = map(
        _sha, (selection, receipt_bytes, permission_bytes)
    )
    receipt, references = _source_context(
        receipt, selection, permission, receipt_format
    )
    for path, digest in _permission(
        permission, receipt, receipt_hash, selection_hash
    ).items():
        if path in references and references[path] != digest:
            raise CorpusValidationError("permission evidence has conflicting digests")
        references[path] = digest
    if type(evidence) is not tuple or len(evidence) > MAX_EVIDENCE_FILES:
        raise CorpusValidationError("invalid saved evidence bundle")
    observed = {}
    for item in evidence:
        if (
            type(item) is not SavedEvidence
            or type(item.payload) is not bytes
            or not item.payload
            or len(item.payload) > MAX_EVIDENCE_BYTES
        ):
            raise CorpusValidationError("invalid saved evidence payload")
        if item.path in observed or _sha(item.payload) != item.sha256:
            raise CorpusValidationError(
                "duplicate or corrupt saved permission evidence"
            )
        observed[item.path] = item.sha256
    if references != observed:
        raise CorpusValidationError(
            "permission evidence bundle is incomplete or unreferenced"
        )
    if (
        sum(map(len, (selection, receipt_bytes, permission_bytes)))
        + sum(len(item.payload) for item in evidence)
        > MAX_TOTAL_INPUT_BYTES
    ):
        raise CorpusValidationError("source inputs exceed aggregate byte limit")
    if receipt_format == REAL_FULL_RECEIPT:
        binder = (
            _bound_recovery_permission
            if _json_object(receipt_bytes, "receipt").get("scope") == RECOVERY_SCOPE
            else _bound_real_permission
        )
        bound = binder(receipt_bytes, receipt["source_id"], evidence)
        if permission != bound:
            raise CorpusValidationError(
                "bound purpose permission differs from its prospective grant"
            )
    records = _records(selection, receipt, permission)
    if receipt_format == SOURCE_RECEIPT:
        _statistics(records, receipt)
    elif len(records) != receipt["retained_groups"]:
        raise CorpusValidationError("fictional retained count differs from selection")
    snapshot_id = _sha(
        _canonical(
            [
                "candidate-snapshot-v1",
                receipt_format,
                receipt["source_id"],
                selection_hash,
                receipt_hash,
                permission_hash,
            ]
        )
    )
    observations = _candidate_observations(records, snapshot_id, receipt["role"])
    return PreparedSource(
        snapshot_id,
        receipt["source_id"],
        selection_hash,
        receipt_hash,
        permission_hash,
        selection,
        receipt_bytes,
        permission_bytes,
        tuple(sorted(evidence, key=lambda item: item.path)),
        tuple(observations),
        receipt_format,
    )


def prepare_source(
    selection_path: Path,
    receipt_path: Path,
    permission_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_permission_sha256: str,
    evidence_root: Path,
) -> PreparedSource:
    """Admit bounded local evidence without writes or reliance on file names.

    The caller supplies receipt/permission digests from its trusted review record.
    These pins detect changed inputs; this function cannot authenticate that review.
    All relative evidence paths must stay under a real, nonsymlink evidence root.
    """
    return _prepare_source(
        selection_path,
        receipt_path,
        permission_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_permission_sha256=expected_permission_sha256,
        evidence_root=evidence_root,
        receipt_format=SOURCE_RECEIPT,
    )


def prepare_fictional_full_source(
    selection_path: Path,
    receipt_path: Path,
    permission_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_permission_sha256: str,
    evidence_root: Path,
) -> PreparedSource:
    """Admit an explicitly fictional full-profile fixture, never a live receipt.

    The separate entry point preserves the full aggregate receipt as written.
    It does not invent legacy acquisition grants, HTTP attempts or raw replay.
    Purpose evidence must still bind the exact receipt and selected source bytes.
    """
    return _prepare_source(
        selection_path,
        receipt_path,
        permission_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_permission_sha256=expected_permission_sha256,
        evidence_root=evidence_root,
        receipt_format=FICTIONAL_FULL_RECEIPT,
    )


def _bind_full_permission(
    selection_path: Path,
    receipt_path: Path,
    *,
    source_id: str,
    expected_receipt_sha256: str,
    expected_grant_sha256: str,
    evidence_root: Path,
    recovery: bool = False,
) -> dict:
    """Return the existing approved purpose narrowed to successful saved bytes.

    This performs no writes or review. The caller must retain the returned single
    binding in a new private file without overwriting any earlier grant/binding.
    Original review metadata and conditions are copied exactly from the grant.
    """
    _digest(expected_receipt_sha256, "expected real full receipt")
    _digest(expected_grant_sha256, "expected prospective grant")
    receipt_bytes = _read_saved(
        Path(receipt_path), MAX_METADATA_BYTES, "real full receipt"
    )
    if _sha(receipt_bytes) != expected_receipt_sha256:
        raise CorpusValidationError("real full receipt differs from its trusted digest")
    selection = _read_saved(
        Path(selection_path), MAX_SELECTION_BYTES, "real full selection"
    )
    receipt = _json_object(receipt_bytes, "real full receipt")
    validator = _recovery_receipt if recovery else _real_full_receipt
    selected, references = validator(receipt, selection, source_id)
    if selected["permission"]["sha256"] != expected_grant_sha256:
        raise CorpusValidationError("prospective grant differs from its trusted digest")
    grant_path, grant_hash = _reference(
        selected["permission"], "prospective source grant"
    )
    grant_bytes = _read_saved(
        Path(evidence_root) / grant_path, MAX_EVIDENCE_BYTES, "prospective source grant"
    )
    if _sha(grant_bytes) != grant_hash:
        raise CorpusValidationError("prospective source grant bytes differ")
    grant = _json_object(grant_bytes, "prospective source grant")
    for path, digest in _evidence_references(
        grant.get("evidence"), acquisition=False
    ).items():
        if path in references and references[path] != digest:
            raise CorpusValidationError("conflicting prospective grant evidence")
        references[path] = digest
    if len(references) > MAX_EVIDENCE_FILES:
        raise CorpusValidationError("too many bound purpose evidence files")
    evidence = tuple(
        SavedEvidence(
            path,
            digest,
            grant_bytes
            if path == grant_path
            else _read_saved(
                Path(evidence_root) / path, MAX_EVIDENCE_BYTES, "bound purpose evidence"
            ),
        )
        for path, digest in sorted(references.items())
    )
    binder = _bound_recovery_permission if recovery else _bound_real_permission
    permission = binder(receipt_bytes, source_id, evidence)
    _from_buffers(
        selection, receipt_bytes, _canonical(permission), evidence, REAL_FULL_RECEIPT
    )
    return permission


def bind_real_full_permission(
    selection_path: Path,
    receipt_path: Path,
    *,
    source_id: str,
    expected_receipt_sha256: str,
    expected_grant_sha256: str,
    evidence_root: Path,
) -> dict:
    """Return an original complete-session binding without writing or new review."""
    return _bind_full_permission(
        selection_path,
        receipt_path,
        source_id=source_id,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_grant_sha256=expected_grant_sha256,
        evidence_root=evidence_root,
    )


def bind_recovered_full_permission(
    selection_path: Path,
    receipt_path: Path,
    *,
    source_id: str,
    expected_receipt_sha256: str,
    expected_grant_sha256: str,
    evidence_root: Path,
) -> dict:
    """Bind separately approved recovery evidence; never create an old receipt.

    No file or claim is modified. The existing purpose is narrowed to this new
    completed assembly, with the old interrupted session retained as evidence.
    """
    return _bind_full_permission(
        selection_path,
        receipt_path,
        source_id=source_id,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_grant_sha256=expected_grant_sha256,
        evidence_root=evidence_root,
        recovery=True,
    )


def prepare_real_full_source(
    selection_path: Path,
    receipt_path: Path,
    permission_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_permission_sha256: str,
    evidence_root: Path,
) -> PreparedSource:
    """Verify one real full selection and its prospectively authorized binding.

    Admission is restricted to the complete three-source 08B-2 receipt. All
    material remains shared development evidence with no final-custody claim.
    """
    return _prepare_source(
        selection_path,
        receipt_path,
        permission_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_permission_sha256=expected_permission_sha256,
        evidence_root=evidence_root,
        receipt_format=REAL_FULL_RECEIPT,
        expected_receipt_scope="08B-2-development-candidate-acquisition-v1",
    )


def prepare_recovered_full_source(
    selection_path: Path,
    receipt_path: Path,
    permission_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_permission_sha256: str,
    evidence_root: Path,
) -> PreparedSource:
    """Admit one source from the new complete recovery assembly, read-only.

    The unchanged schema-v2 real-receipt codec stores the new explicit scope.
    Its original consumed claim and failed/running historical rows remain saved.
    Candidate publication requires all three sources from the same new receipt.
    """
    return _prepare_source(
        selection_path,
        receipt_path,
        permission_path,
        expected_receipt_sha256=expected_receipt_sha256,
        expected_permission_sha256=expected_permission_sha256,
        evidence_root=evidence_root,
        receipt_format=REAL_FULL_RECEIPT,
        expected_receipt_scope=RECOVERY_SCOPE,
    )


def _prepare_source(
    selection_path: Path,
    receipt_path: Path,
    permission_path: Path,
    *,
    expected_receipt_sha256: str,
    expected_permission_sha256: str,
    evidence_root: Path,
    receipt_format: str,
    expected_receipt_scope: str | None = None,
) -> PreparedSource:
    _digest(expected_receipt_sha256, "expected receipt")
    _digest(expected_permission_sha256, "expected permission")
    receipt_bytes = _read_saved(Path(receipt_path), MAX_METADATA_BYTES, "receipt")
    permission_bytes = _read_saved(
        Path(permission_path), MAX_METADATA_BYTES, "purpose permission"
    )
    if (
        _sha(receipt_bytes) != expected_receipt_sha256
        or _sha(permission_bytes) != expected_permission_sha256
    ):
        raise CorpusValidationError(
            "receipt or purpose permission differs from its trusted digest"
        )
    selection = _read_saved(Path(selection_path), MAX_SELECTION_BYTES, "selection")
    receipt = _json_object(receipt_bytes, "receipt")
    if (
        expected_receipt_scope is not None
        and receipt.get("scope") != expected_receipt_scope
    ):
        raise CorpusValidationError(
            "receipt requires its explicit admission entry point"
        )
    permission = _json_object(permission_bytes, "purpose permission")
    receipt, references = _source_context(
        receipt, selection, permission, receipt_format
    )
    for path, digest in _permission(
        permission, receipt, _sha(receipt_bytes), _sha(selection)
    ).items():
        if path in references and references[path] != digest:
            raise CorpusValidationError("permission evidence has conflicting digests")
        references[path] = digest
    if len(references) > MAX_EVIDENCE_FILES:
        raise CorpusValidationError("too many permission evidence files")
    evidence = tuple(
        SavedEvidence(
            path,
            digest,
            _read_saved(
                Path(evidence_root) / path, MAX_EVIDENCE_BYTES, "permission evidence"
            ),
        )
        for path, digest in sorted(references.items())
    )
    return _from_buffers(
        selection, receipt_bytes, permission_bytes, evidence, receipt_format
    )


def _continuation_manifest(
    receipt_path: str,
    receipt_bytes: bytes,
    sources: tuple[ContinuationSource, ...],
    evidence: tuple[SavedEvidence, ...],
) -> bytes:
    """Bind retained inputs and provenance without creating a corpus-release hash."""
    receipt = _json_object(receipt_bytes, "continuation receipt")
    return _canonical(
        {
            "schema_version": 1,
            "artifact_kind": CONTINUATION_PREPARATION,
            "receipt": {"path": _relative(receipt_path), "sha256": _sha(receipt_bytes)},
            "receipt_scope": CONTINUATION_SCOPE,
            "selection_use": "shared-development-candidates-only",
            "release_authorized": False,
            "training_eligible": False,
            "evaluation_eligible": False,
            "fresh_final_eligible": False,
            "human_review_count": 0,
            "accepted_independent_families": 0,
            "sources": [
                {
                    "source_id": source.source_id,
                    "snapshot_id": source.snapshot_id,
                    "selection": {
                        "path": source.selection_path,
                        "sha256": source.selection_sha256,
                    },
                    "permission": {
                        "path": source.permission_path,
                        "sha256": source.permission_sha256,
                    },
                    "acquisition_origin": source.acquisition_origin,
                    "retained_groups": len(source.observations),
                }
                for source in sources
            ],
            "evidence": [
                {"path": item.path, "sha256": item.sha256} for item in evidence
            ],
            "lineage": {
                "original_session": receipt["prior_session"],
                "failed_recovery": receipt["continuation"],
                "continuation_claim": receipt["session_claim"],
                "prior_session_accounting": receipt["prior_session_accounting"],
                "recovery_accounting": receipt["recovery_accounting"],
            },
        }
    )


def prepare_continuation_sources(
    receipt_path: Path,
    *,
    expected_receipt_sha256: str,
    evidence_root: Path,
    checkpoint: Callable[[], None] | None = None,
) -> ContinuationPreparation:
    """Admit all three saved continuation selections for local readiness only.

    The trusted receipt digest pins every input. All file components must be
    ordinary contained paths; symlinks, traversal, changed hashes and partial
    sessions fail closed. Original grants remain unchanged, while an in-memory
    narrowed permission binds each selection to this exact receipt. No network,
    claim consumption, purpose-file write or candidate publication is performed.
    """
    if checkpoint is not None and not callable(checkpoint):
        raise CorpusValidationError("continuation checkpoint must be callable")

    def check() -> None:
        if checkpoint is not None:
            checkpoint()

    check()
    _digest(expected_receipt_sha256, "expected continuation receipt")
    root = Path(evidence_root).absolute()
    absolute_receipt = Path(receipt_path).absolute()
    if (
        ".." in root.parts
        or ".." in absolute_receipt.parts
        or not absolute_receipt.is_relative_to(root)
    ):
        raise CorpusValidationError(
            "continuation receipt must be contained in evidence root"
        )
    receipt_name = _relative(absolute_receipt.relative_to(root).as_posix())
    try:
        directory = _open_directory(root)
        os.close(directory)
        receipt_bytes = _read_saved(
            absolute_receipt, MAX_METADATA_BYTES, "continuation receipt"
        )
        if _sha(receipt_bytes) != expected_receipt_sha256:
            raise CorpusValidationError(
                "continuation receipt differs from its trusted digest"
            )
        receipt = _json_object(receipt_bytes, "continuation receipt")
        if receipt.get("scope") != CONTINUATION_SCOPE:
            raise CorpusValidationError(
                "continuation requires its explicit receipt scope"
            )
        rows = receipt.get("sources")
        if not isinstance(rows, list) or len(rows) != 3:
            raise CorpusValidationError(
                "continuation requires all three completed sources"
            )
        selections = {}
        references = None
        total = len(receipt_bytes)
        for row in rows:
            check()
            if not isinstance(row, dict) or row.get("source_id") not in {
                "opensanctions_un",
                "ofac_sdn",
                "eu_consolidated",
            }:
                raise CorpusValidationError("continuation source is unsupported")
            key = row["source_id"]
            if key in selections or row.get("selection_path") != f"{key}.jsonl":
                raise CorpusValidationError(
                    "continuation selection path or source coverage differs"
                )
            selected_path = absolute_receipt.parent / row["selection_path"]
            selection = _read_saved(
                selected_path, MAX_SELECTION_BYTES, "continuation selection"
            )
            _, source_refs = _completed_session_receipt(
                receipt, selection, key, continuation=True
            )
            if references is not None and references != source_refs:
                raise CorpusValidationError("continuation source evidence differs")
            references = source_refs
            selections[key] = (selected_path.relative_to(root).as_posix(), selection)
            total += len(selection)
            if total > MAX_TOTAL_INPUT_BYTES:
                raise CorpusValidationError(
                    "continuation inputs exceed aggregate byte limit"
                )
        saved = []
        for path, expected in sorted(references.items()):
            check()
            payload = _read_saved(
                root / path, MAX_EVIDENCE_BYTES, "continuation evidence"
            )
            if not payload or _sha(payload) != expected:
                raise CorpusValidationError("missing or changed continuation evidence")
            total += len(payload)
            if total > MAX_TOTAL_INPUT_BYTES:
                raise CorpusValidationError(
                    "continuation inputs exceed aggregate byte limit"
                )
            saved.append(SavedEvidence(path, expected, payload))
        evidence = tuple(saved)
        evidence_by_path = {item.path: item for item in evidence}
        current_claim = _json_object(
            evidence_by_path[receipt["session_claim"]["path"]].payload,
            "continuation claim",
        )
        if (
            Path(_text(current_claim.get("output"), "continuation output")).absolute()
            != absolute_receipt.parent
        ):
            raise CorpusValidationError(
                "continuation claim belongs to a different output directory"
            )
        for claim_ref, expected_output in (
            (
                receipt["prior_session"]["claim"],
                (root / receipt["prior_session"]["selection"]["path"]).parent,
            ),
            (
                receipt["continuation"]["claim"],
                (root / receipt["continuation"]["receipt"]["path"]).parent,
            ),
        ):
            claim = _json_object(
                evidence_by_path[claim_ref["path"]].payload, "lineage claim"
            )
            if claim.get("output") != str(expected_output):
                raise CorpusValidationError(
                    "continuation lineage crosses claimed output directories"
                )
        original_output = (root / receipt["prior_session"]["selection"]["path"]).parent
        directory = _open_directory(original_output)
        try:
            try:
                os.stat("receipt.json", dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise CorpusValidationError(
                    "original interrupted session unexpectedly has a final receipt"
                )
        finally:
            os.close(directory)
        sources = []
        for row in sorted(rows, key=lambda item: item["source_id"]):
            check()
            key = row["source_id"]
            selection_path, selection = selections[key]
            permission = _bound_completed_session_permission(
                receipt_bytes, key, evidence, continuation=True
            )
            source_context = {**row, "role": "sanctions_reference"}
            _permission(
                permission, source_context, expected_receipt_sha256, _sha(selection)
            )
            records = _records(
                selection, source_context, permission, checkpoint=checkpoint
            )
            if len(records) != row["retained_groups"]:
                raise CorpusValidationError(
                    "continuation retained count differs from selection"
                )
            bound_permission = _canonical(permission)
            snapshot_id = _sha(
                _canonical(
                    [
                        "continuation-preparation-snapshot-v1",
                        key,
                        row["selection_sha256"],
                        expected_receipt_sha256,
                        row["permission"]["sha256"],
                        _sha(bound_permission),
                    ]
                )
            )
            observations = _candidate_observations(
                records, snapshot_id, "sanctions_reference", checkpoint=checkpoint
            )
            grant = evidence_by_path[row["permission"]["path"]]
            sources.append(
                ContinuationSource(
                    snapshot_id,
                    key,
                    selection_path,
                    row["selection_sha256"],
                    selection,
                    grant.path,
                    grant.sha256,
                    grant.payload,
                    bound_permission,
                    row["acquisition_origin"],
                    observations,
                )
            )
        immutable_sources = tuple(sources)
        observations = tuple(
            item for source in immutable_sources for item in source.observations
        )
        if len(observations) > MAX_OBSERVATIONS:
            raise CorpusValidationError(
                "continuation exceeds aggregate observation bound"
            )
        manifest = _continuation_manifest(
            receipt_name, receipt_bytes, immutable_sources, evidence
        )
        check()
        return ContinuationPreparation(
            expected_receipt_sha256,
            receipt_bytes,
            manifest,
            _sha(manifest),
            evidence,
            immutable_sources,
            observations,
        )
    except (OSError, KeyError, TypeError) as exc:
        raise CorpusValidationError(
            "continuation input path or evidence is unsafe or incomplete"
        ) from exc


def _validated_sources(sources: Iterable[PreparedSource]) -> tuple[PreparedSource, ...]:
    """Reconstruct public dataclasses from saved bytes instead of trusting them."""
    result = []
    total = 0
    count = 0
    for source in sources:
        if type(source) is not PreparedSource or len(result) >= MAX_SNAPSHOTS:
            raise CorpusValidationError("invalid candidate source count/type")
        rebuilt = _from_buffers(
            source.selection_bytes,
            source.receipt_bytes,
            source.permission_bytes,
            source.evidence,
            source.receipt_format,
        )
        if rebuilt != source:
            raise CorpusValidationError(
                "prepared source differs from its saved input evidence"
            )
        total += sum(
            map(
                len,
                (
                    rebuilt.selection_bytes,
                    rebuilt.receipt_bytes,
                    rebuilt.permission_bytes,
                ),
            )
        )
        total += sum(len(item.payload) for item in rebuilt.evidence)
        count += len(rebuilt.observations)
        if total > MAX_TOTAL_INPUT_BYTES or count > MAX_OBSERVATIONS:
            raise CorpusValidationError(
                "candidate inputs exceed aggregate preparation bounds"
            )
        result.append(rebuilt)
    if not result or len({source.snapshot_id for source in result}) != len(result):
        raise CorpusValidationError("candidate release needs unique source snapshots")
    return tuple(sorted(result, key=lambda source: source.snapshot_id))


def _recovery_manifest(sources: tuple[PreparedSource, ...]) -> dict:
    """Name the new assembly and preserve the original session's actual status."""
    recovery = [
        (source, _json_object(source.receipt_bytes, "source receipt"))
        for source in sources
        if source.receipt_format == REAL_FULL_RECEIPT
        and _json_object(source.receipt_bytes, "source receipt").get("scope")
        == RECOVERY_SCOPE
    ]
    if not recovery:
        return {}
    if (
        len(recovery) != 3
        or len(sources) != 3
        or {source.source_id for source, _ in recovery}
        != {"opensanctions_un", "ofac_sdn", "eu_consolidated"}
        or len({source.receipt_sha256 for source, _ in recovery}) != 1
    ):
        raise CorpusValidationError(
            "recovery assembly requires all three sources from one new receipt"
        )
    source, receipt = recovery[0]
    return {
        "assembly": {
            "kind": "separately_completed_source_sessions",
            "receipt_scope": RECOVERY_SCOPE,
            "receipt_sha256": source.receipt_sha256,
            "recovery_session_claim": receipt["session_claim"],
            "prior_session": receipt["prior_session"],
            "original_session_status": "interrupted",
            "original_final_receipt_available": False,
            "historical_source_statuses": {
                "opensanctions_un": "passed",
                "ofac_sdn": "failed",
                "eu_consolidated": "running",
            },
            "prior_session_accounting": receipt["prior_session_accounting"],
            "recovery_accounting": receipt["recovery_accounting"],
            "prior_received_bytes_are_lower_bound": True,
        }
    }


def _recovery_source_manifest(source: PreparedSource) -> dict:
    if source.receipt_format != REAL_FULL_RECEIPT:
        return {}
    receipt = _json_object(source.receipt_bytes, "source receipt")
    if receipt.get("scope") != RECOVERY_SCOPE:
        return {}
    row = next(
        row for row in receipt["sources"] if row["source_id"] == source.source_id
    )
    return {
        "receipt_scope": RECOVERY_SCOPE,
        "acquisition_origin": row["acquisition_origin"],
        "source_session_policy_sha256": receipt["prior_session"]["policy"]["sha256"]
        if row["acquisition_origin"] == "reused_completed_source"
        else receipt["policy_sha256"],
    }


def _manifest(
    release_id: str,
    sources: tuple[PreparedSource, ...],
    *,
    schema_version: int = SCHEMA_VERSION,
) -> bytes:
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise CorpusValidationError("unsupported candidate manifest version")
    if schema_version == 1 and any(
        source.receipt_format == REAL_FULL_RECEIPT for source in sources
    ):
        raise CorpusValidationError(
            "real full receipts require candidate schema version 2"
        )
    _text(release_id, "release ID", 128)
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", release_id) is None:
        raise CorpusValidationError("release ID must be a simple lowercase identifier")
    return _canonical(
        {
            "schema_version": schema_version,
            "release_id": release_id,
            "status": "prepared_candidate",
            "purpose": PURPOSE,
            "exposure_class": "developer_visible_candidate_preparation",
            "reviewed_corpus_accepted": False,
            "training_eligible": False,
            "evaluation_eligible": False,
            "fresh_final_eligible": False,
            "source_snapshots": len(sources),
            "source_observations": sum(len(source.observations) for source in sources),
            "name_evidence": sum(
                len(record.aliases)
                for source in sources
                for record in source.observations
            ),
            "accepted_independent_families": 0,
            "accepted_reference_families": 0,
            "accepted_absent_families": 0,
            "human_review_count": 0,
            "adjudicated_label_count": 0,
            "partition_count": 0,
            "acceptance_blockers": list(_BLOCKERS),
            "raw_replay_available": False,
            **_recovery_manifest(sources),
            "integrity_limit": "Hashes establish byte consistency, not reviewer authenticity, legal permission or custody.",
            "admission_bounds": {
                "max_total_input_bytes": MAX_TOTAL_INPUT_BYTES,
                "max_release_bytes": MAX_RELEASE_BYTES,
                "max_observations": MAX_OBSERVATIONS,
                "max_snapshots": MAX_SNAPSHOTS,
                "rss_bound_proven": False,
            },
            "sources": [
                {
                    "snapshot_id": source.snapshot_id,
                    "source_id": source.source_id,
                    "receipt_format": source.receipt_format,
                    **_recovery_source_manifest(source),
                    "selection_scope": "fictional_development_only"
                    if source.receipt_format == FICTIONAL_FULL_RECEIPT
                    else "shared_development_candidates_only"
                    if source.receipt_format == REAL_FULL_RECEIPT
                    else "unreviewed_saved_selection",
                    "selection_sha256": source.selection_sha256,
                    "receipt_sha256": source.receipt_sha256,
                    "permission_sha256": source.permission_sha256,
                    "evidence": [
                        {"path": item.path, "sha256": item.sha256}
                        for item in source.evidence
                    ],
                }
                for source in sources
            ],
        }
    )


def _schema(schema_version: int = SCHEMA_VERSION) -> str:
    """Keep the exact historical v1 schema available for read-only validation."""
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise CorpusValidationError("unsupported candidate schema version")
    source = (
        files("watchlist").joinpath("corpus_schema.sql").read_text(encoding="utf-8")
    )
    if schema_version == 1:
        return source.replace(
            "PRAGMA user_version = 2;", "PRAGMA user_version = 1;"
        ).replace(", 'real-full-acquisition-v1'", "")
    return source


def _new_database(schema_version: int = SCHEMA_VERSION) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.executescript(_schema(schema_version))
    return connection


def _schema_identity(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name"
    ).fetchall()


def _source_row(source: PreparedSource) -> tuple:
    return (
        source.snapshot_id,
        source.source_id,
        source.selection_sha256,
        source.receipt_sha256,
        source.permission_sha256,
        source.selection_bytes,
        source.receipt_bytes,
        source.permission_bytes,
        source.receipt_format,
    )


def _observation_row(observation: CandidateObservation) -> tuple:
    return (
        observation.observation_id,
        observation.snapshot_id,
        observation.source_id,
        observation.provider_id,
        observation.entity_type,
        observation.primary_name,
        observation.provider_schema,
        observation.classification_basis,
        _canonical(observation.referents),
        _canonical(observation.provider_datasets),
        _canonical(observation.provider_topics),
        observation.source_role,
    )


def _name_rows(observation: CandidateObservation) -> list[tuple]:
    return [
        (
            alias.evidence_id,
            observation.observation_id,
            index,
            alias.value,
            alias.field,
            alias.language,
            _canonical(alias.attributes),
        )
        for index, alias in enumerate(observation.aliases)
    ]


def _database_bytes(
    manifest: bytes,
    sources: tuple[PreparedSource, ...],
    *,
    schema_version: int = SCHEMA_VERSION,
) -> bytes:
    connection = _new_database(schema_version)
    try:
        connection.execute(
            "INSERT INTO candidate_manifest VALUES (1, ?, ?)",
            (manifest, _sha(manifest)),
        )
        for source in sources:
            connection.execute(
                "INSERT INTO candidate_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _source_row(source),
            )
            connection.executemany(
                "INSERT INTO candidate_permission_evidence VALUES (?, ?, ?, ?)",
                [
                    (source.snapshot_id, item.path, item.sha256, item.payload)
                    for item in source.evidence
                ],
            )
            for observation in source.observations:
                connection.execute(
                    "INSERT INTO candidate_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _observation_row(observation),
                )
                connection.executemany(
                    "INSERT INTO candidate_names VALUES (?, ?, ?, ?, ?, ?, ?)",
                    _name_rows(observation),
                )
        connection.commit()
        result = connection.serialize()
        if len(result) > MAX_RELEASE_BYTES:
            raise CorpusValidationError("candidate artifact exceeds its byte limit")
        return result
    finally:
        connection.close()


def _load_bytes(
    payload: bytes, expected_artifact_sha256: str | None
) -> CandidateRelease:
    """Read a snapshot in memory, validate schema, then rebuild every logical row."""
    if type(payload) is not bytes or not 100 <= len(payload) <= MAX_RELEASE_BYTES:
        raise CorpusValidationError("candidate artifact byte length is invalid")
    artifact_hash = _sha(payload)
    if expected_artifact_sha256 is not None:
        if artifact_hash != _digest(
            expected_artifact_sha256, "expected candidate artifact"
        ):
            raise CorpusValidationError(
                "candidate artifact differs from its trusted digest"
            )
    if payload[:16] != b"SQLite format 3\x00":
        raise CorpusValidationError("candidate artifact is not SQLite")
    # Reject WAL images and appended/truncated bytes before SQLite parses them.
    page_size = int.from_bytes(payload[16:18], "big")
    if page_size == 1:
        page_size = 65536
    pages = int.from_bytes(payload[28:32], "big")
    if (
        page_size < 512
        or page_size > 65536
        or page_size & (page_size - 1)
        or payload[18:20] != b"\x01\x01"
        or pages * page_size != len(payload)
    ):
        raise CorpusValidationError(
            "candidate artifact has an unsupported/incomplete SQLite image"
        )
    connection = sqlite3.connect(":memory:")
    expected = None
    try:
        connection.deserialize(payload)
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA query_only = ON")
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if schema_version not in (1, 2):
            raise CorpusValidationError("unrelated or altered candidate schema")
        expected = _new_database(schema_version)
        if connection.execute("PRAGMA application_id").fetchone() != (
            APPLICATION_ID,
        ) or _schema_identity(connection) != _schema_identity(expected):
            raise CorpusValidationError("unrelated or altered candidate schema")
        if (
            connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise CorpusValidationError("candidate database integrity checks failed")
        manifests = connection.execute(
            "SELECT singleton, manifest_json, logical_sha256 FROM candidate_manifest"
        ).fetchall()
        if len(manifests) != 1 or manifests[0][0] != 1:
            raise CorpusValidationError("candidate manifest is missing or ambiguous")
        _, manifest_bytes, logical_hash = manifests[0]
        if (
            type(manifest_bytes) is not bytes
            or len(manifest_bytes) > MAX_METADATA_BYTES
            or _sha(manifest_bytes) != logical_hash
        ):
            raise CorpusValidationError("candidate manifest digest differs")
        manifest = _json_object(manifest_bytes, "candidate manifest")
        source_rows = connection.execute(
            "SELECT * FROM candidate_sources ORDER BY snapshot_id"
        ).fetchall()
        if not 1 <= len(source_rows) <= MAX_SNAPSHOTS:
            raise CorpusValidationError("candidate source count exceeds bounds")
        sources = []
        for row in source_rows:
            snapshot_id, _, _, _, _, selection, receipt, permission, receipt_format = (
                row
            )
            saved = tuple(
                SavedEvidence(*item)
                for item in connection.execute(
                    "SELECT path, sha256, payload FROM candidate_permission_evidence WHERE snapshot_id = ? ORDER BY path",
                    (snapshot_id,),
                )
            )
            source = _from_buffers(
                selection, receipt, permission, saved, receipt_format
            )
            if row != _source_row(source):
                raise CorpusValidationError(
                    "stored source differs from admitted evidence"
                )
            sources.append(source)
        sources = _validated_sources(sources)
        rebuilt_manifest = _manifest(
            manifest.get("release_id"), sources, schema_version=schema_version
        )
        if rebuilt_manifest != manifest_bytes:
            raise CorpusValidationError(
                "candidate manifest claims differ from preparation evidence"
            )
        observations = tuple(
            record for source in sources for record in source.observations
        )
        expected_observations = sorted(
            (_observation_row(record) for record in observations),
            key=lambda row: row[0],
        )
        actual_observations = connection.execute(
            "SELECT * FROM candidate_observations ORDER BY observation_id"
        ).fetchall()
        if actual_observations != expected_observations:
            raise CorpusValidationError(
                "stored observations differ from saved source evidence"
            )
        expected_names = sorted(
            (row for record in observations for row in _name_rows(record)),
            key=lambda row: row[0],
        )
        if (
            connection.execute(
                "SELECT * FROM candidate_names ORDER BY evidence_id"
            ).fetchall()
            != expected_names
        ):
            raise CorpusValidationError(
                "stored names differ from complete source evidence"
            )
        if connection.execute(
            "SELECT COUNT(*) FROM candidate_permission_evidence"
        ).fetchone()[0] != sum(len(source.evidence) for source in sources):
            raise CorpusValidationError(
                "candidate artifact contains unreferenced evidence"
            )
        return CandidateRelease(
            manifest["release_id"],
            logical_hash,
            artifact_hash,
            manifest_bytes,
            sources,
            observations,
        )
    except (sqlite3.Error, TypeError, KeyError, UnicodeError) as exc:
        raise CorpusValidationError("malformed candidate artifact") from exc
    finally:
        if expected is not None:
            expected.close()
        connection.close()


def load_candidate_release(
    path: Path,
    *,
    expected_artifact_sha256: str | None = None,
) -> CandidateRelease:
    """Validate without creating files, opening a writable DB or consulting inputs.

    Without a trusted external digest, this detects internal corruption but cannot
    detect an adversary coherently replacing every input, manifest and digest.
    """
    payload = _read_saved(Path(path), MAX_RELEASE_BYTES, "candidate artifact")
    return _load_bytes(payload, expected_artifact_sha256)


def _publish_new(destination: Path, payload: bytes) -> None:
    """Validate a private staged file and publish it with one exclusive hard link.

    All writes use one pinned directory descriptor. The destination must have an
    existing real parent directory. Failure before link leaves no final artifact;
    a failure after link can leave only the already validated complete artifact.
    Existing files, directories and symlinks are never removed or replaced.
    """
    directory = _open_directory(destination.parent)
    temporary = f".candidate-{uuid.uuid4().hex}.tmp"
    descriptor = None
    created = False
    try:
        try:
            os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("candidate destination already exists")
        descriptor = os.open(
            temporary,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        created = True
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0:
                raise OSError("candidate staging write made no progress")
            view = view[count:]
        os.fsync(descriptor)
        before_validation = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        _load_bytes(b"".join(chunks), _sha(payload))
        if _fingerprint(os.fstat(descriptor)) != _fingerprint(before_validation):
            raise CorpusValidationError(
                "candidate staging file changed during validation"
            )
        pinned = os.fstat(directory)
        reopened = _open_directory(destination.parent)
        try:
            if (pinned.st_dev, pinned.st_ino) != (
                os.fstat(reopened).st_dev,
                os.fstat(reopened).st_ino,
            ):
                raise CorpusValidationError("candidate destination parent changed")
        finally:
            os.close(reopened)
        staged = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
        if _fingerprint(staged) != _fingerprint(os.fstat(descriptor)):
            raise CorpusValidationError("candidate staging file changed")
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        os.link(
            temporary,
            destination.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        os.fsync(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def build_candidate_release(
    destination: Path,
    sources: Iterable[PreparedSource],
    *,
    release_id: str,
) -> CandidateRelease:
    """Publish a new candidate file, with no overwrite, labels or acceptance claim.

    Preparation bounds limit bytes and records; they are not a demonstrated RSS
    limit. Use the separately approved acquisition/resource controls for real data.
    The returned artifact digest can be pinned by a later authorized workflow.
    """
    destination = Path(destination)
    if not destination.name or destination.name in {".", ".."}:
        raise CorpusValidationError("invalid candidate destination")
    checked = _validated_sources(sources)
    manifest = _manifest(release_id, checked)
    payload = _database_bytes(manifest, checked)
    result = _load_bytes(payload, _sha(payload))
    _publish_new(destination, payload)
    return result


def audit_candidate_release(
    path: Path,
    *,
    expected_artifact_sha256: str | None = None,
    require_reviewed_corpus: bool = False,
) -> dict:
    """Report preparation counts; fail closed on any reviewed/full-corpus request."""
    if type(require_reviewed_corpus) is not bool:
        raise CorpusValidationError(
            "reviewed-corpus requirement must be an explicit boolean"
        )
    release = load_candidate_release(
        path, expected_artifact_sha256=expected_artifact_sha256
    )
    if require_reviewed_corpus:
        raise CorpusValidationError(
            "prepared candidate is not an accepted reviewed corpus: "
            + "; ".join(_BLOCKERS)
        )
    return release.summary()
