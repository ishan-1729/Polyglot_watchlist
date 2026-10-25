"""Parse the reviewed, no-namespace UN consolidated XML profile offline."""

from __future__ import annotations

import re
from xml.etree import ElementTree

from watchlist.ingest._parse_common import (
    alias_evidence,
    check_schema_version,
    children,
    expanded_tag,
    field_text,
    finish,
    node_text,
    one,
    prepare_payload,
    source_record,
    unique_identifier,
    xml_language,
    xml_root,
)
from watchlist.ingest.source_registry import (
    ParseContext,
    ParseResult,
    SourceValidationError,
)


PARSER_VERSION = "un-consolidated-non-person-v1"


def _provider_id(node: ElementTree.Element, seen: set[str]) -> str:
    provider_id = unique_identifier(field_text(node, "DATAID"), seen)
    if not re.fullmatch(r"[0-9]+", provider_id):
        raise SourceValidationError("UN DATAID must contain ASCII digits only.")
    return provider_id


def parse_un(payload: bytes, *, context: ParseContext) -> ParseResult:
    """Keep entity-name evidence and exclude the explicit INDIVIDUALS section.

    ENTITY is the source's non-person grouping. It does not distinguish vessels
    reliably, so this profile preserves its organization classification without
    guessing a more specific type from a name. FIRST_NAME is the original primary
    text; any later name parts remain metadata rather than invented aliases.
    This parser grants no permission to download or redistribute UN data.
    """
    text = prepare_payload(payload, context, "un_consolidated")
    root = xml_root(text, root_name="CONSOLIDATED_LIST", namespaces=frozenset({""}))
    check_schema_version(root)
    if any(
        expanded_tag(child.tag)[1] not in {"INDIVIDUALS", "ENTITIES"} for child in root
    ):
        raise SourceValidationError("Unsupported UN top-level XML structure.")
    people = one(root, "INDIVIDUALS")
    entities = one(root, "ENTITIES")
    if any(expanded_tag(child.tag)[1] != "INDIVIDUAL" for child in people):
        raise SourceValidationError("Unsupported record in UN INDIVIDUALS.")
    if any(expanded_tag(child.tag)[1] != "ENTITY" for child in entities):
        raise SourceValidationError("Unsupported record in UN ENTITIES.")
    seen: set[str] = set()
    for person in people:
        _provider_id(person, seen)
    records = []
    for entity in entities:
        provider_id = _provider_id(entity, seen)
        primary_node = one(entity, "FIRST_NAME")
        primary = node_text(primary_node, "FIRST_NAME")
        name_parts = []
        for field in ("SECOND_NAME", "THIRD_NAME", "FOURTH_NAME"):
            part = one(entity, field, required=False)
            if part is not None:
                name_parts.append((field, node_text(part, field, required=False) or ""))
        evidence = [
            alias_evidence(
                primary,
                "ENTITY.FIRST_NAME",
                context,
                language=xml_language(primary_node, entity, entities, root),
                attributes=name_parts,
            )
        ]
        original = one(entity, "NAME_ORIGINAL_SCRIPT", required=False)
        original_text = node_text(original, "NAME_ORIGINAL_SCRIPT", required=False)
        if original_text is not None:
            evidence.append(
                alias_evidence(
                    original_text,
                    "ENTITY.NAME_ORIGINAL_SCRIPT",
                    context,
                    language=xml_language(original, entity, entities, root),
                )
            )
        for alias in children(entity, "ENTITY_ALIAS"):
            name_node = one(alias, "ALIAS_NAME")
            name = node_text(name_node, "ALIAS_NAME", required=False)
            quality_node = one(alias, "QUALITY", required=False)
            quality = node_text(quality_node, "QUALITY", required=False)
            if name is None:
                if quality is not None:
                    raise SourceValidationError(
                        "UN alias quality has no associated alias name."
                    )
                continue
            attributes = () if quality_node is None else (("QUALITY", quality or ""),)
            evidence.append(
                alias_evidence(
                    name,
                    "ENTITY.ENTITY_ALIAS.ALIAS_NAME",
                    context,
                    language=xml_language(name_node, alias, entity, entities, root),
                    attributes=attributes,
                )
            )
        records.append(
            source_record(
                context,
                provider_id=provider_id,
                entity_type="organization",
                primary_name=primary,
                aliases=evidence,
                provider_schema="CONSOLIDATED_LIST.ENTITIES.ENTITY",
            )
        )
    version = root.get("dateGenerated")
    return finish(
        payload,
        context,
        records,
        input_records=len(people) + len(entities),
        excluded_person_records=len(people),
        excluded_other_records=0,
        parser_version=PARSER_VERSION,
        source_version=version,
        source_version_field="CONSOLIDATED_LIST@dateGenerated"
        if version is not None
        else None,
    )
