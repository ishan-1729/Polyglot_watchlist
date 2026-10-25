"""One serial, receipt-backed official-metadata session; never fetch datasets.

The endpoint policy is an explicit local review artifact. Redirects are not
followed automatically. A complete HTTP response is evidence for later review,
not proof of permission or of a working corpus adapter.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import urlsplit

from watchlist.ingest.acquire import (
    HTTPTransport,
    Transport,
    _FetchFailure,
    _HTTPResponse,
    _PinnedHTTPSConnection,
)
from watchlist.ingest.source_registry import strict_json_loads


LIMITS = {
    "total_bytes": 5_000_000,
    "transactions": 16,
    "response_bytes": 512_000,
    "request_seconds": 30,
    "session_seconds": 3600,
}
SOURCES = {"opensanctions_un", "ofac_sdn", "eu_consolidated", "wikidata_orgs"}
HOSTS = {
    "www.opensanctions.org",
    "data.opensanctions.org",
    "creativecommons.org",
    "ofac.treasury.gov",
    "sanctionslistservice.ofac.treas.gov",
    "www.copyright.gov",
    "data.europa.eu",
    "commission.europa.eu",
    "webgate.ec.europa.eu",
    "www.wikidata.org",
    "www.mediawiki.org",
    "foundation.wikimedia.org",
}
# Exact metadata-only routes reviewed against the saved registry and 08A plan.
# New routes require a code/policy review, not a hostname-wide exception.
REVIEWED_ROUTES = {
    (
        "opensanctions_un",
        "https://www.opensanctions.org/docs/commercial/exemption/",
        "GET",
        "html",
    ),
    (
        "opensanctions_un",
        "https://creativecommons.org/licenses/by-nc/4.0/legalcode.en",
        "GET",
        "html",
    ),
    (
        "opensanctions_un",
        "https://data.opensanctions.org/datasets/latest/un_sc_sanctions/index.json",
        "GET",
        "json",
    ),
    (
        "opensanctions_un",
        "https://data.opensanctions.org/artifacts/un_sc_sanctions/20261024160105-nsw/index.json",
        "GET",
        "json",
    ),
    # Exact current index from the saved metadata-10 redirect, reviewed before
    # using the reserved sixteenth transaction; never a dataset or host wildcard.
    (
        "opensanctions_un",
        "https://data.opensanctions.org/artifacts/un_sc_sanctions/20261025000105-chi/index.json",
        "GET",
        "json",
    ),
    (
        "ofac_sdn",
        "https://ofac.treasury.gov/sdn-list-data-formats-data-schemas/tutorial-on-the-use-of-list-related-legacy-flat-files",
        "GET",
        "html",
    ),
    (
        "ofac_sdn",
        "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/SdnList",
        "POST",
        "json",
    ),
    ("ofac_sdn", "https://www.copyright.gov/title17/92chap1.html", "GET", "html"),
    (
        "eu_consolidated",
        "https://data.europa.eu/api/hub/search/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions",
        "GET",
        "json",
    ),
    ("eu_consolidated", "https://commission.europa.eu/legal-notice_en", "GET", "html"),
    (
        "eu_consolidated",
        "https://webgate.ec.europa.eu/fsd/fsf/public/files/xsdFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
        "GET",
        "xml",
    ),
    (
        "wikidata_orgs",
        "https://www.wikidata.org/wiki/Wikidata:Data_access",
        "GET",
        "html",
    ),
    (
        "wikidata_orgs",
        "https://www.wikidata.org/wiki/Wikidata:Copyright",
        "GET",
        "html",
    ),
    (
        "wikidata_orgs",
        "https://foundation.wikimedia.org/wiki/Special:MyLanguage/User-Agent_policy",
        "GET",
        "html",
    ),
    (
        "wikidata_orgs",
        "https://www.wikidata.org/w/api.php?action=paraminfo&modules=wbgetentities%7Cwbsearchentities&format=json&formatversion=2",
        "GET",
        "json",
    ),
    (
        "wikidata_orgs",
        "https://www.mediawiki.org/wiki/Wikibase/Indexing/RDF_Dump_Format",
        "GET",
        "html",
    ),
}


class MetadataError(ValueError):
    """The metadata policy, evidence path or response is not acceptable."""


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_policy(path: Path, project_root: Path) -> dict:
    """Validate exact reviewed metadata routes and hash-bound local rationale."""
    policy = strict_json_loads(path.read_bytes())
    if not isinstance(policy, dict) or set(policy) != {
        "schema_version",
        "scope",
        "approval",
        "limits",
        "endpoints",
    }:
        raise MetadataError("invalid policy fields")
    if policy["schema_version"] != 1 or policy["scope"] != "08B-1-metadata-only":
        raise MetadataError("not an approved metadata policy")
    if (
        policy["limits"] != LIMITS
        or not isinstance(policy["approval"], str)
        or not policy["approval"]
    ):
        raise MetadataError("metadata limits or approval invalid")
    endpoints = policy["endpoints"]
    if not isinstance(endpoints, list) or not 1 <= len(endpoints) <= 16:
        raise MetadataError("invalid endpoint count")
    seen: set[str] = set()
    routes: set[str] = set()
    root = project_root.resolve(strict=True)
    for endpoint in endpoints:
        if not isinstance(endpoint, dict) or set(endpoint) != {
            "id",
            "source_id",
            "url",
            "method",
            "kind",
            "purpose",
            "basis",
            "basis_sha256",
        }:
            raise MetadataError("invalid endpoint fields")
        if any(not isinstance(v, str) or not v for v in endpoint.values()):
            raise MetadataError("invalid endpoint values")
        if (
            tuple(endpoint[k] for k in ("source_id", "url", "method", "kind"))
            not in REVIEWED_ROUTES
        ):
            raise MetadataError("route is not in the exact reviewed metadata allowlist")
        identifier, url = endpoint["id"], endpoint["url"]
        if (
            not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", identifier)
            or identifier in seen
            or url in routes
        ):
            raise MetadataError("duplicate or unsafe endpoint")
        seen.add(identifier)
        routes.add(url)
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.hostname not in HOSTS
            or parts.port not in (None, 443)
            or parts.username
            or parts.password
            or parts.fragment
            or any(ord(c) < 33 or ord(c) > 126 for c in url)
        ):
            raise MetadataError("unapproved metadata destination")
        if endpoint["source_id"] not in SOURCES or endpoint["kind"] not in {
            "html",
            "json",
            "xml",
            "text",
        }:
            raise MetadataError("invalid metadata source or format")
        if endpoint["method"] not in {"GET", "POST"}:
            raise MetadataError("invalid metadata method")
        if (
            endpoint["method"] == "POST"
            and url
            != "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/SdnList"
        ):
            raise MetadataError(
                "only reviewed read-only OFAC metadata POST is permitted"
            )
        # Reject obvious data routes even if accidentally placed into metadata.
        if any(
            token in parts.path.lower()
            for token in (
                "entities.ftm",
                "sdn_xml.zip",
                "xmlfullsanctionslist",
                "/entity/",
                "/special:entitydata/",
            )
        ):
            raise MetadataError("dataset route in metadata policy")
        if parts.path == "/w/api.php" and not (
            parts.hostname == "www.wikidata.org"
            and endpoint["method"] == "GET"
            and parts.query
            == "action=paraminfo&modules=wbgetentities%7Cwbsearchentities&format=json&formatversion=2"
        ):
            raise MetadataError("only exact module metadata query is permitted")
        basis = root / endpoint["basis"]
        if (
            basis.is_symlink()
            or not basis.is_file()
            or not basis.resolve().is_relative_to(root)
            or _digest(basis.read_bytes()) != endpoint["basis_sha256"]
        ):
            raise MetadataError("metadata rationale evidence mismatch")
    return policy


class MetadataTransport(HTTPTransport):
    """Reuse bounded verified TLS, with one explicit read-only metadata POST."""

    def __init__(self, policy: dict) -> None:
        self.methods = {e["url"]: e["method"] for e in policy["endpoints"]}

    def open(self, url: str, *, timeout: float):
        method = self.methods[url]
        if method == "GET":
            return super().open(url, timeout=timeout)
        parts = urlsplit(url)
        connection = _PinnedHTTPSConnection(
            parts.hostname, deadline=time.monotonic() + timeout
        )
        try:
            connection.request(
                "POST",
                parts.path,
                body=b"",
                headers={
                    "User-Agent": "PolyglotWatchlistResearch/0.8 (https://github.com/raiha-siddiqui/Polyglot_watchlist; metadata only)",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            return _HTTPResponse(connection.getresponse(), connection, url)
        except BaseException:
            connection.close()
            raise


def _write(path: Path, value: dict, *, replace: bool = False) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    target = path.with_suffix(".pending") if replace else path
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(target, path)


def _format_valid(payload: bytes, kind: str, content_type: str) -> bool:
    if kind == "json":
        try:
            return isinstance(strict_json_loads(payload), (dict, list))
        except (ValueError, UnicodeError):
            return False
    if kind == "html":
        return "html" in content_type.lower() and b"<" in payload[:1024]
    if kind == "xml":
        return (
            "xml" in content_type.lower() or "text/plain" in content_type.lower()
        ) and payload.lstrip().startswith(b"<")
    return content_type.lower().startswith("text/")


def _validated_prior(
    path: Path, root: Path, seen: set[Path] | None = None
) -> tuple[dict, str]:
    """Verify the completed batch chain and every receipt before carrying limits."""
    seen = set() if seen is None else seen
    resolved = path.resolve(strict=True)
    if (
        path.is_symlink()
        or resolved in seen
        or not resolved.is_relative_to(root.resolve())
    ):
        raise MetadataError("unsafe previous metadata receipt")
    seen.add(resolved)
    payload = path.read_bytes()
    prior = strict_json_loads(payload)
    if not isinstance(prior, dict) or prior.get("status") != "finished_metadata_only":
        raise MetadataError("invalid or unfinished previous metadata batch")
    if (
        prior.get("limits") != LIMITS
        or prior.get("scope") != "08B-1-metadata-only"
        or prior.get("reserved_bytes") != 0
    ):
        raise MetadataError("invalid previous metadata limits")
    for key, maximum in (
        ("transactions", LIMITS["transactions"]),
        ("bytes_received", LIMITS["total_bytes"]),
    ):
        if type(prior.get(key)) is not int or not 0 <= prior[key] <= maximum:
            raise MetadataError("invalid previous metadata accounting")
    results = prior.get("results")
    if not isinstance(results, list) or len(results) != prior["transactions"]:
        raise MetadataError("invalid previous transaction list")
    urls: set[str] = set()
    for item in results:
        if (
            not isinstance(item, dict)
            or type(item.get("bytes_received")) is not int
            or not 0 <= item["bytes_received"] <= LIMITS["response_bytes"]
            or not isinstance(item.get("url"), str)
            or item["url"] in urls
        ):
            raise MetadataError("invalid previous per-response accounting")
        urls.add(item["url"])
    if sum(item["bytes_received"] for item in results) != prior["bytes_received"]:
        raise MetadataError("inconsistent previous byte accounting")
    policy_path = path.parent / "policy.json"
    policy = load_policy(policy_path, root)
    if _digest(policy_path.read_bytes()) != prior.get("policy_artifact_sha256"):
        raise MetadataError("previous policy artifact changed")
    prefix = 0
    if "previous_session" in prior:
        reference = prior["previous_session"]
        ancestor, ancestor_hash = _validated_prior(Path(reference["path"]), root, seen)
        if (
            ancestor_hash != reference["sha256"]
            or results[: ancestor["transactions"]] != ancestor["results"]
            or prior["started_at_utc"] != ancestor["started_at_utc"]
        ):
            raise MetadataError("previous batch chain changed")
        prefix = ancestor["transactions"]
    routes = {e["id"]: e for e in policy["endpoints"]}
    for item in results[prefix:]:
        entry = routes.get(item.get("id"))
        if entry is None or any(
            item.get(k) != entry[k] for k in ("url", "method", "source_id")
        ):
            raise MetadataError("previous result does not match reviewed route")
        saved = path.parent / (entry["id"] + ".receipt.json")
        if saved.is_symlink() or strict_json_loads(saved.read_bytes()) != item:
            raise MetadataError("previous transaction receipt changed")
        if "artifact" in item:
            if item["artifact"] != entry["id"] + ".body":
                raise MetadataError("unsafe metadata evidence path")
            artifact = path.parent / item["artifact"]
            if (
                artifact.is_symlink()
                or artifact.stat().st_size != item["bytes_received"]
                or _digest(artifact.read_bytes()) != item["received_sha256"]
            ):
                raise MetadataError("previous metadata body changed")
    return prior, _digest(payload)


def run_session(
    policy_path: Path,
    output: Path,
    *,
    project_root: Path,
    transport: Transport | None = None,
    clock: Callable[[], float] = time.monotonic,
    previous: Path | None = None,
) -> dict:
    """Run each approved route once, serially, saving charged failure receipts.

    Reserve the full remaining per-response allowance before each request. A
    crash leaves that reservation charged and the session incomplete. Existing
    directories cannot be reused. An explicitly supplied completed prior batch
    carries its counters and original wall deadline forward; it never retries a
    URL. There is no automatic resume, and incomplete batches cannot continue.
    """
    policy = load_policy(policy_path, project_root)
    prior = None
    prior_hash = None
    if previous is not None:
        prior, prior_hash = _validated_prior(previous, project_root)
        if (
            prior.get("status") != "finished_metadata_only"
            or prior.get("limits") != LIMITS
            or prior.get("scope") != policy["scope"]
            or prior.get("reserved_bytes") != 0
            or prior.get("transactions") != len(prior.get("results", []))
            or prior.get("bytes_received")
            != sum(r["bytes_received"] for r in prior["results"])
            or not 0 <= prior["transactions"] <= LIMITS["transactions"]
            or not 0 <= prior["bytes_received"] <= LIMITS["total_bytes"]
        ):
            raise MetadataError("invalid or unfinished previous metadata batch")
        if {e["url"] for e in policy["endpoints"]} & {
            r["url"] for r in prior["results"]
        }:
            raise MetadataError("metadata URL already attempted; retries are forbidden")
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(prior["started_at_utc"])
        ).total_seconds()
        if not 0 <= age < LIMITS["session_seconds"]:
            raise MetadataError(
                "prior session deadline expired or clock moved backwards"
            )
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise MetadataError("metadata output already exists")
    if not output.parent.is_dir() or any(
        p.is_symlink() for p in [output.parent, *output.parents]
    ):
        raise MetadataError("unsafe metadata output parent")
    output.mkdir(mode=0o700)
    started = clock()
    deadline = started + LIMITS["session_seconds"] - (age if prior else 0)
    state = {
        "schema_version": 1,
        "scope": policy["scope"],
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "limits": LIMITS,
        "policy_sha256": _digest(policy_path.read_bytes()),
        "transactions": 0,
        "bytes_received": 0,
        "reserved_bytes": 0,
        "results": [],
        "dataset_acquisition_authorized": False,
    }
    if prior is not None:
        state.update(
            {
                key: prior[key]
                for key in (
                    "started_at_utc",
                    "transactions",
                    "bytes_received",
                    "results",
                )
            }
        )
        state["previous_session"] = {
            "path": str(previous.absolute()),
            "sha256": prior_hash,
        }
    _write(output / "policy.json", policy)
    state["policy_artifact_sha256"] = _digest((output / "policy.json").read_bytes())
    _write(output / "session.json", state)
    transport = MetadataTransport(policy) if transport is None else transport
    try:
        for endpoint in policy["endpoints"]:
            available = LIMITS["total_bytes"] - state["bytes_received"]
            if (
                clock() >= deadline
                or state["transactions"] >= LIMITS["transactions"]
                or available <= 0
            ):
                state["stop_reason"] = "session_limit"
                break
            cap = min(LIMITS["response_bytes"], available)
            state["reserved_bytes"] = cap
            state["transactions"] += 1
            _write(output / "session.json", state, replace=True)
            item = {
                "id": endpoint["id"],
                "source_id": endpoint["source_id"],
                "url": endpoint["url"],
                "method": endpoint["method"],
                "bytes_received": 0,
                "outcome": "failed",
                "http_status": None,
                "complete": False,
                "contract_verified": False,
            }
            request_start = clock()
            request_deadline = min(deadline, request_start + LIMITS["request_seconds"])
            response = None
            body = bytearray()
            hasher = hashlib.sha256()
            try:
                timeout = request_deadline - clock()
                if timeout <= 0:
                    raise TimeoutError()
                response = transport.open(endpoint["url"], timeout=timeout)
                if clock() >= request_deadline:
                    raise TimeoutError()
                if response.url != endpoint["url"]:
                    raise MetadataError("unreviewed_transport_redirect")
                item["http_status"] = response.status
                if (
                    type(response.status) is not int
                    or not 100 <= response.status <= 599
                ):
                    raise MetadataError("invalid_http_status")
                headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                if headers.get("content-encoding", "identity").lower() != "identity":
                    raise MetadataError("unexpected_content_encoding")
                length = headers.get("content-length")
                declared = None
                if length is not None:
                    if not re.fullmatch(r"[0-9]{1,20}", length):
                        raise MetadataError("invalid_content_length")
                    declared = int(length)
                    if declared > cap:
                        raise MetadataError("declared_body_exceeds_cap")
                encoding = headers.get("transfer-encoding")
                if encoding and (encoding.lower() != "chunked" or declared is not None):
                    raise MetadataError("invalid_transfer_framing")
                while True:
                    remaining = cap - item["bytes_received"]
                    timeout = request_deadline - clock()
                    if timeout <= 0:
                        raise TimeoutError()
                    if declared is not None and item["bytes_received"] == declared:
                        break
                    if remaining <= 0:
                        raise MetadataError("response_cap_before_eof")
                    size = min(16384, remaining)
                    chunk = response.read(size, timeout=timeout)
                    if not isinstance(chunk, bytes):
                        raise MetadataError("invalid_transport_chunk")
                    item["bytes_received"] += len(chunk)
                    state["bytes_received"] += len(chunk)
                    hasher.update(chunk)
                    if len(chunk) > size:
                        raise MetadataError("transport_exceeded_read_bound")
                    if clock() >= request_deadline:
                        raise TimeoutError()
                    if declared is not None and item["bytes_received"] > declared:
                        raise MetadataError("content_length_mismatch")
                    if not chunk:
                        if declared is not None and item["bytes_received"] != declared:
                            raise MetadataError("incomplete_response")
                        break
                    body.extend(chunk)
                item["complete"] = True
                if response.status in (301, 302, 303, 307, 308):
                    # Record route evidence without following or leaking signing parameters.
                    location = headers.get("location", "")
                    item["redirect_location_sha256"] = _digest(location.encode())
                    try:
                        parts = urlsplit(location)
                        if (
                            parts.scheme == "https"
                            and parts.hostname
                            and not parts.username
                            and not parts.password
                        ):
                            item["redirect_location_without_query"] = parts._replace(
                                query="", fragment=""
                            ).geturl()
                    except ValueError:
                        pass
                    raise MetadataError("redirect_not_followed")
                if response.status != 200:
                    raise MetadataError("http_non_200")
                if not _format_valid(
                    bytes(body), endpoint["kind"], headers.get("content-type", "")
                ):
                    raise MetadataError("unexpected_metadata_format")
                artifact = output / (endpoint["id"] + ".body")
                descriptor = os.open(
                    artifact, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                item["artifact"] = artifact.name
                item["outcome"] = "complete_metadata_pending_review"
                item["content_type"] = headers.get("content-type", "")
            except MetadataError as error:
                item["error"] = str(error)
            except TimeoutError:
                item["error"] = "request_timeout"
            except _FetchFailure as error:
                item["error"] = error.code
            except http.client.IncompleteRead as error:
                # Preserve explicitly returned partial bytes in accounting,
                # without accepting or saving an incomplete metadata body.
                partial = error.partial
                if isinstance(partial, bytes):
                    item["bytes_received"] += len(partial)
                    state["bytes_received"] += len(partial)
                    hasher.update(partial)
                    item["error"] = (
                        "transport_exceeded_read_bound"
                        if item["bytes_received"] > cap
                        else "incomplete_response"
                    )
                else:
                    item["error"] = "invalid_transport_partial"
            except (OSError, http.client.HTTPException):
                item["error"] = "transport_failure"
            except BaseException:
                item["error"] = "interrupted_or_unexpected_failure"
                state["status"] = "aborted_no_automatic_resume"
                raise
            finally:
                if response is not None:
                    try:
                        response.close()
                    except OSError:
                        pass
                body.clear()
                item["received_sha256"] = hasher.hexdigest()
                item["elapsed_seconds"] = round(clock() - request_start, 6)
                state["reserved_bytes"] = 0
                state["results"].append(item)
                _write(output / (endpoint["id"] + ".receipt.json"), item)
                _write(output / "session.json", state, replace=True)
            if item.get("error") in {
                "transport_exceeded_read_bound",
                "invalid_transport_partial",
            }:
                state["stop_reason"] = "invalid_transport"
                break
        state["status"] = "finished_metadata_only"
    finally:
        state["elapsed_seconds"] = round(clock() - started + (age if prior else 0), 6)
        state["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write(output / "session.json", state, replace=True)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--execute-approved-metadata", action="store_true")
    parser.add_argument("--previous-session", type=Path)
    args = parser.parse_args(argv)
    if not args.execute_approved_metadata:
        load_policy(args.policy, args.project_root)
        print("Metadata policy validated offline; no request sent.")
        return 0
    result = run_session(
        args.policy,
        args.output,
        project_root=args.project_root,
        previous=args.previous_session,
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "transactions",
                    "bytes_received",
                    "elapsed_seconds",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
