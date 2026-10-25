"""Shared strict decoding and evidence preservation for the bounded adapters.

These helpers never fetch data, normalize a name, or establish record identity.
They keep source evidence intact and apply selection limits only after validation.
"""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
import math
import re
from xml.etree import ElementTree

from watchlist.ingest.source_registry import (
    AliasEvidence,
    MAX_EU_SOURCE_BYTES,
    MAX_SOURCE_BYTES,
    ParseContext,
    ParseResult,
    SourceRecord,
    SourceValidationError,
)


MAX_NODES = 200_000
MAX_XML_NODES = 1_000_000
MAX_DEPTH = 64
XML_LANGUAGE = "{http://www.w3.org/XML/1998/namespace}lang"


def validate_payload(payload: bytes, context: ParseContext, source_id: str) -> None:
    """Validate the source and finite limits before interpreting input bytes."""
    if not isinstance(context, ParseContext) or context.source_id != source_id:
        raise SourceValidationError("Parser context does not match the source adapter.")
    for name, ceiling in (
        ("max_groups", 200),
        ("max_aliases", 128),
        ("max_name_chars", 1024),
        (
            "max_input_bytes",
            MAX_EU_SOURCE_BYTES if source_id == "eu_consolidated" else MAX_SOURCE_BYTES,
        ),
    ):
        value = getattr(context, name)
        if type(value) is not int or not 1 <= value <= ceiling:
            raise SourceValidationError(f"Invalid finite parser limit: {name}.")
    if not isinstance(payload, bytes):
        raise SourceValidationError("Parser input must be bytes.")
    if not payload or len(payload) > context.max_input_bytes:
        raise SourceValidationError("Parser input is empty or exceeds its byte limit.")


def utf8_text(payload: bytes) -> str:
    """Decode already-bounded bytes, without changing meaningful source text."""
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceValidationError("Parser input must use valid UTF-8.") from exc
    if not text.strip() or "\x00" in text:
        raise SourceValidationError(
            "Parser input is empty or contains a NUL character."
        )
    return text


def prepare_payload(payload: bytes, context: ParseContext, source_id: str) -> str:
    """Validate an uncompressed source payload before UTF-8 decoding."""
    validate_payload(payload, context, source_id)
    return utf8_text(payload)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SourceValidationError("JSON contains a duplicate object key.")
        result[key] = value
    return result


def _nonfinite_constant(value: str) -> None:
    raise SourceValidationError("JSON must not contain nonfinite numbers.")


def strict_json(text: str) -> object:
    """Reject ambiguous keys, nonfinite numbers and excessive JSON structure."""
    try:
        value = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_nonfinite_constant
        )
    except SourceValidationError:
        raise
    except (ValueError, RecursionError, OverflowError) as exc:
        raise SourceValidationError("Malformed or excessively nested JSON.") from exc
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if visited > MAX_NODES or depth > MAX_DEPTH:
            raise SourceValidationError("JSON exceeds its structural limit.")
        if isinstance(item, float) and not math.isfinite(item):
            raise SourceValidationError("JSON must not contain nonfinite numbers.")
        if isinstance(item, str) and any(
            0xD800 <= ord(character) <= 0xDFFF for character in item
        ):
            raise SourceValidationError(
                "JSON must not contain lone Unicode surrogates."
            )
        if isinstance(item, dict):
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def require_text(value: object, field: str, *, maximum: int = 1024) -> str:
    """Preserve meaningful whitespace; reject blank, invalid or oversized text."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(
            0xD800 <= ord(character) <= 0xDFFF
            or (ord(character) < 32 and character not in "\t\n\r")
            for character in value
        )
    ):
        raise SourceValidationError(f"Invalid text in {field}.")
    return value


def identifier(value: object) -> str:
    result = require_text(value, "provider identifier", maximum=256)
    if any(character.isspace() for character in result):
        raise SourceValidationError("Provider identifiers must not contain whitespace.")
    return result


def unique_identifier(value: object, seen: set[str]) -> str:
    result = identifier(value)
    if result in seen:
        raise SourceValidationError("Duplicate provider identifier in source payload.")
    seen.add(result)
    return result


def alias_evidence(
    value: object,
    field: str,
    context: ParseContext,
    *,
    language: object = None,
    attributes: Iterable[tuple[str, str]] = (),
) -> AliasEvidence:
    """Keep original names, explicit languages and source alias qualifiers."""
    name = require_text(value, "name or alias", maximum=context.max_name_chars)
    if language is not None:
        language = require_text(language, "alias language", maximum=64)
        if not re.fullmatch(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*", language):
            raise SourceValidationError(
                "Alias language is not a supported language tag."
            )
    pairs = tuple(sorted(attributes))
    if len(pairs) != len({key for key, _ in pairs}):
        raise SourceValidationError("Duplicate alias attribute key.")
    for key, attribute in pairs:
        require_text(key, "alias attribute key", maximum=128)
        # XSD Boolean whitespace stays in the original EU main-name evidence.
        allow_xml_boolean_whitespace = (
            context.source_id == "eu_consolidated"
            and field
            in {
                "sanctionEntity.nameAlias@wholeName",
                "sanctionEntity.nameAlias@firstName",
                "sanctionEntity.nameAlias@middleName",
                "sanctionEntity.nameAlias@lastName",
            }
            and key == "strong"
        )
        if (
            not isinstance(attribute, str)
            or len(attribute) > 1024
            or any(
                0xD800 <= ord(character) <= 0xDFFF
                or (
                    ord(character) < 32
                    and not (allow_xml_boolean_whitespace and character in "\t\n\r")
                )
                for character in attribute
            )
        ):
            raise SourceValidationError("Invalid alias attribute value.")
    return AliasEvidence(value=name, field=field, language=language, attributes=pairs)


def source_record(
    context: ParseContext,
    *,
    provider_id: str,
    entity_type: str,
    primary_name: object,
    aliases: Iterable[AliasEvidence],
    provider_schema: str,
    referents: Iterable[str] = (),
    provider_datasets: Iterable[str] = (),
    provider_topics: Iterable[str] = (),
    classification_basis: str | None = None,
) -> SourceRecord:
    """Deduplicate exact evidence only; different fields/languages remain distinct."""
    primary = require_text(primary_name, "primary name", maximum=context.max_name_chars)
    unique = tuple(
        sorted(
            set(aliases),
            key=lambda item: (
                item.value,
                item.field,
                item.language or "",
                item.attributes,
            ),
        )
    )
    if not unique or len(unique) > context.max_aliases:
        raise SourceValidationError(
            "Record has no name evidence or exceeds its alias limit."
        )
    if not any(item.value == primary for item in unique):
        raise SourceValidationError("Primary name must occur in source alias evidence.")
    if entity_type not in {"organization", "vessel"}:
        raise SourceValidationError(
            "Only explicitly identified non-person types are eligible."
        )
    return SourceRecord(
        source_id=context.source_id,
        provider_id=identifier(provider_id),
        entity_type=entity_type,
        primary_name=primary,
        aliases=unique,
        provider_schema=provider_schema,
        referents=tuple(sorted({identifier(item) for item in referents})),
        provider_datasets=tuple(sorted(set(provider_datasets))),
        provider_topics=tuple(sorted(set(provider_topics))),
        classification_basis=classification_basis,
    )


def finish(
    payload: bytes,
    context: ParseContext,
    records: Iterable[SourceRecord],
    *,
    input_records: int,
    excluded_person_records: int,
    excluded_other_records: int,
    parser_version: str,
    source_version: str | None = None,
    source_version_field: str | None = None,
    container_format: str | None = None,
    container_member: str | None = None,
    decoded_bytes: int | None = None,
    decoded_sha256: str | None = None,
) -> ParseResult:
    """Account for every logical record before applying deterministic selection."""
    ordered = tuple(sorted(records, key=lambda item: item.qualified_id))
    if len({item.qualified_id for item in ordered}) != len(ordered):
        raise SourceValidationError("Duplicate provider identifier after parsing.")
    if input_records != len(ordered) + excluded_person_records + excluded_other_records:
        raise SourceValidationError("Parser record accounting is inconsistent.")
    if (source_version is None) != (source_version_field is None):
        raise SourceValidationError(
            "Source version requires its explicit field provenance."
        )
    if source_version is not None:
        require_text(source_version, "source version", maximum=2048)
        require_text(source_version_field, "source version field", maximum=256)
    return ParseResult(
        records=ordered[: context.max_groups],
        input_records=input_records,
        excluded_person_records=excluded_person_records,
        excluded_other_records=excluded_other_records,
        excluded_by_limit=max(0, len(ordered) - context.max_groups),
        parser_version=parser_version,
        input_sha256=hashlib.sha256(payload).hexdigest(),
        source_version=source_version,
        source_version_field=source_version_field,
        container_format=container_format,
        container_member=container_member,
        decoded_bytes=decoded_bytes,
        decoded_sha256=decoded_sha256,
    )


def expanded_tag(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        namespace, local = tag[1:].split("}", 1)
        return namespace, local
    return "", tag


def xml_root(
    text: str, *, root_name: str, namespaces: frozenset[str]
) -> ElementTree.Element:
    """Reject DTD/entity declarations before parsing a bounded XML tree.

    Parsing a decoded UTF-8 string prevents alternate encodings from hiding
    forbidden declarations. Namespace prefixes may vary; namespace URIs may not.
    """
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        raise SourceValidationError("XML DTD and entity declarations are forbidden.")
    declaration = re.match(r"\s*<\?xml\s+([^?]+)\?>", text)
    if declaration:
        attributes = dict(
            re.findall(r"([A-Za-z]+)\s*=\s*['\"]([^'\"]+)['\"]", declaration.group(1))
        )
        if attributes.get("version") != "1.0" or attributes.get(
            "encoding", "utf-8"
        ).lower() not in {"utf-8", "utf8"}:
            raise SourceValidationError("Only XML 1.0 encoded as UTF-8 is supported.")
    try:
        root = ElementTree.fromstring(text)
    except (ElementTree.ParseError, RecursionError) as exc:
        raise SourceValidationError("Malformed XML source payload.") from exc
    namespace, local = expanded_tag(root.tag)
    if local != root_name or namespace not in namespaces:
        raise SourceValidationError("Unsupported XML root or namespace.")
    pending = [(root, 0)]
    visited = 0
    while pending:
        node, depth = pending.pop()
        visited += 1
        if visited > MAX_XML_NODES or depth > MAX_DEPTH:
            raise SourceValidationError("XML exceeds its structural limit.")
        if expanded_tag(node.tag)[0] != namespace:
            raise SourceValidationError("Unexpected mixed XML namespaces.")
        pending.extend((child, depth + 1) for child in node)
    return root


def children(node: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in node if expanded_tag(child.tag)[1] == name]


def one(
    node: ElementTree.Element, name: str, *, required: bool = True
) -> ElementTree.Element | None:
    matches = children(node, name)
    if len(matches) > 1 or (required and not matches):
        raise SourceValidationError(f"Missing or duplicate XML field: {name}.")
    return matches[0] if matches else None


def node_text(
    node: ElementTree.Element | None, field: str, *, required: bool = True
) -> str | None:
    if node is None:
        if required:
            raise SourceValidationError(f"Missing XML text field: {field}.")
        return None
    if len(node):
        raise SourceValidationError(
            f"Nested content is unsupported in XML text field: {field}."
        )
    value = node.text or ""
    if not value.strip() and not required:
        return None
    return require_text(value, field, maximum=4096)


def field_text(
    node: ElementTree.Element, name: str, *, required: bool = True
) -> str | None:
    return node_text(one(node, name, required=required), name, required=required)


def xml_language(*nodes: ElementTree.Element) -> str | None:
    """Read explicit XML language inheritance from nearest node to its ancestors.

    An empty xml:lang resets an inherited language to unknown, as XML specifies.
    Callers supply the known ancestor path; no language is inferred from text.
    """
    for node in nodes:
        if XML_LANGUAGE in node.attrib:
            return node.attrib[XML_LANGUAGE] or None
    return None


def check_schema_version(root: ElementTree.Element) -> None:
    """An unreviewed explicit schema version must not be silently ignored."""
    if any(
        expanded_tag(key)[1].lower() in {"version", "schemaversion", "schema-version"}
        for key in root.attrib
    ):
        raise SourceValidationError(
            "An explicit XML schema version requires a reviewed adapter."
        )
