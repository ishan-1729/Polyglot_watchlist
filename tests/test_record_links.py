"""Fictional evidence exercises link closure without real review decisions."""

from dataclasses import asdict, replace

import pytest

from watchlist.ingest.link_records import (
    LinkCandidate,
    LinkDecision,
    LinkName,
    LinkRecord,
    LinkReviewAttestation,
    READINESS_NORMALIZATION_VERSION,
    READINESS_NOMINATION_VERSION,
    READINESS_UNICODE_VERSION,
    ReviewRegistry,
    build_leakage_families,
    build_record_groups,
    nominate_links,
    nominate_readiness_links,
    readiness_name_key,
    validate_link_decisions,
    validate_readiness_links,
)


RELEASE = "a" * 64


def record(
    name,
    *,
    source="fictional",
    provider=None,
    snapshot="snapshot-1",
    alias=None,
    events=(),
    referents=(),
):
    return LinkRecord(
        name,
        (source, provider or name),
        snapshot,
        (LinkName("name-" + name, alias or "Invented " + name),),
        referents,
        events,
    )


def candidate(left, right, method="manual_evidence"):
    return LinkCandidate(
        "candidate-" + left + right, left, right, method, (left, right), RELEASE
    )


def decision(left, right, relation):
    return LinkDecision(
        "decision-" + left + right,
        left,
        right,
        relation,
        "fixture-reviewer",
        "adjudication-" + left + right,
        ("support-" + left + right,),
        RELEASE,
    )


def registry(decisions):
    return ReviewRegistry(
        ("fixture-reviewer",),
        tuple(sorted({ref for item in decisions for ref in item.evidence_refs})),
        tuple(item.adjudication_ref for item in decisions),
        tuple(
            LinkReviewAttestation(
                item.adjudication_ref,
                item.left,
                item.right,
                item.relation,
                item.actor_id,
                item.candidate_release_hash,
                item.evidence_refs,
            )
            for item in decisions
        ),
    )


def build(records, candidates, decisions=(), *, mode="leakage"):
    function = build_leakage_families if mode == "leakage" else build_record_groups
    return function(
        records,
        candidates,
        decisions,
        candidate_release_hash=RELEASE,
        registry=registry(decisions),
    )


def test_equal_provider_ids_from_different_sources_never_link_automatically():
    records = [
        record("A", source="source-a", provider="17"),
        record("B", source="source-b", provider="17"),
    ]
    assert nominate_links(records, candidate_release_hash=RELEASE) == ()
    result = build(records, ())
    assert [item.members for item in result.groups] == [("A",), ("B",)]
    assert not result.accepted_reviewed_corpus


def test_source_key_encoding_is_not_ambiguous_concatenation():
    records = [
        record("A", source="a:b", provider="c"),
        record("B", source="a", provider="b:c"),
    ]
    assert nominate_links(records, candidate_release_hash=RELEASE) == ()


def test_exact_names_nominate_but_quarantine_without_equivalence():
    records = [
        record("A", alias="Fictional Silver Lantern"),
        record("B", alias="Fictional Silver Lantern"),
    ]
    candidates = nominate_links(records, candidate_release_hash=RELEASE)
    assert len(candidates) == 1
    assert candidates[0].method == "exact_name"
    result = build(records, candidates)
    assert [item.members for item in result.groups] == [("A",), ("B",)]
    assert all(item.quarantined for item in result.groups)
    assert result.quarantine[0].members == ("A", "B")


def test_qualified_referents_and_snapshot_continuity_are_only_candidates():
    records = [
        record("A", provider="17"),
        record("B", provider="17", snapshot="snapshot-2"),
        record("C", referents=(("fictional", "17"),)),
    ]
    candidates = nominate_links(records, candidate_release_hash=RELEASE)
    assert {(item.left, item.right, item.method) for item in candidates} == {
        ("A", "B", "source_key_continuity"),
        ("A", "C", "source_referent"),
        ("B", "C", "source_referent"),
    }
    assert len(build(records, candidates).groups) == 3


@pytest.mark.parametrize(
    "relation,record_count,family_count",
    [
        ("record_equivalent", 1, 1),
        ("same_entity", 2, 1),
        ("dependent_example", 2, 1),
        ("related_entity", 2, 2),
        ("distinct_entity", 2, 2),
        ("dismissed_candidate", 2, 2),
    ],
)
def test_record_identity_dependence_and_dismissal_remain_separate(
    relation, record_count, family_count
):
    records = [record("A"), record("B")]
    candidates = [candidate("A", "B")]
    decisions = [decision("A", "B", relation)]
    assert (
        len(build(records, candidates, decisions, mode="record").groups) == record_count
    )
    result = build(records, candidates, decisions)
    assert len(result.groups) == family_count
    assert result.quarantine == ()


def test_transitive_distinct_conflict_quarantines_dependence_component():
    records = [record(letter) for letter in "ABCD"]
    pairs = [
        ("A", "B", "same_entity"),
        ("B", "C", "record_equivalent"),
        ("A", "C", "distinct_entity"),
        ("C", "D", "dependent_example"),
    ]
    candidates = [candidate(left, right) for left, right, _ in pairs]
    decisions = [decision(*pair) for pair in pairs]
    result = build(records, candidates, decisions)
    assert result.quarantine[0].members == ("A", "B", "C", "D")
    assert result.quarantine[0].reasons == ("transitive_identity_conflict",)
    assert all(group.quarantined for group in result.groups)


def test_uncertainty_and_exposure_propagate_across_all_affected_components():
    records = [
        record("A", events=("inspected-old-version",)),
        record("B"),
        record("C"),
        record("D"),
    ]
    candidates = [candidate("A", "B"), candidate("B", "C"), candidate("C", "D")]
    decisions = [
        decision("A", "B", "record_equivalent"),
        decision("C", "D", "dependent_example"),
    ]
    result = build(records, candidates, decisions)
    assert result.quarantine[0].members == ("A", "B", "C", "D")
    assert all(
        group.exposure_events == ("inspected-old-version",) for group in result.groups
    )
    assert [group.members for group in result.groups] == [("A", "B"), ("C", "D")]


def test_related_entities_may_be_distinct_without_identity_conflict():
    records = [record(letter) for letter in "ABC"]
    pairs = [
        ("A", "B", "dependent_example"),
        ("B", "C", "dependent_example"),
        ("A", "C", "distinct_entity"),
    ]
    result = build(
        records,
        [candidate(a, b) for a, b, _ in pairs],
        [decision(*pair) for pair in pairs],
    )
    assert result.groups[0].members == ("A", "B", "C")
    assert not result.quarantine


def test_reordered_input_preserves_grouping_and_exposure_hash():
    records = [record("A", events=("development",)), record("B"), record("C")]
    candidates = [candidate("A", "B"), candidate("B", "C")]
    decisions = [
        decision("A", "B", "record_equivalent"),
        decision("B", "C", "dependent_example"),
    ]
    assert build(records, candidates, decisions) == build(
        records[::-1], candidates[::-1], decisions[::-1]
    )


@pytest.mark.parametrize(
    "change",
    [
        {"candidate_release_hash": "b" * 64},
        {"actor_id": "unregistered"},
        {"adjudication_ref": "missing"},
        {"evidence_refs": ("unknown-support",)},
        {"relation": "distinct_entity"},
    ],
)
def test_decision_cannot_reuse_unrelated_authority_or_release(change):
    records = [record("A"), record("B")]
    original = decision("A", "B", "record_equivalent")
    with pytest.raises(ValueError):
        validate_link_decisions(
            records,
            [candidate("A", "B")],
            [replace(original, **change)],
            candidate_release_hash=RELEASE,
            registry=registry([original]),
        )


def test_review_authority_cannot_be_just_the_matching_name_evidence():
    records = [record("A"), record("B")]
    item = replace(decision("A", "B", "same_entity"), evidence_refs=("name-A",))
    with pytest.raises(ValueError, match="separate"):
        build(records, [candidate("A", "B")], [item])


def test_ai_origin_cannot_be_promoted_to_reviewed_link():
    with pytest.raises(ValueError, match="human"):
        replace(decision("A", "B", "same_entity"), origin="ai")


def test_duplicate_active_decisions_cannot_silently_supersede():
    item = decision("A", "B", "same_entity")
    with pytest.raises(ValueError, match="multiple active"):
        validate_link_decisions(
            [record("A"), record("B")],
            [candidate("A", "B")],
            [item, replace(item, decision_id="second")],
            candidate_release_hash=RELEASE,
            registry=registry([item]),
        )


@pytest.mark.parametrize(
    "records",
    [
        [record("A"), record("A")],
        [record("A", provider="17"), record("B", provider="17")],
        [
            record("A"),
            replace(record("B"), aliases=(LinkName("name-A", "Other fictional name"),)),
        ],
    ],
)
def test_duplicate_observation_or_evidence_is_rejected(records):
    with pytest.raises(ValueError, match="duplicate|unique"):
        nominate_links(records, candidate_release_hash=RELEASE)


def test_unknown_nomination_endpoint_and_stale_nomination_reject():
    for item in (
        candidate("A", "C"),
        replace(candidate("A", "B"), candidate_release_hash="b" * 64),
    ):
        with pytest.raises(ValueError):
            build([record("A"), record("B")], [item])


def test_unregistered_adjudication_id_cannot_be_declared_without_scope():
    with pytest.raises(ValueError, match="scoped attestation"):
        ReviewRegistry(("actor",), ("evidence",), ("adjudication",))


def test_readiness_normalized_key_is_conservative_complete_and_versioned():
    assert readiness_name_key("ＦＩＣＴＩＯＮＡＬ\t  Straße\u00a0LAB") == (
        "fictional strasse lab"
    )
    assert readiness_name_key("Fictional Café") == readiness_name_key(
        "FICTIONAL Cafe\u0301"
    )
    assert readiness_name_key("\u01f0") == "\u01f0"  # NFKC again after casefold.
    assert readiness_name_key("Fictional Café") != readiness_name_key("Fictional Cafe")
    assert readiness_name_key("Fictional-Lab") != readiness_name_key("Fictional Lab")
    assert readiness_name_key("Αlpha") != readiness_name_key("Alpha")
    assert readiness_name_key("x" * 600 + "A") != readiness_name_key("x" * 600 + "B")
    assert READINESS_NORMALIZATION_VERSION == "nfkc-casefold-nfkc-whitespace-v1"
    assert READINESS_NOMINATION_VERSION == "readiness-name-equality-v1"


def test_readiness_all_exact_and_normalized_witnesses_share_one_pair():
    first = replace(
        record("A"),
        aliases=(
            LinkName("a1", "Fictional Orion"),
            LinkName("a2", "Fictional Orion"),
            LinkName("a3", "Fictional Nebula"),
        ),
    )
    second = replace(
        record("B"),
        aliases=(
            LinkName("b1", "Fictional Orion"),
            LinkName("b2", "FICTIONAL   ORION"),
            LinkName("b3", "fictional nebula"),
        ),
    )
    nominations = nominate_readiness_links(
        [second, first], preparation_input_sha256=RELEASE
    )
    assert len(nominations) == 1
    nomination = nominations[0]
    assert (nomination.left, nomination.right) == ("A", "B")
    assert nomination.methods == ("exact_name", "normalized_name")
    assert nomination.evidence_refs == ("a1", "a2", "a3", "b1", "b2", "b3")
    assert nomination.unicode_version == READINESS_UNICODE_VERSION
    witnesses = {
        (item.method, item.left_evidence_id, item.right_evidence_id)
        for item in nomination.witnesses
    }
    assert witnesses == {
        ("exact_name", "a1", "b1"),
        ("exact_name", "a2", "b1"),
        ("normalized_name", "a1", "b1"),
        ("normalized_name", "a1", "b2"),
        ("normalized_name", "a2", "b1"),
        ("normalized_name", "a2", "b2"),
        ("normalized_name", "a3", "b3"),
    }
    reversed_records = [
        replace(first, aliases=first.aliases[::-1]),
        replace(second, aliases=second.aliases[::-1]),
    ]
    assert nominations == nominate_readiness_links(
        reversed_records, preparation_input_sha256=RELEASE
    )
    validate_readiness_links(
        reversed_records, nominations, preparation_input_sha256=RELEASE
    )


def test_readiness_normalized_collision_does_not_create_identity_or_review():
    records = [
        record("A", alias="ＦＩＣＴＩＯＮＡＬ Lab"),
        record("B", alias="fictional lab"),
    ]
    nominations = nominate_readiness_links(records, preparation_input_sha256=RELEASE)
    assert len(nominations) == 1
    assert nominations[0].methods == ("normalized_name",)
    serialized = asdict(nominations[0])
    assert serialized["preparation_input_sha256"] == RELEASE
    assert not {"candidate_release_hash", "relation", "origin", "actor_id"} & (
        serialized.keys()
    )
    assert nominate_links(records, candidate_release_hash=RELEASE) == ()
    with pytest.raises(ValueError, match="invalid nomination object"):
        build_record_groups(records, nominations, candidate_release_hash=RELEASE)
    with pytest.raises(ValueError, match="preparation nominations"):
        validate_readiness_links(
            records, [candidate("A", "B")], preparation_input_sha256=RELEASE
        )


def test_readiness_namespace_distinction_and_unambiguous_pair_ids():
    records = [
        record("A", source="source-a", provider="17", alias="Fictional Shared"),
        record("B", source="source-b", provider="17", alias="Fictional Shared"),
        record("C", source="a:b", provider="c"),
        record("D", source="a", provider="b:c"),
    ]
    nominations = nominate_readiness_links(records, preparation_input_sha256=RELEASE)
    assert [(item.left, item.right) for item in nominations] == [("A", "B")]
    assert nominations[0].methods == ("exact_name", "normalized_name")
    assert len({item.source_record_key for item in records}) == 4
    # Delimiter-shaped IDs remain separately encoded in the stable pair digest.
    pairs = [
        [
            record("a:b", alias="Fictional Shared"),
            record("c", alias="Fictional Shared"),
        ],
        [
            record("a", alias="Fictional Shared"),
            record("b:c", alias="Fictional Shared"),
        ],
    ]
    ids = [
        nominate_readiness_links(pair, preparation_input_sha256=RELEASE)[
            0
        ].nomination_id
        for pair in pairs
    ]
    assert len(set(ids)) == 2


def test_readiness_cross_binding_changed_originals_and_missing_witnesses_reject():
    records = [
        record("A", alias="Fictional Orion"),
        record("B", alias="FICTIONAL ORION"),
    ]
    nominations = nominate_readiness_links(records, preparation_input_sha256=RELEASE)
    with pytest.raises(ValueError, match="another preparation"):
        validate_readiness_links(
            records, nominations, preparation_input_sha256="b" * 64
        )
    rebound = nominate_readiness_links(records, preparation_input_sha256="b" * 64)
    assert rebound[0].nomination_id != nominations[0].nomination_id
    changed = [record("A", alias="fictional orion"), records[1]]
    assert (
        nominations[0].methods
        == nominate_readiness_links(changed, preparation_input_sha256=RELEASE)[
            0
        ].methods
    )
    with pytest.raises(ValueError, match="complete source evidence"):
        validate_readiness_links(changed, nominations, preparation_input_sha256=RELEASE)
    for invalid in ((), nominations + nominations):
        with pytest.raises(ValueError, match="complete source evidence"):
            validate_readiness_links(records, invalid, preparation_input_sha256=RELEASE)
    with pytest.raises(ValueError, match="content/hash mismatch"):
        replace(nominations[0], nomination_id="invented-id")
    with pytest.raises(ValueError, match="unique and sorted"):
        replace(nominations[0], witnesses=nominations[0].witnesses * 2)
    with pytest.raises(ValueError, match="version"):
        replace(nominations[0], normalization_version="unapproved-normalizer")


def test_readiness_exact_subset_cannot_be_removed_and_originals_are_bound():
    records = [
        record("A", alias="Fictional Shared"),
        record("B", alias="Fictional Shared"),
    ]
    nomination = nominate_readiness_links(records, preparation_input_sha256=RELEASE)[0]
    exact = tuple(item for item in nomination.witnesses if item.method == "exact_name")
    with pytest.raises(ValueError, match="normalized subset"):
        replace(nomination, witnesses=exact)
    with pytest.raises(ValueError, match="original hashes"):
        replace(exact[0], left_original_sha256="0" * 64)
    with pytest.raises(ValueError, match="witness limit"):
        validate_readiness_links(
            records,
            (nomination,),
            preparation_input_sha256=RELEASE,
            max_witnesses=1,
        )


def test_readiness_reordered_ties_keep_complete_unique_unordered_pairs():
    records = [
        record("A", alias="Fictional Shared"),
        record("B", alias="fictional shared"),
        record("C", alias="Fictional Shared"),
        record("D", alias="Other Fictional"),
    ]
    nominations = nominate_readiness_links(records, preparation_input_sha256=RELEASE)
    assert [(item.left, item.right) for item in nominations] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    assert [item.methods for item in nominations] == [
        ("normalized_name",),
        ("exact_name", "normalized_name"),
        ("normalized_name",),
    ]
    assert (
        nominate_readiness_links(
            records[2:] + records[:2], preparation_input_sha256=RELEASE
        )
        == nominations
    )
    validate_readiness_links(
        records[::-1], nominations[::-1], preparation_input_sha256=RELEASE
    )


@pytest.mark.parametrize(
    "limits,message",
    [
        ({"max_records": 1}, "record limit"),
        ({"max_names": 1}, "name limit"),
        ({"max_pairs": 0}, "pair limit"),
        ({"max_witnesses": 1}, "witness limit"),
        ({"max_name_characters": 2}, "character limit"),
        ({"max_total_name_characters": 20}, "character limit"),
        ({"max_names": True}, "finite nonnegative integers"),
        ({"max_pairs": -1}, "finite nonnegative integers"),
    ],
)
def test_readiness_bounded_work_rejects_instead_of_truncating(limits, message):
    records = [
        record("A", alias="Fictional Shared"),
        record("B", alias="Fictional Shared"),
    ]
    with pytest.raises(ValueError, match=message):
        nominate_readiness_links(records, preparation_input_sha256=RELEASE, **limits)


def test_readiness_checkpoint_can_stop_mid_work_without_a_partial_return():
    calls = []

    def stop():
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("fictional resource stop")

    records = [record(f"observation-{index:03d}") for index in range(300)]
    with pytest.raises(RuntimeError, match="fictional resource stop"):
        nominate_readiness_links(
            records, preparation_input_sha256=RELEASE, checkpoint=stop
        )
    assert len(calls) == 2


def test_readiness_no_matches_and_same_record_aliases_make_no_pairs():
    first = replace(
        record("A"),
        aliases=(
            LinkName("a1", "Fictional Shared"),
            LinkName("a2", "Fictional Shared"),
        ),
    )
    assert nominate_readiness_links([first], preparation_input_sha256=RELEASE) == ()
    assert nominate_readiness_links([], preparation_input_sha256=RELEASE) == ()
    validate_readiness_links([], (), preparation_input_sha256=RELEASE)


def test_readiness_duplicate_source_observation_or_evidence_rejects():
    for records in (
        [record("A"), record("A")],
        [record("A", provider="17"), record("B", provider="17")],
        [
            record("A"),
            replace(record("B"), aliases=(LinkName("name-A", "Other fictional name"),)),
        ],
    ):
        with pytest.raises(ValueError, match="duplicate|unique"):
            nominate_readiness_links(records, preparation_input_sha256=RELEASE)
