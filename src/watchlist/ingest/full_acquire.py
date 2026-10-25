"""Separate fictional preparation and explicitly authorized direct acquisition.

The fictional API has no live fallback. Live APIs require an exact policy
digest, all hash-bound purpose grants and a permanent exclusive session claim.
Recovery binds a completed source separately from the newly approved requests.
Existing feasibility contexts/results retain their 200 record ceiling.
"""

from __future__ import annotations

from bisect import insort
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import time
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree

from watchlist.ingest._parse_common import (
    check_schema_version,
    children,
    expanded_tag,
    field_text,
    one,
    strict_json,
    unique_identifier,
    utf8_text,
    xml_root,
)
from watchlist.ingest.acquire import (
    HTTPTransport,
    Transport,
    _FetchFailure,
    _PrivateRun,
)
from watchlist.ingest.parse_eu import (
    NAME_ATTRIBUTES as EU_NAME_ATTRIBUTES,
    NAMESPACE as EU_NAMESPACE,
    parse_eu,
)
from watchlist.ingest.parse_ftm import NAME_FIELDS as FTM_NAME_FIELDS, parse_ftm
from watchlist.ingest.parse_ofac import (
    NAMESPACE as OFAC_NAMESPACE,
    _decode_zip_xml,
    _uid,
    parse_ofac,
)
from watchlist.ingest.resource_guard import (
    BULK_SOURCES,
    STEP08_LIMITS,
    BudgetLedger,
    ResourceGuard,
    ResourceStop,
    system_snapshot,
)
from watchlist.ingest.source_registry import (
    OFAC_OBJECT_HOST,
    OFAC_OBJECT_PATH,
    ParseContext,
    ParseResult,
    SourceRecord,
    SourceValidationError,
    strict_json_loads,
    validate_source_url,
)


RETENTION_LIMITS: Mapping[str, int] = MappingProxyType(
    {"opensanctions_un": 300, "ofac_sdn": 12_000, "eu_consolidated": 2_000}
)
FULL_PARSER_VERSION = "step08-full-fragments-v1"


class FullAcquisitionError(ValueError):
    """A policy, response or preparation boundary rejected the operation."""


def _native_tls_preflight(transport: Transport | None) -> None:
    """Check local native TLS trust before consuming an acquisition claim.

    This does not perform a handshake or alter certificate configuration. The
    native transport creates its default context from the same process setup.
    Fictional injected transports do not need a local TLS trust store.
    """
    if transport is not None and not isinstance(transport, HTTPTransport):
        return
    try:
        context = ssl.create_default_context()
    except (OSError, ValueError):
        raise FullAcquisitionError("tls_context_unavailable") from None
    if not isinstance(context, ssl.SSLContext):
        raise FullAcquisitionError("tls_context_invalid")
    if context.verify_mode != ssl.CERT_REQUIRED or context.check_hostname is not True:
        raise FullAcquisitionError("tls_verification_required")
    try:
        certificates = context.get_ca_certs(binary_form=True)
    except (OSError, ValueError):
        raise FullAcquisitionError("tls_trust_store_unavailable") from None
    if not certificates:
        raise FullAcquisitionError("tls_trust_store_empty")


def _safe_transport_failure_code(exc: Exception) -> str:
    """Classify failure types without retaining exception text or signed URLs."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "tls_certificate_verification_failed"
    if isinstance(exc, ssl.SSLError):
        return "tls_handshake_or_io_failed"
    if isinstance(exc, socket.gaierror):
        return "dns_resolution_failed"
    if isinstance(exc, ConnectionError):
        return "connection_failed"
    if isinstance(exc, http.client.HTTPException):
        return "http_framing_error"
    if isinstance(exc, _FetchFailure):
        return (
            "http_framing_error"
            if exc.code == "invalid_transfer_framing"
            else "transport_boundary_rejected"
        )
    if isinstance(exc, SourceValidationError):
        return "response_validation_failed"
    return "transport_io_failed"


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class FullSourcePolicy:
    """Exact routes and optional publisher pins for an offline preparation."""

    source_id: str
    url: str
    allowed_redirects: tuple[str, ...] = ()
    expected_sha256: str | None = None
    expected_bytes: int | None = None
    max_groups: int | None = None

    def __post_init__(self) -> None:
        if self.source_id not in BULK_SOURCES:
            raise FullAcquisitionError("source_not_in_full_bulk_profile")
        validate_source_url(self.source_id, self.url)
        if (
            not isinstance(self.allowed_redirects, tuple)
            or len(self.allowed_redirects) > 2
            or len(set(self.allowed_redirects)) != len(self.allowed_redirects)
            or self.url in self.allowed_redirects
        ):
            raise FullAcquisitionError("invalid_exact_redirect_routes")
        for route in self.allowed_redirects:
            validate_source_url(self.source_id, route)
        if self.expected_sha256 is not None and (
            not isinstance(self.expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256)
        ):
            raise FullAcquisitionError("invalid_publisher_sha256")
        if self.expected_bytes is not None and (
            type(self.expected_bytes) is not int
            or not 1
            <= self.expected_bytes
            <= STEP08_LIMITS[self.source_id].received_bytes
        ):
            raise FullAcquisitionError("invalid_publisher_size")
        cap = (
            RETENTION_LIMITS[self.source_id]
            if self.max_groups is None
            else self.max_groups
        )
        if type(cap) is not int or not 1 <= cap <= RETENTION_LIMITS[self.source_id]:
            raise FullAcquisitionError("retention_cap_exceeds_approval")
        object.__setattr__(self, "max_groups", cap)


@dataclass(frozen=True, slots=True)
class FullProfile:
    sources: tuple[FullSourcePolicy, ...]
    policy_sha256: str
    live_authorized: bool = False


def prepare_full_profile(sources: tuple[FullSourcePolicy, ...]) -> FullProfile:
    """Validate a separate full policy without changing feasibility contracts.

    This validates preparation, not licenses, current endpoints, reviewer access
    or independent custody. Those remain prerequisites to any future live path.
    """
    if not isinstance(sources, tuple) or not 1 <= len(sources) <= 3:
        raise FullAcquisitionError("invalid_full_source_count")
    if any(type(source) is not FullSourcePolicy for source in sources):
        raise FullAcquisitionError("invalid_full_source_policy")
    if len({source.source_id for source in sources}) != len(sources):
        raise FullAcquisitionError("duplicate_full_source")
    canonical = {
        "scope": "08B-0-offline-fictional-only",
        "sources": [asdict(source) for source in sources],
        "limits": {name: asdict(value) for name, value in STEP08_LIMITS.items()},
        "live_authorized": False,
    }
    return FullProfile(sources, hashlib.sha256(_json_bytes(canonical)).hexdigest())


@dataclass(frozen=True, slots=True)
class FullParseResult:
    """Full source-local selection; never an identity finding or a label set."""

    source_id: str
    records: tuple[SourceRecord, ...]
    input_records: int
    excluded_person_records: int
    excluded_other_records: int
    excluded_by_limit: int
    input_sha256: str
    parser_version: str = FULL_PARSER_VERSION
    source_version: str | None = None
    source_version_field: str | None = None
    container_format: str | None = None
    container_member: str | None = None
    decoded_bytes: int | None = None
    decoded_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.source_id not in RETENTION_LIMITS or not isinstance(
            self.records, tuple
        ):
            raise SourceValidationError("invalid full result source or records")
        if len(self.records) > RETENTION_LIMITS[self.source_id]:
            raise SourceValidationError("full selection exceeds source retention cap")
        if any(
            not isinstance(record, SourceRecord) or record.source_id != self.source_id
            for record in self.records
        ):
            raise SourceValidationError("invalid full result record source")
        if len({record.provider_id for record in self.records}) != len(self.records):
            raise SourceValidationError("duplicate full result provider ID")
        # Reuse the old metadata validators with an EMPTY record tuple. No
        # enlarged context/result is ever passed to a feasibility adapter.
        metadata = {
            key: getattr(self, key)
            for key in (
                "input_records",
                "excluded_person_records",
                "excluded_other_records",
                "excluded_by_limit",
                "input_sha256",
                "parser_version",
                "source_version",
                "source_version_field",
                "container_format",
                "container_member",
                "decoded_bytes",
                "decoded_sha256",
            )
        }
        metadata["records"] = ()
        ParseResult(**metadata)
        if self.input_records != (
            len(self.records)
            + self.excluded_person_records
            + self.excluded_other_records
            + self.excluded_by_limit
        ):
            raise SourceValidationError("full record accounting is inconsistent")


def parse_full_payload(
    payload: bytes,
    policy: FullSourcePolicy,
    *,
    checkpoint: Callable[[], object] = lambda: None,
) -> FullParseResult:
    """Validate every source record, preserving aliases without truncation.

    Only a bounded lexicographic selection is retained in memory. Provider IDs
    are checked across all records, including excluded people. Whole-source
    hashes and publication metadata refer to the original input, not fragments.
    The checkpoint is cooperative; use process supervision for a blocking parse.
    """
    if type(policy) is not FullSourcePolicy:
        raise SourceValidationError("invalid full parser policy")
    if (
        type(payload) is not bytes
        or not 1 <= len(payload) <= STEP08_LIMITS[policy.source_id].received_bytes
    ):
        raise SourceValidationError("full input exceeds its source byte bound")
    digest = hashlib.sha256(payload).hexdigest()
    if policy.expected_sha256 is not None and digest != policy.expected_sha256:
        raise SourceValidationError("full input publisher digest mismatch")
    if policy.expected_bytes is not None and len(payload) != policy.expected_bytes:
        raise SourceValidationError("full input publisher size mismatch")
    checkpoint()
    context = ParseContext(source_id=policy.source_id)
    selected: list[tuple[str, SourceRecord]] = []
    seen: set[str] = set()
    counts = {"input": 0, "people": 0, "other": 0, "eligible": 0}
    metadata: dict = {}

    def accept(result: ParseResult) -> None:
        if result.input_records != 1 or result.excluded_by_limit:
            raise SourceValidationError(
                "fragment parser must account for exactly one record"
            )
        counts["input"] += 1
        counts["people"] += result.excluded_person_records
        counts["other"] += result.excluded_other_records
        for record in result.records:
            counts["eligible"] += 1
            item = (record.qualified_id, record)
            if len(selected) < policy.max_groups:
                insort(selected, item)
            elif item[0] < selected[-1][0]:
                selected.pop()
                insort(selected, item)
        checkpoint()

    if policy.source_id == "opensanctions_un":
        for line in io.StringIO(utf8_text(payload)):
            if not line.strip():
                continue
            raw = strict_json(line)
            if not isinstance(raw, dict):
                raise SourceValidationError("FTM record must be an object")
            unique_identifier(raw.get("id"), seen)
            accept(parse_ftm(line.encode("utf-8"), context=context))
    else:
        if policy.source_id == "ofac_sdn":
            if not payload.startswith(b"PK"):
                raise SourceValidationError(
                    "full OFAC route requires the reviewed ZIP container"
                )
            decoded = _decode_zip_xml(payload)
            checkpoint()
            root = xml_root(
                utf8_text(decoded),
                root_name="sdnList",
                namespaces=frozenset({OFAC_NAMESPACE}),
            )
            check_schema_version(root)
            if any(
                expanded_tag(child.tag)[1] not in {"publshInformation", "sdnEntry"}
                for child in root
            ):
                raise SourceValidationError("unsupported OFAC top-level structure")
            publication = one(root, "publshInformation")
            version = field_text(publication, "Publish_Date", required=False)
            declared = field_text(publication, "Record_Count", required=False)
            entries = children(root, "sdnEntry")
            if declared is not None and (
                not re.fullmatch(r"[0-9]{1,9}", declared)
                or int(declared) != len(entries)
            ):
                raise SourceValidationError("OFAC whole-document record count mismatch")
            metadata = {
                "source_version": version,
                "source_version_field": "sdnList.publshInformation.Publish_Date"
                if version is not None
                else None,
                "container_format": "zip",
                "container_member": "SDN.XML",
                "decoded_bytes": len(decoded),
                "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
            }
            for entry in entries:
                provider_id = _uid(entry)
                unique_identifier(provider_id, seen)
                fragment = ElementTree.Element(root.tag, dict(root.attrib))
                fragment_publication = deepcopy(publication)
                fragment_count = one(
                    fragment_publication, "Record_Count", required=False
                )
                if fragment_count is not None:
                    fragment_count.text = "1"
                fragment.append(fragment_publication)
                fragment.append(entry)
                accept(
                    parse_ofac(
                        ElementTree.tostring(fragment, encoding="utf-8"),
                        context=context,
                    )
                )
        else:
            root = xml_root(
                utf8_text(payload),
                root_name="export",
                namespaces=frozenset({EU_NAMESPACE}),
            )
            check_schema_version(root)
            if any(expanded_tag(child.tag)[1] != "sanctionEntity" for child in root):
                raise SourceValidationError("unsupported EU top-level structure")
            # Validate root metadata even for an empty document. The fragment
            # keeps every root attribute, including xml:lang inheritance.
            empty_root = ElementTree.Element(root.tag, dict(root.attrib))
            root_result = parse_eu(
                ElementTree.tostring(empty_root, encoding="utf-8"), context=context
            )
            metadata = {
                "source_version": root_result.source_version,
                "source_version_field": root_result.source_version_field,
            }
            for entry in children(root, "sanctionEntity"):
                unique_identifier(entry.get("logicalId"), seen)
                fragment = ElementTree.Element(root.tag, dict(root.attrib))
                fragment.append(entry)
                accept(
                    parse_eu(
                        ElementTree.tostring(fragment, encoding="utf-8"),
                        context=context,
                    )
                )
    if counts["input"] == 0:
        raise SourceValidationError("full input contains no records")
    checkpoint()
    return FullParseResult(
        source_id=policy.source_id,
        records=tuple(record for _, record in selected),
        input_records=counts["input"],
        excluded_person_records=counts["people"],
        excluded_other_records=counts["other"],
        excluded_by_limit=counts["eligible"] - len(selected),
        input_sha256=digest,
        **metadata,
    )


@dataclass(frozen=True, slots=True)
class FictionalReply:
    """Finite response bytes supplied by a test; no sockets or arbitrary reader."""

    body: bytes
    status: int = 200
    headers: tuple[tuple[str, str], ...] = ()
    response_url: str | None = None
    chunk_bytes: int = 64 * 1024
    fail_after_bytes: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.body) is not bytes
            or type(self.status) is not int
            or not 100 <= self.status <= 599
        ):
            raise FullAcquisitionError("invalid_fictional_reply")
        if type(self.chunk_bytes) is not int or self.chunk_bytes < 1:
            raise FullAcquisitionError("invalid_fictional_chunk_size")
        if self.fail_after_bytes is not None and (
            type(self.fail_after_bytes) is not int or self.fail_after_bytes < 0
        ):
            raise FullAcquisitionError("invalid_fictional_failure_offset")
        if not isinstance(self.headers, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or any(not isinstance(value, str) for value in pair)
            for pair in self.headers
        ):
            raise FullAcquisitionError("invalid_fictional_headers")


class _FictionalResponse:
    def __init__(self, url: str, reply: FictionalReply) -> None:
        self.url = reply.response_url or url
        self.status = reply.status
        self.headers = reply.headers
        self._reply = reply
        self._position = 0
        self.closed = False

    @property
    def body_complete(self) -> bool:
        """Prove finite fictional body completion without an over-budget read."""
        return self._position == len(self._reply.body)

    def read(self, size: int, *, timeout: float) -> bytes:
        if self.closed or size <= 0 or timeout <= 0:
            raise FullAcquisitionError("invalid_fictional_read")
        if (
            self._reply.fail_after_bytes is not None
            and self._position >= self._reply.fail_after_bytes
        ):
            raise OSError("fictional interrupted response")
        end = self._position + min(size, self._reply.chunk_bytes)
        result = self._reply.body[self._position : end]
        self._position += len(result)
        return result

    def close(self) -> None:
        self.closed = True


class FictionalTransport:
    """Sealed acquisition boundary that can only return supplied memory bytes."""

    def __init__(self, replies: Mapping[str, tuple[FictionalReply, ...]]) -> None:
        self._replies = {}
        for url, outcomes in replies.items():
            if (
                not isinstance(url, str)
                or not isinstance(outcomes, tuple)
                or any(type(outcome) is not FictionalReply for outcome in outcomes)
            ):
                raise FullAcquisitionError("invalid_fictional_transport")
            self._replies[url] = list(outcomes)
        self.calls: list[str] = []
        self.responses: list[_FictionalResponse] = []

    def open(self, url: str, *, timeout: float) -> _FictionalResponse:
        if timeout <= 0:
            raise FullAcquisitionError("fictional_open_deadline")
        self.calls.append(url)
        if not self._replies.get(url):
            raise OSError("no fictional response provided")
        response = _FictionalResponse(url, self._replies[url].pop(0))
        self.responses.append(response)
        return response


def _response_headers(response: _FictionalResponse) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in response.headers:
        lowered = key.lower()
        if lowered in headers:
            raise FullAcquisitionError("duplicate_response_header")
        if any(character in key + value for character in "\r\n\x00"):
            raise FullAcquisitionError("invalid_response_header")
        headers[lowered] = value
    if headers.get("content-encoding", "identity").lower() != "identity":
        raise FullAcquisitionError("unexpected_content_encoding")
    return headers


def _transfer_fictional(
    policy: FullSourcePolicy,
    transport: FictionalTransport,
    ledger: BudgetLedger,
    guard: ResourceGuard,
    journal: Callable[[], None],
) -> bytes:
    url = policy.url
    visited: set[str] = set()
    for redirect_number in range(3):
        guard.check()
        if url in visited or (
            url != policy.url and url not in policy.allowed_redirects
        ):
            raise FullAcquisitionError("unreviewed_or_repeated_redirect")
        validate_source_url(policy.source_id, url)
        visited.add(url)
        ticket = ledger.begin_request(policy.source_id)
        journal()  # A crash leaves the whole possible response reserved.
        response = None
        try:
            response = transport.open(url, timeout=ledger.remaining_seconds(ticket))
            if response.url != url:
                raise FullAcquisitionError("automatic_transport_redirect_forbidden")
            headers = _response_headers(response)
            declared = headers.get("content-length")
            if declared is not None:
                if not re.fullmatch(r"[0-9]{1,12}", declared):
                    raise FullAcquisitionError("invalid_content_length")
                ledger.declare_length(ticket, int(declared))
            body = bytearray()
            while True:
                guard.check()
                remaining = ledger.remaining_bytes(ticket)
                if declared is not None and len(body) == int(declared):
                    if not response.body_complete:
                        raise FullAcquisitionError(
                            "declared_length_hides_trailing_body"
                        )
                    break
                if remaining <= 0:
                    if response.body_complete:
                        break
                    raise FullAcquisitionError("body_limit_before_eof")
                size = min(64 * 1024, remaining)
                if declared is not None:
                    size = min(size, int(declared) - len(body))
                block = response.read(size, timeout=ledger.remaining_seconds(ticket))
                try:
                    ledger.charge_received(ticket, len(block))
                finally:
                    journal()
                if len(block) > size:
                    raise FullAcquisitionError("response_exceeded_requested_read")
                if not block:
                    break
                body.extend(block)
                guard.check()
            if declared is not None and len(body) != int(declared):
                raise FullAcquisitionError("incomplete_declared_body")
            ledger.remaining_seconds(ticket)
            if response.status in {301, 302, 303, 307, 308}:
                if redirect_number >= 2:
                    raise FullAcquisitionError("redirect_limit")
                destination = headers.get("location")
                if destination not in policy.allowed_redirects:
                    raise FullAcquisitionError("unreviewed_redirect_destination")
                url = destination
                continue
            if response.status != 200:
                raise FullAcquisitionError("http_status_rejected")
            return bytes(body)
        finally:
            if response is not None:
                response.close()
            ledger.finish_request(ticket)
            journal()
    raise FullAcquisitionError("redirect_limit")


def _selection_bytes(
    result: FullParseResult, maximum: int, checkpoint: Callable[[], object]
) -> bytes:
    selected = bytearray()
    for record in result.records:
        line = _json_bytes(
            {
                **asdict(record),
                "qualified_id": record.qualified_id,
                "source_role": "sanctions_reference",
            }
        )
        if len(selected) + len(line) > maximum:
            raise ResourceStop("normalized_byte_limit")
        selected.extend(line)
        checkpoint()
    return bytes(selected)


def acquire_fictional(
    profile: FullProfile,
    output: Path,
    *,
    transport: FictionalTransport,
    ledger: BudgetLedger,
    guard: ResourceGuard,
) -> dict:
    """Exercise admission, transfer, parsing and private publication offline.

    A concrete ``FictionalTransport`` is mandatory. A caller-supplied boolean,
    policy digest or folder does not authorize live data. No existing output is
    reopened, no resume is offered, and no raw mixed-source body is written.
    A single shared ledger/guard retains counters across the whole session.
    """
    if type(transport) is not FictionalTransport:
        raise FullAcquisitionError("live_transport_not_authorized")
    if type(profile) is not FullProfile or profile != prepare_full_profile(
        profile.sources
    ):
        raise FullAcquisitionError("invalid_or_live_full_profile")
    if guard.admitted:
        guard.check()
    else:
        guard.admit()
    # Reserve aggregate failure evidence before creating a private run.
    guard.reserve_artifact(65_536)
    run = _PrivateRun(Path(output))
    sequence = 0
    receipt = {
        "schema_version": 1,
        "scope": "08B-0-offline-fictional-only",
        "policy_sha256": profile.policy_sha256,
        "status": "running",
        "live_authorized": False,
        "independent_custody_verified": False,
        "selection_use": "fictional-development-only",
        "sources": [],
        "resume_supported": False,
    }

    def publish(name: str, payload: bytes, *, normalized: bool = False) -> None:
        ledger.remaining_seconds()
        guard.reserve_artifact(len(payload), normalized=normalized)
        run.publish(name, payload)
        guard.check()
        ledger.remaining_seconds()

    def journal() -> None:
        nonlocal sequence
        sequence += 1
        publish(f"ledger-{sequence:06d}.json", _json_bytes(ledger.receipt()))

    # A fixed bounded emergency receipt allowance is reserved before any
    # transfer; later resource breaches must not prevent aggregate evidence.
    active_source = None
    try:
        publish(
            "preparation.json",
            _json_bytes(
                {
                    "scope": receipt["scope"],
                    "policy_sha256": profile.policy_sha256,
                    "sources": [asdict(source) for source in profile.sources],
                    "live_authorized": False,
                }
            ),
        )
        pending: list[tuple[str, bytes]] = []
        pending_bytes = 0
        for policy in profile.sources:
            ledger.begin_source(policy.source_id)
            active_source = policy.source_id
            journal()
            payload = _transfer_fictional(policy, transport, ledger, guard, journal)

            def checkpoint() -> None:
                guard.check()
                ledger.remaining_seconds()

            result = parse_full_payload(payload, policy, checkpoint=checkpoint)
            selection = _selection_bytes(
                result,
                guard.limits.max_normalized_bytes
                - pending_bytes
                - guard.normalized_bytes,
                checkpoint,
            )
            pending_bytes += len(selection)
            pending.append((f"{policy.source_id}.jsonl", selection))
            receipt["sources"].append(
                {
                    "source_id": policy.source_id,
                    "input_sha256": result.input_sha256,
                    "input_bytes": len(payload),
                    "input_records": result.input_records,
                    "retained_groups": len(result.records),
                    "excluded_person_records": result.excluded_person_records,
                    "excluded_other_records": result.excluded_other_records,
                    "excluded_by_limit": result.excluded_by_limit,
                    "parser_version": result.parser_version,
                    "source_version": result.source_version,
                    "source_version_field": result.source_version_field,
                    "container_format": result.container_format,
                    "container_member": result.container_member,
                    "decoded_bytes": result.decoded_bytes,
                    "decoded_sha256": result.decoded_sha256,
                    "selection_sha256": hashlib.sha256(selection).hexdigest(),
                    "selection_bytes": len(selection),
                }
            )
            del payload, result, selection
            ledger.finish_source(policy.source_id)
            active_source = None
            journal()
        for name, payload in pending:
            publish(name, payload, normalized=True)
        receipt["status"] = "passed"
    except (FullAcquisitionError, ResourceStop, SourceValidationError, OSError) as exc:
        receipt["status"] = "failed"
        receipt["stop_reason"] = (
            exc.code
            if isinstance(exc, ResourceStop)
            else str(exc)
            if isinstance(exc, FullAcquisitionError)
            else "source_validation_failed"
            if isinstance(exc, SourceValidationError)
            else "transport_or_storage_error"
        )
        receipt["failed_source"] = active_source
    finally:
        receipt["ledger"] = ledger.receipt()
        receipt["peak_sampled_rss_bytes"] = guard.peak_rss_bytes
        receipt["rss_enforcement"] = (
            "cooperative-checks; use-supervise_command-for-worker-termination"
        )
        receipt_bytes = _json_bytes(receipt)
        try:
            if len(receipt_bytes) > 65_536:
                raise FullAcquisitionError("emergency_receipt_exceeds_reservation")
            run.publish("receipt.json", receipt_bytes)
        finally:
            run.close()
    return receipt


# Recovery is a separately approved session. The original live policy and
# receipt contract remain unchanged.
RECOVERY_SCOPE = "08B-2R-development-candidate-recovery-v1"
RECOVERY_POLICY_SCOPE = "08B-2R-ofac-eu-recovery-acquisition"
RECOVERY_OFAC_REDIRECT = (
    "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/"
    "Published/c855675f-4385-4bb5-b89a-59ccb73a83e6/2026-10-20/"
    "4166a9f5-d268-432a-a70b-65bd16bcd16a/SDN_XML.ZIP"
)
RECOVERY_LIMITS = {
    "total_bytes": 34_000_000,
    "transactions": 3,
    "max_attempts": 1,
    "max_redirects": 1,
    "session_seconds": 3600,
}
RECOVERY_SOURCE_IDS = ("ofac_sdn", "eu_consolidated")
CONTINUATION_POLICY_SCOPE = "08B-2R-ofac-eu-continuation-acquisition"
CONTINUATION_SCOPE = "08B-2R-development-candidate-continuation-v1"
CONTINUATION_LIMITS = {**RECOVERY_LIMITS, "total_bytes": 30_000_000}


@dataclass(frozen=True, slots=True)
class RecoveryExecutionPolicy:
    """New approval plus a pinned completed source from an interrupted session."""

    data: dict
    policy_path: str
    policy_sha256: str
    policy_bytes: bytes
    project_root: Path
    grants: Mapping[str, dict]
    evidence: tuple[dict, ...]
    reused_row: dict
    reused_selection: bytes
    prior_accounting: dict


def _recovery_permission(
    grant: dict, source_id: str, approval: dict, *, reused: bool = False
) -> None:
    """Require the same narrow name fields and development-only purpose."""
    fields_allowed = _GRANT_FIELDS | ({"recovery_binding"} if reused else set())
    _object_fields(grant, fields_allowed, "recovery_grant")
    binding = dict(_BINDING)
    if not reused:
        del binding["require_complete_direct_200"]
        binding["require_complete_approved_200"] = True
    if (
        type(grant["schema_version"]) is not int
        or grant["schema_version"] != 1
        or grant["grant_kind"] != "prospective_source_purpose"
        or grant["source_id"] != source_id
        or grant["status"] != "approved"
        or grant["purpose"] != _PURPOSE
        or grant["approval"] != approval
        or grant["exact_url"] != LIVE_URLS[source_id]
        or grant["source_role"] != "sanctions_reference"
        or grant["development_exposed_only"] is not True
        or grant["final_eligible"] is not False
        or grant["raw_retention_allowed"] is not False
        or grant["transient_full_response_allowed"] is not True
        or grant["prospective_binding"] != binding
        or any(
            type(value) is not bool for value in grant["prospective_binding"].values()
        )
    ):
        raise FullAcquisitionError("unapproved_recovery_permission")
    for name, expected in (
        ("operations", _OPERATIONS),
        ("record_fields", _RECORD_FIELDS),
        ("alias_fields", _ALIAS_FIELDS),
        (
            "entity_types",
            {"organization"}
            if source_id == "eu_consolidated"
            else {"organization", "vessel"},
        ),
    ):
        if _string_set(grant[name], name) != expected:
            raise FullAcquisitionError("incomplete_recovery_field_permission")
    if (
        not isinstance(grant["name_fields"], dict)
        or {
            key: _string_set(value, "name_attributes")
            for key, value in grant["name_fields"].items()
        }
        != _NAME_FIELDS[source_id]
    ):
        raise FullAcquisitionError("incomplete_recovery_name_permission")
    for name in ("review_id", "reviewer", "reviewed_at", "attribution", "license"):
        _text_value(grant[name], name)
    try:
        reviewed = datetime.fromisoformat(grant["reviewed_at"])
        if reviewed.tzinfo is None:
            raise ValueError
    except ValueError:
        raise FullAcquisitionError("invalid_permission_review_date") from None
    if not _string_set(grant["conditions"], "conditions"):
        raise FullAcquisitionError("permission_conditions_required")


def load_recovery_execution_policy(
    path: Path, *, project_root: Path, expected_policy_sha256: str
) -> RecoveryExecutionPolicy:
    """Validate all new grants and old completed evidence before any request.

    Only the pinned old source row is reused. An absent original final receipt
    remains absent; this loader does not repair or complete the old session.
    """
    root = Path(project_root).resolve(strict=True)
    policy_path = Path(path)
    if policy_path.is_absolute():
        try:
            policy_path = policy_path.relative_to(root)
        except ValueError:
            raise FullAcquisitionError("policy_outside_project") from None
    relative = _relative_path(policy_path.as_posix()).as_posix()
    payload = _local_bytes(root, relative)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != _digest_value(expected_policy_sha256):
        raise FullAcquisitionError("execution_policy_digest_mismatch")
    raw = strict_json_loads(payload)
    continuation = (
        isinstance(raw, dict) and raw.get("scope") == CONTINUATION_POLICY_SCOPE
    )
    data = _object_fields(
        raw,
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
        "recovery_policy",
    )
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or data["scope"]
        != (CONTINUATION_POLICY_SCOPE if continuation else RECOVERY_POLICY_SCOPE)
        or data["limits"] != (CONTINUATION_LIMITS if continuation else RECOVERY_LIMITS)
        or any(type(value) is not int for value in data["limits"].values())
    ):
        raise FullAcquisitionError("unapproved_recovery_scope_or_limits")
    _relative_path(data["session_claim_path"])
    evidence = {relative: digest}

    def verified(reference: object) -> bytes:
        item = _object_fields(reference, {"path", "sha256"}, "recovery_reference")
        name = _relative_path(item["path"]).as_posix()
        expected = _digest_value(item["sha256"])
        if name in evidence and evidence[name] != expected:
            raise FullAcquisitionError("conflicting_evidence_digest")
        if len(evidence) >= 128:
            raise FullAcquisitionError("recovery_evidence_limit")
        contents = _local_bytes(root, name)
        if hashlib.sha256(contents).hexdigest() != expected:
            raise FullAcquisitionError("recovery_evidence_digest_mismatch")
        evidence[name] = expected
        return contents

    verified(data["approval"])
    if continuation:
        _validate_continuation(data, root, verified)
    sources = data["sources"]
    if not isinstance(sources, list) or [
        s.get("source_id") for s in sources if isinstance(s, dict)
    ] != list(RECOVERY_SOURCE_IDS):
        raise FullAcquisitionError("recovery_requires_ofac_then_eu")
    grants = {}
    for source in sources:
        _object_fields(
            source,
            _SOURCE_POLICY_FIELDS
            | {"transactions", "content_length_required", "expected_decoded_bytes"},
            "recovery_source",
        )
        source_id = source["source_id"]
        if (
            source["url"] != LIVE_URLS[source_id]
            or source["content_length_required"] is not True
        ):
            raise FullAcquisitionError("unapproved_recovery_route_or_length_gate")
        if source["allowed_redirects"] != (
            [RECOVERY_OFAC_REDIRECT] if source_id == "ofac_sdn" else []
        ):
            raise FullAcquisitionError("unapproved_recovery_redirect")
        for name, expected in (
            ("received_bytes", STEP08_LIMITS[source_id].received_bytes),
            ("max_groups", RETENTION_LIMITS[source_id]),
            ("request_seconds", STEP08_LIMITS[source_id].request_seconds),
            ("source_seconds", STEP08_LIMITS[source_id].source_seconds),
            ("transactions", 2 if source_id == "ofac_sdn" else 1),
        ):
            if type(source[name]) is not int or source[name] != expected:
                raise FullAcquisitionError("unapproved_recovery_source_limits")
        FullSourcePolicy(
            source_id,
            source["url"],
            expected_sha256=source["expected_sha256"],
            expected_bytes=source["expected_bytes"],
            max_groups=source["max_groups"],
        )
        if source_id == "ofac_sdn":
            if (
                source["decoded_bytes"] != 32_000_000
                or type(source["decoded_bytes"]) is not int
            ):
                raise FullAcquisitionError("unapproved_ofac_decoded_limit")
            if (
                type(source["expected_decoded_bytes"]) is not int
                or not 1 <= source["expected_decoded_bytes"] <= source["decoded_bytes"]
                or source["expected_bytes"] is None
            ):
                raise FullAcquisitionError("ofac_recovery_size_pins_required")
            _digest_value(source["expected_decoded_sha256"])
        elif any(
            source[name] is not None
            for name in (
                "decoded_bytes",
                "expected_bytes",
                "expected_decoded_bytes",
                "expected_decoded_sha256",
                "expected_sha256",
                "expected_sha1",
            )
        ):
            raise FullAcquisitionError("eu_recovery_has_no_exact_publisher_pin")
        if source["expected_sha1"] is not None:
            _digest_value(source["expected_sha1"], length=40)
        grant = strict_json_loads(
            verified(
                {
                    "path": source["permission_path"],
                    "sha256": source["permission_sha256"],
                }
            )
        )
        _recovery_permission(grant, source_id, data["approval"])
        grants[source_id] = grant

    reuse = _object_fields(
        data["reuse_completed_source"],
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
        "reused_source",
    )
    if reuse["source_id"] != "opensanctions_un":
        raise FullAcquisitionError("only_completed_opensanctions_may_be_reused")
    old_buffers = {
        name: verified(reuse[name])
        for name in (
            "policy",
            "claim",
            "interruption_assessment",
            "completed_journal",
            "selection",
            "permission",
            "recovery_permission",
        )
    }
    original = load_execution_policy(
        root / reuse["policy"]["path"],
        project_root=root,
        expected_policy_sha256=reuse["policy"]["sha256"],
    )
    for item in original.evidence:
        verified(item)
    old_source = next(
        item
        for item in original.data["sources"]
        if item["source_id"] == "opensanctions_un"
    )
    if reuse["permission"] != {
        "path": old_source["permission_path"],
        "sha256": old_source["permission_sha256"],
    }:
        raise FullAcquisitionError("reused_original_permission_mismatch")
    claim = strict_json_loads(old_buffers["claim"])
    old_output = Path(claim.get("output", ""))
    if (
        claim.get("scope") != LIVE_SCOPE
        or claim.get("policy_sha256") != original.policy_sha256
        or claim.get("resume_supported") is not False
        or reuse["claim"]["path"] != original.data["session_claim_path"]
        or not old_output.is_absolute()
        or not old_output.is_relative_to(root)
        or root / reuse["policy"]["path"] != old_output / "execution-policy.json"
        or (old_output / "receipt.json").exists()
        or data["session_claim_path"] == original.data["session_claim_path"]
    ):
        raise FullAcquisitionError("invalid_interrupted_session_claim")
    journal = strict_json_loads(old_buffers["completed_journal"])
    if (
        journal.get("policy_sha256") != original.policy_sha256
        or (root / reuse["completed_journal"]["path"]).parent != old_output
    ):
        raise FullAcquisitionError("reused_journal_policy_or_session_mismatch")
    rows = [
        row
        for row in journal.get("sources", [])
        if row.get("source_id") == "opensanctions_un"
    ]
    if len(rows) != 1:
        raise FullAcquisitionError("completed_source_row_required")
    row = rows[0]
    if (
        row.get("status") != "passed"
        or row.get("complete") is not True
        or row.get("http_status") != 200
        or row.get("transaction_count") != 1
        or row.get("permission") != reuse["permission"]
        or row.get("requested_url") != old_source["url"]
        or row.get("final_url") != old_source["url"]
        or row.get("input_sha256") != row.get("body_sha256")
        or row.get("input_bytes") != row.get("bytes_received")
        or row.get("selection_sha256") != reuse["selection"]["sha256"]
        or row.get("selection_bytes") != len(old_buffers["selection"])
        or root / reuse["selection"]["path"] != old_output / "opensanctions_un.jsonl"
        or row.get("selection_path") != "opensanctions_un.jsonl"
    ):
        raise FullAcquisitionError("incomplete_or_cross_session_reused_source")
    selected = [
        strict_json_loads(line) for line in old_buffers["selection"].splitlines()
    ]
    if not 1 <= len(selected) == row.get("retained_groups") <= RETENTION_LIMITS[
        "opensanctions_un"
    ] or len({item.get("qualified_id") for item in selected}) != len(selected):
        raise FullAcquisitionError("reused_selection_count_or_identifiers")
    for item in selected:
        _object_fields(item, _RECORD_FIELDS, "reused_selection_record")
        if (
            item["source_id"] != "opensanctions_un"
            or item["source_role"] != "sanctions_reference"
            or item["entity_type"] not in {"organization", "vessel"}
        ):
            raise FullAcquisitionError("unapproved_reused_selection_record")
    assessment = strict_json_loads(old_buffers["interruption_assessment"])

    def pair(value: dict) -> dict:
        return {name: value[name] for name in ("path", "sha256")}

    if (
        assessment.get("scope") != "08B-2-offline-interruption-assessment-v1"
        or assessment.get("assessment_status") != "persisted_evidence_consistent"
        or pair(assessment["claim"]["evidence"]) != reuse["claim"]
        or pair(assessment["policy"]["execution_policy_copy"]) != reuse["policy"]
        or [
            item["persisted_row"]
            for item in assessment["sources"]
            if item["source_id"] == "opensanctions_un"
        ]
        != [row]
        or assessment["artifact_state"]["final_acquisition_receipt_exists"] is not False
    ):
        raise FullAcquisitionError("interruption_assessment_mismatch")
    last_journal = strict_json_loads(verified(pair(assessment["journals"]["last"])))
    if (
        last_journal["policy_sha256"] != original.policy_sha256
        or last_journal["ledger"] != assessment["journals"]["last_ledger"]
    ):
        raise FullAcquisitionError("interruption_final_journal_mismatch")
    prior = {
        name: assessment["accounting"][name]
        for name in (
            "persisted_received_body_bytes_lower_bound",
            "conservative_active_response_reservation_bytes",
            "received_plus_reservation_bytes",
        )
    }
    if any(type(value) is not int or value < 0 for value in prior.values()) or (
        prior["persisted_received_body_bytes_lower_bound"]
        != last_journal["ledger"]["total_received_bytes"]
        or prior["conservative_active_response_reservation_bytes"]
        != last_journal["ledger"]["active_response_reservation"]
        or prior["received_plus_reservation_bytes"] != sum(list(prior.values())[:2])
        or prior["received_plus_reservation_bytes"] > 39_000_000
    ):
        raise FullAcquisitionError("interrupted_session_accounting_mismatch")
    grant = strict_json_loads(old_buffers["recovery_permission"])
    _recovery_permission(grant, "opensanctions_un", data["approval"], reused=True)
    expected_binding = {
        "original_policy": reuse["policy"],
        "original_claim": reuse["claim"],
        "interruption_assessment": reuse["interruption_assessment"],
        "completed_journal": reuse["completed_journal"],
        "selection": reuse["selection"],
        "original_permission": reuse["permission"],
        "original_final_receipt_absent": True,
        "original_session_remains_interrupted": True,
        "cross_session_manifest_required": True,
    }
    if grant["recovery_binding"] != expected_binding:
        raise FullAcquisitionError("unapproved_recovery_binding")
    for name in (
        "review_id",
        "reviewer",
        "reviewed_at",
        "operations",
        "record_fields",
        "alias_fields",
        "entity_types",
        "name_fields",
    ):
        if grant[name] != original.grants["opensanctions_un"][name]:
            raise FullAcquisitionError("reused_review_metadata_changed")
    grants["opensanctions_un"] = grant
    for grant in grants.values():
        if not isinstance(grant["evidence"], list) or not grant["evidence"]:
            raise FullAcquisitionError("recovery_permission_evidence_required")
        names = set()
        for item in grant["evidence"]:
            verified(item)
            if item["path"] in names:
                raise FullAcquisitionError("duplicate_grant_evidence")
            names.add(item["path"])
        if data["approval"]["path"] not in names:
            raise FullAcquisitionError("grant_approval_evidence_missing")
    return RecoveryExecutionPolicy(
        data,
        relative,
        digest,
        payload,
        root,
        MappingProxyType(grants),
        tuple(
            {"path": name, "sha256": value} for name, value in sorted(evidence.items())
        ),
        deepcopy(row),
        old_buffers["selection"],
        prior,
    )


def _validate_continuation(data: dict, root: Path, verified: Callable) -> None:
    """Bind exactly one failed recovery; never refund its unresolved reservation."""
    binding = _object_fields(
        data["continuation"],
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
        "continuation_binding",
    )
    for key, expected in {
        "carried_reservation_bytes": 4_000_000,
        "prior_charged_transactions": 1,
        "cumulative_transaction_limit": 4,
        "recovery_ceiling_bytes": 34_000_000,
    }.items():
        if type(binding[key]) is not int or binding[key] != expected:
            raise FullAcquisitionError("unapproved_continuation_accounting")
    if binding["release_authorized"] is not False:
        raise FullAcquisitionError("continuation_release_forbidden")
    prior_data = strict_json_loads(verified(binding["policy"]))
    if prior_data.get("scope") != RECOVERY_POLICY_SCOPE:
        raise FullAcquisitionError("continuation_requires_original_recovery")
    previous = load_recovery_execution_policy(
        root / binding["policy"]["path"],
        project_root=root,
        expected_policy_sha256=binding["policy"]["sha256"],
    )
    for ref in previous.evidence:
        verified(ref)
    receipt = strict_json_loads(verified(binding["receipt"]))
    claim = strict_json_loads(verified(binding["claim"]))
    rows = receipt.get("sources", [])
    if (
        receipt.get("scope") != RECOVERY_SCOPE
        or receipt.get("status") != "partial"
        or receipt.get("policy_sha256") != previous.policy_sha256
        or receipt.get("session_claim") != binding["claim"]
        or binding["claim"]["path"] != previous.data["session_claim_path"]
        or claim.get("policy_sha256") != previous.policy_sha256
        or claim.get("scope") != RECOVERY_SCOPE
        or claim.get("resume_supported") is not False
        or root / binding["receipt"]["path"]
        != Path(claim.get("output", "")) / "receipt.json"
        or data["session_claim_path"]
        in {
            previous.data["session_claim_path"],
            previous.data["reuse_completed_source"]["claim"]["path"],
        }
        or len(rows) != 2
        or rows[0].get("status") != "passed"
        or rows[0].get("selection_sha256") != previous.reused_row["selection_sha256"]
        or rows[1].get("source_id") != "ofac_sdn"
        or rows[1].get("status") != "failed"
        or rows[1].get("bytes_received") != 0
        or rows[1].get("http_status") is not None
        or rows[1].get("transaction_count") != 1
        or len(rows[1].get("transactions", [])) != 1
        or receipt.get("ledger", {}).get("total_received_bytes") != 0
        or sum(receipt.get("ledger", {}).get("transactions", {}).values()) != 1
        or receipt.get("recovery_accounting", {}).get("received_plus_reservation_bytes")
        != 4_000_000
    ):
        raise FullAcquisitionError("continuation_prior_receipt_mismatch")
    tx = rows[1]["transactions"][0]
    if (
        tx.get("bytes_received") != 0
        or tx.get("http_status") is not None
        or tx.get("complete") is not False
        or tx.get("unresolved_response_reservation_bytes") != 4_000_000
    ):
        raise FullAcquisitionError("continuation_reservation_mismatch")
    for old, new in zip(previous.data["sources"], data["sources"], strict=True):
        if {
            k: v
            for k, v in old.items()
            if k not in {"permission_path", "permission_sha256"}
        } != {
            k: v
            for k, v in new.items()
            if k not in {"permission_path", "permission_sha256"}
        }:
            raise FullAcquisitionError("continuation_source_contract_changed")
    if {
        k: v
        for k, v in previous.data["reuse_completed_source"].items()
        if k != "recovery_permission"
    } != {
        k: v
        for k, v in data["reuse_completed_source"].items()
        if k != "recovery_permission"
    }:
        raise FullAcquisitionError("continuation_reused_source_changed")
    verified(binding["tls_ca_bundle"])


def continuation_tls_preflight(policy: RecoveryExecutionPolicy) -> dict:
    """Verify the default context used by HTTPTransport loads the pinned bundle.

    No network, environment mutation or insecure fallback is performed here.
    The supervised worker must select SSL_CERT_FILE before entering this API.
    """
    ref = policy.data["continuation"]["tls_ca_bundle"]
    bundle = policy.project_root / ref["path"]
    if (
        os.environ.get("SSL_CERT_FILE") != str(bundle)
        or hashlib.sha256(_local_bytes(policy.project_root, ref["path"])).hexdigest()
        != ref["sha256"]
    ):
        raise FullAcquisitionError("continuation_tls_bundle_not_selected")
    _native_tls_preflight(None)
    context = ssl.create_default_context()
    expected = ssl.create_default_context(cafile=str(bundle))
    certificates = set(context.get_ca_certs(binary_form=True))
    if certificates != set(expected.get_ca_certs(binary_form=True)):
        raise FullAcquisitionError("continuation_tls_trust_mismatch")
    return {
        "ca_bundle": ref,
        "ca_count": len(certificates),
        "certificate_chain_verification": context.verify_mode == ssl.CERT_REQUIRED,
        "hostname_verification": context.check_hostname,
        "client": "HTTPTransport/_PinnedHTTPSConnection/ssl.create_default_context",
    }


def _claim_recovery_session(
    policy: RecoveryExecutionPolicy, output: Path, guard: ResourceGuard
) -> dict:
    relative = _relative_path(policy.data["session_claim_path"])
    payload = _json_bytes(
        {
            "schema_version": 1,
            "scope": CONTINUATION_SCOPE
            if "continuation" in policy.data
            else RECOVERY_SCOPE,
            "policy_sha256": policy.policy_sha256,
            "output": str(output),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "maximum_reserved_body_bytes": policy.data["limits"]["total_bytes"],
            **(
                {"continuation": policy.data["continuation"]}
                if "continuation" in policy.data
                else {}
            ),
            "maximum_transactions": 3,
            "resume_supported": False,
            "prior_claim": policy.data["reuse_completed_source"]["claim"],
        }
    )
    guard.reserve_artifact(len(payload))
    parent = _local_parent(policy.project_root, relative)
    try:
        descriptor = os.open(
            relative.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return {"path": relative.as_posix(), "sha256": hashlib.sha256(payload).hexdigest()}


def _recovery_redirect(source: dict, location: object) -> tuple[str, str, bool]:
    """Validate official storage syntax; the caller separately checks approval.

    A valid but unapproved official object can be recorded without its signing
    query so a reviewer can assess it without another discovery request.
    """
    if source["source_id"] != "ofac_sdn" or not isinstance(location, str):
        raise FullAcquisitionError("recovery_redirect_forbidden")
    try:
        validate_source_url("ofac_sdn", location)
        parts = urlsplit(location)
    except (ValueError, SourceValidationError):
        raise FullAcquisitionError("unapproved_recovery_redirect") from None
    if parts.hostname != OFAC_OBJECT_HOST or not OFAC_OBJECT_PATH.fullmatch(parts.path):
        raise FullAcquisitionError("unapproved_recovery_redirect")
    unsigned = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return location, unsigned, bool(parts.query)


def _transfer_recovery(
    source: dict,
    transport: Transport,
    ledger: BudgetLedger,
    checkpoint: Callable[[], None],
    journal: Callable[[], None],
    row: dict,
) -> bytes:
    """Read at most one approved redirect; retain only redacted transaction data.

    A positive Content-Length is mandatory for a 200 dataset response before
    its first body read. Failed or interrupted responses keep the remaining
    reservation in their transaction evidence even after the socket closes.
    """
    next_url = public_url = source["url"]
    signing_query = False
    for request_number in range(1, source["transactions"] + 1):
        ticket = ledger.begin_request(source["source_id"])
        tx = {
            "sequence": ticket.sequence,
            "request_number": request_number,
            "requested_url": public_url,
            "final_url": None,
            "signing_query_present": signing_query,
            "http_status": None,
            "declared_body_bytes": None,
            "complete": False,
            "bytes_received": 0,
            "body_sha256": hashlib.sha256(b"").hexdigest(),
            "outcome": "started",
            "stop_reason": None,
            "redirect_target": None,
            "unresolved_response_reservation_bytes": ledger.receipt()[
                "active_response_reservation"
            ],
        }
        row["transactions"].append(tx)
        row["transaction_count"] = len(row["transactions"])
        response = None
        body = bytearray()
        hasher = hashlib.sha256()
        transfer_succeeded = False
        redirect = None

        def charge(block: bytes) -> None:
            if not isinstance(block, bytes):
                raise FullAcquisitionError("invalid_response_block")
            tx["bytes_received"] += len(block)
            row["bytes_received"] += len(block)
            hasher.update(block)
            tx["body_sha256"] = hasher.hexdigest()
            row["body_sha256"] = tx["body_sha256"]
            try:
                ledger.charge_received(ticket, len(block))
            finally:
                tx["unresolved_response_reservation_bytes"] = ledger.receipt()[
                    "active_response_reservation"
                ]
                journal()

        try:
            journal()  # Durable reservation precedes every transport attempt.
            response = transport.open(
                next_url, timeout=ledger.remaining_seconds(ticket)
            )
            if response.url != next_url:
                raise FullAcquisitionError("automatic_transport_redirect_forbidden")
            tx["final_url"] = row["final_url"] = public_url
            tx["http_status"] = row["http_status"] = response.status
            if type(response.status) is not int or not 100 <= response.status <= 599:
                raise FullAcquisitionError("invalid_http_status")
            headers = _live_headers(response)
            declared_text = headers.get("content-length")
            declared = None
            if declared_text is not None:
                if not re.fullmatch(r"[0-9]{1,12}", declared_text):
                    raise FullAcquisitionError("invalid_content_length")
                declared = int(declared_text)
                tx["declared_body_bytes"] = declared
                ledger.declare_length(ticket, declared)
            if response.status == 200:
                if declared is None or declared <= 0:
                    raise FullAcquisitionError("positive_content_length_required")
                if (
                    source["expected_bytes"] is not None
                    and declared != source["expected_bytes"]
                ):
                    raise FullAcquisitionError("publisher_declared_size_mismatch")
            while True:
                checkpoint()
                if declared is not None and tx["bytes_received"] == declared:
                    # Native HTTP defines its frame at the declared length.
                    # Fictional transports can expose a stronger EOF witness.
                    if getattr(response, "body_complete", True) is not True:
                        raise FullAcquisitionError(
                            "declared_length_before_transport_eof"
                        )
                    break
                remaining = ledger.remaining_bytes(ticket)
                if remaining <= 0:
                    raise FullAcquisitionError("response_cap_before_eof")
                size = min(64 * 1024, remaining)
                if declared is not None:
                    size = min(size, declared - tx["bytes_received"])
                try:
                    block = response.read(
                        size, timeout=ledger.remaining_seconds(ticket)
                    )
                except http.client.IncompleteRead as exc:
                    if not isinstance(exc.partial, bytes):
                        raise FullAcquisitionError("invalid_partial_response") from None
                    charge(exc.partial)
                    raise FullAcquisitionError("incomplete_response") from None
                charge(block)
                if len(block) > size:
                    raise FullAcquisitionError("transport_exceeded_read_bound")
                if not block:
                    break
                if response.status == 200:
                    body.extend(block)
            if declared is not None and tx["bytes_received"] != declared:
                raise FullAcquisitionError("incomplete_declared_body")
            checkpoint()
            ledger.remaining_seconds(ticket)
            tx["complete"] = True
            tx["unresolved_response_reservation_bytes"] = 0
            if response.status in {301, 302, 303, 307, 308}:
                if request_number != 1 or source["transactions"] != 2:
                    raise FullAcquisitionError("recovery_redirect_limit")
                redirect = _recovery_redirect(source, headers.get("location"))
                tx["redirect_target"] = redirect[1]
                if redirect[1] != RECOVERY_OFAC_REDIRECT or source[
                    "allowed_redirects"
                ] != [redirect[1]]:
                    raise FullAcquisitionError("unapproved_recovery_redirect")
                tx["outcome"] = "approved_redirect"
            elif response.status != 200:
                raise FullAcquisitionError("http_non_200")
            else:
                tx["outcome"] = "complete_200"
                row["complete"] = True
            transfer_succeeded = True
        except (ResourceStop, FullAcquisitionError) as exc:
            tx["outcome"] = "rejected"
            tx["stop_reason"] = exc.code if isinstance(exc, ResourceStop) else str(exc)
            raise
        except TimeoutError:
            tx.update(outcome="rejected", stop_reason="request_timeout")
            raise ResourceStop("request_timeout") from None
        except (
            OSError,
            http.client.HTTPException,
            _FetchFailure,
            SourceValidationError,
        ) as exc:
            code = _safe_transport_failure_code(exc)
            tx.update(outcome="rejected", stop_reason=code)
            raise FullAcquisitionError(code) from None
        finally:
            close_failed = False
            if response is not None:
                try:
                    response.close()
                except OSError:
                    close_failed = True
            if close_failed and transfer_succeeded:
                tx.update(outcome="rejected", stop_reason="response_close_failed")
            ledger.finish_request(ticket)
            journal()
            if close_failed and transfer_succeeded:
                raise FullAcquisitionError("response_close_failed")
        if redirect is None:
            return bytes(body)
        next_url, public_url, signing_query = redirect
    raise FullAcquisitionError("recovery_transaction_limit")


def acquire_recovery(
    policy_path: Path,
    output: Path,
    *,
    project_root: Path,
    expected_policy_sha256: str,
    guard: ResourceGuard,
    transport: Transport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Run the separately authorized OFAC/EU session under external supervision.

    The caller must count both artifact roots in its guard and preload the old
    normalized selection size. No retry, old-session repair or raw persistence
    occurs. Every source failure stops this package.
    """
    policy = load_recovery_execution_policy(
        policy_path,
        project_root=project_root,
        expected_policy_sha256=expected_policy_sha256,
    )
    output = Path(output).absolute()
    if ".." in output.parts or not output.is_relative_to(policy.project_root):
        raise FullAcquisitionError("live_output_outside_project")
    if not isinstance(guard, ResourceGuard) or guard.normalized_bytes < len(
        policy.reused_selection
    ):
        raise FullAcquisitionError("prior_normalized_reservation_required")
    continuation = policy.data.get("continuation")
    tls_evidence = None
    if continuation and (transport is None or isinstance(transport, HTTPTransport)):
        tls_evidence = continuation_tls_preflight(policy)
    _native_tls_preflight(transport)
    if guard.admitted:
        guard.check()
    else:
        guard.admit()
    guard.reserve_artifact(_LOCAL_MAX_BYTES)
    run = _PrivateRun(output)
    try:
        claim_reference = _claim_recovery_session(policy, output, guard)
    except BaseException:
        run.close()
        raise
    limits = dict(STEP08_LIMITS)
    for source in policy.data["sources"]:
        limits[source["source_id"]] = replace(
            limits[source["source_id"]], transactions=source["transactions"]
        )
    ledger = BudgetLedger(
        clock=clock,
        limits=limits,
        total_received_limit=policy.data["limits"]["total_bytes"],
        bulk_transaction_limit=3,
        allowed_buckets=frozenset(RECOVERY_SOURCE_IDS),
    )
    reuse = policy.data["reuse_completed_source"]
    receipt = {
        "schema_version": 1,
        "scope": CONTINUATION_SCOPE if continuation else RECOVERY_SCOPE,
        "policy_sha256": policy.policy_sha256,
        "execution_policy_path": policy.policy_path,
        "execution_policy_sha256": policy.policy_sha256,
        "approval": policy.data["approval"],
        "session_claim": claim_reference,
        "permission_grants": [
            {"source_id": "opensanctions_un", **reuse["recovery_permission"]}
        ]
        + [
            {
                "source_id": source["source_id"],
                "path": source["permission_path"],
                "sha256": source["permission_sha256"],
            }
            for source in policy.data["sources"]
        ],
        "evidence": [*policy.evidence, claim_reference],
        "status": "running",
        "live_authorized": True,
        "independent_custody_verified": False,
        "selection_use": "shared-development-candidates-only",
        "sources": [],
        "resume_supported": False,
        "total_body_limit": policy.data["limits"]["total_bytes"],
        "prior_session": reuse,
        "prior_session_accounting": policy.prior_accounting,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if continuation:
        receipt["continuation"] = continuation
        receipt["tls_preflight"] = tls_evidence
    sequence = 0
    last_probe = clock()

    def checkpoint(force: bool = False) -> None:
        nonlocal last_probe
        ledger.remaining_seconds()
        now = clock()
        if force or now - last_probe >= 0.25:
            guard.check()
            last_probe = now

    def publish(name: str, payload: bytes, *, normalized: bool = False) -> None:
        guard.reserve_artifact(len(payload), normalized=normalized)
        run.publish(name, payload)

    def accounting() -> dict:
        received = ledger.receipt()["total_received_bytes"]
        reserved = sum(
            tx["unresolved_response_reservation_bytes"]
            for row in receipt["sources"]
            for tx in row["transactions"]
        )
        carried = continuation["carried_reservation_bytes"] if continuation else 0
        return {
            **(
                {
                    "carried_prior_recovery_reservation_bytes": carried,
                    "cumulative_recovery_accounted_bytes": carried
                    + received
                    + reserved,
                    "cumulative_recovery_transactions": 1
                    + sum(ledger.receipt()["transactions"].values()),
                }
                if continuation
                else {}
            ),
            "received_body_bytes": received,
            "unresolved_response_reservation_bytes": reserved,
            "received_plus_reservation_bytes": received + reserved,
            "combined_prior_plus_recovery_reserved_bytes": policy.prior_accounting[
                "received_plus_reservation_bytes"
            ]
            + carried
            + received
            + reserved,
        }

    def journal() -> None:
        nonlocal sequence
        sequence += 1
        publish(
            f"recovery-ledger-{sequence:06d}.json",
            _json_bytes(
                {
                    "scope": CONTINUATION_SCOPE if continuation else RECOVERY_SCOPE,
                    "policy_sha256": policy.policy_sha256,
                    "ledger": ledger.receipt(),
                    "recovery_accounting": accounting(),
                    "sources": receipt["sources"],
                }
            ),
        )

    try:
        publish("execution-policy.json", policy.policy_bytes)
        publish("opensanctions_un.jsonl", policy.reused_selection, normalized=True)
        reused_row = deepcopy(policy.reused_row)
        reused_row.update(
            permission=reuse["recovery_permission"],
            acquisition_origin="reused_completed_source",
            origin_evidence={
                "completed_journal": reuse["completed_journal"],
                "source_row": deepcopy(policy.reused_row),
            },
            transactions=[],
        )
        receipt["sources"].append(reused_row)
        journal()
        chosen_transport = HTTPTransport() if transport is None else transport
        for source in policy.data["sources"]:
            row = {
                "source_id": source["source_id"],
                "requested_url": source["url"],
                "final_url": None,
                "status": "running",
                "complete": False,
                "http_status": None,
                "bytes_received": 0,
                "body_sha256": hashlib.sha256(b"").hexdigest(),
                "transaction_count": 0,
                "permission": {
                    "path": source["permission_path"],
                    "sha256": source["permission_sha256"],
                },
                "acquisition_origin": "recovery_session",
                "origin_evidence": None,
                "transactions": [],
            }
            receipt["sources"].append(row)
            payload = result = selection = None
            try:
                checkpoint(True)
                ledger.begin_source(source["source_id"])
                journal()
                payload = _transfer_recovery(
                    source, chosen_transport, ledger, checkpoint, journal, row
                )
                result = parse_full_payload(
                    payload,
                    FullSourcePolicy(
                        source["source_id"],
                        source["url"],
                        expected_sha256=source["expected_sha256"],
                        expected_bytes=source["expected_bytes"],
                        max_groups=source["max_groups"],
                    ),
                    checkpoint=checkpoint,
                )
                publisher = _publisher_checks(source, payload, result)
                if (
                    source["expected_decoded_bytes"] is not None
                    and result.decoded_bytes != source["expected_decoded_bytes"]
                ):
                    raise FullAcquisitionError("publisher_decoded_size_mismatch")
                publisher["expected_decoded_bytes"] = source["expected_decoded_bytes"]
                selection = _selection_bytes(
                    result,
                    guard.limits.max_normalized_bytes - guard.normalized_bytes,
                    checkpoint,
                )
                checkpoint(True)
                publish(f"{source['source_id']}.jsonl", selection, normalized=True)
                row.update(
                    {
                        "status": "passed",
                        "input_sha256": result.input_sha256,
                        "input_bytes": len(payload),
                        "input_records": result.input_records,
                        "retained_groups": len(result.records),
                        "excluded_person_records": result.excluded_person_records,
                        "excluded_other_records": result.excluded_other_records,
                        "excluded_by_limit": result.excluded_by_limit,
                        "parser_version": result.parser_version,
                        "source_version": result.source_version,
                        "source_version_field": result.source_version_field,
                        "version_fallback": "input_sha256"
                        if result.source_version is None
                        else None,
                        "container_format": result.container_format,
                        "container_member": result.container_member,
                        "decoded_bytes": result.decoded_bytes,
                        "decoded_sha256": result.decoded_sha256,
                        "selection_sha256": hashlib.sha256(selection).hexdigest(),
                        "selection_bytes": len(selection),
                        "selection_path": f"{source['source_id']}.jsonl",
                        "publisher_checksum": publisher,
                    }
                )
                checkpoint(True)
                ledger.finish_source(source["source_id"])
                journal()
            except (
                ResourceStop,
                FullAcquisitionError,
                SourceValidationError,
                OSError,
            ) as exc:
                code = (
                    exc.code
                    if isinstance(exc, ResourceStop)
                    else str(exc)
                    if isinstance(exc, FullAcquisitionError)
                    else "source_validation_or_storage_failed"
                )
                row.update(status="failed", stop_reason=code)
                receipt["stop_reason"] = code
                break
            finally:
                del payload, result, selection
        passed = sum(row["status"] == "passed" for row in receipt["sources"])
        receipt["status"] = (
            "passed" if passed == 3 else "partial" if passed else "failed"
        )
    except (FullAcquisitionError, ResourceStop, OSError) as exc:
        receipt["status"] = "failed"
        receipt["stop_reason"] = (
            exc.code
            if isinstance(exc, ResourceStop)
            else "preparation_or_storage_failed"
        )
    finally:
        receipt.update(
            finished_at=datetime.now(timezone.utc).isoformat(),
            ledger=ledger.receipt(),
            recovery_accounting=accounting(),
            peak_sampled_rss_bytes=guard.peak_rss_bytes,
            rss_enforcement="cooperative-checks; external-owned-process-group-supervision-required",
        )
        receipt_bytes = _json_bytes(receipt)
        try:
            if len(receipt_bytes) > _LOCAL_MAX_BYTES:
                raise FullAcquisitionError("recovery_receipt_exceeds_reservation")
            if receipt["status"] == "passed" and not continuation:
                receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
                indexed = {row["source_id"]: row for row in receipt["sources"]}
                grant_sources = [
                    {
                        "source_id": "opensanctions_un",
                        "permission_path": reuse["recovery_permission"]["path"],
                        "permission_sha256": reuse["recovery_permission"]["sha256"],
                    },
                    *policy.data["sources"],
                ]
                for source in grant_sources:
                    purpose = _derived_purpose(
                        policy, source, indexed[source["source_id"]], receipt_digest
                    )
                    publish(f"{source['source_id']}.purpose.json", _json_bytes(purpose))
            run.publish("receipt.json", receipt_bytes)
        finally:
            run.close()
    return receipt


LIVE_SCOPE = "08B-2-development-candidate-acquisition-v1"
LIVE_POLICY_SCOPE = "08B-2-three-source-candidate-acquisition"
LIVE_URLS = MappingProxyType(
    {
        "opensanctions_un": "https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000105-chi/entities.ftm.json",
        "ofac_sdn": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_XML.ZIP",
        "eu_consolidated": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
    }
)
LIVE_LIMITS = {
    "total_bytes": 39_000_000,
    "transactions": 3,
    "max_attempts": 1,
    "max_redirects": 0,
    "session_seconds": 3600,
}
_PURPOSE = "local_candidate_corpus_preparation"
_OPERATIONS = frozenset({"retain_selected_names", "prepare_candidate_corpus"})
_RECORD_FIELDS = frozenset(field.name for field in fields(SourceRecord)) | {
    "qualified_id",
    "source_role",
}
_ALIAS_FIELDS = frozenset({"value", "field", "language", "attributes"})
_NAME_FIELDS = {
    "opensanctions_un": {f"properties.{name}": frozenset() for name in FTM_NAME_FIELDS},
    "ofac_sdn": {
        "sdnEntry.lastName": frozenset({"firstName"}),
        "sdnEntry.akaList.aka.lastName": frozenset(
            {"uid", "type", "category", "firstName"}
        ),
        "sdnEntry.akaList.aka.firstName": frozenset(
            {"uid", "type", "category", "lastName"}
        ),
    },
    "eu_consolidated": {
        f"sanctionEntity.nameAlias@{name}": frozenset(EU_NAME_ATTRIBUTES)
        for name in ("wholeName", "firstName", "middleName", "lastName")
    },
}
_BINDING = {
    "same_policy": True,
    "require_complete_direct_200": True,
    "bind_receipt_sha256": True,
    "bind_selection_sha256": True,
    "one_derived_grant_per_source": True,
    "preserve_review_metadata": True,
    "new_human_review_asserted": False,
}
_GRANT_FIELDS = frozenset(
    {
        "schema_version",
        "grant_kind",
        "source_id",
        "status",
        "purpose",
        "review_id",
        "reviewer",
        "reviewed_at",
        "operations",
        "record_fields",
        "alias_fields",
        "entity_types",
        "name_fields",
        "evidence",
        "attribution",
        "conditions",
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
)
_SOURCE_POLICY_FIELDS = frozenset(
    {
        "source_id",
        "url",
        "allowed_redirects",
        "received_bytes",
        "max_groups",
        "request_seconds",
        "source_seconds",
        "decoded_bytes",
        "expected_sha256",
        "expected_sha1",
        "expected_bytes",
        "expected_decoded_sha256",
        "permission_path",
        "permission_sha256",
    }
)
_LOCAL_MAX_BYTES = 2_000_000


@dataclass(frozen=True, slots=True)
class LiveExecutionPolicy:
    """Validated local review evidence, not an identity or custody assertion."""

    data: dict
    policy_path: str
    policy_sha256: str
    policy_bytes: bytes
    project_root: Path
    grants: Mapping[str, dict]
    evidence: tuple[dict, ...]


def _object_fields(value: object, keys: set | frozenset, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise FullAcquisitionError(f"invalid_{label}_fields")
    return value


def _text_value(value: object, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise FullAcquisitionError(f"invalid_{label}")
    return value


def _digest_value(value: object, *, length: int = 64) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise FullAcquisitionError("invalid_evidence_digest")
    return value


def _string_set(value: object, label: str) -> frozenset[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise FullAcquisitionError(f"invalid_{label}")
    values = [_text_value(item, label) for item in value]
    if len(set(values)) != len(values):
        raise FullAcquisitionError(f"duplicate_{label}")
    return frozenset(values)


def _relative_path(value: object) -> Path:
    text = _text_value(value, "local_evidence_path", maximum=2048)
    path = Path(text)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != text
        or not path.name
        or text == "."
    ):
        raise FullAcquisitionError("unsafe_local_evidence_path")
    return path


def _local_parent(root: Path, relative: Path) -> int:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _local_bytes(root: Path, relative: str) -> bytes:
    """Read a bounded regular evidence file through non-symlink descriptors."""
    path = _relative_path(relative)
    parent = _local_parent(root, path)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or not 1 <= metadata.st_size <= _LOCAL_MAX_BYTES
            ):
                raise FullAcquisitionError("invalid_local_evidence_file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(_LOCAL_MAX_BYTES + 1)
            if not payload or len(payload) > _LOCAL_MAX_BYTES:
                raise FullAcquisitionError("local_evidence_byte_limit")
            return payload
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def load_execution_policy(
    path: Path,
    *,
    project_root: Path,
    expected_policy_sha256: str,
) -> LiveExecutionPolicy:
    """Validate all three exact grants and evidence hashes before networking.

    Hashes bind the saved review; they do not authenticate a reviewer. The
    caller supplies the reviewed policy digest, and this loader accepts only
    the already approved three direct routes and development-only purpose.
    """
    root = Path(project_root).resolve(strict=True)
    policy_path = Path(path)
    if policy_path.is_absolute():
        try:
            policy_path = policy_path.relative_to(root)
        except ValueError as exc:
            raise FullAcquisitionError("policy_outside_project") from exc
    relative = _relative_path(policy_path.as_posix()).as_posix()
    policy_bytes = _local_bytes(root, relative)
    digest = hashlib.sha256(policy_bytes).hexdigest()
    if digest != _digest_value(expected_policy_sha256):
        raise FullAcquisitionError("execution_policy_digest_mismatch")
    policy = _object_fields(
        strict_json_loads(policy_bytes),
        {
            "schema_version",
            "scope",
            "approval",
            "limits",
            "sources",
            "session_claim_path",
        },
        "execution_policy",
    )
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["scope"] != LIVE_POLICY_SCOPE
    ):
        raise FullAcquisitionError("unapproved_execution_scope")
    if policy["limits"] != LIVE_LIMITS or any(
        type(value) is not int for value in policy["limits"].values()
    ):
        raise FullAcquisitionError("unapproved_live_limits")
    _relative_path(policy["session_claim_path"])
    evidence: dict[str, str] = {}

    def verify(reference: object) -> dict:
        item = _object_fields(reference, {"path", "sha256"}, "evidence_reference")
        name = _relative_path(item["path"]).as_posix()
        expected = _digest_value(item["sha256"])
        if name in evidence and evidence[name] != expected:
            raise FullAcquisitionError("conflicting_evidence_digest")
        if name not in evidence:
            if (
                len(evidence) >= 128
                or hashlib.sha256(_local_bytes(root, name)).hexdigest() != expected
            ):
                raise FullAcquisitionError("permission_evidence_digest_mismatch")
            evidence[name] = expected
        return item

    verify(policy["approval"])
    sources = policy["sources"]
    if not isinstance(sources, list) or len(sources) != 3:
        raise FullAcquisitionError("all_three_source_grants_required")
    grants = {}
    for source in sources:
        _object_fields(source, _SOURCE_POLICY_FIELDS, "live_source_policy")
        source_id = source["source_id"]
        if (
            source_id not in LIVE_URLS
            or source_id in grants
            or source["url"] != LIVE_URLS[source_id]
        ):
            raise FullAcquisitionError("unapproved_exact_live_source")
        if source["allowed_redirects"] != []:
            raise FullAcquisitionError("live_redirects_forbidden")
        for name, expected in (
            ("received_bytes", STEP08_LIMITS[source_id].received_bytes),
            ("max_groups", RETENTION_LIMITS[source_id]),
            ("request_seconds", STEP08_LIMITS[source_id].request_seconds),
            ("source_seconds", STEP08_LIMITS[source_id].source_seconds),
        ):
            if type(source[name]) is not int or source[name] != expected:
                raise FullAcquisitionError("unapproved_source_limits")
        FullSourcePolicy(
            source_id,
            source["url"],
            expected_sha256=source["expected_sha256"],
            expected_bytes=source["expected_bytes"],
            max_groups=source["max_groups"],
        )
        if source["expected_sha1"] is not None:
            _digest_value(source["expected_sha1"], length=40)
        if source_id == "ofac_sdn":
            if (
                type(source["decoded_bytes"]) is not int
                or source["decoded_bytes"] != 32_000_000
            ):
                raise FullAcquisitionError("unapproved_ofac_decoded_limit")
            _digest_value(source["expected_decoded_sha256"])
        elif (
            source["decoded_bytes"] is not None
            or source["expected_decoded_sha256"] is not None
        ):
            raise FullAcquisitionError("unexpected_decoded_source_policy")
        if source_id == "opensanctions_un" and (
            source["expected_sha1"] is None or source["expected_bytes"] is None
        ):
            raise FullAcquisitionError("opensanctions_publisher_pins_required")
        reference = verify(
            {"path": source["permission_path"], "sha256": source["permission_sha256"]}
        )
        grant_bytes = _local_bytes(root, reference["path"])
        if hashlib.sha256(grant_bytes).hexdigest() != reference["sha256"]:
            raise FullAcquisitionError("permission_evidence_digest_mismatch")
        grant = _object_fields(
            strict_json_loads(grant_bytes),
            _GRANT_FIELDS,
            "prospective_grant",
        )
        if (
            type(grant["schema_version"]) is not int
            or grant["schema_version"] != 1
            or grant["grant_kind"] != "prospective_source_purpose"
            or grant["status"] != "approved"
            or grant["purpose"] != _PURPOSE
            or grant["source_id"] != source_id
            or grant["exact_url"] != source["url"]
            or grant["source_role"] != "sanctions_reference"
            or grant["approval"] != policy["approval"]
            or grant["development_exposed_only"] is not True
            or grant["final_eligible"] is not False
            or grant["raw_retention_allowed"] is not False
            or grant["transient_full_response_allowed"] is not True
            or grant["prospective_binding"] != _BINDING
            or any(
                type(value) is not bool
                for value in grant["prospective_binding"].values()
            )
        ):
            raise FullAcquisitionError("unapproved_source_purpose")
        for name, expected in (
            ("operations", _OPERATIONS),
            ("record_fields", _RECORD_FIELDS),
            ("alias_fields", _ALIAS_FIELDS),
        ):
            if _string_set(grant[name], name) != expected:
                raise FullAcquisitionError("incomplete_purpose_field_permission")
        types = (
            {"organization"}
            if source_id == "eu_consolidated"
            else {"organization", "vessel"}
        )
        if _string_set(grant["entity_types"], "entity_types") != types:
            raise FullAcquisitionError("unapproved_entity_types")
        if (
            not isinstance(grant["name_fields"], dict)
            or {
                key: _string_set(value, "name_attributes")
                for key, value in grant["name_fields"].items()
            }
            != _NAME_FIELDS[source_id]
        ):
            raise FullAcquisitionError("incomplete_original_name_field_permission")
        for name in ("review_id", "reviewer", "reviewed_at", "attribution", "license"):
            _text_value(grant[name], name)
        try:
            datetime.fromisoformat(grant["reviewed_at"])
        except ValueError as exc:
            raise FullAcquisitionError("invalid_permission_review_date") from exc
        if not _string_set(grant["conditions"], "conditions"):
            raise FullAcquisitionError("permission_conditions_required")
        if not isinstance(grant["evidence"], list) or not grant["evidence"]:
            raise FullAcquisitionError("permission_evidence_required")
        seen_evidence = set()
        for item in grant["evidence"]:
            verified = verify(item)
            if verified["path"] in seen_evidence:
                raise FullAcquisitionError("duplicate_grant_evidence")
            seen_evidence.add(verified["path"])
        if policy["approval"]["path"] not in seen_evidence:
            raise FullAcquisitionError("grant_approval_evidence_missing")
        grants[source_id] = grant
    evidence[relative] = digest
    return LiveExecutionPolicy(
        policy,
        relative,
        digest,
        policy_bytes,
        root,
        MappingProxyType(grants),
        tuple(
            {"path": name, "sha256": value} for name, value in sorted(evidence.items())
        ),
    )


def _claim_live_session(
    policy: LiveExecutionPolicy, output: Path, guard: ResourceGuard
) -> None:
    """Consume the single execution permanently; incomplete runs cannot resume."""
    relative = _relative_path(policy.data["session_claim_path"])
    payload = _json_bytes(
        {
            "schema_version": 1,
            "scope": LIVE_SCOPE,
            "policy_sha256": policy.policy_sha256,
            "output": str(output),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "maximum_reserved_body_bytes": 39_000_000,
            "maximum_transactions": 3,
            "resume_supported": False,
        }
    )
    guard.reserve_artifact(len(payload))
    parent = _local_parent(policy.project_root, relative)
    try:
        descriptor = os.open(
            relative.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)


def _live_headers(response) -> dict[str, str]:
    if not isinstance(response.headers, Mapping):
        raise FullAcquisitionError("invalid_live_response_headers")
    headers = {}
    for key, value in response.headers.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
            or any(char in key + value for char in "\r\n\x00")
            or key.lower() in headers
        ):
            raise FullAcquisitionError("invalid_live_response_header")
        headers[key.lower()] = value
    if headers.get("content-encoding", "identity").lower() != "identity":
        raise FullAcquisitionError("unexpected_content_encoding")
    if "transfer-encoding" in headers and (
        "content-length" in headers or headers["transfer-encoding"].lower() != "chunked"
    ):
        raise FullAcquisitionError("ambiguous_transfer_framing")
    return headers


def _transfer_live(
    source: dict,
    transport: Transport,
    ledger: BudgetLedger,
    checkpoint: Callable[[], None],
    journal: Callable[[], None],
    row: dict,
) -> bytes:
    """One direct request; count returned errors/partials before status checks."""
    ticket = ledger.begin_request(source["source_id"])
    row["transaction_count"] = 1
    journal()  # Conservative reservation survives a supervisor interruption.
    response = None
    transfer_succeeded = False
    body = bytearray()
    hasher = hashlib.sha256()

    def charge(block: bytes) -> None:
        if not isinstance(block, bytes):
            raise FullAcquisitionError("invalid_response_block")
        row["bytes_received"] += len(block)
        hasher.update(block)
        row["body_sha256"] = hasher.hexdigest()
        try:
            ledger.charge_received(ticket, len(block))
        finally:
            journal()

    try:
        response = transport.open(
            source["url"], timeout=ledger.remaining_seconds(ticket)
        )
        row["final_url"] = response.url
        row["http_status"] = response.status
        if response.url != source["url"]:
            raise FullAcquisitionError("automatic_transport_redirect_forbidden")
        if type(response.status) is not int or not 100 <= response.status <= 599:
            raise FullAcquisitionError("invalid_http_status")
        headers = _live_headers(response)
        declared = headers.get("content-length")
        if declared is not None:
            if not re.fullmatch(r"[0-9]{1,12}", declared):
                raise FullAcquisitionError("invalid_content_length")
            ledger.declare_length(ticket, int(declared))
        while True:
            checkpoint()
            if declared is not None and row["bytes_received"] == int(declared):
                break  # Native HTTP transport defines this complete frame.
            remaining = ledger.remaining_bytes(ticket)
            if remaining <= 0:
                raise FullAcquisitionError("response_cap_before_eof")
            size = min(64 * 1024, remaining)
            if declared is not None:
                size = min(size, int(declared) - row["bytes_received"])
            try:
                block = response.read(size, timeout=ledger.remaining_seconds(ticket))
            except http.client.IncompleteRead as exc:
                if not isinstance(exc.partial, bytes):
                    raise FullAcquisitionError("invalid_partial_response") from None
                charge(exc.partial)
                raise FullAcquisitionError("incomplete_response") from None
            charge(block)
            if len(block) > size:
                raise FullAcquisitionError("transport_exceeded_read_bound")
            if not block:
                break
            if response.status == 200:
                body.extend(block)
        if declared is not None and row["bytes_received"] != int(declared):
            raise FullAcquisitionError("incomplete_declared_body")
        ledger.remaining_seconds(ticket)
        checkpoint()
        row["complete"] = True
        if response.status in {301, 302, 303, 307, 308}:
            raise FullAcquisitionError("redirect_not_followed")
        if response.status != 200:
            raise FullAcquisitionError("http_non_200")
        transfer_succeeded = True
        return bytes(body)
    except TimeoutError:
        raise ResourceStop("request_timeout") from None
    except (
        OSError,
        http.client.HTTPException,
        _FetchFailure,
        SourceValidationError,
    ) as exc:
        raise FullAcquisitionError(_safe_transport_failure_code(exc)) from None
    finally:
        close_failed = False
        if response is not None:
            try:
                response.close()
            except OSError:
                close_failed = True
        ledger.finish_request(ticket)
        journal()
        if close_failed and transfer_succeeded:
            raise FullAcquisitionError("response_close_failed")


def _publisher_checks(source: dict, payload: bytes, result: FullParseResult) -> dict:
    expected = {
        key: source[key]
        for key in (
            "expected_sha256",
            "expected_sha1",
            "expected_bytes",
            "expected_decoded_sha256",
        )
    }
    if (
        expected["expected_sha1"] is not None
        and hashlib.sha1(payload).hexdigest() != expected["expected_sha1"]
    ):
        raise FullAcquisitionError("publisher_sha1_mismatch")
    if (
        expected["expected_decoded_sha256"] is not None
        and result.decoded_sha256 != expected["expected_decoded_sha256"]
    ):
        raise FullAcquisitionError("publisher_decoded_sha256_mismatch")
    supplied = any(value is not None for value in expected.values())
    supplied_hash = any(
        expected[key] is not None
        for key in ("expected_sha256", "expected_sha1", "expected_decoded_sha256")
    )
    return {**expected, "verified": supplied, "hash_verified": supplied_hash}


def _derived_purpose(
    policy: LiveExecutionPolicy, source: dict, row: dict, receipt_digest: str
) -> dict:
    grant = policy.grants[source["source_id"]]
    result = {
        key: deepcopy(grant[key])
        for key in (
            "schema_version",
            "review_id",
            "source_id",
            "status",
            "purpose",
            "operations",
            "record_fields",
            "alias_fields",
            "entity_types",
            "name_fields",
            "reviewed_at",
            "reviewer",
            "attribution",
            "conditions",
        )
    }
    references = {item["path"]: item["sha256"] for item in grant["evidence"]}
    references[source["permission_path"]] = source["permission_sha256"]
    references[policy.policy_path] = policy.policy_sha256
    result.update(
        receipt_sha256=receipt_digest,
        selection_sha256=row["selection_sha256"],
        evidence=[
            {"path": path, "sha256": digest}
            for path, digest in sorted(references.items())
        ],
    )
    return result


def acquire_live(
    policy_path: Path,
    output: Path,
    *,
    project_root: Path,
    expected_policy_sha256: str,
    transport: Transport | None = None,
    guard: ResourceGuard | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Execute the reviewed three direct requests under external supervision.

    Call only from an independently supervised trusted worker. All permissions
    are checked before creating transport or claiming the session. Successes
    remain development-only; a partial package cannot become an accepted full
    corpus. Raw mixed bodies stay in memory and are never written or printed.
    """
    policy = load_execution_policy(
        policy_path,
        project_root=project_root,
        expected_policy_sha256=expected_policy_sha256,
    )
    output = Path(output).absolute()
    if ".." in output.parts or not output.is_relative_to(policy.project_root):
        raise FullAcquisitionError("live_output_outside_project")
    _native_tls_preflight(transport)
    resources = guard or ResourceGuard(
        probe=lambda: system_snapshot(output), clock=clock
    )
    if resources.admitted:
        resources.check()
    else:
        resources.admit()
    resources.reserve_artifact(_LOCAL_MAX_BYTES)
    run = _PrivateRun(output)
    try:
        _claim_live_session(policy, output, resources)
    except BaseException:
        run.close()
        raise
    limits = {
        name: replace(value, transactions=1) if name in BULK_SOURCES else value
        for name, value in STEP08_LIMITS.items()
    }
    ledger = BudgetLedger(
        clock=clock,
        limits=limits,
        total_received_limit=39_000_000,
        bulk_transaction_limit=3,
        allowed_buckets=BULK_SOURCES,
    )
    receipt = {
        "schema_version": 1,
        "scope": LIVE_SCOPE,
        "policy_sha256": policy.policy_sha256,
        "execution_policy_path": policy.policy_path,
        "execution_policy_sha256": policy.policy_sha256,
        "approval": policy.data["approval"],
        "permission_grants": [
            {
                "source_id": source["source_id"],
                "path": source["permission_path"],
                "sha256": source["permission_sha256"],
            }
            for source in policy.data["sources"]
        ],
        "evidence": list(policy.evidence),
        "status": "running",
        "live_authorized": True,
        "independent_custody_verified": False,
        "selection_use": "shared-development-candidates-only",
        "sources": [],
        "resume_supported": False,
        "total_body_limit": 39_000_000,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    sequence = 0
    last_probe = clock()

    def checkpoint(force: bool = False) -> None:
        nonlocal last_probe
        ledger.remaining_seconds()
        now = clock()
        if force or now - last_probe >= 0.25:
            resources.check()
            last_probe = now

    def publish(name: str, payload: bytes, *, normalized: bool = False) -> None:
        resources.reserve_artifact(len(payload), normalized=normalized)
        run.publish(name, payload)

    def journal() -> None:
        nonlocal sequence
        sequence += 1
        publish(
            f"live-ledger-{sequence:06d}.json",
            _json_bytes(
                {
                    "policy_sha256": policy.policy_sha256,
                    "ledger": ledger.receipt(),
                    "sources": receipt["sources"],
                }
            ),
        )

    try:
        publish("execution-policy.json", policy.policy_bytes)
        chosen_transport = HTTPTransport() if transport is None else transport
        for source in policy.data["sources"]:
            row = {
                "source_id": source["source_id"],
                "requested_url": source["url"],
                "final_url": None,
                "status": "running",
                "complete": False,
                "http_status": None,
                "bytes_received": 0,
                "body_sha256": hashlib.sha256(b"").hexdigest(),
                "transaction_count": 0,
                "permission": {
                    "path": source["permission_path"],
                    "sha256": source["permission_sha256"],
                },
            }
            receipt["sources"].append(row)
            payload = result = selection = None
            try:
                checkpoint(True)
                ledger.begin_source(source["source_id"])
                journal()
                payload = _transfer_live(
                    source, chosen_transport, ledger, checkpoint, journal, row
                )
                parser_policy = FullSourcePolicy(
                    source["source_id"],
                    source["url"],
                    expected_sha256=source["expected_sha256"],
                    expected_bytes=source["expected_bytes"],
                    max_groups=source["max_groups"],
                )
                result = parse_full_payload(
                    payload, parser_policy, checkpoint=checkpoint
                )
                publisher = _publisher_checks(source, payload, result)
                selection = _selection_bytes(
                    result,
                    resources.limits.max_normalized_bytes - resources.normalized_bytes,
                    checkpoint,
                )
                checkpoint(True)
                publish(f"{source['source_id']}.jsonl", selection, normalized=True)
                row.update(
                    {
                        "status": "passed",
                        "input_sha256": result.input_sha256,
                        "input_bytes": len(payload),
                        "input_records": result.input_records,
                        "retained_groups": len(result.records),
                        "excluded_person_records": result.excluded_person_records,
                        "excluded_other_records": result.excluded_other_records,
                        "excluded_by_limit": result.excluded_by_limit,
                        "parser_version": result.parser_version,
                        "source_version": result.source_version,
                        "source_version_field": result.source_version_field,
                        "version_fallback": "input_sha256"
                        if result.source_version is None
                        else None,
                        "container_format": result.container_format,
                        "container_member": result.container_member,
                        "decoded_bytes": result.decoded_bytes,
                        "decoded_sha256": result.decoded_sha256,
                        "selection_sha256": hashlib.sha256(selection).hexdigest(),
                        "selection_bytes": len(selection),
                        "selection_path": f"{source['source_id']}.jsonl",
                        "publisher_checksum": publisher,
                    }
                )
                checkpoint(True)
                ledger.finish_source(source["source_id"])
                journal()
            except ResourceStop as exc:
                row.update(status="failed", stop_reason=exc.code)
                receipt["stop_reason"] = exc.code
                break
            except (
                FullAcquisitionError,
                SourceValidationError,
                OSError,
                http.client.HTTPException,
                _FetchFailure,
            ) as exc:
                row.update(
                    status="failed",
                    stop_reason=str(exc)
                    if isinstance(exc, FullAcquisitionError)
                    else "source_validation_failed"
                    if isinstance(exc, SourceValidationError)
                    else "transport_or_storage_error",
                )
                try:
                    ledger.finish_source(source["source_id"])
                    journal()
                except ResourceStop as limit_error:
                    receipt["stop_reason"] = limit_error.code
                    break
            finally:
                del payload, result, selection
        passed = sum(row["status"] == "passed" for row in receipt["sources"])
        receipt["status"] = (
            "passed" if passed == 3 else "partial" if passed else "failed"
        )
    except (FullAcquisitionError, ResourceStop, OSError) as exc:
        receipt["status"] = "failed"
        receipt["stop_reason"] = (
            exc.code
            if isinstance(exc, ResourceStop)
            else "preparation_or_storage_failed"
        )
    finally:
        receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
        receipt["ledger"] = ledger.receipt()
        receipt["peak_sampled_rss_bytes"] = resources.peak_rss_bytes
        receipt["rss_enforcement"] = (
            "cooperative-checks; external-owned-process-group-supervision-required"
        )
        receipt_bytes = _json_bytes(receipt)
        try:
            if len(receipt_bytes) > _LOCAL_MAX_BYTES:
                raise FullAcquisitionError("live_receipt_exceeds_reservation")
            if receipt["status"] == "passed":
                receipt_digest = hashlib.sha256(receipt_bytes).hexdigest()
                by_source = {row["source_id"]: row for row in receipt["sources"]}
                for source in policy.data["sources"]:
                    purpose = _derived_purpose(
                        policy, source, by_source[source["source_id"]], receipt_digest
                    )
                    publish(f"{source['source_id']}.purpose.json", _json_bytes(purpose))
            run.publish("receipt.json", receipt_bytes)
        finally:
            run.close()
    return receipt
