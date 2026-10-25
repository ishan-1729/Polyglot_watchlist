"""Parse bounded FollowTheMoney JSON Lines without reusing the legacy importer."""

from __future__ import annotations

from watchlist.ingest._parse_common import (
    alias_evidence,
    finish,
    identifier,
    prepare_payload,
    require_text,
    source_record,
    strict_json,
    unique_identifier,
)
from watchlist.ingest.source_registry import (
    ParseContext,
    ParseResult,
    SourceValidationError,
)


PARSER_VERSION = "ftm-non-person-v2"
NAME_FIELDS = ("name", "alias", "previousName", "weakAlias")
ELIGIBLE_SCHEMAS = {
    "Organization": "organization",
    "Company": "organization",
    "Vessel": "vessel",
}


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SourceValidationError(f"FTM {field} must be an array of strings.")
    return value


def parse_ftm(payload: bytes, *, context: ParseContext) -> ParseResult:
    """Preserve names and apply the narrowly reviewed UN classification mapping.

    FTM properties are unordered, multi-valued strings. A deterministic source
    primary name is chosen from ``properties.name``; every original name value
    remains evidence. Weak aliases retain their separate property name and are
    not silently promoted to ordinary matching aliases. Bare LegalEntity is
    ambiguous. Only the explicitly named UN dataset may use the reviewed mapper
    from the source's ENTITY section to that schema; the acquisition registry
    pins that distribution and records its classification evidence.
    """
    text = prepare_payload(payload, context, "opensanctions_un")
    seen: set[str] = set()
    records = []
    input_records = excluded_people = excluded_other = 0
    for line_number, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            raw = strict_json(line)
        except SourceValidationError as exc:
            raise SourceValidationError(
                f"Invalid FTM JSON on line {line_number}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise SourceValidationError("Each FTM line must contain one entity object.")
        provider_id = unique_identifier(raw.get("id"), seen)
        schema = require_text(raw.get("schema"), "FTM schema", maximum=128)
        properties = raw.get("properties")
        if not isinstance(properties, dict):
            raise SourceValidationError(
                "FTM properties must be an object of string arrays."
            )
        for key, values in properties.items():
            require_text(key, "FTM property name", maximum=128)
            _string_list(values, "property values")
        referents = _string_list(raw.get("referents", []), "referents")
        if len(referents) > 1024:
            raise SourceValidationError("FTM record exceeds its referent limit.")
        for referent in referents:
            identifier(referent)
        datasets = _string_list(raw.get("datasets", []), "datasets")
        for dataset in datasets:
            identifier(dataset)
        if raw.get("caption") is not None:
            require_text(raw["caption"], "FTM caption", maximum=4096)
        input_records += 1
        if schema in {"Person", "Individual"}:
            excluded_people += 1
            continue
        entity_type = ELIGIBLE_SCHEMAS.get(schema)
        classification_basis = "ftm-explicit-schema"
        if schema == "LegalEntity" and "un_sc_sanctions" in datasets:
            entity_type = "organization"
            classification_basis = "reviewed-un-entity-mapping"
        if entity_type is None:
            excluded_other += 1
            continue
        primary_values = properties.get("name", [])
        if not primary_values:
            raise SourceValidationError(
                "Eligible FTM records require properties.name evidence."
            )
        aliases = [
            alias_evidence(value, f"properties.{field}", context)
            for field in NAME_FIELDS
            for value in properties.get(field, [])
        ]
        parsed = source_record(
            context,
            provider_id=provider_id,
            entity_type=entity_type,
            primary_name=min(primary_values),
            aliases=aliases,
            provider_schema=schema,
            referents=referents,
            provider_datasets=datasets,
            provider_topics=properties.get("topics", []),
            classification_basis=classification_basis,
        )
        if "sanction" not in properties.get("topics", []):
            excluded_other += 1
            continue
        records.append(parsed)
    if input_records == 0:
        raise SourceValidationError("FTM input contains no records.")
    return finish(
        payload,
        context,
        records,
        input_records=input_records,
        excluded_person_records=excluded_people,
        excluded_other_records=excluded_other,
        parser_version=PARSER_VERSION,
    )
