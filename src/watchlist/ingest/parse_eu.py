"""Parse the EU financial-sanctions XML 1.1 name profile offline."""

from __future__ import annotations

import json
import re
from xml.etree import ElementTree

from watchlist.ingest._parse_common import (
    alias_evidence,
    check_schema_version,
    children,
    expanded_tag,
    finish,
    identifier,
    one,
    prepare_payload,
    require_text,
    source_record,
    unique_identifier,
    xml_root,
)
from watchlist.ingest.source_registry import (
    ParseContext,
    ParseResult,
    SourceValidationError,
)


PARSER_VERSION = "eu-fsd-1.1-non-person-v1"
NAMESPACE = "http://eu.europa.ec/fpi/fsd/export"
NAME_ATTRIBUTES = (
    "logicalId",
    "strong",
    "nameLanguage",
    "regulationLanguage",
    "firstName",
    "middleName",
    "lastName",
)


def _subject_type(entity: ElementTree.Element) -> tuple[str, str]:
    subject = one(entity, "subjectType")
    if len(subject) or (subject.text and subject.text.strip()):
        raise SourceValidationError("EU subjectType must use its source attributes.")
    code = require_text(subject.get("code"), "EU subjectType code", maximum=32)
    classification = require_text(
        subject.get("classificationCode"), "EU subject classification", maximum=1
    )
    if classification not in {"P", "E"}:
        raise SourceValidationError("Unsupported EU subject classification code.")
    expected = {"person": "P", "enterprise": "E"}.get(code)
    if expected is not None and classification != expected:
        raise SourceValidationError("EU subject type attributes conflict.")
    return code, classification


def _name_language(alias: ElementTree.Element) -> str | None:
    """Keep unrecognized source codes as metadata without inventing a language.

    The XSD permits a free string of at most six characters, not necessarily a
    language tag. Its original value is separately preserved in attributes.
    """
    value = alias.get("nameLanguage")
    if value is None or value == "":
        return None
    if len(value) > 6:
        raise SourceValidationError("EU name language exceeds its schema limit.")
    return (
        value if re.fullmatch(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*", value) else None
    )


def _is_main_name(value: str | None) -> bool:
    """Interpret an XSD Boolean token without changing its source evidence."""
    if value is None:
        return False
    token = value.strip(" \t\n\r")
    if token not in {"true", "false", "1", "0"}:
        raise SourceValidationError("EU alias strong must use an XML boolean value.")
    return token in {"true", "1"}


def parse_eu(payload: bytes, *, context: ParseContext) -> ParseResult:
    """Select explicit enterprise classifications and preserve original names.

    The source's ``strong`` main-name flag, name language and alias identifier
    stay attached to each name. A missing wholeName uses supplied name parts as
    separately identified evidence, never a synthesized concatenation. A
    regulation's language is never substituted for the name's language.
    """
    text = prepare_payload(payload, context, "eu_consolidated")
    root = xml_root(text, root_name="export", namespaces=frozenset({NAMESPACE}))
    check_schema_version(root)
    generation_date = require_text(
        root.get("generationDate"), "EU generation date", maximum=128
    )
    global_file_id = identifier(root.get("globalFileId"))
    if any(expanded_tag(child.tag)[1] != "sanctionEntity" for child in root):
        raise SourceValidationError("Unsupported EU top-level XML structure.")
    entries = children(root, "sanctionEntity")
    seen: set[str] = set()
    records = []
    excluded_people = excluded_other = 0
    for entity in entries:
        provider_id = unique_identifier(entity.get("logicalId"), seen)
        subject_type, classification = _subject_type(entity)
        if classification == "P":
            excluded_people += 1
            continue
        evidence = []
        for alias in children(entity, "nameAlias"):
            identifier(alias.get("logicalId"))
            regulation_language = alias.get("regulationLanguage")
            if regulation_language is None or len(regulation_language) > 6:
                raise SourceValidationError(
                    "Missing or oversized EU regulation language."
                )
            one(alias, "regulationSummary")
            _is_main_name(alias.get("strong"))
            language = _name_language(alias)
            name_fields = (
                ("wholeName",)
                if (alias.get("wholeName") or "").strip()
                else ("firstName", "middleName", "lastName")
            )
            for field in name_fields:
                value = alias.get(field)
                if value is None or not value.strip():
                    continue
                evidence.append(
                    alias_evidence(
                        value,
                        f"sanctionEntity.nameAlias@{field}",
                        context,
                        language=language,
                        attributes=tuple(
                            (key, alias.attrib[key])
                            for key in NAME_ATTRIBUTES
                            if key in alias.attrib
                        ),
                    )
                )
        if not evidence:
            raise SourceValidationError(
                "EU enterprise requires original name evidence."
            )
        primary_names = [
            name.value
            for name in evidence
            if _is_main_name(dict(name.attributes).get("strong"))
        ]
        records.append(
            source_record(
                context,
                provider_id=provider_id,
                entity_type="organization",
                primary_name=min(primary_names or [name.value for name in evidence]),
                aliases=evidence,
                provider_schema=f"export.sanctionEntity:code={subject_type};classificationCode=E",
                classification_basis="eu-subjectType-classificationCode-E",
            )
        )
    version = json.dumps(
        {"generationDate": generation_date, "globalFileId": global_file_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return finish(
        payload,
        context,
        records,
        input_records=len(entries),
        excluded_person_records=excluded_people,
        excluded_other_records=excluded_other,
        parser_version=PARSER_VERSION,
        source_version=version,
        source_version_field="export@generationDate,export@globalFileId",
    )
