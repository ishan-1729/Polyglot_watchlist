"""Parse the fixed organization-name SPARQL JSON projection without fetching."""

from __future__ import annotations

import re

from watchlist.ingest._parse_common import (
    alias_evidence,
    finish,
    prepare_payload,
    require_text,
    source_record,
    strict_json,
)
from watchlist.ingest.source_registry import (
    AliasEvidence,
    ParseContext,
    ParseResult,
    SourceValidationError,
)


PARSER_VERSION = "wikidata-organization-names-v1"
VARIABLES = frozenset({"item", "name", "name_kind", "type"})
ENTITY_PREFIX = "http://www.wikidata.org/entity/"
ORGANIZATION_URI = ENTITY_PREFIX + "Q43229"
PERSON_URI = ENTITY_PREFIX + "Q5"
STRING_DATATYPE = "http://www.w3.org/2001/XMLSchema#string"
LANGUAGE_DATATYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"
NAME_FIELDS = {"label": "rdfs:label", "alias": "skos:altLabel"}


def _entity_uri(binding: object, field: str) -> str:
    if not isinstance(binding, dict) or set(binding) != {"type", "value"}:
        raise SourceValidationError(f"Wikidata {field} must be a URI binding.")
    value = binding.get("value")
    if (
        binding.get("type") != "uri"
        or not isinstance(value, str)
        or not re.fullmatch(re.escape(ENTITY_PREFIX) + r"Q[1-9][0-9]*", value)
    ):
        raise SourceValidationError(
            f"Wikidata {field} requires a canonical entity URI."
        )
    return value


def _literal(binding: object, field: str) -> tuple[str, str | None]:
    if (
        not isinstance(binding, dict)
        or not {"type", "value"} <= set(binding)
        or not set(binding) <= {"type", "value", "xml:lang", "datatype"}
        or binding.get("type") != "literal"
    ):
        raise SourceValidationError(f"Wikidata {field} must be a literal binding.")
    value = require_text(binding["value"], f"Wikidata {field}", maximum=4096)
    language = binding.get("xml:lang")
    if language is not None:
        language = require_text(language, f"Wikidata {field} language", maximum=64)
    datatype = binding.get("datatype")
    if datatype is not None and datatype != (
        LANGUAGE_DATATYPE if language is not None else STRING_DATATYPE
    ):
        raise SourceValidationError(
            "Unsupported or inconsistent Wikidata literal datatype."
        )
    return value, language


def parse_wikidata(payload: bytes, *, context: ParseContext) -> ParseResult:
    """Group repeated item rows while retaining source fields and language tags.

    The reviewed acquisition query supplies explicit organization qualification
    through direct P31 Q43229. A name is never used to infer that qualification.
    Input accounting counts unique items, because multiple bindings represent
    the labels and aliases of one logical source record. These supplementary
    names carry no sanctions or absence label.
    """
    text = prepare_payload(payload, context, "wikidata_orgs")
    raw = strict_json(text)
    if not isinstance(raw, dict) or set(raw) != {"head", "results"}:
        raise SourceValidationError("Unsupported Wikidata SPARQL JSON document.")
    head, result = raw["head"], raw["results"]
    if not isinstance(head, dict) or set(head) != {"vars"}:
        raise SourceValidationError("Unsupported Wikidata projection header.")
    variables = head["vars"]
    if (
        not isinstance(variables, list)
        or len(variables) != len(VARIABLES)
        or any(not isinstance(value, str) for value in variables)
        or set(variables) != VARIABLES
    ):
        raise SourceValidationError(
            "Wikidata projection must match the reviewed query."
        )
    if (
        not isinstance(result, dict)
        or set(result) != {"bindings"}
        or not isinstance(result["bindings"], list)
    ):
        raise SourceValidationError("Wikidata results must contain a bindings array.")
    groups: dict[str, tuple[str, set[AliasEvidence]]] = {}
    for binding in result["bindings"]:
        if not isinstance(binding, dict) or set(binding) != VARIABLES:
            raise SourceValidationError(
                "Incomplete or unexpected Wikidata result binding."
            )
        item = _entity_uri(binding["item"], "item")
        entity_type = _entity_uri(binding["type"], "type")
        name_kind, kind_language = _literal(binding["name_kind"], "name_kind")
        if name_kind not in NAME_FIELDS or kind_language is not None:
            raise SourceValidationError("Unsupported Wikidata name_kind literal.")
        name, language = _literal(binding["name"], "name")
        evidence = alias_evidence(
            name, NAME_FIELDS[name_kind], context, language=language
        )
        if item not in groups:
            groups[item] = (entity_type, set())
        existing_type, names = groups[item]
        if entity_type != existing_type:
            raise SourceValidationError("Conflicting Wikidata types for one item.")
        names.add(evidence)
        if len(names) > context.max_aliases:
            raise SourceValidationError(
                "Wikidata item exceeds its distinct alias limit."
            )
    records = []
    excluded_people = excluded_other = 0
    for item, (entity_type, evidence) in groups.items():
        if entity_type == PERSON_URI:
            excluded_people += 1
            continue
        if entity_type != ORGANIZATION_URI:
            excluded_other += 1
            continue
        labels = [name.value for name in evidence if name.field == "rdfs:label"]
        if not labels:
            raise SourceValidationError(
                "Wikidata organization requires source label evidence."
            )
        records.append(
            source_record(
                context,
                provider_id=item.removeprefix(ENTITY_PREFIX),
                entity_type="organization",
                primary_name=min(labels),
                aliases=evidence,
                provider_schema="wikidata:P31:Q43229",
            )
        )
    return finish(
        payload,
        context,
        records,
        input_records=len(groups),
        excluded_person_records=excluded_people,
        excluded_other_records=excluded_other,
        parser_version=PARSER_VERSION,
    )
