"""Reviewed source policy and lossless, non-person parser boundary types.

This module performs no network access. A public URL is not a permission grant:
the checked-in registry carries the separate review decision for each source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Literal, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit


SOURCE_IDS = (
    "opensanctions_un",
    "un_consolidated",
    "ofac_sdn",
    "eu_consolidated",
    "wikidata_orgs",
)
PARSER_IDS = dict(zip(SOURCE_IDS, ("ftm", "un", "ofac", "eu", "wikidata")))
MAX_SOURCE_BYTES = 10_000_000
MAX_EU_SOURCE_BYTES = 32_000_000
MAX_TOTAL_BYTES = 50_000_000
MAX_GROUPS = 200
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "data-sources.json"
WIKIDATA_QUERY = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?item ?name ?name_kind ?type WHERE {
  { SELECT ?item WHERE {
      { SELECT ?item WHERE {
          ?item wdt:P31 wd:Q43229 .
        } LIMIT 20 }
      FILTER NOT EXISTS {
        ?item wdt:P31 ?candidateType .
        ?candidateType wdt:P279* wd:Q5 .
      }
    } }
  { ?item rdfs:label ?name . BIND("label" AS ?name_kind) }
  UNION
  { ?item skos:altLabel ?name . BIND("alias" AS ?name_kind) }
  BIND(wd:Q43229 AS ?type)
}"""
WIKIDATA_URL = "https://query.wikidata.org/sparql?" + urlencode(
    {"query": WIKIDATA_QUERY, "format": "json"}
)
OFAC_OBJECT_HOST = "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com"
OFAC_OBJECT_PATH = re.compile(
    r"/Published/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"/[0-9]{4}-[0-9]{2}-[0-9]{2}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/SDN_XML\.ZIP"
)
OFAC_SIGNED_QUERY_LIMITS = {
    "X-Amz-Expires": 4,
    "X-Amz-Security-Token": 8192,
    "response-content-disposition": 512,
    "response-content-type": 128,
    "X-Amz-Algorithm": 32,
    "X-Amz-Credential": 512,
    "X-Amz-Date": 16,
    "X-Amz-SignedHeaders": 128,
    "X-Amz-Signature": 64,
}


def _validate_ofac_signed_query(query: str) -> None:
    """Allow the publisher's observed public-download signature shape only."""
    try:
        values = parse_qs(query, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise SourceValidationError("invalid OFAC redirect query") from exc
    if set(values) != set(OFAC_SIGNED_QUERY_LIMITS):
        raise SourceValidationError("unexpected OFAC redirect query keys")
    for key, maximum in OFAC_SIGNED_QUERY_LIMITS.items():
        if len(values[key]) != 1:
            raise SourceValidationError("duplicate OFAC redirect query keys")
        _text(values[key][0], "OFAC redirect parameter", limit=maximum)
    flattened = {key: value[0] for key, value in values.items()}
    expiry = flattened["X-Amz-Expires"]
    date = flattened["X-Amz-Date"]
    if (
        flattened["X-Amz-Algorithm"] != "AWS4-HMAC-SHA256"
        or flattened["X-Amz-SignedHeaders"] != "host"
        or not expiry.isascii()
        or not expiry.isdecimal()
        or not 1 <= int(expiry) <= 3600
        or not re.fullmatch(r"[0-9a-f]{64}", flattened["X-Amz-Signature"])
        or not re.fullmatch(r"\d{8}T\d{6}Z", date)
        or not re.fullmatch(
            r"[A-Z0-9]{16,128}/" + date[:8] + r"/us-gov-west-1/s3/aws4_request",
            flattened["X-Amz-Credential"],
        )
    ):
        raise SourceValidationError("invalid OFAC public-download signature shape")
    try:
        datetime.strptime(date, "%Y%m%dT%H%M%SZ")
    except ValueError as exc:
        raise SourceValidationError("invalid OFAC redirect signature date") from exc


class SourceValidationError(ValueError):
    """A configuration, source payload or boundary value is unacceptable."""


def _text(
    value: object,
    label: str,
    *,
    limit: int = 4096,
    allow_name_whitespace: bool = False,
    allow_empty: bool = False,
) -> str:
    if (
        not isinstance(value, str)
        or (not allow_empty and not value.strip())
        or len(value) > limit
    ):
        raise SourceValidationError(f"invalid {label}")
    if any(
        (ord(char) < 32 and not (allow_name_whitespace and char in "\t\n\r"))
        or 0xD800 <= ord(char) <= 0xDFFF
        for char in value
    ):
        raise SourceValidationError(f"invalid control character in {label}")
    return value


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SourceValidationError(f"{label} must be an integer in the approved range")
    return value


@dataclass(frozen=True, slots=True)
class AliasEvidence:
    """One original name and the provider field that supports it."""

    value: str
    field: str
    language: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.value, "name", limit=1024, allow_name_whitespace=True)
        _text(self.field, "source name field", limit=1024)
        if self.language is not None:
            _text(self.language, "name language", limit=128)
        if not isinstance(self.attributes, tuple) or len(self.attributes) > 32:
            raise SourceValidationError("invalid alias attributes")
        for pair in self.attributes:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise SourceValidationError("invalid alias attribute pair")
            _text(pair[0], "alias attribute key", limit=128)
            # XML boolean whitespace is retained in this exact EU evidence field.
            _text(
                pair[1],
                "alias attribute value",
                limit=1024,
                allow_empty=True,
                allow_name_whitespace=pair[0] == "strong"
                and self.field
                in {
                    "sanctionEntity.nameAlias@wholeName",
                    "sanctionEntity.nameAlias@firstName",
                    "sanctionEntity.nameAlias@middleName",
                    "sanctionEntity.nameAlias@lastName",
                },
            )


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """A provider-ID group; identical names never establish shared identity."""

    source_id: str
    provider_id: str
    entity_type: Literal["organization", "vessel"]
    primary_name: str
    aliases: tuple[AliasEvidence, ...]
    provider_schema: str
    referents: tuple[str, ...] = ()
    provider_datasets: tuple[str, ...] = ()
    provider_topics: tuple[str, ...] = ()
    classification_basis: str | None = None

    def __post_init__(self) -> None:
        if self.source_id not in SOURCE_IDS:
            raise SourceValidationError("unknown record source")
        _text(self.provider_id, "provider ID", limit=1024)
        if self.entity_type not in ("organization", "vessel"):
            raise SourceValidationError("record is not an approved non-person type")
        _text(self.primary_name, "primary name", limit=1024, allow_name_whitespace=True)
        _text(self.provider_schema, "provider schema", limit=1024)
        if not isinstance(self.aliases, tuple) or not 1 <= len(self.aliases) <= 128:
            raise SourceValidationError("record alias evidence exceeds approved bounds")
        if any(not isinstance(item, AliasEvidence) for item in self.aliases):
            raise SourceValidationError("invalid record alias evidence")
        if not any(item.value == self.primary_name for item in self.aliases):
            raise SourceValidationError("primary name lacks source evidence")
        if not isinstance(self.referents, tuple) or len(self.referents) > 1024:
            raise SourceValidationError("invalid provider referents")
        for referent in self.referents:
            _text(referent, "provider referent", limit=1024)
        for values in (self.provider_datasets, self.provider_topics):
            if not isinstance(values, tuple) or len(values) > 128:
                raise SourceValidationError("invalid provider classification evidence")
            for value in values:
                _text(value, "provider classification value", limit=1024)
        if self.classification_basis is not None:
            _text(self.classification_basis, "classification basis", limit=256)

    @property
    def qualified_id(self) -> str:
        """Keep provider IDs in separate source namespaces without merging."""
        return f"{self.source_id}:{self.provider_id}"


@dataclass(frozen=True, slots=True)
class ParseContext:
    """Hard parser bounds, reducible for deterministic small fixtures."""

    source_id: str
    max_groups: int = MAX_GROUPS
    max_aliases: int = 128
    max_name_chars: int = 1024
    max_input_bytes: int = MAX_SOURCE_BYTES

    def __post_init__(self) -> None:
        if self.source_id not in SOURCE_IDS:
            raise SourceValidationError("unknown parser source")
        for name, ceiling in (
            ("max_groups", MAX_GROUPS),
            ("max_aliases", 128),
            ("max_name_chars", 1024),
            (
                "max_input_bytes",
                MAX_EU_SOURCE_BYTES
                if self.source_id == "eu_consolidated"
                else MAX_SOURCE_BYTES,
            ),
        ):
            _integer(getattr(self, name), name, minimum=1, maximum=ceiling)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """A bounded selection and aggregate counters, without excluded identities."""

    records: tuple[SourceRecord, ...]
    input_records: int
    excluded_person_records: int
    excluded_other_records: int
    excluded_by_limit: int
    parser_version: str
    input_sha256: str
    source_version: str | None = None
    source_version_field: str | None = None
    container_format: str | None = None
    container_member: str | None = None
    decoded_bytes: int | None = None
    decoded_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or len(self.records) > MAX_GROUPS:
            raise SourceValidationError("invalid parser record selection")
        if any(not isinstance(item, SourceRecord) for item in self.records):
            raise SourceValidationError("invalid parsed record")
        for name in (
            "input_records",
            "excluded_person_records",
            "excluded_other_records",
            "excluded_by_limit",
        ):
            _integer(getattr(self, name), name, minimum=0, maximum=10_000_000)
        _text(self.parser_version, "parser version", limit=128)
        if not re.fullmatch(r"[0-9a-f]{64}", self.input_sha256):
            raise SourceValidationError("invalid input SHA-256")
        if (self.source_version is None) != (self.source_version_field is None):
            raise SourceValidationError(
                "source version must identify its evidence field"
            )
        if self.source_version is not None:
            _text(self.source_version, "source version", limit=1024)
            _text(self.source_version_field, "source version field", limit=1024)
        container = (
            self.container_format,
            self.container_member,
            self.decoded_bytes,
            self.decoded_sha256,
        )
        if any(value is not None for value in container):
            if (
                any(value is None for value in container)
                or self.container_format != "zip"
            ):
                raise SourceValidationError(
                    "container evidence must be complete and identify ZIP"
                )
            _text(self.container_member, "container member", limit=128)
            if (
                "/" in self.container_member
                or "\\" in self.container_member
                or self.container_member in (".", "..")
            ):
                raise SourceValidationError(
                    "container member must be one plain filename"
                )
            _integer(self.decoded_bytes, "decoded bytes", minimum=1, maximum=32_000_000)
            if not re.fullmatch(r"[0-9a-f]{64}", self.decoded_sha256):
                raise SourceValidationError("invalid decoded SHA-256")


@dataclass(frozen=True, slots=True)
class AcquisitionLimits:
    max_source_bytes: int = MAX_SOURCE_BYTES
    max_eu_source_bytes: int = MAX_SOURCE_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_groups: int = MAX_GROUPS
    request_timeout_seconds: int = 30
    source_deadline_seconds: int = 120
    max_attempts: int = 2
    max_redirects: int = 3
    eu_request_timeout_seconds: int = 30
    eu_source_deadline_seconds: int = 120
    wikidata_request_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        bounds = {
            "max_source_bytes": (1, MAX_SOURCE_BYTES),
            "max_eu_source_bytes": (1, MAX_EU_SOURCE_BYTES),
            "max_total_bytes": (1, MAX_TOTAL_BYTES),
            "max_groups": (1, MAX_GROUPS),
            "request_timeout_seconds": (1, 30),
            "source_deadline_seconds": (1, 120),
            "eu_request_timeout_seconds": (1, 180),
            "eu_source_deadline_seconds": (1, 240),
            "wikidata_request_timeout_seconds": (1, 90),
            "max_attempts": (1, 2),
            "max_redirects": (0, 3),
        }
        for name, (minimum, maximum) in bounds.items():
            _integer(getattr(self, name), name, minimum=minimum, maximum=maximum)

    def source_byte_limit(self, source_id: str) -> int:
        """Apply the user's narrow EU amendment; other source ceilings stay fixed."""
        if source_id not in SOURCE_IDS:
            raise SourceValidationError("unknown source byte limit")
        return (
            self.max_eu_source_bytes
            if source_id == "eu_consolidated"
            else self.max_source_bytes
        )

    def request_timeout_for(self, source_id: str) -> int:
        """Return the absolute request duration in seconds for this source."""
        if source_id not in SOURCE_IDS:
            raise SourceValidationError("unknown source request timeout")
        if source_id == "eu_consolidated":
            return self.eu_request_timeout_seconds
        if source_id == "wikidata_orgs":
            return self.wikidata_request_timeout_seconds
        return self.request_timeout_seconds

    def source_deadline_for(self, source_id: str) -> int:
        """Return the total source duration in seconds, including all attempts."""
        if source_id not in SOURCE_IDS:
            raise SourceValidationError("unknown source deadline")
        return (
            self.eu_source_deadline_seconds
            if source_id == "eu_consolidated"
            else self.source_deadline_seconds
        )


@dataclass(frozen=True, slots=True)
class SourcePermission:
    status: Literal["approved", "blocked", "pending"]
    reviewed_at: str
    license: str
    terms_urls: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    label: str
    role: Literal["sanctions_reference", "supplemental_unlabelled"]
    url: str
    allowed_redirects: tuple[str, ...]
    parser: str
    permission: SourcePermission


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    schema_version: int
    profile: str
    limits: AcquisitionLimits
    sources: tuple[SourceSpec, ...]
    policy_sha256: str
    project_root: Path


def validate_source_url(source_id: str, url: str) -> None:
    """Reject credentials and destinations outside each source's narrow route.

    Redirects additionally need an exact entry in the source's reviewed list.
    This validation runs before calling even an injected transport.
    """
    _text(url, "source URL", limit=16000)
    try:
        parts = urlsplit(url)
        invalid = (
            parts.scheme != "https"
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
            or parts.fragment
            or "\\" in url
            or " " in url
        )
    except ValueError as exc:
        raise SourceValidationError("invalid source URL") from exc
    if invalid:
        raise SourceValidationError("source URL requires uncredentialed HTTPS")
    allowed = False
    if source_id == "opensanctions_un":
        allowed = (
            parts.hostname == "data.opensanctions.org"
            and not parts.query
            and bool(
                re.fullmatch(
                    r"/artifacts/un_sc_sanctions/[0-9]{14}-[a-z0-9]+/entities\.ftm\.json",
                    parts.path,
                )
            )
        )
    elif source_id == "un_consolidated":
        allowed = (
            parts.hostname == "scsanctions.un.org"
            and parts.path == "/resources/xml/en/consolidated.xml"
            and not parts.query
        )
    elif source_id == "ofac_sdn":
        allowed = (
            parts.hostname == "sanctionslistservice.ofac.treas.gov"
            and parts.path == "/api/PublicationPreview/exports/SDN_XML.ZIP"
            and not parts.query
        )
        if parts.hostname == OFAC_OBJECT_HOST and OFAC_OBJECT_PATH.fullmatch(
            parts.path
        ):
            if parts.query:
                _validate_ofac_signed_query(parts.query)
            allowed = True
    elif source_id == "eu_consolidated":
        allowed = (
            parts.hostname == "webgate.ec.europa.eu"
            and parts.path == "/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
            and parts.query in ("", "token=dG9rZW4tMjAxNw")
        )
    elif source_id == "wikidata_orgs":
        try:
            query = parse_qs(parts.query, strict_parsing=True) if parts.query else {}
        except ValueError as exc:
            raise SourceValidationError("invalid source URL query") from exc
        allowed = (
            parts.hostname == "query.wikidata.org"
            and parts.path == "/sparql"
            and (
                set(query) == {"query", "format"}
                and query["format"] == ["json"]
                and query["query"] == [WIKIDATA_QUERY]
            )
        )
    if not allowed:
        raise SourceValidationError("URL is outside the reviewed source route")


def _mapping(value: object, keys: set[str], label: str) -> Mapping:
    if not isinstance(value, dict) or set(value) != keys:
        raise SourceValidationError(f"invalid {label} fields")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 20:
        raise SourceValidationError(f"invalid {label}")
    result = tuple(_text(item, label, limit=16000) for item in value)
    if len(set(result)) != len(result):
        raise SourceValidationError(f"duplicate {label}")
    return result


def registry_from_dict(
    data: object, *, project_root: Path = PROJECT_ROOT
) -> SourceRegistry:
    """Validate the reviewed policy; unknown keys and higher limits fail closed."""
    data = _mapping(
        data, {"schema_version", "profile", "limits", "sources"}, "registry"
    )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SourceValidationError("unsupported registry schema version")
    if data["profile"] != "feasibility":
        raise SourceValidationError("unsupported acquisition profile")
    limit_names = set(AcquisitionLimits.__dataclass_fields__)
    if (
        isinstance(data["limits"], dict)
        and "wikidata_request_timeout_seconds" not in data["limits"]
    ):
        limit_names.remove("wikidata_request_timeout_seconds")
    limits = AcquisitionLimits(**_mapping(data["limits"], limit_names, "limits"))
    if not isinstance(data["sources"], list) or len(data["sources"]) != 5:
        raise SourceValidationError(
            "registry must contain exactly the five reviewed sources"
        )
    sources = []
    for item in data["sources"]:
        item = _mapping(
            item,
            {
                "source_id",
                "label",
                "role",
                "url",
                "allowed_redirects",
                "parser",
                "permission",
            },
            "source",
        )
        source_id = item["source_id"]
        if source_id not in SOURCE_IDS or item["parser"] != PARSER_IDS[source_id]:
            raise SourceValidationError("unknown source or parser")
        expected_role = (
            "supplemental_unlabelled"
            if source_id == "wikidata_orgs"
            else "sanctions_reference"
        )
        if item["role"] != expected_role:
            raise SourceValidationError("source role does not match reviewed policy")
        validate_source_url(source_id, item["url"])
        if source_id == "ofac_sdn" and urlsplit(item["url"]).query:
            raise SourceValidationError(
                "OFAC policy cannot retain ephemeral signing parameters"
            )
        redirects = _strings(item["allowed_redirects"], "redirect URLs")
        for url in redirects:
            validate_source_url(source_id, url)
            if source_id == "ofac_sdn" and urlsplit(url).query:
                raise SourceValidationError(
                    "reviewed OFAC redirect policy must not retain signing parameters"
                )
        permission = _mapping(
            item["permission"],
            {
                "status",
                "reviewed_at",
                "license",
                "terms_urls",
                "evidence_paths",
                "rationale",
            },
            "permission",
        )
        if permission["status"] not in ("approved", "blocked", "pending"):
            raise SourceValidationError("invalid permission status")
        reviewed_at = _text(
            permission["reviewed_at"], "permission review date", limit=32
        )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_at):
            raise SourceValidationError("invalid permission review date")
        terms = _strings(permission["terms_urls"], "terms URLs")
        for url in terms:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise SourceValidationError("invalid terms URL")
        evidence = _strings(permission["evidence_paths"], "permission evidence paths")
        for path in evidence:
            parts = Path(path)
            if parts.is_absolute() or ".." in parts.parts:
                raise SourceValidationError(
                    "permission evidence must be a local project path"
                )
        if permission["status"] == "approved" and (not terms or not evidence):
            raise SourceValidationError(
                "approved sources require saved permission evidence"
            )
        sources.append(
            SourceSpec(
                source_id=source_id,
                label=_text(item["label"], "source label", limit=256),
                role=item["role"],
                url=item["url"],
                allowed_redirects=redirects,
                parser=item["parser"],
                permission=SourcePermission(
                    status=permission["status"],
                    reviewed_at=reviewed_at,
                    license=_text(permission["license"], "license", limit=256),
                    terms_urls=terms,
                    evidence_paths=evidence,
                    rationale=_text(permission["rationale"], "permission rationale"),
                ),
            )
        )
    if {item.source_id for item in sources} != set(SOURCE_IDS):
        raise SourceValidationError("registry source IDs must be unique and complete")
    canonical = json.dumps(
        {**data, "limits": asdict(limits)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return SourceRegistry(
        schema_version=1,
        profile="feasibility",
        limits=limits,
        sources=tuple(sources),
        policy_sha256=hashlib.sha256(canonical).hexdigest(),
        project_root=Path(project_root),
    )


def strict_json_loads(payload: bytes | str) -> object:
    """Decode bounded policy/evidence JSON without duplicate or nonfinite values."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise SourceValidationError("duplicate registry JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SourceValidationError("nonfinite registry JSON value")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise SourceValidationError("nonfinite JSON value")
        return number

    try:
        decoded = json.loads(
            payload,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
        stack = [(decoded, 0)]
        visited = 0
        while stack:
            value, depth = stack.pop()
            visited += 1
            if depth > 32 or visited > 100_000:
                raise SourceValidationError(
                    "JSON policy/evidence exceeds structural bounds"
                )
            children = (
                value.values()
                if isinstance(value, dict)
                else value
                if isinstance(value, list)
                else ()
            )
            if visited + len(stack) + len(children) > 100_000:
                raise SourceValidationError(
                    "JSON policy/evidence exceeds structural bounds"
                )
            stack.extend((child, depth + 1) for child in children)
        return decoded
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SourceValidationError(
            "invalid or ambiguous JSON policy/evidence"
        ) from exc


def load_registry(
    path: Path | str = DEFAULT_REGISTRY, *, project_root: Path = PROJECT_ROOT
) -> SourceRegistry:
    """Load a small local policy without contacting any publisher."""

    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(100_001)
        if len(raw) > 100_000:
            raise SourceValidationError("registry exceeds local policy size limit")
        data = strict_json_loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceValidationError("cannot read a valid source registry") from exc
    return registry_from_dict(data, project_root=project_root)
