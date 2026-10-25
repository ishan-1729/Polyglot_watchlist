"""Explicit, serial acquisition of reviewed non-person research selections.

Use ``preflight`` for an offline permission/limit check. Only ``fetch`` performs
network access. Mixed provider responses are never written to disk.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import http.client
import importlib
import io
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import stat
import sys
import threading
import time
import traceback
from typing import Callable, Mapping, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
import uuid

from watchlist.ingest.source_registry import (
    DEFAULT_REGISTRY,
    OFAC_OBJECT_HOST,
    ParseContext,
    ParseResult,
    SourceRegistry,
    SourceSpec,
    SourceValidationError,
    load_registry,
    registry_from_dict,
    strict_json_loads,
    validate_source_url,
)
from watchlist.scripts import SCRIPT_METHOD, UNICODE_VERSION, script_set


class Response(Protocol):
    status: int
    headers: Mapping[str, str]
    url: str

    def read(self, size: int, *, timeout: float) -> bytes: ...

    def close(self) -> None: ...


class Transport(Protocol):
    def open(self, url: str, *, timeout: float) -> Response: ...


class _FetchFailure(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def _release_exception_frames(error: BaseException) -> None:
    """Drop handled traceback/context references to mixed parser/transport data.

    Python skips frames that are still executing; their payload locals are
    released by the surrounding finally blocks. This releases references, not
    a guarantee that the runtime or operating system has zeroed memory.
    """
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
        traceback.clear_frames(current.__traceback__)
        current.__traceback__ = None
        current.__cause__ = None
        current.__context__ = None


def _remaining(deadline: float, clock: Callable[[], float], maximum: float) -> float:
    remaining = deadline - clock()
    if remaining <= 0:
        raise _FetchFailure("deadline_exceeded")
    return min(maximum, remaining)


class _DeadlineRaw(io.RawIOBase):
    """Reset each receive timeout against an absolute request deadline."""

    def __init__(self, owner: _DeadlineSocket, deadline: float) -> None:
        self.owner = owner
        self.sock = owner.sock
        self.deadline = deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray) -> int:
        timeout = self.deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("request deadline elapsed")
        self.sock.settimeout(timeout)
        return self.sock.recv_into(buffer)

    def read1(self, size: int) -> bytes:
        if type(size) is not int or size < 0:
            raise _FetchFailure("invalid_transfer_framing")
        buffer = bytearray(size)
        received = self.readinto(buffer)
        return bytes(buffer[:received])

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise ValueError("unbounded HTTP reads are forbidden")
        chunks = []
        received = 0
        while received < size:
            chunk = self.read1(size - received)
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        if not self.closed:
            super().close()
            self.owner.release_reader()


class _DeadlineSocket:
    def __init__(self, sock: ssl.SSLSocket, deadline: float) -> None:
        self.sock = sock
        self.deadline = deadline
        self.reader_count = 0
        self.close_requested = False

    def makefile(self, mode: str) -> _DeadlineRaw:
        if mode != "rb":
            raise ValueError("only HTTP response reads are supported")
        if self.close_requested:
            raise OSError("HTTP connection is already closed")
        # Avoid application-level buffering that could read response-body bytes
        # beyond the explicit budget while parsing headers or a final chunk.
        self.reader_count += 1
        return _DeadlineRaw(self, self.deadline)

    def sendall(self, data: bytes) -> None:
        timeout = self.deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("request deadline elapsed")
        self.sock.settimeout(timeout)
        self.sock.sendall(data)

    def close(self) -> None:
        self.close_requested = True
        if self.reader_count == 0:
            self.sock.close()

    def release_reader(self) -> None:
        # HTTPConnection closes its own reference immediately for responses with
        # Connection: close. The response file must keep the TLS socket alive,
        # matching the lifetime contract of socket.makefile().
        self.reader_count -= 1
        if self.reader_count == 0 and self.close_requested:
            self.sock.close()


def _resolve_public(host: str, deadline: float) -> tuple:
    """Bound the wait for DNS, then pin a public address for this TLS request.

    The daemon can finish a slow system DNS lookup after the caller times out;
    it cannot open an HTTP connection or perform an acquisition by itself.
    """
    result: queue.Queue = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except OSError as exc:
            result.put(exc)

    threading.Thread(target=resolve, daemon=True).start()
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise TimeoutError("DNS deadline elapsed")
    try:
        addresses = result.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError("DNS deadline elapsed") from exc
    if isinstance(addresses, OSError):
        raise addresses
    if not addresses or any(
        not ipaddress.ip_address(item[4][0]).is_global for item in addresses
    ):
        raise _FetchFailure("nonpublic_destination")
    return addresses[0]


class _StrictHTTPResponse(http.client.HTTPResponse):
    """Require complete chunk framing instead of accepting an EOF as a trailer."""

    def _get_chunk_left(self) -> int | None:
        if self.chunk_left:
            if self.chunk_left < 0:
                raise _FetchFailure("invalid_transfer_framing")
            return self.chunk_left
        if self.chunk_left == 0 and self._safe_read(2) != b"\r\n":
            raise _FetchFailure("invalid_transfer_framing")
        line = self.fp.readline(65_537)
        if len(line) > 65_536 or not line.endswith(b"\r\n"):
            raise _FetchFailure("invalid_transfer_framing")
        size_text = line[:-2].split(b";", 1)[0]
        if not re.fullmatch(rb"[0-9a-fA-F]+", size_text):
            raise _FetchFailure("invalid_transfer_framing")
        size = int(size_text, 16)
        if size == 0:
            for _ in range(101):
                line = self.fp.readline(65_537)
                if line == b"\r\n":
                    self._close_conn()
                    self.chunk_left = None
                    return None
                if len(line) > 65_536 or not line.endswith(b"\r\n") or b":" not in line:
                    raise _FetchFailure("invalid_transfer_framing")
            raise _FetchFailure("invalid_transfer_framing")
        self.chunk_left = size
        return size


class _PinnedHTTPSConnection(http.client.HTTPConnection):
    default_port = 443
    response_class = _StrictHTTPResponse

    def __init__(self, host: str, *, deadline: float) -> None:
        super().__init__(host, port=443)
        self.deadline = deadline

    def connect(self) -> None:
        family, kind, proto, _, address = _resolve_public(self.host, self.deadline)
        raw = socket.socket(family, kind, proto)
        try:
            timeout = self.deadline - time.monotonic()
            if timeout <= 0:
                raise TimeoutError("connection deadline elapsed")
            raw.settimeout(timeout)
            raw.connect(address)
            timeout = self.deadline - time.monotonic()
            if timeout <= 0:
                raise TimeoutError("TLS deadline elapsed")
            raw.settimeout(timeout)
            secured = ssl.create_default_context().wrap_socket(
                raw, server_hostname=self.host
            )
            self.sock = _DeadlineSocket(secured, self.deadline)
        except BaseException:
            raw.close()
            raise


class _HTTPResponse:
    """One request's deadline covers DNS, headers and every body read together.

    ``read(timeout=...)`` preserves the injected-transport interface; the native
    socket's absolute deadline was set at open() and cannot be extended by reads.
    """

    def __init__(
        self,
        response: http.client.HTTPResponse,
        connection: _PinnedHTTPSConnection,
        url: str,
    ) -> None:
        self._response = response
        self._connection = connection
        self.status = response.status
        self.url = url
        # Joining duplicates makes conflicting Content-Length fields fail closed.
        self.headers = {
            key.lower(): ", ".join(response.headers.get_all(key))
            for key in response.headers.keys()
        }

    def read(self, size: int, *, timeout: float) -> bytes:
        if timeout <= 0:
            raise TimeoutError("body deadline elapsed")
        return self._response.read1(size)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


class HTTPTransport:
    """Verified TLS with no proxies, cookies, credentials or automatic redirects."""

    def open(self, url: str, *, timeout: float) -> Response:
        parts = urlsplit(url)
        connection = _PinnedHTTPSConnection(
            parts.hostname, deadline=time.monotonic() + timeout
        )
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "PolyglotWatchlistResearch/0.7 (https://github.com/raiha-siddiqui/Polyglot_watchlist; noncommercial research)",
                    "Accept-Encoding": "identity",
                    "Accept": "application/json, application/xml, text/xml, */*;q=0.1",
                    "Connection": "close",
                },
            )
            return _HTTPResponse(connection.getresponse(), connection, url)
        except BaseException:
            connection.close()
            raise


def _policy_dict(registry: SourceRegistry) -> dict:
    return {
        "schema_version": registry.schema_version,
        "profile": registry.profile,
        "limits": asdict(registry.limits),
        "sources": [asdict(source) for source in registry.sources],
    }


def _permission_evidence(registry: SourceRegistry, source: SourceSpec) -> list[dict]:
    evidence = []
    for relative in source.permission.evidence_paths:
        path = registry.project_root / relative
        try:
            root = registry.project_root.resolve(strict=True)
            if not path.resolve(strict=True).is_relative_to(root):
                raise SourceValidationError("permission evidence escapes project")
            with path.open("rb") as stream:
                payload = stream.read(2_000_001)
        except OSError as exc:
            raise SourceValidationError(
                "approved permission evidence is unavailable"
            ) from exc
        if len(payload) > 2_000_000:
            raise SourceValidationError("permission evidence exceeds review size limit")
        item = {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        if (
            source.source_id == "opensanctions_un"
            and path.name == "opensanctions-un-index.json"
        ):
            try:
                metadata = strict_json_loads(payload)
                resources = [
                    entry
                    for entry in metadata["resources"]
                    if entry["name"] == "entities.ftm.json"
                ]
                resource = resources[0]
                version = urlsplit(source.url).path.split("/")[-2]
                if (
                    len(resources) != 1
                    or metadata["name"] != "un_sc_sanctions"
                    or resource["url"] != source.url
                    or metadata["version"] != version
                    or type(resource["size"]) is not int
                    or resource["size"] <= 0
                    or not re.fullmatch(r"[0-9a-f]{40}", resource["checksum"])
                ):
                    raise SourceValidationError(
                        "saved publisher metadata does not bind this artifact"
                    )
                item["publisher_snapshot"] = {
                    "version": version,
                    "version_field": "index.json.version",
                    "resource_url": source.url,
                    "resource_bytes": resource["size"],
                    "published_checksum": resource["checksum"],
                    "checksum_comparison": "sha1",
                }
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise SourceValidationError(
                    "saved publisher metadata is malformed"
                ) from exc
        if (
            source.source_id == "ofac_sdn"
            and path.name == "ofac-sdn-metadata-post.json"
        ):
            try:
                metadata = strict_json_loads(payload)
                zipped = [
                    entry for entry in metadata if entry["fileName"] == "SDN_XML.ZIP"
                ]
                decoded = [
                    entry for entry in metadata if entry["fileName"] == "SDN.XML"
                ]
                archive, xml = zipped[0], decoded[0]
                decoded_hash = strict_json_loads(xml["hashCodes"])["SHA-256"]
                if (
                    len(zipped) != 1
                    or len(decoded) != 1
                    or type(archive["size"]) is not int
                    or not 0 < archive["size"] <= 10_000_000
                    or type(xml["size"]) is not int
                    or not 0 < xml["size"] <= 32_000_000
                    or not re.fullmatch(r"[0-9a-f]{64}", decoded_hash)
                    or not isinstance(archive["lastUpdated"], str)
                    or not archive["lastUpdated"]
                    or xml["lastUpdated"] != archive["lastUpdated"]
                ):
                    raise SourceValidationError(
                        "saved OFAC metadata violates approved bounds"
                    )
                object_url = f"https://{OFAC_OBJECT_HOST}/{archive['downloadLink']}"
                validate_source_url(source.source_id, object_url)
                if object_url not in source.allowed_redirects:
                    raise SourceValidationError(
                        "saved OFAC object path lacks exact redirect approval"
                    )
                item["publisher_snapshot"] = {
                    "version": archive["lastUpdated"],
                    "version_field": "SDN_XML.ZIP.lastUpdated in SdnList metadata",
                    "resource_url": source.url,
                    "resource_bytes": archive["size"],
                    "published_checksum": None,
                    "checksum_comparison": None,
                    "publisher_archive_checksum_available": False,
                    "decoded_bytes": xml["size"],
                    "decoded_sha256": decoded_hash,
                    "decoded_hash_field": "SDN.XML.hashCodes.SHA-256 in SdnList metadata",
                    "published_object_path": archive["downloadLink"],
                }
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise SourceValidationError("saved OFAC metadata is malformed") from exc
        evidence.append(item)
    return evidence


def preflight(
    registry: SourceRegistry, *, source_ids: list[str] | tuple[str, ...] | None = None
) -> dict:
    """Check all authorization before network access or output-directory creation."""
    # Recheck public dataclasses as well as JSON-created registries. JSON roundtrip
    # converts immutable tuples back to the loader's required array format.
    checked = registry_from_dict(
        json.loads(json.dumps(_policy_dict(registry))),
        project_root=registry.project_root,
    )
    if checked.policy_sha256 != registry.policy_sha256:
        raise SourceValidationError("registry policy changed after validation")
    by_id = {item.source_id: item for item in registry.sources}
    if source_ids is None:
        requested = [
            item.source_id
            for item in registry.sources
            if item.permission.status == "approved"
        ]
    else:
        if (
            isinstance(source_ids, str)
            or not source_ids
            or len(set(source_ids)) != len(source_ids)
        ):
            raise SourceValidationError(
                "requested source IDs must be a nonempty unique sequence"
            )
        requested = list(source_ids)
        if any(source_id not in by_id for source_id in requested):
            raise SourceValidationError("unknown requested source")
        if any(
            by_id[source_id].permission.status != "approved" for source_id in requested
        ):
            raise SourceValidationError(
                "requested source lacks current acquisition permission"
            )
    permissions = {}
    for source_id in requested:
        source = by_id[source_id]
        validate_source_url(source_id, source.url)
        permissions[source_id] = _permission_evidence(registry, source)
    return {
        "schema_version": 1,
        "profile": registry.profile,
        "policy_sha256": registry.policy_sha256,
        "limits": asdict(registry.limits),
        "approved_sources": requested,
        "candidate_sources": [
            {
                "source_id": item.source_id,
                "role": item.role,
                "permission_status": item.permission.status,
                "status": "authorized_not_started"
                if item.source_id in requested
                else "approved_not_requested"
                if item.permission.status == "approved"
                else item.permission.status,
                "max_response_body_bytes": registry.limits.source_byte_limit(
                    item.source_id
                ),
                "request_timeout_seconds": registry.limits.request_timeout_for(
                    item.source_id
                ),
                "source_deadline_seconds": registry.limits.source_deadline_for(
                    item.source_id
                ),
            }
            for item in registry.sources
        ],
        "blocked_sources": [
            {
                "source_id": item.source_id,
                "status": item.permission.status,
                "reason": item.permission.rationale,
            }
            for item in registry.sources
            if item.permission.status != "approved"
        ],
        "permission_evidence": permissions,
        "network_performed": False,
        "raw_retained": False,
        "evaluation_eligibility_established": False,
        "training_eligibility_established": False,
    }


def _exclusive_directory_rename(parent_fd: int, source: str, destination: str) -> None:
    """Publish a new directory without replacing an existing pathname.

    macOS and Linux expose different names for the same required no-replace
    operation. An unsupported platform fails closed rather than using rename's
    overwrite semantics.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        name, flag = "renameatx_np", 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        name, flag = "renameat2", 1  # RENAME_NOREPLACE
    else:
        raise SourceValidationError(
            "exclusive output-directory publication requires macOS or Linux"
        )
    try:
        rename = getattr(libc, name)
    except AttributeError as exc:
        raise SourceValidationError(
            "exclusive output-directory publication is unavailable"
        ) from exc
    rename.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    rename.restype = ctypes.c_int
    result = rename(
        parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), flag
    )
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), destination)


class _PrivateRun:
    """Anchor every output operation to directory descriptors, without overwrite."""

    def __init__(self, path: Path) -> None:
        if ".." in path.parts or not path.name:
            raise SourceValidationError("output path cannot contain parent traversal")
        absolute = path if path.is_absolute() else Path.cwd() / path
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent_fd = os.open(absolute.anchor, flags)
        staging = f".watchlist-run-{uuid.uuid4().hex}"
        opened = False
        published = False
        checked_staging = False
        try:
            for component in absolute.parts[1:-1]:
                next_fd = os.open(component, flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = next_fd
            # Open an unpredictable private staging directory first. Publish it
            # under the user-selected name with an exclusive OS rename only
            # after checking its descriptor; never open/reuse that target name.
            os.mkdir(staging, mode=0o700, dir_fd=parent_fd)
            self.fd = os.open(staging, flags, dir_fd=parent_fd)
            opened = True
            held = os.fstat(self.fd)
            named = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
                or stat.S_IMODE(held.st_mode) != 0o700
                or held.st_uid != os.geteuid()
                or os.listdir(self.fd)
            ):
                raise SourceValidationError(
                    "new output staging directory was substituted"
                )
            checked_staging = True
            _exclusive_directory_rename(parent_fd, staging, absolute.name)
            published = True
            self.parent_fd = parent_fd
            self.name = absolute.name
            self.path = absolute
            self.verify()
        except BaseException as exc:
            # Failed exclusive publication can leave only our empty staging
            # directory. Never remove a substituted/nonempty directory.
            if opened and checked_staging and not published:
                try:
                    named = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
                    if (named.st_dev, named.st_ino) == (
                        held.st_dev,
                        held.st_ino,
                    ) and not os.listdir(self.fd):
                        os.rmdir(staging, dir_fd=parent_fd)
                except OSError:
                    pass
            if opened:
                os.close(self.fd)
            os.close(parent_fd)
            if isinstance(exc, OSError) and not isinstance(exc, FileExistsError):
                raise SourceValidationError(
                    "output parent must exist and contain no symlinks"
                ) from exc
            raise

    def verify(self) -> None:
        current = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
        held = os.fstat(self.fd)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise SourceValidationError("output directory changed during acquisition")

    def publish(self, name: str, payload: bytes) -> None:
        if "/" in name or name in (".", ".."):
            raise SourceValidationError("invalid output filename")
        self.verify()
        temporary = f".pending-{uuid.uuid4().hex}"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.fd,
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.verify()
            # link() is an atomic exclusive publication; rename() could replace
            # a file created concurrently in the destination.
            os.link(
                temporary,
                name,
                src_dir_fd=self.fd,
                dst_dir_fd=self.fd,
                follow_symlinks=False,
            )
            os.fsync(self.fd)
        finally:
            os.unlink(temporary, dir_fd=self.fd)

    def close(self) -> None:
        os.close(self.fd)
        os.close(self.parent_fd)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _attribution(source: SourceSpec) -> str:
    publisher = {
        "opensanctions_un": "OpenSanctions; upstream publisher United Nations Security Council",
        "un_consolidated": "United Nations Security Council",
        "ofac_sdn": "U.S. Department of the Treasury, Office of Foreign Assets Control (OFAC)",
        "eu_consolidated": "European Union / European Commission, DG FISMA",
        "wikidata_orgs": "Wikidata contributors",
    }[source.source_id]
    return (
        f"{publisher}. License/permission: {source.permission.license}. "
        "Filtered and converted into non-person name evidence for local noncommercial research. "
        "Source URLs, permission links and available publisher version are recorded separately. "
        "No endorsement or identity/wrongdoing finding."
    )


def _default_parsers(source_ids: list[str]) -> dict[str, Callable]:
    names = {
        "opensanctions_un": "ftm",
        "un_consolidated": "un",
        "ofac_sdn": "ofac",
        "eu_consolidated": "eu",
        "wikidata_orgs": "wikidata",
    }
    parsers = {}
    for source_id in source_ids:
        name = f"parse_{names[source_id]}"
        try:
            module = importlib.import_module(f"watchlist.ingest.{name}")
            parsers[source_id] = getattr(module, name)
        except (ImportError, AttributeError) as exc:
            raise SourceValidationError(
                "an approved source parser is unavailable"
            ) from exc
    return parsers


def _header_values(response: Response) -> dict[str, str]:
    if not isinstance(response.headers, Mapping):
        raise _FetchFailure("invalid_response_headers")
    values = {}
    for key, value in response.headers.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
            or key.lower() in values
        ):
            raise _FetchFailure("invalid_response_headers")
        values[key.lower()] = value.strip()
    return values


def _redirect_allowed(source: SourceSpec, destination: str) -> bool:
    """Match exact reviewed objects before requesting any redirect target."""
    if destination in source.allowed_redirects:
        return True
    parsed = urlsplit(destination)
    canonical = urlunsplit(parsed._replace(query="", fragment=""))
    return (
        source.source_id == "ofac_sdn"
        and parsed.hostname == OFAC_OBJECT_HOST
        and bool(parsed.query)
        and canonical in source.allowed_redirects
    )


def _url_receipt(url: str) -> dict:
    """Keep provider-issued signing values out of every saved/logged URL."""
    parsed = urlsplit(url)
    redacted = parsed.hostname == OFAC_OBJECT_HOST and bool(parsed.query)
    return {
        "url": urlunsplit(parsed._replace(query="", fragment="")) if redacted else url,
        "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        "query_present": bool(parsed.query),
        "signing_query_redacted": redacted,
    }


def _transfer(
    source: SourceSpec,
    registry: SourceRegistry,
    transport: Transport,
    receipt: dict,
    budget: dict,
    deadline: float,
    clock: Callable[[], float],
) -> bytes:
    limits = registry.limits
    request_timeout = limits.request_timeout_for(source.source_id)
    for attempt_number in range(1, limits.max_attempts + 1):
        attempt = {"attempt": attempt_number, "bytes_received": 0, "status": "failed"}
        receipt["attempts"].append(attempt)
        chunks = []
        chunk = None
        payload = None
        digest = hashlib.sha256()
        response = None
        url = source.url
        redirects = 0
        try:
            while True:
                if (
                    min(
                        limits.source_byte_limit(source.source_id)
                        - receipt["bytes_received"],
                        limits.max_total_bytes - budget["bytes"],
                    )
                    <= 0
                ):
                    raise _FetchFailure("body_budget_exhausted_before_request")
                validate_source_url(source.source_id, url)
                timeout = _remaining(deadline, clock, request_timeout)
                response = transport.open(url, timeout=timeout)
                _remaining(deadline, clock, request_timeout)
                if response.url != url:
                    raise _FetchFailure("transport_followed_unchecked_redirect")
                status = response.status
                if type(status) is not int or not 100 <= status <= 599:
                    raise _FetchFailure("invalid_http_status")
                attempt["http_status"] = status
                headers = _header_values(response)
                if status in (301, 302, 303, 307, 308):
                    location = headers.get("location")
                    if location is None:
                        raise _FetchFailure("missing_redirect_location")
                    destination = urljoin(url, location)
                    validate_source_url(source.source_id, destination)
                    if not _redirect_allowed(source, destination):
                        raise _FetchFailure("unapproved_redirect")
                    redirects += 1
                    if redirects > limits.max_redirects:
                        raise _FetchFailure("redirect_limit_exceeded")
                    receipt.setdefault("redirects", []).append(
                        _url_receipt(destination)
                    )
                    response.close()
                    response = None
                    url = destination
                    continue
                if status != 200:
                    raise _FetchFailure(
                        "http_error", retryable=status in (502, 503, 504)
                    )
                break
            final_url_evidence = _url_receipt(url)
            receipt["final_url"] = final_url_evidence.pop("url")
            receipt["final_url_evidence"] = final_url_evidence
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise _FetchFailure("unexpected_content_encoding")
            transfer_encoding = headers.get("transfer-encoding")
            length_text = headers.get("content-length")
            if transfer_encoding and (
                transfer_encoding.lower() != "chunked" or length_text is not None
            ):
                raise _FetchFailure("invalid_transfer_framing")
            declared = None
            if length_text is not None:
                if (
                    not length_text
                    or len(length_text) > 20
                    or not length_text.isascii()
                    or not length_text.isdecimal()
                ):
                    raise _FetchFailure("invalid_content_length")
                declared = int(length_text)
                if declared > min(
                    limits.source_byte_limit(source.source_id)
                    - receipt["bytes_received"],
                    limits.max_total_bytes - budget["bytes"],
                ):
                    raise _FetchFailure("declared_body_exceeds_budget")
            body_bytes = 0
            while True:
                available = min(
                    limits.source_byte_limit(source.source_id)
                    - receipt["bytes_received"],
                    limits.max_total_bytes - budget["bytes"],
                )
                if available <= 0:
                    if declared is not None and body_bytes == declared:
                        break  # Content-Length supplies the exact framing at the cap.
                    raise _FetchFailure("body_budget_exhausted_before_eof")
                requested = min(65_536, available)
                chunk = response.read(
                    requested,
                    timeout=_remaining(deadline, clock, request_timeout),
                )
                if not isinstance(chunk, bytes):
                    raise _FetchFailure("invalid_transport_chunk")
                # Account bytes even if a broken injected transport returns more
                # than requested. Native HTTPResponse.read1 obeys this bound.
                receipt["bytes_received"] += len(chunk)
                budget["bytes"] += len(chunk)
                attempt["bytes_received"] += len(chunk)
                digest.update(chunk)
                body_bytes += len(chunk)
                if len(chunk) > requested:
                    raise _FetchFailure("transport_exceeded_read_bound")
                _remaining(deadline, clock, request_timeout)
                if declared is not None and body_bytes > declared:
                    raise _FetchFailure("content_length_mismatch")
                if not chunk:
                    if declared is not None and body_bytes != declared:
                        raise _FetchFailure("incomplete_response")
                    break
                chunks.append(chunk)
            payload = b"".join(chunks)
            receipt["complete_body_sha256"] = hashlib.sha256(payload).hexdigest()
            receipt["complete_body_bytes"] = len(payload)
            receipt["response_version_evidence"] = {
                key: headers[key] for key in ("etag", "last-modified") if key in headers
            }
            attempt["status"] = "success"
            attempt["complete_body_sha256"] = receipt["complete_body_sha256"]
            return payload
        except KeyboardInterrupt as exc:
            _release_exception_frames(exc)
            failure = _FetchFailure("interrupted")
        except SourceValidationError as exc:
            _release_exception_frames(exc)
            failure = _FetchFailure("unapproved_destination")
        except _FetchFailure as exc:
            failure = _FetchFailure(exc.code, retryable=exc.retryable)
            _release_exception_frames(exc)
        except TimeoutError as exc:
            _release_exception_frames(exc)
            failure = _FetchFailure("transport_timeout", retryable=True)
        except (OSError, http.client.HTTPException) as exc:
            _release_exception_frames(exc)
            failure = _FetchFailure("transport_failure", retryable=True)
        finally:
            try:
                if response is not None:
                    try:
                        response.close()
                    except OSError:
                        pass
            finally:
                response = None
                chunks.clear()
                chunk = None
                payload = None
                partial_digest = digest.hexdigest()
                digest = None
        attempt["error_code"] = failure.code
        attempt["partial_body_sha256"] = partial_digest
        if not failure.retryable or attempt_number == limits.max_attempts:
            raise failure
        _remaining(deadline, clock, request_timeout)
    raise _FetchFailure("attempt_limit_exceeded")


def _selection(
    result: ParseResult, source: SourceSpec, registry: SourceRegistry, payload: bytes
) -> tuple[bytes, dict]:
    if not isinstance(result, ParseResult):
        raise _FetchFailure("invalid_parser_result")
    if result.input_sha256 != hashlib.sha256(payload).hexdigest():
        raise _FetchFailure("parser_input_hash_mismatch")
    if len(result.records) > registry.limits.max_groups:
        raise _FetchFailure("parser_group_limit_exceeded")
    ids = [record.provider_id for record in result.records]
    if len(set(ids)) != len(ids) or any(
        record.source_id != source.source_id for record in result.records
    ):
        raise _FetchFailure("invalid_parser_source_groups")
    lines = []
    names: set[str] = set()
    name_groups: dict[str, set[str]] = {}
    scripts: dict[str, int] = {}
    languages: dict[str, int] = {}
    alias_count = 0
    for record in sorted(result.records, key=lambda item: item.provider_id):
        item = asdict(record)
        item["qualified_id"] = record.qualified_id
        item["source_role"] = source.role
        lines.append(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        for alias in record.aliases:
            alias_count += 1
            names.add(alias.value)
            name_groups.setdefault(alias.value, set()).add(record.provider_id)
            language = alias.language or "unknown"
            languages[language] = languages.get(language, 0) + 1
            for script in script_set(alias.value) or {"NO_SCRIPT_EVIDENCE"}:
                scripts[script] = scripts.get(script, 0) + 1
    selected = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    stats = {
        "input_records": result.input_records,
        "selected_provider_groups": len(result.records),
        "excluded_person_records": result.excluded_person_records,
        "excluded_other_records": result.excluded_other_records,
        "excluded_by_limit": result.excluded_by_limit,
        "alias_evidence_count": alias_count,
        "unique_name_strings": len(names),
        "repeated_name_evidence": alias_count - len(names),
        "same_name_distinct_provider_groups": sum(
            len(groups) > 1 for groups in name_groups.values()
        ),
        "provider_referents": sum(len(record.referents) for record in result.records),
        "name_script_counts": dict(sorted(scripts.items())),
        "name_language_counts": dict(sorted(languages.items())),
        "script_count_method": SCRIPT_METHOD,
        "unicode_version": UNICODE_VERSION,
        "script_count_unit": "alias evidence; mixed scripts count in each; UNKNOWN is unresolved",
        "cross_source_identity_adjudicated": False,
    }
    return selected, stats


def fetch_profile(
    registry: SourceRegistry,
    output_dir: Path | str,
    *,
    source_ids: list[str] | tuple[str, ...] | None = None,
    transport: Transport | None = None,
    parsers: Mapping[str, Callable] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Fetch authorized sources serially, retaining normalized selections only.

    Validation failures occur before any write/network. Authorized source errors
    produce failed receipts; successful earlier sources remain independently
    usable acquisition artifacts. The manifest is complete/partial/failed and
    never asserts corpus, evaluation, training or operational readiness.
    """
    plan = preflight(registry, source_ids=source_ids)
    selected_ids = plan["approved_sources"]
    if not selected_ids:
        raise SourceValidationError("no sources have current acquisition permission")
    parsers = _default_parsers(selected_ids) if parsers is None else parsers
    if any(
        source_id not in parsers or not callable(parsers[source_id])
        for source_id in selected_ids
    ):
        raise SourceValidationError("an approved source parser is unavailable")
    run = _PrivateRun(Path(output_dir))
    transport = HTTPTransport() if transport is None else transport
    budget = {"bytes": 0}
    manifest = {
        **plan,
        "network_performed": True,
        "status": "failed",
        "sources": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_bytes_received": 0,
        "byte_counter_scope": "Response-body bytes returned by read(), including failed attempts; excludes HTTP/TLS/DNS overhead and unread error/redirect bodies",
    }
    by_id = {item.source_id: item for item in registry.sources}
    interrupted = False
    try:
        for source_id in selected_ids:
            source = by_id[source_id]
            request_timeout = registry.limits.request_timeout_for(source_id)
            source_deadline_seconds = registry.limits.source_deadline_for(source_id)
            receipt = {
                "schema_version": 1,
                "source_id": source_id,
                "role": source.role,
                "status": "failed",
                "requested_url": source.url,
                "final_url": None,
                "permission": asdict(source.permission),
                "permission_evidence": plan["permission_evidence"][source_id],
                "policy_sha256": registry.policy_sha256,
                "max_response_body_bytes": registry.limits.source_byte_limit(source_id),
                "request_timeout_seconds": request_timeout,
                "source_deadline_seconds": source_deadline_seconds,
                "attempts": [],
                "bytes_received": 0,
                "complete_body_sha256": None,
                "normalized_selection_sha256": None,
                "records_path": None,
                "raw_retained": False,
                "attribution": _attribution(source),
            }
            publisher_snapshot = next(
                (
                    item["publisher_snapshot"]
                    for item in receipt["permission_evidence"]
                    if "publisher_snapshot" in item
                ),
                None,
            )
            receipt["publisher_snapshot"] = publisher_snapshot
            deadline = clock() + source_deadline_seconds
            payload = None
            try:
                if budget["bytes"] >= registry.limits.max_total_bytes:
                    raise _FetchFailure("profile_budget_exhausted")
                payload = _transfer(
                    source, registry, transport, receipt, budget, deadline, clock
                )
                if publisher_snapshot is not None:
                    if len(payload) != publisher_snapshot["resource_bytes"] or (
                        publisher_snapshot["published_checksum"] is not None
                        and hashlib.new(
                            publisher_snapshot["checksum_comparison"], payload
                        ).hexdigest()
                        != publisher_snapshot["published_checksum"]
                    ):
                        raise _FetchFailure("publisher_snapshot_mismatch")
                    receipt["publisher_checksum_verified"] = (
                        True
                        if publisher_snapshot["published_checksum"] is not None
                        else None
                    )
                try:
                    parsed = parsers[source_id](
                        payload,
                        context=ParseContext(
                            source_id=source_id,
                            max_groups=registry.limits.max_groups,
                            max_input_bytes=registry.limits.source_byte_limit(
                                source_id
                            ),
                        ),
                    )
                    normalized, stats = _selection(parsed, source, registry, payload)
                except (ValueError, TypeError, KeyError, OverflowError):
                    raise _FetchFailure("parser_rejected") from None
                if (
                    publisher_snapshot is not None
                    and "decoded_sha256" in publisher_snapshot
                ):
                    if (
                        parsed.container_format != "zip"
                        or parsed.decoded_bytes != publisher_snapshot["decoded_bytes"]
                        or parsed.decoded_sha256 != publisher_snapshot["decoded_sha256"]
                    ):
                        raise _FetchFailure("publisher_decoded_snapshot_mismatch")
                    receipt["publisher_decoded_checksum_verified"] = True
                _remaining(deadline, clock, request_timeout)
                source_version = parsed.source_version
                source_version_field = parsed.source_version_field
                if source_version is None and publisher_snapshot is not None:
                    source_version = publisher_snapshot["version"]
                    source_version_field = publisher_snapshot["version_field"]
                receipt.update(
                    {
                        "parser_version": parsed.parser_version,
                        "source_version": source_version,
                        "source_version_field": source_version_field,
                        "version_fallback": None
                        if source_version is not None
                        else "complete_body_sha256",
                        "selected_provider_schemas": sorted(
                            {record.provider_schema for record in parsed.records}
                        ),
                        "container_format": parsed.container_format,
                        "container_member": parsed.container_member,
                        "decoded_bytes": parsed.decoded_bytes,
                        "decoded_sha256": parsed.decoded_sha256,
                        "normalized_selection_sha256": hashlib.sha256(
                            normalized
                        ).hexdigest(),
                        "stats": stats,
                    }
                )
                run.publish(f"{source_id}.jsonl", normalized)
                receipt["records_path"] = f"{source_id}.jsonl"
                receipt["status"] = "success"
            except _FetchFailure as exc:
                receipt["error_code"] = exc.code
                interrupted = exc.code == "interrupted"
                _release_exception_frames(exc)
            except KeyboardInterrupt as exc:
                receipt["error_code"] = "interrupted"
                interrupted = True
                _release_exception_frames(exc)
            except BaseException as exc:
                _release_exception_frames(exc)
                raise
            finally:
                # Drop mixed source bytes on every exit before saving a receipt
                # or beginning another source, including failed validation.
                payload = None
            if receipt["status"] == "failed" and receipt["records_path"] is None:
                receipt["normalized_selection_sha256"] = None
            receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
            run.publish(f"{source_id}.receipt.json", _json_bytes(receipt))
            manifest["sources"].append(receipt)
            if interrupted:
                manifest["not_attempted_sources"] = selected_ids[
                    len(manifest["sources"]) :
                ]
                break
        successes = sum(item["status"] == "success" for item in manifest["sources"])
        manifest["status"] = (
            "complete"
            if successes == len(selected_ids)
            else "partial"
            if successes
            else "failed"
        )
        manifest["total_bytes_received"] = budget["bytes"]
        source_results = {
            item["source_id"]: item["status"] for item in manifest["sources"]
        }
        for candidate in manifest["candidate_sources"]:
            if candidate["source_id"] in source_results:
                candidate["status"] = source_results[candidate["source_id"]]
            elif candidate["status"] == "authorized_not_started":
                candidate["status"] = "not_attempted_after_interrupt"
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        run.publish("manifest.json", _json_bytes(manifest))
        run.verify()
        if interrupted:
            raise KeyboardInterrupt
        return manifest
    finally:
        run.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "fetch"):
        child = subparsers.add_parser(command)
        child.add_argument("--profile", choices=["feasibility"], default="feasibility")
        child.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
        child.add_argument(
            "--project-root",
            type=Path,
            help="Root containing the registry's saved permission evidence; required when running an installed package outside its checkout",
        )
        child.add_argument("--source", action="append", dest="source_ids")
        if command == "fetch":
            child.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        kwargs = (
            {"project_root": args.project_root} if args.project_root is not None else {}
        )
        registry = load_registry(args.registry, **kwargs)
        if args.command == "preflight":
            result = preflight(registry, source_ids=args.source_ids)
        else:
            result = fetch_profile(
                registry, args.output_dir, source_ids=args.source_ids
            )
    except (SourceValidationError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status", "complete") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
