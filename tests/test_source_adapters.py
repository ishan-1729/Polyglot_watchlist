"""Offline source contracts exercised with authored fictional records only."""

from copy import deepcopy
import hashlib
import importlib
import io
import json
from pathlib import Path
import stat
import struct
import warnings
from xml.etree import ElementTree
import zipfile
import zlib

import pytest

from watchlist.ingest.parse_ftm import parse_ftm
from watchlist.ingest.source_registry import AliasEvidence, ParseContext


FIXTURES = Path(__file__).parent / "fixtures/acquisition"
XML_ADAPTERS = (
    ("un", "un_consolidated", "un.xml"),
    ("ofac", "ofac_sdn", "ofac.xml"),
    ("eu", "eu_consolidated", "eu.xml"),
)


def parse_source(kind: str, source_id: str, payload: bytes, **limits: int):
    module = importlib.import_module(f"watchlist.ingest.parse_{kind}")
    parser = getattr(module, f"parse_{kind}")
    return parser(payload, context=ParseContext(source_id=source_id, **limits))


def local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def xml_elements(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if local_name(element) == name]


def xml_payload(root: ElementTree.Element) -> bytes:
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def ftm_record(provider_id: str = "fictional-org-001", **changes: object) -> dict:
    """Build one independent fictional FollowTheMoney record for boundary tests."""
    record = {
        "id": provider_id,
        "schema": "Organization",
        "caption": "Fictional Moonberry Loom",
        "properties": {
            "name": ["Fictional Moonberry Loom"],
            "alias": ["Fictional Moonberry Weaving", "مونبيري الخيالية"],
            "topics": ["sanction"],
        },
        "datasets": ["fictional-test-data"],
        "referents": [],
    }
    record.update(changes)
    return record


def ftm_bytes(*records: dict) -> bytes:
    return (
        b"\n".join(
            json.dumps(record, ensure_ascii=False, allow_nan=False).encode("utf-8")
            for record in records
        )
        + b"\n"
    )


def parse_fictional_ftm(payload: bytes, **limits: int):
    return parse_ftm(
        payload, context=ParseContext(source_id="opensanctions_un", **limits)
    )


def test_ftm_alias_evidence_retains_original_text_and_distinct_fields() -> None:
    record = ftm_record()
    original = "  Fictional  Moonberry\tLoom  "
    record["properties"]["name"] = [original]
    record["properties"]["alias"] += [original, original]
    payload = ftm_bytes(record)
    result = parse_fictional_ftm(payload)
    assert result.input_sha256 == hashlib.sha256(payload).hexdigest()
    assert len(result.records) == 1
    entity = result.records[0]
    assert entity.provider_id == record["id"]
    assert entity.source_id == "opensanctions_un"
    assert entity.entity_type == "organization"
    assert record["id"] in entity.qualified_id
    assert "opensanctions_un" in entity.qualified_id
    original_evidence = [alias for alias in entity.aliases if alias.value == original]
    assert len(original_evidence) == 2
    assert len({alias.field for alias in original_evidence}) == 2
    assert all(alias.language is None for alias in entity.aliases)
    assert "مونبيري الخيالية" in {alias.value for alias in entity.aliases}


def test_ftm_record_and_alias_order_is_deterministic() -> None:
    first, second = ftm_record("fictional-a"), ftm_record("fictional-z")
    second["caption"] = "Fictional Starlight Vessel"
    second["schema"] = "Vessel"
    second["properties"]["name"] = [second["caption"]]
    reversed_first = deepcopy(first)
    reversed_first["properties"]["alias"].reverse()
    forward = parse_fictional_ftm(ftm_bytes(first, second))
    backward = parse_fictional_ftm(ftm_bytes(second, reversed_first))
    assert forward.records == backward.records
    assert {record.entity_type for record in forward.records} == {
        "organization",
        "vessel",
    }


def test_ftm_identical_names_do_not_merge_distinct_provider_ids() -> None:
    result = parse_fictional_ftm(
        ftm_bytes(ftm_record("fictional-a"), ftm_record("fictional-b"))
    )
    assert len(result.records) == 2
    assert result.records[0].primary_name == result.records[1].primary_name
    assert len({record.qualified_id for record in result.records}) == 2


def test_ftm_explicit_referents_are_sorted_and_deduplicated_without_name_inference() -> (
    None
):
    record = ftm_record(referents=["fictional-z", "fictional-a", "fictional-z"])
    result = parse_fictional_ftm(ftm_bytes(record))
    assert result.records[0].referents == ("fictional-a", "fictional-z")


@pytest.mark.parametrize("topics", [[], ["fictional-other-topic"]])
def test_ftm_organization_without_explicit_sanction_topic_is_not_selected(
    topics,
) -> None:
    record = ftm_record()
    record["properties"]["topics"] = topics
    result = parse_fictional_ftm(ftm_bytes(record))
    assert result.records == ()
    assert result.excluded_other_records == 1


@pytest.mark.parametrize("schema", ["Person", "Individual"])
def test_ftm_explicit_people_are_excluded_from_mixed_input(schema: str) -> None:
    person = ftm_record("fictional-person", schema=schema)
    result = parse_fictional_ftm(ftm_bytes(ftm_record(), person))
    assert result.excluded_person_records == 1
    assert result.input_records == 2
    assert [record.provider_id for record in result.records] == ["fictional-org-001"]


@pytest.mark.parametrize(
    "schema", ["LegalEntity", "Aircraft", "Address", "UnknownEntity"]
)
def test_ftm_unknown_or_out_of_scope_types_are_never_organizations(schema: str) -> None:
    result = parse_fictional_ftm(
        ftm_bytes(ftm_record("fictional-other", schema=schema))
    )
    assert result.records == ()
    assert result.excluded_other_records == 1


@pytest.mark.parametrize("schema", ["Organization", "Company", "Vessel"])
def test_ftm_explicit_approved_entity_types(schema: str) -> None:
    result = parse_fictional_ftm(ftm_bytes(ftm_record(schema=schema)))
    assert len(result.records) == 1
    assert result.records[0].entity_type == (
        "vessel" if schema == "Vessel" else "organization"
    )


@pytest.mark.parametrize(
    "dataset,topics,selected",
    [
        ("un_sc_sanctions", ["sanction"], True),
        ("un_sc_sanctions", [], False),
        ("fictional_other", ["sanction"], False),
    ],
)
def test_ftm_legal_entity_requires_the_explicit_reviewed_un_mapping(
    dataset, topics, selected
) -> None:
    record = ftm_record(schema="LegalEntity", datasets=[dataset])
    record["properties"]["topics"] = topics
    result = parse_fictional_ftm(ftm_bytes(record))
    assert len(result.records) == int(selected)
    if selected:
        assert result.records[0].entity_type == "organization"
        assert result.records[0].provider_schema == "LegalEntity"
    else:
        assert result.excluded_other_records == 1


@pytest.mark.parametrize(
    "schema,basis",
    [
        ("Organization", "ftm-explicit-schema"),
        ("LegalEntity", "reviewed-un-entity-mapping"),
    ],
)
def test_ftm_selection_keeps_original_dataset_topic_and_classification_evidence(
    schema, basis
) -> None:
    record = ftm_record(
        schema=schema,
        datasets=["un_sc_sanctions", "fictional-extra-dataset"],
    )
    record["properties"]["topics"] = ["sanction", "fictional-extra-topic"]
    selected = parse_fictional_ftm(ftm_bytes(record)).records[0]
    assert selected.provider_datasets == ("fictional-extra-dataset", "un_sc_sanctions")
    assert selected.provider_topics == ("fictional-extra-topic", "sanction")
    assert selected.provider_schema == schema
    assert selected.classification_basis == basis
    assert selected.source_id == "opensanctions_un"
    assert selected.qualified_id.startswith("opensanctions_un:")


@pytest.mark.parametrize("second_schema", ["Organization", "Person", "Vessel"])
def test_ftm_duplicate_provider_ids_fail_even_in_excluded_rows(
    second_schema: str,
) -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record(), ftm_record(schema=second_schema)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", None),
        ("id", ""),
        ("id", 7),
        ("id", True),
        ("schema", None),
        ("schema", ["Organization"]),
        ("properties", []),
        ("properties", {"name": "not a list"}),
        ("properties", {"name": [7]}),
        ("properties", {"name": ["Fictional Loom"], "alias": [None]}),
        ("referents", "not a list"),
    ],
)
def test_ftm_malformed_record_shapes_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record(**{field: value})))


@pytest.mark.parametrize(
    "suffix",
    [
        ',"id":"conflicting-fictional-id"}',
        ',"extra":{"field":1,"field":2}}',
        ',"extra":NaN}',
        ',"extra":Infinity}',
        ',"extra":-Infinity}',
        ',"extra":1e999}',
    ],
)
def test_ftm_duplicate_json_keys_and_nonfinite_numbers_are_rejected(
    suffix: str,
) -> None:
    valid = json.dumps(ftm_record(), ensure_ascii=False)
    payload = (valid[:-1] + suffix).encode("utf-8")
    with pytest.raises(ValueError):
        parse_fictional_ftm(payload)


@pytest.mark.parametrize("payload", [b"[]", b"null", b"true", b"{", b"\xff"])
def test_ftm_invalid_json_documents_are_rejected(payload: bytes) -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(payload)


def test_ftm_escaped_surrogate_name_is_a_clean_validation_failure() -> None:
    record = ftm_record()
    record["properties"]["alias"] = ["fictional\ud800name"]
    payload = json.dumps(record, ensure_ascii=True).encode("utf-8")
    with pytest.raises(ValueError):
        parse_fictional_ftm(payload)


def test_ftm_excessive_json_nesting_is_a_clean_validation_failure() -> None:
    valid = json.dumps(ftm_record())
    payload = (valid[:-1] + ',"nested":' + "[" * 200 + "0" + "]" * 200 + "}").encode()
    with pytest.raises(ValueError):
        parse_fictional_ftm(payload)


def test_ftm_group_cap_is_order_independent_and_does_not_hide_invalid_tail() -> None:
    first, second = ftm_record("fictional-a"), ftm_record("fictional-z")
    one = parse_fictional_ftm(ftm_bytes(second, first), max_groups=1)
    reverse = parse_fictional_ftm(ftm_bytes(first, second), max_groups=1)
    assert one.records == reverse.records
    assert len(one.records) == 1 and one.excluded_by_limit == 1
    assert one.input_records == 2
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(first) + b"{malformed tail}\n", max_groups=1)


def test_ftm_exact_input_byte_cap_accepts_boundary_and_rejects_one_more() -> None:
    payload = ftm_bytes(ftm_record())
    assert len(parse_fictional_ftm(payload, max_input_bytes=len(payload)).records) == 1
    with pytest.raises(ValueError):
        parse_fictional_ftm(payload, max_input_bytes=len(payload) - 1)


def test_ftm_alias_and_name_caps_reject_instead_of_silently_dropping_evidence() -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record()), max_aliases=1)
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record()), max_name_chars=5)


def test_parser_rejects_a_context_for_a_different_source() -> None:
    with pytest.raises(ValueError):
        parse_ftm(
            ftm_bytes(ftm_record()), context=ParseContext(source_id="un_consolidated")
        )


@pytest.mark.parametrize(
    "field", ["max_groups", "max_aliases", "max_name_chars", "max_input_bytes"]
)
@pytest.mark.parametrize("invalid", [None, True, False, 0, -1, 1.5, "2", float("inf")])
def test_parse_limits_require_positive_integers(field: str, invalid: object) -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record()), **{field: invalid})


@pytest.mark.parametrize(
    "field,ceiling",
    [
        ("max_groups", 200),
        ("max_aliases", 128),
        ("max_name_chars", 1024),
        ("max_input_bytes", 10_000_000),
    ],
)
def test_parse_limits_cannot_exceed_approved_ceilings(field: str, ceiling: int) -> None:
    with pytest.raises(ValueError):
        parse_fictional_ftm(ftm_bytes(ftm_record()), **{field: ceiling + 1})


@pytest.mark.parametrize("max_input_bytes", [10_000_001, 28_000_001, 32_000_000])
def test_eu_parser_accepts_only_its_explicit_larger_byte_allowance(max_input_bytes):
    payload = (FIXTURES / "eu.xml").read_bytes()
    assert (
        len(
            parse_source(
                "eu", "eu_consolidated", payload, max_input_bytes=max_input_bytes
            ).records
        )
        == 2
    )
    for source_id in (
        "opensanctions_un",
        "un_consolidated",
        "ofac_sdn",
        "wikidata_orgs",
    ):
        with pytest.raises(ValueError):
            ParseContext(source_id=source_id, max_input_bytes=max_input_bytes)


@pytest.mark.parametrize("invalid", [32_000_001, True, 0, 1.5])
def test_eu_parser_cannot_expand_or_bypass_its_finite_ceiling(invalid):
    with pytest.raises(ValueError):
        parse_source(
            "eu",
            "eu_consolidated",
            (FIXTURES / "eu.xml").read_bytes(),
            max_input_bytes=invalid,
        )


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
def test_xml_fixtures_preserve_nonperson_names_languages_and_version_evidence(
    kind, source_id, filename
) -> None:
    payload = (FIXTURES / filename).read_bytes()
    result = parse_source(kind, source_id, payload)
    assert len(result.records) == 2
    assert result.excluded_person_records == 1
    assert result.excluded_other_records == (1 if kind == "ofac" else 0)
    assert result.input_records == 3 + (kind == "ofac")
    assert result.input_sha256 == hashlib.sha256(payload).hexdigest()
    assert result.source_version and result.source_version_field
    assert all(record.source_id == source_id for record in result.records)
    assert all(record.provider_schema for record in result.records)
    aliases = [alias for record in result.records for alias in record.aliases]
    if kind == "ofac":
        assert all(alias.language is None for alias in aliases)
    else:
        assert "ar" in {alias.language for alias in aliases}
    assert all("Excluded Person" not in alias.value for alias in aliases)
    assert {record.entity_type for record in result.records} == (
        {"organization", "vessel"} if kind == "ofac" else {"organization"}
    )
    if kind == "un":
        weak = next(alias for alias in aliases if alias.value == "Fictional Silverfern")
        assert dict(weak.attributes)["QUALITY"] == "Low"
    elif kind == "ofac":
        weak = next(alias for alias in aliases if alias.value == "Fictional Cloudberry")
        assert dict(weak.attributes)["category"] == "weak"
        assert dict(weak.attributes)["type"] == "a.k.a."
        assert dict(weak.attributes)["uid"] == "990000113"
    else:
        alternative = next(
            alias for alias in aliases if alias.value == "Fictional Jadebranch"
        )
        assert dict(alternative.attributes)["strong"] == "false"
        assert any(alias.language == "EN" for alias in aliases)


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
def test_xml_record_order_does_not_change_selected_evidence(
    kind, source_id, filename
) -> None:
    original = (FIXTURES / filename).read_bytes()
    root = ElementTree.fromstring(original)
    if kind == "un":
        container = xml_elements(root, "ENTITIES")[0]
        container[:] = list(reversed(container))
    else:
        record_tag = "sdnEntry" if kind == "ofac" else "sanctionEntity"
        records = [element for element in root if local_name(element) == record_tag]
        for element in records:
            root.remove(element)
        root.extend(reversed(records))
    assert (
        parse_source(kind, source_id, original).records
        == parse_source(kind, source_id, xml_payload(root)).records
    )


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-id",
        "missing-id",
        "duplicate-required-field",
        "unknown-namespace",
        "mixed-namespace",
    ],
)
def test_xml_ambiguous_or_unknown_structure_is_rejected(
    kind, source_id, filename, mutation
) -> None:
    root = ElementTree.fromstring((FIXTURES / filename).read_bytes())
    tag = {"un": "ENTITY", "ofac": "sdnEntry", "eu": "sanctionEntity"}[kind]
    records = xml_elements(root, tag)
    if mutation == "duplicate-id":
        if kind in {"un", "ofac"}:
            field = "DATAID" if kind == "un" else "uid"
            xml_elements(records[1], field)[0].text = xml_elements(records[0], field)[
                0
            ].text
        else:
            field = "logicalId"
            records[1].set(field, records[0].get(field))
    elif mutation == "missing-id":
        if kind in {"un", "ofac"}:
            field = "DATAID" if kind == "un" else "uid"
            records[0].remove(xml_elements(records[0], field)[0])
        else:
            del records[0].attrib["logicalId"]
    elif mutation == "duplicate-required-field":
        field = {"un": "FIRST_NAME", "ofac": "sdnType", "eu": "subjectType"}[kind]
        records[0].append(deepcopy(xml_elements(records[0], field)[0]))
    elif mutation == "unknown-namespace":
        for element in root.iter():
            element.tag = "{urn:fictional:unsupported-source:9}" + local_name(element)
    else:
        records[0].tag = "{urn:fictional:foreign-child:9}" + local_name(records[0])
    with pytest.raises(ValueError):
        parse_source(kind, source_id, xml_payload(root))


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
@pytest.mark.parametrize(
    "declaration",
    [
        "<!DOCTYPE fictional>",
        '<!DOCTYPE fictional [<!ENTITY authored "Fictional injected name">]>',
        '<!DOCTYPE fictional [<!ENTITY authored SYSTEM "file:///fictional-do-not-read">]>',
        '<!DOCTYPE fictional [<!ENTITY % authored SYSTEM "https://fictional.invalid/no-fetch">%authored;]>',
    ],
)
def test_xml_dtd_and_entity_declarations_are_rejected_before_parsing(
    kind, source_id, filename, declaration
) -> None:
    original = (FIXTURES / filename).read_bytes()
    payload = original.replace(b"?>", b"?>\n" + declaration.encode(), 1)
    with pytest.raises(ValueError):
        parse_source(kind, source_id, payload)


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
def test_xml_alternate_encoding_cannot_hide_a_dtd(kind, source_id, filename) -> None:
    text = (FIXTURES / filename).read_text(encoding="utf-8").replace("UTF-8", "UTF-16")
    text = text.replace("?>", "?>\n<!DOCTYPE fictional>", 1)
    with pytest.raises(ValueError):
        parse_source(kind, source_id, text.encode("utf-16"))


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
def test_xml_limits_apply_without_ignoring_malformed_tail(
    kind, source_id, filename
) -> None:
    payload = (FIXTURES / filename).read_bytes()
    limited = parse_source(kind, source_id, payload, max_groups=1)
    assert len(limited.records) == limited.excluded_by_limit == 1
    assert limited.input_records >= 3
    assert (
        len(
            parse_source(kind, source_id, payload, max_input_bytes=len(payload)).records
        )
        == 2
    )
    for bad_payload, limits in (
        (payload, {"max_input_bytes": len(payload) - 1}),
        (payload + b"<incomplete-tail>", {"max_groups": 1}),
        (payload, {"max_aliases": 1}),
        (payload, {"max_name_chars": 5}),
    ):
        with pytest.raises(ValueError):
            parse_source(kind, source_id, bad_payload, **limits)


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS)
def test_xml_language_metadata_is_validated_without_guessing(
    kind, source_id, filename
) -> None:
    root = ElementTree.fromstring((FIXTURES / filename).read_bytes())
    if kind == "eu":
        name = xml_elements(root, "nameAlias")[0]
        name.set("nameLanguage", "not a language tag")
    else:
        tag = "NAME_ORIGINAL_SCRIPT" if kind == "un" else "lastName"
        xml_elements(root, tag)[0].set(
            "{http://www.w3.org/XML/1998/namespace}lang", "not a language tag"
        )
    with pytest.raises(ValueError):
        parse_source(kind, source_id, xml_payload(root))


def test_eu_conflicting_person_and_enterprise_markers_fail_closed() -> None:
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    xml_elements(root, "subjectType")[0].set("classificationCode", "P")
    with pytest.raises(ValueError):
        parse_source("eu", "eu_consolidated", xml_payload(root))


@pytest.mark.parametrize("strong", ["true", "1", " true ", " 1 ", "\ttrue\n", "\r1\t"])
@pytest.mark.parametrize(
    "alternative_flag", ["false", "0", " false ", " 0 ", "\tfalse\r", "\n0\t"]
)
def test_eu_display_name_prefers_explicit_main_names_and_keeps_alternatives(
    strong, alternative_flag
):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    entity = xml_elements(root, "sanctionEntity")[0]
    for name in xml_elements(entity, "nameAlias"):
        if name.get("strong") == "true":
            name.set("strong", strong)
        else:
            name.set("strong", alternative_flag)
    result = parse_source("eu", "eu_consolidated", xml_payload(root))
    selected = next(
        record
        for record in result.records
        if record.provider_id == entity.get("logicalId")
    )
    assert selected.primary_name == "Fictional Jadebranch Cooperative"
    assert {alias.value for alias in selected.aliases} == {
        "Fictional Jadebranch Cooperative",
        "虚构玉枝合作社",
        "Fictional Jadebranch",
    }
    alternative = next(
        alias for alias in selected.aliases if alias.value == "Fictional Jadebranch"
    )
    assert dict(alternative.attributes)["strong"] == alternative_flag
    main = next(
        alias for alias in selected.aliases if alias.value == selected.primary_name
    )
    assert dict(main.attributes)["strong"] == strong


@pytest.mark.parametrize("flag", [None, "false", "0", " false ", " 0 "])
def test_eu_without_main_name_flag_uses_deterministic_original_display_name(flag):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    entity = xml_elements(root, "sanctionEntity")[0]
    for name in xml_elements(entity, "nameAlias"):
        if flag is None:
            name.attrib.pop("strong")
        else:
            name.set("strong", flag)
    selected = parse_source("eu", "eu_consolidated", xml_payload(root)).records[0]
    assert selected.primary_name == "Fictional Jadebranch"
    original = {name.get("wholeName") for name in xml_elements(entity, "nameAlias")}
    assert {alias.value for alias in selected.aliases} == original
    entity[:] = list(reversed(entity))
    assert (
        parse_source("eu", "eu_consolidated", xml_payload(root)).records[0] == selected
    )


@pytest.mark.parametrize(
    "flag", ["TRUE", "yes", "1.0", "", "   ", "tr ue", "tr\tue", "\u00a0true\u00a0"]
)
def test_eu_nonboolean_main_name_flags_are_rejected(flag):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    xml_elements(root, "nameAlias")[0].set("strong", flag)
    with pytest.raises(ValueError):
        parse_source("eu", "eu_consolidated", xml_payload(root))


@pytest.mark.parametrize(
    "field",
    [
        "logicalId",
        "regulationLanguage",
        "nameLanguage",
        "firstName",
        "middleName",
        "lastName",
    ],
)
def test_eu_boolean_whitespace_exception_does_not_allow_controls_in_other_metadata(
    field,
):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    xml_elements(root, "nameAlias")[0].set(field, "a\tb")
    with pytest.raises(ValueError):
        parse_source("eu", "eu_consolidated", xml_payload(root))


@pytest.mark.parametrize(
    "field",
    [
        "sdnEntry.akaList.aka.lastName",
        "properties.alias",
        "sanctionEntity.nameAlias@unsupported",
    ],
)
def test_boolean_whitespace_exception_does_not_expand_other_alias_field_contracts(
    field,
):
    with pytest.raises(ValueError):
        AliasEvidence(
            value="Fictional non-EU-field alias",
            field=field,
            attributes=(("strong", "\ttrue\n"),),
        )


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x0b", "\x1f"])
def test_eu_strong_attribute_still_rejects_controls_outside_xml_whitespace(control):
    with pytest.raises(ValueError):
        AliasEvidence(
            value="Fictional EU name",
            field="sanctionEntity.nameAlias@wholeName",
            attributes=(("strong", control + "true"),),
        )


@pytest.mark.parametrize("classification,selected", [("E", True), ("P", False)])
def test_eu_explicit_classification_controls_selection_for_free_text_type_code(
    classification, selected
):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    entity = xml_elements(root, "sanctionEntity")[0]
    subject = xml_elements(entity, "subjectType")[0]
    subject.set("code", "fictional-company")
    subject.set("classificationCode", classification)
    result = parse_source("eu", "eu_consolidated", xml_payload(root))
    matches = [
        record
        for record in result.records
        if record.provider_id == entity.get("logicalId")
    ]
    assert len(matches) == int(selected)
    if selected:
        assert matches[0].entity_type == "organization"
        assert "fictional-company" in matches[0].provider_schema
        assert matches[0].classification_basis == "eu-subjectType-classificationCode-E"
    else:
        assert result.excluded_person_records == 2


@pytest.mark.parametrize("classification", [None, "", "X", "Enterprise"])
def test_eu_missing_or_unknown_classification_is_rejected(classification):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    subject = xml_elements(root, "subjectType")[0]
    if classification is None:
        subject.attrib.pop("classificationCode")
    else:
        subject.set("classificationCode", classification)
    with pytest.raises(ValueError):
        parse_source("eu", "eu_consolidated", xml_payload(root))


@pytest.mark.parametrize(
    "field",
    [
        "generationDate",
        "globalFileId",
        "logicalId",
        "regulationLanguage",
        "regulationSummary",
    ],
)
def test_eu_required_publisher_and_alias_metadata_cannot_be_missing(field):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    name = xml_elements(root, "nameAlias")[0]
    if field in {"generationDate", "globalFileId"}:
        root.attrib.pop(field)
    elif field == "regulationSummary":
        name.remove(xml_elements(name, field)[0])
    else:
        name.attrib.pop(field)
    with pytest.raises(ValueError):
        parse_source("eu", "eu_consolidated", xml_payload(root))


def test_eu_version_preserves_both_explicit_publisher_fields():
    payload = (FIXTURES / "eu.xml").read_bytes()
    root = ElementTree.fromstring(payload)
    result = parse_source("eu", "eu_consolidated", payload)
    assert json.loads(result.source_version) == {
        "generationDate": root.get("generationDate"),
        "globalFileId": root.get("globalFileId"),
    }
    assert result.source_version_field == "export@generationDate,export@globalFileId"


def test_eu_missing_whole_name_preserves_separate_parts_without_inventing_language():
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    entity = xml_elements(root, "sanctionEntity")[0]
    names = xml_elements(entity, "nameAlias")
    name = names[0]
    for other in names[1:]:
        entity.remove(other)
    name.attrib.pop("wholeName")
    name.attrib.pop("nameLanguage")
    parts = {
        "firstName": "Fictional First",
        "middleName": "Fictional Middle",
        "lastName": "Fictional Last",
    }
    for field, value in parts.items():
        name.set(field, value)
    name.set("regulationLanguage", "FR")
    name.set("strong", "\t1\r\n")
    selected = parse_source("eu", "eu_consolidated", xml_payload(root)).records[0]
    assert {alias.value for alias in selected.aliases} == set(parts.values())
    assert {alias.field for alias in selected.aliases} == {
        f"sanctionEntity.nameAlias@{field}" for field in parts
    }
    assert all(alias.language is None for alias in selected.aliases)
    assert all(
        dict(alias.attributes)["regulationLanguage"] == "FR"
        for alias in selected.aliases
    )
    assert all(
        dict(alias.attributes)["strong"] == "\t1\r\n" for alias in selected.aliases
    )


def test_eu_present_empty_regulation_language_is_preserved_without_name_inference():
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    name = xml_elements(root, "nameAlias")[0]
    name.set("regulationLanguage", "")
    name.attrib.pop("nameLanguage")
    result = parse_source("eu", "eu_consolidated", xml_payload(root))
    selected = next(
        alias
        for alias in result.records[0].aliases
        if alias.value == name.get("wholeName")
    )
    assert dict(selected.attributes)["regulationLanguage"] == ""
    assert selected.language is None


def test_eu_retains_name_evidence_without_unrelated_occupation_title_or_gender():
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    name = xml_elements(root, "nameAlias")[0]
    omitted = {
        "function": "Fictional unrelated occupation",
        "title": "Fictional unrelated honorific",
        "gender": "M",
    }
    for field, value in omitted.items():
        name.set(field, value)
    result = parse_source("eu", "eu_consolidated", xml_payload(root))
    selected = next(
        alias
        for alias in result.records[0].aliases
        if alias.value == name.get("wholeName")
    )
    assert dict(selected.attributes)["logicalId"] == name.get("logicalId")
    assert dict(selected.attributes)["strong"] == name.get("strong")
    assert all(
        not (set(omitted) & dict(alias.attributes).keys())
        for record in result.records
        for alias in record.aliases
    )


@pytest.mark.parametrize("language", ["??", "EN?"])
def test_eu_short_unrecognized_source_language_stays_evidence_without_a_language_claim(
    language,
):
    root = ElementTree.fromstring((FIXTURES / "eu.xml").read_bytes())
    name = xml_elements(root, "nameAlias")[0]
    name.set("nameLanguage", language)
    result = parse_source("eu", "eu_consolidated", xml_payload(root))
    selected = next(
        alias
        for alias in result.records[0].aliases
        if alias.value == name.get("wholeName")
    )
    assert dict(selected.attributes)["nameLanguage"] == language
    assert selected.language is None


def test_ofac_declared_record_count_cannot_hide_missing_records() -> None:
    root = ElementTree.fromstring((FIXTURES / "ofac.xml").read_bytes())
    xml_elements(root, "Record_Count")[0].text = "999"
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", xml_payload(root))


@pytest.mark.parametrize("kind,source_id,filename", XML_ADAPTERS[:2])
@pytest.mark.parametrize("reset", [False, True])
def test_xml_language_inheritance_and_explicit_empty_reset(
    kind, source_id, filename, reset
) -> None:
    root = ElementTree.fromstring((FIXTURES / filename).read_bytes())
    language = "{http://www.w3.org/XML/1998/namespace}lang"
    root.set(language, "fr")
    tag = "FIRST_NAME" if kind == "un" else "lastName"
    name = xml_elements(root, tag)[1 if kind == "un" else 0]
    # The UN fixture's first FIRST_NAME is the deliberately excluded person.
    if reset:
        name.set(language, "")
    if kind == "ofac":
        xml_elements(root, "lastName")[1].set(language, "ar")
    result = parse_source(kind, source_id, xml_payload(root))
    aliases = [alias for record in result.records for alias in record.aliases]
    primary = next(alias for alias in aliases if alias.value == name.text)
    assert primary.language == (None if reset else "fr")
    assert any(alias.language == "ar" for alias in aliases)


def test_un_later_name_fields_remain_evidence_without_invented_joined_alias() -> None:
    root = ElementTree.fromstring((FIXTURES / "un.xml").read_bytes())
    entity = xml_elements(root, "ENTITY")[0]
    ElementTree.SubElement(entity, "SECOND_NAME").text = "Fictional Source Second Part"
    ElementTree.SubElement(entity, "THIRD_NAME").text = "Fictional Source Third Part"
    result = parse_source("un", "un_consolidated", xml_payload(root))
    primary = next(
        alias
        for alias in result.records[0].aliases
        if alias.value == result.records[0].primary_name
    )
    assert dict(primary.attributes)["SECOND_NAME"] == "Fictional Source Second Part"
    assert dict(primary.attributes)["THIRD_NAME"] == "Fictional Source Third Part"
    assert all(
        "Fictional Source Second Part" not in alias.value
        for alias in result.records[0].aliases
    )


@pytest.mark.parametrize("conflict", [False, True])
def test_ofac_duplicate_alias_uid_deduplicates_only_identical_evidence(
    conflict,
) -> None:
    original = (FIXTURES / "ofac.xml").read_bytes()
    root = ElementTree.fromstring(original)
    aliases = xml_elements(root, "akaList")[0]
    duplicate = deepcopy(aliases[0])
    if conflict:
        xml_elements(duplicate, "lastName")[
            0
        ].text = "Fictional conflicting alias for one UID"
    aliases.append(duplicate)
    if conflict:
        with pytest.raises(ValueError):
            parse_source("ofac", "ofac_sdn", xml_payload(root))
    else:
        assert (
            parse_source("ofac", "ofac_sdn", xml_payload(root)).records
            == parse_source("ofac", "ofac_sdn", original).records
        )


def wikidata_document() -> dict:
    return json.loads((FIXTURES / "wikidata.json").read_text(encoding="utf-8"))


def parse_wikidata_document(document: dict, **limits):
    return parse_source(
        "wikidata",
        "wikidata_orgs",
        json.dumps(document, ensure_ascii=False).encode(),
        **limits,
    )


def test_wikidata_repeated_alias_rows_preserve_languages_fields_and_unique_item_counts() -> (
    None
):
    document = wikidata_document()
    result = parse_wikidata_document(document)
    assert result.input_records == 3
    assert result.excluded_person_records == 1
    assert len(result.records) == 2
    assert {record.provider_schema for record in result.records} == {
        "wikidata:P31:Q43229"
    }
    assert result.source_version is result.source_version_field is None
    document["results"]["bindings"] += deepcopy(document["results"]["bindings"])
    document["results"]["bindings"].reverse()
    repeated = parse_wikidata_document(document)
    assert repeated.records == result.records
    assert repeated.input_records == 3
    first = next(
        record for record in result.records if record.provider_id == "Q999999901"
    )
    same_value = [
        alias
        for alias in first.aliases
        if alias.value == "Fictional Amberquill Cooperative"
    ]
    assert {alias.field for alias in same_value} == {"rdfs:label", "skos:altLabel"}
    assert all(alias.language == "en" for alias in same_value)
    assert "ar" in {alias.language for alias in first.aliases}


def test_wikidata_same_text_in_different_languages_stays_separate_evidence() -> None:
    document = wikidata_document()
    alternate = deepcopy(document["results"]["bindings"][0])
    alternate["name"]["xml:lang"] = "fr"
    document["results"]["bindings"].append(alternate)
    result = parse_wikidata_document(document)
    first = next(
        record for record in result.records if record.provider_id == "Q999999901"
    )
    labels = [
        alias
        for alias in first.aliases
        if alias.field == "rdfs:label" and alias.value == alternate["name"]["value"]
    ]
    assert {alias.language for alias in labels} == {"en", "fr"}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-item",
        "missing-name",
        "missing-name-kind",
        "missing-type",
        "unknown-column",
        "wrong-header",
        "noncanonical-item",
        "wrong-literal-type",
        "unknown-name-kind",
        "invalid-language",
        "conflicting-type",
        "alias-without-label",
    ],
)
def test_wikidata_malformed_or_ambiguous_projection_is_rejected(mutation) -> None:
    document = wikidata_document()
    binding = document["results"]["bindings"][0]
    missing = {
        "missing-item": "item",
        "missing-name": "name",
        "missing-name-kind": "name_kind",
        "missing-type": "type",
    }
    if mutation in missing:
        del binding[missing[mutation]]
    elif mutation == "unknown-column":
        binding["extra"] = {"type": "literal", "value": "fictional"}
    elif mutation == "wrong-header":
        document["head"]["vars"] = ["item", "name"]
    elif mutation == "noncanonical-item":
        binding["item"]["value"] = "https://unapproved.invalid/entity/Q999999901"
    elif mutation == "wrong-literal-type":
        binding["name"]["type"] = "uri"
    elif mutation == "unknown-name-kind":
        binding["name_kind"]["value"] = "identity_inference"
    elif mutation == "invalid-language":
        binding["name"]["xml:lang"] = "not a language"
    elif mutation == "conflicting-type":
        duplicate = deepcopy(binding)
        duplicate["type"]["value"] = "http://www.wikidata.org/entity/Q5"
        document["results"]["bindings"].append(duplicate)
    else:
        for item in document["results"]["bindings"]:
            item["name_kind"]["value"] = "alias"
    with pytest.raises(ValueError):
        parse_wikidata_document(document)


@pytest.mark.parametrize(
    "suffix",
    [
        ',"head":{"vars":[]}}',
        ',"extra":{"x":1,"x":2}}',
        ',"extra":NaN}',
        ',"extra":1e999}',
    ],
)
def test_wikidata_rejects_duplicate_json_keys_and_nonfinite_values(suffix) -> None:
    payload = (json.dumps(wikidata_document())[:-1] + suffix).encode()
    with pytest.raises(ValueError):
        parse_source("wikidata", "wikidata_orgs", payload)


def test_wikidata_group_cap_keeps_aliases_together_and_validates_later_bindings() -> (
    None
):
    document = wikidata_document()
    full = parse_wikidata_document(document)
    limited = parse_wikidata_document(document, max_groups=1)
    assert limited.records == full.records[:1]
    assert limited.excluded_by_limit == 1
    document["results"]["bindings"].append({"malformed": "fictional tail"})
    with pytest.raises(ValueError):
        parse_wikidata_document(document, max_groups=1)


def test_legacy_twenty_record_parser_contract_is_unchanged() -> None:
    from watchlist.ingest.parse_opensanctions import parse_records, read_records

    fixture = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
    records = read_records(fixture)
    selected, _ = parse_records(records, synthetic=True, limit=20)
    assert len(selected) == 3
    with pytest.raises(ValueError):
        parse_records(records, synthetic=True, limit=21)


def ofac_archive(
    payload: bytes,
    *,
    name="SDN.XML",
    compression=zipfile.ZIP_DEFLATED,
    extra=(),
    mode=None,
    comment=b"",
) -> bytes:
    """Construct a tiny fictional archive without any filesystem extraction."""
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Duplicate name:.*", category=UserWarning
        )
        with zipfile.ZipFile(stream, "w", compression=compression) as archive:
            if mode is None:
                archive.writestr(name, payload)
            else:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                info.compress_type = compression
                archive.writestr(info, payload)
            for extra_name, extra_payload in extra:
                archive.writestr(extra_name, extra_payload)
            archive.comment = comment
    return stream.getvalue()


def alter_zip_fields(
    payload: bytes,
    *,
    uncompressed=None,
    encrypted=False,
    compression=None,
    corrupt_crc=False,
) -> bytes:
    """Change matching local/central metadata for deliberately hostile fixtures."""
    changed = bytearray(payload)
    local = changed.index(b"PK\x03\x04")
    central = changed.index(b"PK\x01\x02")
    if uncompressed is not None:
        struct.pack_into("<I", changed, local + 22, uncompressed)
        struct.pack_into("<I", changed, central + 24, uncompressed)
    if encrypted:
        for offset in (local + 6, central + 8):
            flags = struct.unpack_from("<H", changed, offset)[0]
            struct.pack_into("<H", changed, offset, flags | 1)
    if compression is not None:
        struct.pack_into("<H", changed, local + 8, compression)
        struct.pack_into("<H", changed, central + 10, compression)
    if corrupt_crc:
        for offset in (local + 14, central + 16):
            crc = struct.unpack_from("<I", changed, offset)[0]
            struct.pack_into("<I", changed, offset, crc ^ 1)
    return bytes(changed)


@pytest.mark.parametrize("compression", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_ofac_zip_preserves_original_container_and_decoded_xml_hashes(
    compression,
) -> None:
    xml = (FIXTURES / "ofac.xml").read_bytes()
    archive = ofac_archive(xml, compression=compression)
    result = parse_source("ofac", "ofac_sdn", archive)
    plain = parse_source("ofac", "ofac_sdn", xml)
    assert result.records == plain.records
    assert result.input_sha256 == hashlib.sha256(archive).hexdigest()
    assert result.input_sha256 != hashlib.sha256(xml).hexdigest()
    assert result.container_format == "zip"
    assert result.container_member == "SDN.XML"
    assert result.decoded_bytes == len(xml)
    assert result.decoded_sha256 == hashlib.sha256(xml).hexdigest()
    assert (
        parse_source("ofac", "ofac_sdn", archive, max_input_bytes=len(archive)).records
        == result.records
    )
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", archive, max_input_bytes=len(archive) - 1)


@pytest.mark.parametrize(
    "name",
    ["../SDN.XML", "/SDN.XML", "nested/SDN.XML", "sdn.xml", "SDN.XML/", "C:\\SDN.XML"],
)
def test_ofac_zip_only_accepts_the_exact_flat_member_name(name) -> None:
    xml = (FIXTURES / "ofac.xml").read_bytes()
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", ofac_archive(xml, name=name))


@pytest.mark.parametrize("extra_name", ["SDN.XML", "README.txt", "folder/"])
def test_ofac_zip_duplicate_or_additional_members_are_rejected(extra_name) -> None:
    xml = (FIXTURES / "ofac.xml").read_bytes()
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", ofac_archive(xml, extra=[(extra_name, xml)]))


@pytest.mark.parametrize(
    "mode", [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o755, stat.S_IFIFO | 0o600]
)
def test_ofac_zip_member_must_be_an_ordinary_file(mode) -> None:
    xml = (FIXTURES / "ofac.xml").read_bytes()
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", ofac_archive(xml, mode=mode))


@pytest.mark.parametrize(
    "fault",
    [
        "encrypted",
        "unsupported-compression",
        "crc",
        "truncated",
        "prefix",
        "trailer",
        "comment",
    ],
)
def test_ofac_zip_rejects_unsupported_or_corrupted_container(fault) -> None:
    xml = (FIXTURES / "ofac.xml").read_bytes()
    archive = ofac_archive(xml)
    if fault == "encrypted":
        archive = alter_zip_fields(archive, encrypted=True)
    elif fault == "unsupported-compression":
        archive = alter_zip_fields(archive, compression=zipfile.ZIP_BZIP2)
    elif fault == "crc":
        archive = alter_zip_fields(archive, corrupt_crc=True)
    elif fault == "truncated":
        archive = archive[:-10]
    elif fault == "prefix":
        archive = b"fictional-prefix" + archive
    elif fault == "trailer":
        archive += b"fictional-trailer"
    else:
        archive = ofac_archive(xml, comment=b"fictional archive comment")
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", archive)


def test_ofac_zip_declared_decoded_size_is_checked_before_decompression(
    monkeypatch,
) -> None:
    archive = alter_zip_fields(
        ofac_archive((FIXTURES / "ofac.xml").read_bytes()),
        uncompressed=32_000_001,
    )

    def forbidden_decompress(*args, **kwargs):
        raise AssertionError("Oversized declared XML must fail before decompression.")

    monkeypatch.setattr(zlib, "decompressobj", forbidden_decompress)
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", archive)


def test_ofac_zip_actual_expansion_cannot_bypass_a_forged_small_declaration() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open("SDN.XML", "w") as member:
            block = b"x" * 1_000_000
            for _ in range(32):
                member.write(block)
            member.write(b"x")
    archive = alter_zip_fields(stream.getvalue(), uncompressed=1)
    assert len(archive) < 10_000_000
    with pytest.raises(ValueError, match="(?i)limit|exceed|expanded|bound"):
        parse_source("ofac", "ofac_sdn", archive)


OFAC_CURRENT_NAMESPACE = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
)


def current_ofac_fixture() -> ElementTree.Element:
    root = ElementTree.fromstring((FIXTURES / "ofac.xml").read_bytes())
    assert root.tag == "{" + OFAC_CURRENT_NAMESPACE + "}sdnList"
    return root


def test_ofac_current_verified_schema_uses_child_identifiers() -> None:
    root = current_ofac_fixture()
    result = parse_source("ofac", "ofac_sdn", xml_payload(root))
    assert len(result.records) == 2 and result.excluded_person_records == 1
    assert {record.provider_id for record in result.records} == {
        "990000101",
        "990000102",
    }
    aliases = [alias for record in result.records for alias in record.aliases]
    assert any(dict(alias.attributes).get("uid") == "990000113" for alias in aliases)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-child",
        "duplicate-child",
        "both-forms",
        "attribute-only",
        "legacy-with-child",
    ],
)
def test_ofac_identifier_representation_must_match_its_namespace(mutation) -> None:
    root = current_ofac_fixture()
    entry = xml_elements(root, "sdnEntry")[0]
    child = xml_elements(entry, "uid")[0]
    if mutation == "missing-child":
        entry.remove(child)
    elif mutation == "duplicate-child":
        entry.append(deepcopy(child))
    elif mutation == "both-forms":
        entry.set("uid", child.text)
    elif mutation == "attribute-only":
        entry.set("uid", child.text)
        entry.remove(child)
    else:
        for element in root.iter():
            element.tag = "{http://tempuri.org/sdnList.xsd}" + local_name(element)
    with pytest.raises(ValueError):
        parse_source("ofac", "ofac_sdn", xml_payload(root))


@pytest.mark.parametrize("kind", ["first-name-only", "nameless"])
def test_ofac_optional_alias_name_fields_do_not_create_joined_or_empty_names(
    kind,
) -> None:
    root = current_ofac_fixture()
    alias = xml_elements(root, "aka")[0]
    last_name = xml_elements(alias, "lastName")[0]
    original_name = last_name.text
    alias.remove(last_name)
    if kind == "first-name-only":
        replacement = ElementTree.SubElement(
            alias, "{" + OFAC_CURRENT_NAMESPACE + "}firstName"
        )
        replacement.text = "Fictional Firstname Only Alias"
    result = parse_source("ofac", "ofac_sdn", xml_payload(root))
    names = [name for record in result.records for name in record.aliases]
    assert original_name not in {name.value for name in names}
    assert all(name.value.strip() for name in names)
    if kind == "first-name-only":
        replacement = next(
            name for name in names if name.value == "Fictional Firstname Only Alias"
        )
        assert replacement.field.endswith("firstName")


def test_ofac_absent_optional_publication_fields_use_explicit_no_version() -> None:
    root = current_ofac_fixture()
    publication = xml_elements(root, "publshInformation")[0]
    publication[:] = []
    result = parse_source("ofac", "ofac_sdn", xml_payload(root))
    assert len(result.records) == 2
    assert result.source_version is result.source_version_field is None
