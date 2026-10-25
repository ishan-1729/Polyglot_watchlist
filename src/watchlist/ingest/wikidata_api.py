"""Provisional, offline-only validation of fictional Action API item batches.

This module has no transport, route registration or seed discovery. Its narrow
fixture contract is not a claim about a currently verified Wikimedia API. In
particular, JSON validation cannot establish that a live service supplied every
language or claim. Official contract evidence and separate authorization are
required before adapting or connecting this code to a live acquisition path.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import re
from typing import Literal

from watchlist.ingest._parse_common import (
    alias_evidence,
    require_text,
    source_record,
    strict_json,
    utf8_text,
)
from watchlist.ingest.source_registry import (
    ParseContext,
    SourceRecord,
    SourceValidationError,
)


PARSER_VERSION = "wikidata-action-api-fictional-v1"
ORGANIZATION_QID = "Q43229"
HUMAN_QID = "Q5"
_QID = re.compile(r"Q[1-9][0-9]{0,19}\Z")


@dataclass(frozen=True, slots=True)
class WikidataAPILimits:
    """Reducible offline bounds; these do not grant service or network access.

    The 15 MB decoded-total bound is an additional conservative in-memory input
    bound, not a measurement of received or compressed network bytes. Request
    pacing, wire-byte accounting and wall deadlines belong to a future approved
    acquisition owner, never to this offline parser.
    """

    max_candidates: int = 500
    max_groups: int = 200
    max_type_nodes: int = 800
    max_type_depth: int = 20
    max_batch_ids: int = 10
    max_responses: int = 250
    max_decoded_response_bytes: int = 4_000_000
    max_decoded_total_bytes: int = 15_000_000
    max_redirect_hops: int = 2
    max_type_statements: int = 256
    max_aliases: int = 128

    def __post_init__(self) -> None:
        ceilings = (500, 200, 800, 20, 10, 250, 4_000_000, 15_000_000, 2, 256, 128)
        for name, ceiling in zip(self.__dataclass_fields__, ceilings, strict=True):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise SourceValidationError("Invalid offline Wikidata limit.")


@dataclass(frozen=True, slots=True)
class WikidataAPIBatch:
    """A complete decoded fictional body and its externally known request IDs.

    Candidate batches must contain labels, aliases and complete claims. Type
    batches need complete claims and revision metadata; names are discarded.
    No URL, credentials, live-request switch or inferred seed is accepted here.
    """

    requested_ids: tuple[str, ...]
    purpose: Literal["candidate", "type"]
    payload: bytes


@dataclass(frozen=True, slots=True)
class TypeStatement:
    property_id: str
    rank: Literal["preferred", "normal", "deprecated"]
    value_kind: Literal["value", "somevalue", "novalue"]
    target_qid: str | None


@dataclass(frozen=True, slots=True)
class ItemTypeEvidence:
    """Only item revision and required classification facts, without names."""

    qid: str
    revision_id: int
    modified: str
    statements: tuple[TypeStatement, ...]
    response_sha256: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WikidataAPIOrganization:
    record: SourceRecord
    requested_ids: tuple[str, ...]
    redirect_edges: tuple[tuple[str, str], ...]
    classification: tuple[ItemTypeEvidence, ...]


@dataclass(frozen=True, slots=True)
class WikidataAPISelection:
    """Private eligible projections and counts; never a verified live contract."""

    organizations: tuple[WikidataAPIOrganization, ...]
    input_candidates: int
    supplied_type_ids: int
    examined_type_nodes: int
    eligible_organization_groups: int
    exclusion_counts: tuple[tuple[str, int], ...]
    decoded_input_bytes: int
    response_sha256: tuple[str, ...]
    parser_version: str = field(default=PARSER_VERSION, init=False)
    source_role: str = field(default="supplemental_unlabelled", init=False)
    contract_verified: bool = field(default=False, init=False)
    live_authorized: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _Item:
    qid: str
    revision_id: int
    modified: str
    statements: tuple[TypeStatement, ...]
    labels: object
    aliases: object


def _qid(value: object) -> str:
    if not isinstance(value, str) or not _QID.fullmatch(value):
        raise SourceValidationError("Expected a canonical item QID.")
    return value


def _mapping(value: object, message: str) -> dict:
    if not isinstance(value, dict):
        raise SourceValidationError(message)
    return value


def _statement(raw: object, property_id: str) -> TypeStatement:
    """Validate a relevant statement while discarding unrelated source fields."""
    value = _mapping(raw, "Invalid classification statement.")
    if (
        not {"mainsnak", "type", "rank"} <= set(value)
        or not set(value)
        <= {
            "mainsnak",
            "type",
            "rank",
            "id",
            "qualifiers",
            "qualifiers-order",
            "references",
        }
        or value["type"] != "statement"
        or value["rank"] not in ("preferred", "normal", "deprecated")
    ):
        raise SourceValidationError("Unsupported classification statement shape.")
    snak = _mapping(value["mainsnak"], "Invalid classification value.")
    if (
        not {"snaktype", "property", "datatype"} <= set(snak)
        or not set(snak) <= {"snaktype", "property", "datatype", "datavalue", "hash"}
        or snak["property"] != property_id
        or snak["datatype"] != "wikibase-item"
        or snak["snaktype"] not in ("value", "somevalue", "novalue")
    ):
        raise SourceValidationError("Unsupported classification value shape.")
    target = None
    if snak["snaktype"] == "value":
        data = _mapping(snak.get("datavalue"), "Missing classification target.")
        if set(data) != {"value", "type"} or data["type"] != "wikibase-entityid":
            raise SourceValidationError("Invalid item-valued classification.")
        entity = _mapping(data["value"], "Invalid classification item.")
        if (
            not {"entity-type", "id"} <= set(entity)
            or not set(entity) <= {"entity-type", "id", "numeric-id"}
            or entity["entity-type"] != "item"
        ):
            raise SourceValidationError("Classification must refer to an item.")
        target = _qid(entity["id"])
        if "numeric-id" in entity and (
            type(entity["numeric-id"]) is not int
            or entity["numeric-id"] != int(target[1:])
        ):
            raise SourceValidationError("Conflicting classification item IDs.")
    elif "datavalue" in snak:
        raise SourceValidationError("Non-value classification has a value.")
    return TypeStatement(property_id, value["rank"], snak["snaktype"], target)


def _item(raw: object, qid: str, limits: WikidataAPILimits) -> _Item | None:
    """Require a complete fictional item revision or an explicit missing marker."""
    value = _mapping(raw, "Invalid item document.")
    if value.get("id") != qid:
        raise SourceValidationError("Item key and canonical ID disagree.")
    if "missing" in value:
        if set(value) != {"id", "missing"} or value["missing"] != "":
            raise SourceValidationError("Unsupported missing-item document.")
        return None
    required = {"id", "type", "lastrevid", "modified", "claims"}
    allowed = required | {
        "labels",
        "aliases",
        "descriptions",
        "sitelinks",
        "pageid",
        "ns",
        "title",
    }
    if (
        not required <= set(value)
        or not set(value) <= allowed
        or value["type"] != "item"
    ):
        raise SourceValidationError("Incomplete or unsupported item document.")
    revision = value["lastrevid"]
    modified = value["modified"]
    if type(revision) is not int or not 1 <= revision <= 2**63 - 1:
        raise SourceValidationError("A positive item revision is required.")
    if not isinstance(modified, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", modified
    ):
        raise SourceValidationError("A complete UTC modification time is required.")
    try:
        datetime.strptime(modified, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise SourceValidationError("Invalid item modification time.") from exc
    claims = _mapping(value["claims"], "Complete classification claims are required.")
    statements = []
    for property_id in ("P31", "P279"):
        values = claims.get(property_id, [])
        if not isinstance(values, list) or len(values) > limits.max_type_statements:
            raise SourceValidationError("Classification exceeds its statement bound.")
        statements.extend(_statement(claim, property_id) for claim in values)
    return _Item(
        qid,
        revision,
        modified,
        tuple(
            sorted(
                set(statements),
                key=lambda item: (
                    item.property_id,
                    item.rank,
                    item.value_kind,
                    item.target_qid or "",
                ),
            )
        ),
        value.get("labels"),
        value.get("aliases"),
    )


def _resolve(
    qid: str, redirects: dict[str, str], limit: int
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Resolve only supplied, bounded item redirects and retain every edge."""
    edges = []
    visited = {qid}
    while qid in redirects:
        target = redirects[qid]
        if target in visited or len(edges) >= limit:
            raise SourceValidationError("Cyclic or excessive item redirects.")
        edges.append((qid, target))
        visited.add(target)
        qid = target
    return qid, tuple(edges)


def _decode_batch(
    batch: WikidataAPIBatch, limits: WikidataAPILimits
) -> tuple[dict[str, _Item | None], dict[str, str], str]:
    """Reject partial/error bodies and bind every returned item to a request."""
    if (
        not isinstance(batch, WikidataAPIBatch)
        or batch.purpose not in ("candidate", "type")
        or not isinstance(batch.requested_ids, tuple)
        or not 1 <= len(batch.requested_ids) <= limits.max_batch_ids
        or not isinstance(batch.payload, bytes)
        or not 1 <= len(batch.payload) <= limits.max_decoded_response_bytes
    ):
        raise SourceValidationError("Invalid or oversized offline API batch.")
    requested = {_qid(qid) for qid in batch.requested_ids}
    if len(requested) != len(batch.requested_ids):
        raise SourceValidationError("Duplicate requested item ID.")
    document = _mapping(strict_json(utf8_text(batch.payload)), "Invalid API response.")
    if (
        not {"entities", "success"} <= set(document)
        or not set(document) <= {"entities", "success", "redirects"}
        or type(document["success"]) is not int
        or document["success"] != 1
    ):
        raise SourceValidationError("Incomplete, failed or unsupported API response.")
    raw_redirects = document.get("redirects", [])
    if (
        not isinstance(raw_redirects, list)
        or len(raw_redirects) > len(requested) * limits.max_redirect_hops
    ):
        raise SourceValidationError("Invalid item redirect collection.")
    redirects = {}
    for raw in raw_redirects:
        if not isinstance(raw, dict) or set(raw) != {"from", "to"}:
            raise SourceValidationError("Invalid item redirect mapping.")
        original, target = _qid(raw["from"]), _qid(raw["to"])
        if original in redirects:
            raise SourceValidationError("Duplicate item redirect mapping.")
        redirects[original] = target
    resolved = set()
    used_redirects = set()
    for qid in requested:
        canonical, edges = _resolve(qid, redirects, limits.max_redirect_hops)
        resolved.add(canonical)
        used_redirects.update(original for original, _ in edges)
    if used_redirects != set(redirects):
        raise SourceValidationError("Unrequested item redirect mapping.")
    entities = _mapping(document["entities"], "Item response must contain an object.")
    if set(entities) != resolved:
        raise SourceValidationError("Response IDs differ from the requested items.")
    items = {_qid(qid): _item(value, qid, limits) for qid, value in entities.items()}
    if batch.purpose == "candidate" and any(
        item is not None and (item.labels is None or item.aliases is None)
        for item in items.values()
    ):
        raise SourceValidationError(
            "Candidate labels and aliases must both be supplied."
        )
    return items, redirects, hashlib.sha256(batch.payload).hexdigest()


def _best_targets(item: _Item, property_id: str) -> tuple[tuple[str, ...], bool]:
    """Model truthy rank precedence; unknown/no-value assertions stay unresolved."""
    statements = [
        claim for claim in item.statements if claim.property_id == property_id
    ]
    rank = (
        "preferred"
        if any(claim.rank == "preferred" for claim in statements)
        else "normal"
    )
    chosen = [claim for claim in statements if claim.rank == rank]
    return (
        tuple(
            sorted(
                {claim.target_qid for claim in chosen if claim.target_qid is not None}
            )
        ),
        any(claim.value_kind != "value" for claim in chosen),
    )


def _classify(
    candidate: _Item,
    items: dict[str, _Item | None],
    redirects: dict[str, str],
    limits: WikidataAPILimits,
    examined: set[str],
) -> tuple[str, tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Resolve every relevant parent branch; bounded unknown frontiers fail closed."""
    types, unknown = _best_targets(candidate, "P31")
    if HUMAN_QID in types:
        return "human", (), ()
    if unknown:
        return "unresolved_type", (), ()
    if ORGANIZATION_QID not in types:
        return "not_direct_organization", (), ()
    pending = deque((qid, 0) for qid in types)
    visited: set[str] = set()
    edges: set[tuple[str, str]] = set()
    unresolved = False
    while pending:
        qid, depth = pending.popleft()
        canonical, redirect_path = _resolve(qid, redirects, limits.max_redirect_hops)
        edges.update(redirect_path)
        if canonical in visited:
            continue
        if canonical not in examined and len(examined) >= limits.max_type_nodes:
            unresolved = True
            continue
        examined.add(canonical)
        if depth > limits.max_type_depth:
            unresolved = True
            continue
        if canonical == HUMAN_QID:
            return "human", (), ()
        visited.add(canonical)
        item = items.get(canonical)
        if item is None:
            unresolved = True
            continue
        class_types, class_unknown = _best_targets(item, "P31")
        resolved_class_types = set()
        for class_type in class_types:
            resolved_type, redirect_path = _resolve(
                class_type, redirects, limits.max_redirect_hops
            )
            resolved_class_types.add(resolved_type)
            edges.update(redirect_path)
        if class_unknown or HUMAN_QID in resolved_class_types:
            # Unknown instance typing or an individual used as a class cannot
            # support eligibility. Do not retain that node as class evidence.
            unresolved = True
            continue
        parents, unknown = _best_targets(item, "P279")
        if unknown:
            unresolved = True
        for parent in parents:
            if parent not in visited:
                pending.append((parent, depth + 1))
    return (
        ("unresolved_type" if unresolved else "eligible"),
        tuple(sorted(visited)),
        tuple(sorted(edges)),
    )


def _record(item: _Item, limits: WikidataAPILimits) -> SourceRecord:
    """Keep every supplied name and language or fail; never truncate a group."""
    context = ParseContext(source_id="wikidata_orgs", max_aliases=limits.max_aliases)
    labels = _mapping(item.labels, "Complete label collection is required.")
    aliases = _mapping(item.aliases, "Complete alias collection is required.")
    names = []
    primary = []
    for field_name, collection in (("labels", labels), ("aliases", aliases)):
        for language, raw in collection.items():
            require_text(language, "name language", maximum=64)
            if not re.fullmatch(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*", language):
                raise SourceValidationError("Unsupported name-language tag.")
            values = [raw] if field_name == "labels" else raw
            if not isinstance(values, list):
                raise SourceValidationError(
                    "Each language alias collection must be an array."
                )
            for value in values:
                if (
                    not isinstance(value, dict)
                    or set(value) != {"language", "value"}
                    or value["language"] != language
                ):
                    raise SourceValidationError(
                        "Incomplete or conflicting name-language evidence."
                    )
                evidence = alias_evidence(
                    value["value"],
                    f"{field_name}.{language}{'[]' if field_name == 'aliases' else ''}.value",
                    context,
                    language=language,
                )
                names.append(evidence)
                if field_name == "labels":
                    primary.append(evidence.value)
    if not primary:
        raise SourceValidationError("An eligible organization requires a source label.")
    return source_record(
        context,
        provider_id=item.qid,
        entity_type="organization",
        primary_name=min(primary),
        aliases=names,
        provider_schema="wikidata:P31:Q43229",
        classification_basis="Provisional API direct-P31 organization; complete best-rank human-path check",
    )


def parse_fictional_wikidata_api_batches(
    batches: Iterable[WikidataAPIBatch],
    *,
    limits: WikidataAPILimits = WikidataAPILimits(),
) -> WikidataAPISelection:
    """Validate bounded supplied fixtures and return only eligible organizations.

    Missing and unresolved candidates contribute aggregate counts, not retained
    personal identifiers. Every batch and eligible name group is validated before
    the final group cap. Shared IDs at conflicting revisions fail the entire
    input; no last-response-wins snapshot is invented. No network is performed.
    """
    if not isinstance(limits, WikidataAPILimits):
        raise SourceValidationError("Invalid offline API limits.")
    items: dict[str, _Item | None] = {}
    redirects: dict[str, str] = {}
    requested: dict[str, set[str]] = {"candidate": set(), "type": set()}
    hashes: list[str] = []
    item_hashes: dict[str, set[str]] = {}
    total_bytes = 0
    for index, batch in enumerate(batches):
        if index >= limits.max_responses:
            raise SourceValidationError("Offline API input exceeds its response bound.")
        values, mappings, digest = _decode_batch(batch, limits)
        total_bytes += len(batch.payload)
        if total_bytes > limits.max_decoded_total_bytes:
            raise SourceValidationError(
                "Offline API input exceeds its total byte bound."
            )
        seen = requested[batch.purpose]
        if seen.intersection(batch.requested_ids):
            raise SourceValidationError(
                "A requested ID is repeated within one purpose."
            )
        seen.update(batch.requested_ids)
        if len(seen) > (
            limits.max_candidates
            if batch.purpose == "candidate"
            else limits.max_type_nodes
        ):
            raise SourceValidationError(
                "Offline API input exceeds its examined-ID bound."
            )
        for original, target in mappings.items():
            if original in redirects and redirects[original] != target:
                raise SourceValidationError("Conflicting redirect snapshots.")
            redirects[original] = target
        for qid, value in values.items():
            if qid in items:
                old = items[qid]
                if old is None or value is None:
                    if old != value:
                        raise SourceValidationError(
                            "Conflicting missing-item snapshots."
                        )
                elif (old.qid, old.revision_id, old.modified, old.statements) != (
                    value.qid,
                    value.revision_id,
                    value.modified,
                    value.statements,
                ):
                    raise SourceValidationError(
                        "Conflicting item revision or type snapshots."
                    )
                elif (
                    old.labels is not None
                    and value.labels is not None
                    and (old.labels, old.aliases) != (value.labels, value.aliases)
                ):
                    raise SourceValidationError(
                        "Conflicting name snapshots at one revision."
                    )
                elif value.labels is None:
                    value = old
            items[qid] = value
            item_hashes.setdefault(qid, set()).add(digest)
        hashes.append(digest)
    if not hashes or not requested["candidate"]:
        raise SourceValidationError("At least one candidate batch is required.")
    if set(items).intersection(redirects):
        raise SourceValidationError(
            "An item is both a redirect and an entity snapshot."
        )
    groups: dict[str, list[str]] = {}
    candidate_edges: dict[str, set[tuple[str, str]]] = {}
    for qid in sorted(requested["candidate"]):
        canonical, path = _resolve(qid, redirects, limits.max_redirect_hops)
        groups.setdefault(canonical, []).append(qid)
        candidate_edges.setdefault(canonical, set()).update(path)
    organizations = []
    exclusions: Counter[str] = Counter()
    examined: set[str] = set()
    eligible = 0
    for canonical, original_ids in sorted(groups.items()):
        item = items.get(canonical)
        if item is None:
            exclusions["missing"] += len(original_ids)
            continue
        decision, class_ids, class_edges = _classify(
            item, items, redirects, limits, examined
        )
        if decision != "eligible":
            exclusions[decision] += len(original_ids)
            continue
        record = _record(item, limits)
        eligible += 1
        if len(organizations) >= limits.max_groups:
            exclusions["group_limit"] += len(original_ids)
            continue
        evidence = []
        for qid in sorted({canonical, *class_ids}):
            node = items[qid]
            assert node is not None
            properties = {"P31", "P279"} if qid in class_ids else {"P31"}
            evidence.append(
                ItemTypeEvidence(
                    qid,
                    node.revision_id,
                    node.modified,
                    tuple(
                        claim
                        for claim in node.statements
                        if claim.property_id in properties
                    ),
                    tuple(sorted(item_hashes[qid])),
                )
            )
        organizations.append(
            WikidataAPIOrganization(
                record,
                tuple(original_ids),
                tuple(sorted(candidate_edges[canonical] | set(class_edges))),
                tuple(evidence),
            )
        )
    return WikidataAPISelection(
        organizations=tuple(organizations),
        input_candidates=len(requested["candidate"]),
        supplied_type_ids=len(requested["type"]),
        examined_type_nodes=len(examined),
        eligible_organization_groups=eligible,
        exclusion_counts=tuple(sorted(exclusions.items())),
        decoded_input_bytes=total_bytes,
        response_sha256=tuple(hashes),
    )
