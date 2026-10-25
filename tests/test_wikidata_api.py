"""Fictional contract tests; none of these bodies was obtained from Wikidata."""

from copy import deepcopy
from dataclasses import asdict, replace
import json

import pytest

from watchlist.ingest.source_registry import SourceValidationError, validate_source_url
from watchlist.ingest.wikidata_api import (
    HUMAN_QID,
    ORGANIZATION_QID,
    WikidataAPIBatch,
    WikidataAPILimits,
    parse_fictional_wikidata_api_batches,
)


A = "Q900000001"
B = "Q900000002"
C = "Q900000003"
D = "Q900000004"


def claim(property_id, target=None, *, rank="normal", kind="value"):
    value = {"snaktype": kind, "property": property_id, "datatype": "wikibase-item"}
    if kind == "value":
        value["datavalue"] = {
            "type": "wikibase-entityid",
            "value": {
                "entity-type": "item",
                "numeric-id": int(target[1:]),
                "id": target,
            },
        }
    return {"type": "statement", "rank": rank, "mainsnak": value}


def item(qid, *, types=None, parents=None, names=True):
    """Even ontology items use invented revisions/edges in this fixture."""
    result = {
        "id": qid,
        "type": "item",
        "lastrevid": 123,
        "modified": "2026-01-01T00:00:00Z",
        "claims": {},
    }
    if types is not None:
        result["claims"]["P31"] = [claim("P31", value) for value in types]
    if parents is not None:
        result["claims"]["P279"] = [claim("P279", value) for value in parents]
    if names:
        result.update(
            labels={"en": {"language": "en", "value": "Fictional Cedar Company"}},
            aliases={"en": [{"language": "en", "value": "Fictional Cedar"}]},
        )
    return result


def batch(values, *, purpose="candidate", requested=None, redirects=(), extra=None):
    document = {"entities": {value["id"]: value for value in values}, "success": 1}
    if redirects:
        document["redirects"] = [{"from": start, "to": end} for start, end in redirects]
    if extra:
        document.update(extra)
    return WikidataAPIBatch(
        requested_ids=tuple(
            requested if requested is not None else document["entities"]
        ),
        purpose=purpose,
        payload=json.dumps(document, ensure_ascii=False).encode(),
    )


def fixture(*candidates, type_items=None):
    if not candidates:
        candidates = (item(A, types=[ORGANIZATION_QID]),)
    if type_items is None:
        type_items = [item(ORGANIZATION_QID, parents=[], names=False)]
    result = [batch(candidates)]
    if type_items:
        result.append(batch(type_items, purpose="type"))
    return result


def parse(*candidates, type_items=None, limits=None):
    return parse_fictional_wikidata_api_batches(
        fixture(*candidates, type_items=type_items),
        limits=limits or WikidataAPILimits(),
    )


def test_complete_multilingual_names_rank_and_revision_provenance_are_preserved():
    candidate = item(A, types=[ORGANIZATION_QID])
    candidate["labels"].update(
        ar={"language": "ar", "value": "شركة الأرز الخيالية"},
        ru={"language": "ru", "value": "Вымышленная компания Кедр"},
        zh={"language": "zh", "value": "虚构雪松公司"},
    )
    candidate["aliases"]["ar"] = [{"language": "ar", "value": "  الأرز الخيالي  "}]
    selected = parse(candidate)
    assert len(selected.organizations) == 1
    organization = selected.organizations[0]
    assert len(organization.record.aliases) == 6
    assert {value.language for value in organization.record.aliases} == {
        "en",
        "ar",
        "ru",
        "zh",
    }
    assert any(
        value.value == "  الأرز الخيالي  " and value.field == "aliases.ar[].value"
        for value in organization.record.aliases
    )
    assert organization.requested_ids == (A,)
    assert {node.qid for node in organization.classification} == {A, ORGANIZATION_QID}
    assert all(
        node.revision_id == 123 and node.modified == "2026-01-01T00:00:00Z"
        for node in organization.classification
    )
    assert all(
        len(digest) == 64
        for node in organization.classification
        for digest in node.response_sha256
    )
    assert selected.exclusion_counts == ()
    assert selected.contract_verified is False
    assert selected.live_authorized is False
    assert selected.source_role == "supplemental_unlabelled"


def test_discarded_fields_and_rejected_person_names_do_not_escape_selection():
    organization = item(A, types=[ORGANIZATION_QID])
    organization["descriptions"] = {
        "en": {"language": "en", "value": "UNWANTED DESCRIPTION"}
    }
    organization["claims"]["P999999"] = [{"unrelated": "UNWANTED FIELD"}]
    person = item(B, types=[HUMAN_QID])
    person["labels"]["en"]["value"] = "FICTIONAL PERSON MUST NOT BE RETAINED"
    result = parse(organization, person)
    serialized = json.dumps(asdict(result))
    assert "UNWANTED" not in serialized
    assert "FICTIONAL PERSON" not in serialized
    assert B not in serialized
    assert dict(result.exclusion_counts) == {"human": 1}
    assert result.input_candidates == 2


def test_direct_organization_rule_does_not_expand_to_organization_subclasses():
    result = parse(
        item(A, types=[B]),
        type_items=[item(B, parents=[ORGANIZATION_QID], names=False)],
    )
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"not_direct_organization": 1}


@pytest.mark.parametrize("human_path", [[HUMAN_QID], [B], [B, C]])
def test_direct_and_multihop_humans_are_excluded_across_multiple_types(human_path):
    first = human_path[0]
    types = [ORGANIZATION_QID, first]
    graph = [item(ORGANIZATION_QID, parents=[], names=False)]
    if first != HUMAN_QID:
        chain = human_path + [HUMAN_QID]
        graph.extend(
            item(start, parents=[end], names=False)
            for start, end in zip(chain, chain[1:])
        )
    result = parse(item(A, types=types), type_items=graph)
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"human": 1}


def test_complete_type_cycles_terminate_and_every_branch_is_checked():
    graph = [
        item(ORGANIZATION_QID, parents=[B, D], names=False),
        item(B, parents=[C], names=False),
        item(C, parents=[B], names=False),
        item(D, parents=[], names=False),
    ]
    assert len(parse(type_items=graph).organizations) == 1
    graph[-1]["claims"]["P279"] = [claim("P279", HUMAN_QID)]
    assert dict(parse(type_items=graph).exclusion_counts) == {"human": 1}


def test_an_individual_misused_as_a_class_is_unresolved_and_not_retained():
    candidate = item(A, types=[ORGANIZATION_QID, B])
    graph = [
        item(ORGANIZATION_QID, parents=[], names=False),
        item(B, types=[HUMAN_QID], parents=[], names=False),
    ]
    result = parse(candidate, type_items=graph)
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}
    assert B not in json.dumps(asdict(result))


@pytest.mark.parametrize("redirects", [[(C, HUMAN_QID)], [(C, D), (D, HUMAN_QID)]])
def test_redirected_individual_misused_as_a_class_is_unresolved(redirects):
    candidate = item(A, types=[ORGANIZATION_QID, B])
    bodies = fixture(
        candidate,
        type_items=[
            item(ORGANIZATION_QID, parents=[], names=False),
            item(B, types=[C], parents=[], names=False),
        ],
    )
    bodies.append(
        batch(
            [item(HUMAN_QID, names=False)],
            purpose="type",
            requested=[C],
            redirects=redirects,
        )
    )
    result = parse_fictional_wikidata_api_batches(bodies)
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}
    assert B not in json.dumps(asdict(result))


@pytest.mark.parametrize("kind", ["somevalue", "novalue"])
@pytest.mark.parametrize("rank", ["normal", "preferred"])
def test_unknown_best_rank_class_instance_type_is_unresolved(kind, rank):
    candidate = item(A, types=[ORGANIZATION_QID, B])
    class_item = item(B, types=[C], parents=[], names=False)
    class_item["claims"]["P31"].append(claim("P31", kind=kind, rank=rank))
    result = parse(
        candidate,
        type_items=[item(ORGANIZATION_QID, parents=[], names=False), class_item],
    )
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}


def test_accepted_class_instance_evidence_and_used_redirects_are_preserved():
    bodies = fixture(
        item(A, types=[ORGANIZATION_QID, B]),
        type_items=[
            item(ORGANIZATION_QID, parents=[], names=False),
            item(B, types=[C], parents=[ORGANIZATION_QID], names=False),
        ],
    )
    bodies.append(
        batch([item(D, names=False)], purpose="type", requested=[C], redirects=[(C, D)])
    )
    result = parse_fictional_wikidata_api_batches(bodies)
    assert len(result.organizations) == 1
    organization = result.organizations[0]
    assert organization.redirect_edges == ((C, D),)
    class_evidence = next(node for node in organization.classification if node.qid == B)
    assert {
        (statement.property_id, statement.target_qid)
        for statement in class_evidence.statements
    } == {("P31", C), ("P279", ORGANIZATION_QID)}
    assert class_evidence.response_sha256 == (result.response_sha256[1],)


@pytest.mark.parametrize(
    "missing_kind", ["unprovided", "explicitly-missing", "unknown-value", "no-value"]
)
def test_unresolved_type_frontier_never_counts_as_human_exclusion_proof(missing_kind):
    graph = [item(ORGANIZATION_QID, parents=[B], names=False)]
    if missing_kind == "explicitly-missing":
        graph.append({"id": B, "missing": ""})
    elif missing_kind in {"unknown-value", "no-value"}:
        graph[0]["claims"]["P279"] = [
            claim(
                "P279",
                kind="somevalue" if missing_kind == "unknown-value" else "novalue",
            )
        ]
    result = parse(type_items=graph)
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}


def test_type_depth_and_global_node_bounds_leave_unfinished_paths_unresolved():
    graph = [
        item(ORGANIZATION_QID, parents=[B], names=False),
        item(B, parents=[HUMAN_QID], names=False),
    ]
    result = parse(type_items=graph, limits=WikidataAPILimits(max_type_depth=1))
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}
    result = parse(type_items=graph[:1], limits=WikidataAPILimits(max_type_nodes=1))
    assert result.examined_type_nodes == 1
    assert dict(result.exclusion_counts) == {"unresolved_type": 1}


def test_preferred_ranks_override_normal_and_deprecated_values_in_fixture_contract():
    candidate = item(A, types=[])
    candidate["claims"]["P31"] = [
        claim("P31", ORGANIZATION_QID, rank="preferred"),
        claim("P31", B),
        claim("P31", C, rank="deprecated"),
    ]
    # B and C need no graph expansion: they are not in the best-rank view.
    assert len(parse(candidate).organizations) == 1
    candidate["claims"]["P31"][0]["rank"] = "deprecated"
    assert dict(parse(candidate).exclusion_counts) == {"not_direct_organization": 1}


@pytest.mark.parametrize("property_id", ["P31", "P279"])
def test_preferred_unknown_value_is_not_hidden_by_normal_known_value(property_id):
    candidate = item(A, types=[ORGANIZATION_QID])
    graph = [
        item(ORGANIZATION_QID, parents=[B], names=False),
        item(B, parents=[], names=False),
    ]
    target = candidate if property_id == "P31" else graph[0]
    target["claims"][property_id].append(
        claim(property_id, rank="preferred", kind="somevalue")
    )
    assert dict(parse(candidate, type_items=graph).exclusion_counts) == {
        "unresolved_type": 1
    }


def test_redirects_collapse_groups_without_inventing_cross_source_identity():
    candidate = item(B, types=[ORGANIZATION_QID])
    bodies = [batch([candidate], requested=[A, B], redirects=[(A, B)]), *fixture()[1:]]
    result = parse_fictional_wikidata_api_batches(bodies)
    assert len(result.organizations) == 1
    assert result.organizations[0].requested_ids == (A, B)
    assert result.organizations[0].redirect_edges == ((A, B),)
    assert result.organizations[0].record.provider_id == B
    assert result.input_candidates == 2


def test_redirect_target_type_is_checked_and_missing_ids_are_not_absence_labels():
    human = item(B, types=[HUMAN_QID])
    result = parse_fictional_wikidata_api_batches(
        [batch([human], requested=[A], redirects=[(A, B)])]
    )
    assert result.organizations == ()
    assert dict(result.exclusion_counts) == {"human": 1}
    missing = parse({"id": A, "missing": ""})
    assert dict(missing.exclusion_counts) == {"missing": 1}
    assert A not in json.dumps(asdict(missing))


def test_type_redirects_are_resolved_before_human_ancestry_acceptance():
    candidate = item(A, types=[ORGANIZATION_QID, B])
    bodies = [
        batch([candidate]),
        *fixture()[1:],
        batch(
            [item(HUMAN_QID, names=False)],
            purpose="type",
            requested=[B],
            redirects=[(B, HUMAN_QID)],
        ),
    ]
    assert dict(parse_fictional_wikidata_api_batches(bodies).exclusion_counts) == {
        "human": 1
    }


@pytest.mark.parametrize(
    "redirects",
    [[(A, A)], [(A, B), (B, A)], [(A, B), (B, C), (C, D)], [(C, B)], [(A, B), (A, C)]],
)
def test_cyclic_excessive_unrequested_and_duplicate_redirects_fail(redirects):
    with pytest.raises(SourceValidationError):
        parse_fictional_wikidata_api_batches(
            [batch([item(B)], requested=[A], redirects=redirects)]
        )


def test_an_entity_snapshot_cannot_later_be_reinterpreted_as_a_redirect():
    bodies = fixture()
    bodies.append(
        batch([item(B, names=False)], purpose="type", requested=[A], redirects=[(A, B)])
    )
    with pytest.raises(SourceValidationError, match="both a redirect"):
        parse_fictional_wikidata_api_batches(bodies)


@pytest.mark.parametrize("change", ["revision", "modified", "type", "names", "missing"])
def test_shared_items_cannot_use_conflicting_snapshots(change):
    candidate = item(A, types=[ORGANIZATION_QID])
    changed = deepcopy(candidate)
    if change == "revision":
        changed["lastrevid"] += 1
    elif change == "modified":
        changed["modified"] = "2026-01-02T00:00:00Z"
    elif change == "type":
        changed["claims"]["P31"] = [claim("P31", HUMAN_QID)]
    elif change == "names":
        changed["labels"]["en"]["value"] = "Changed fictional name"
    else:
        changed = {"id": A, "missing": ""}
    with pytest.raises(SourceValidationError, match="Conflicting"):
        parse_fictional_wikidata_api_batches(
            [*fixture(candidate), batch([changed], purpose="type")]
        )


def test_a_type_only_copy_does_not_overwrite_complete_candidate_names():
    candidate = item(A, types=[ORGANIZATION_QID])
    type_copy = item(A, types=[ORGANIZATION_QID], names=False)
    first = parse_fictional_wikidata_api_batches(
        [*fixture(candidate), batch([type_copy], purpose="type")]
    )
    second = parse_fictional_wikidata_api_batches(
        [batch([type_copy], purpose="type"), *fixture(candidate)]
    )
    assert first.organizations[0].record == second.organizations[0].record
    assert len(first.organizations[0].record.aliases) == 2


@pytest.mark.parametrize(
    "field", ["labels", "aliases", "claims", "lastrevid", "modified"]
)
def test_missing_complete_fields_or_revision_metadata_fail(field):
    candidate = item(A, types=[ORGANIZATION_QID])
    del candidate[field]
    with pytest.raises(SourceValidationError):
        parse(candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lastrevid", True),
        ("lastrevid", 0),
        ("lastrevid", "123"),
        ("modified", "2026-02-31T00:00:00Z"),
        ("modified", "2026-01-01"),
        ("type", "property"),
    ],
)
def test_invalid_revision_or_entity_types_fail(field, value):
    candidate = item(A, types=[ORGANIZATION_QID])
    candidate[field] = value
    with pytest.raises(SourceValidationError):
        parse(candidate)


@pytest.mark.parametrize(
    "mutation",
    [
        "language",
        "blank-labels",
        "bad-alias-shape",
        "oversize-name",
        "wrong-numeric-id",
        "unknown-rank",
        "nonvalue-with-value",
    ],
)
def test_malformed_names_or_classification_are_never_silently_repaired(mutation):
    candidate = item(A, types=[ORGANIZATION_QID])
    if mutation == "language":
        candidate["labels"]["en"]["language"] = "ar"
    elif mutation == "blank-labels":
        candidate["labels"] = {}
    elif mutation == "bad-alias-shape":
        candidate["aliases"]["en"] = {}
    elif mutation == "oversize-name":
        candidate["labels"]["en"]["value"] = "x" * 1025
    elif mutation == "wrong-numeric-id":
        candidate["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"][
            "numeric-id"
        ] = 5
    elif mutation == "unknown-rank":
        candidate["claims"]["P31"][0]["rank"] = "best"
    else:
        candidate["claims"]["P31"][0]["mainsnak"]["snaktype"] = "novalue"
    with pytest.raises(SourceValidationError):
        parse(candidate)


def test_group_and_alias_caps_do_not_hide_later_invalid_evidence_or_truncate_names():
    second = item(B, types=[ORGANIZATION_QID])
    result = parse(
        item(A, types=[ORGANIZATION_QID]),
        second,
        limits=WikidataAPILimits(max_groups=1),
    )
    assert len(result.organizations) == 1
    assert result.eligible_organization_groups == 2
    assert dict(result.exclusion_counts) == {"group_limit": 1}
    second["aliases"]["en"] = [
        {"language": "en", "value": f"Fictional alias {number}"}
        for number in range(128)
    ]
    with pytest.raises(SourceValidationError, match="alias limit"):
        parse(
            item(A, types=[ORGANIZATION_QID]),
            second,
            limits=WikidataAPILimits(max_groups=1),
        )
    with pytest.raises(SourceValidationError, match="alias limit"):
        parse(limits=WikidataAPILimits(max_aliases=1))


def test_record_selection_does_not_depend_on_batch_or_language_alias_order():
    first = item(A, types=[ORGANIZATION_QID])
    second = item(B, types=[ORGANIZATION_QID])
    second["aliases"]["en"].append(
        {"language": "en", "value": "Another fictional alias"}
    )
    original = parse(first, second)
    second["aliases"]["en"].reverse()
    reordered = parse_fictional_wikidata_api_batches(
        list(reversed(fixture(second, first)))
    )
    assert [value.record for value in original.organizations] == [
        value.record for value in reordered.organizations
    ]


def test_an_empty_alias_array_does_not_hide_an_invalid_language_key():
    candidate = item(A, types=[ORGANIZATION_QID])
    candidate["aliases"]["invalid_tag"] = []
    with pytest.raises(SourceValidationError, match="language tag"):
        parse(candidate)


@pytest.mark.parametrize(
    "extra",
    [
        {"warnings": {}},
        {"continue": "next"},
        {"error": {"code": "limit"}},
        {"success": True},
        {"success": 0},
    ],
)
def test_partial_warning_error_or_ambiguous_success_responses_fail(extra):
    with pytest.raises(SourceValidationError):
        parse_fictional_wikidata_api_batches([batch([item(A)], extra=extra)])


@pytest.mark.parametrize(
    "payload",
    [
        b'{"entities":{},"entities":{},"success":1}',
        b'{"entities":{},"success":NaN}',
        b'{"entities":{},"success":1e999}',
        b'{"entities":',
        b"\xff",
        b"[]",
    ],
)
def test_ambiguous_malformed_and_nonfinite_json_fails(payload):
    with pytest.raises(SourceValidationError):
        parse_fictional_wikidata_api_batches(
            [WikidataAPIBatch((A,), "candidate", payload)]
        )


def test_unrequested_and_missing_response_ids_fail():
    for requested in [(B,), (A, B)]:
        with pytest.raises(SourceValidationError):
            parse_fictional_wikidata_api_batches(
                [batch([item(A)], requested=requested)]
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_candidates", 501),
        ("max_groups", 201),
        ("max_type_nodes", 801),
        ("max_type_depth", 21),
        ("max_batch_ids", 11),
        ("max_responses", 251),
        ("max_decoded_response_bytes", 4_000_001),
        ("max_decoded_total_bytes", 15_000_001),
        ("max_redirect_hops", 3),
        ("max_type_statements", 257),
        ("max_aliases", 129),
        ("max_groups", True),
        ("max_groups", 0),
    ],
)
def test_limits_can_only_be_reduced(field, value):
    with pytest.raises(SourceValidationError):
        WikidataAPILimits(**{field: value})


def test_response_total_bytes_request_candidate_and_type_caps_are_enforced():
    bodies = fixture()
    cases = [
        WikidataAPILimits(max_decoded_response_bytes=10),
        WikidataAPILimits(
            max_decoded_total_bytes=sum(len(value.payload) for value in bodies) - 1
        ),
        WikidataAPILimits(max_responses=1),
    ]
    for limits in cases:
        with pytest.raises(SourceValidationError):
            parse_fictional_wikidata_api_batches(bodies, limits=limits)
    with pytest.raises(SourceValidationError):
        parse(item(A), item(B), limits=WikidataAPILimits(max_batch_ids=1))
    with pytest.raises(SourceValidationError):
        parse_fictional_wikidata_api_batches(
            [batch([item(A)]), batch([item(B)])],
            limits=WikidataAPILimits(max_candidates=1),
        )
    with pytest.raises(SourceValidationError):
        parse(
            type_items=[item(ORGANIZATION_QID, names=False), item(B, names=False)],
            limits=WikidataAPILimits(max_type_nodes=1),
        )
    candidate = item(A, types=[ORGANIZATION_QID, B])
    with pytest.raises(SourceValidationError):
        parse(candidate, limits=WikidataAPILimits(max_type_statements=1))


def test_no_candidate_input_and_replayed_request_ids_fail():
    for values in [[], fixture()[1:], [fixture()[0], fixture()[0]]]:
        with pytest.raises(SourceValidationError):
            parse_fictional_wikidata_api_batches(values)


def test_offline_adapter_does_not_authorize_an_action_api_route():
    with pytest.raises(SourceValidationError):
        validate_source_url(
            "wikidata_orgs",
            "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q43229&format=json",
        )
    with pytest.raises(TypeError):
        replace(parse(), live_authorized=True)
