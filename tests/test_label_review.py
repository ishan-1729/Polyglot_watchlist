"""Authored review fixtures are never counted as performed human review."""

from dataclasses import replace
import json
import stat

import pytest

from test_readiness_review import digest, fictional_c1_payloads, safe_guard

from watchlist import readiness_review
from watchlist.ingest.link_records import (
    LinkCandidate,
    LinkDecision,
    LinkName,
    LinkRecord,
    LinkReviewAttestation,
    ReviewRegistry,
    build_leakage_families,
)

from watchlist.label_review import (
    Adjudication,
    PairContext,
    ReviewActor,
    ReviewCase,
    ReviewEvidence,
    ReviewSubmission,
    assess_pair_use,
    export_review_packet,
    freeze_review_packet,
    load_review_packet,
    main,
    review_summary,
    validate_adjudications,
    validate_submissions,
)


RELEASE = "a" * 64


@pytest.fixture
def packet():
    evidence = (
        ReviewEvidence(
            "name-a",
            "A",
            ("fictional_a", "1"),
            "snapshot-a",
            "Lumen Orchard",
            "primary_name",
        ),
        ReviewEvidence(
            "name-b",
            "B",
            ("fictional_b", "2"),
            "snapshot-b",
            "Velvet Compass",
            "primary_name",
        ),
        ReviewEvidence(
            "identity-a",
            "A",
            ("fictional_a", "1"),
            "snapshot-a",
            "Authored fictional registration distinction",
            "fictional_registration",
            kind="identity_support",
        ),
    )
    case = ReviewCase(
        "case-1", "negative_candidate", ("A", "B"), evidence, ("fictional_latin",)
    )
    return freeze_review_packet(
        (case,),
        candidate_release_hash=RELEASE,
        sampling_rule="authored fictional adversarial case",
    )


@pytest.fixture
def actors():
    return (
        ReviewActor(
            "reviewer-1",
            "human",
            "fixture-authorization-1",
            ("fictional_latin",),
            ("review", "adjudicate"),
        ),
        ReviewActor(
            "reviewer-2", "human", "fixture-authorization-2", ("fictional_latin",)
        ),
        ReviewActor(
            "adjudicator",
            "human",
            "fixture-authorization-3",
            ("fictional_latin",),
            ("adjudicate",),
        ),
    )


def submission(packet, *, actor="reviewer-1", outcome="supported_distinct"):
    return ReviewSubmission(
        "submission-" + actor,
        packet.packet_hash,
        "case-1",
        actor,
        outcome,
        "Fictional supplied identity facts support this example",
        ("name-a", "name-b", "identity-a"),
        "2026-10-25T10:00:00+00:00",
    )


def adjudication(packet, submissions, *, outcome="supported_distinct"):
    return Adjudication(
        "adjudication-1",
        packet.packet_hash,
        "case-1",
        "adjudicator",
        tuple(item.submission_id for item in submissions),
        outcome,
        "Fictional explicit resolution after reviewing the complete packet",
        ("name-a", "name-b", "identity-a"),
        "2026-10-25T11:00:00+00:00",
    )


def context(packet, **changes):
    release = changes.get("candidate_release_hash", packet.candidate_release_hash)
    relation = changes.get("reviewed_relation", "distinct")
    records = []
    for observation in ("A", "B"):
        evidence = tuple(
            item
            for item in packet.cases[0].evidence
            if item.observation_id == observation and item.kind == "name"
        )
        records.append(
            LinkRecord(
                observation,
                evidence[0].source_record_key,
                evidence[0].snapshot_id,
                tuple(LinkName(item.evidence_id, item.value) for item in evidence),
            )
        )
    candidates = [
        LinkCandidate("candidate-AB", "A", "B", "manual_evidence", ("A", "B"), release)
    ]
    decisions = []

    def add_decision(left, right, link_relation):
        decisions.append(
            LinkDecision(
                "decision-" + left + right,
                left,
                right,
                link_relation,
                "fixture-link-reviewer",
                "link-adjudication-" + left + right,
                ("link-support-" + left + right,),
                release,
            )
        )

    if relation != "uncertain":
        add_decision(
            "A", "B", "same_entity" if relation == "same" else "distinct_entity"
        )
    requested_families = changes.get("family_ids", ("family-a", "family-b"))
    needs_dependence = (
        requested_families[0] == requested_families[1] and relation != "same"
    )
    if changes.get("quarantined") or needs_dependence:
        records.append(
            LinkRecord(
                "C",
                ("fictional_c", "3"),
                "snapshot-c",
                (LinkName("name-c", "Fictional Copper Kite"),),
            )
        )
        candidates.append(
            LinkCandidate(
                "candidate-AC", "A", "C", "manual_evidence", ("A", "C"), release
            )
        )
        if needs_dependence:
            candidates.append(
                LinkCandidate(
                    "candidate-BC", "B", "C", "manual_evidence", ("B", "C"), release
                )
            )
            add_decision("A", "C", "dependent_example")
            add_decision("B", "C", "dependent_example")
    registry = ReviewRegistry(
        ("fixture-link-reviewer",),
        tuple(ref for item in decisions for ref in item.evidence_refs),
        tuple(item.adjudication_ref for item in decisions),
        tuple(
            LinkReviewAttestation(
                item.adjudication_ref,
                item.left,
                item.right,
                item.relation,
                item.actor_id,
                release,
                item.evidence_refs,
            )
            for item in decisions
        ),
    )
    grouping = build_leakage_families(
        records,
        candidates,
        decisions,
        candidate_release_hash=release,
        registry=registry,
    )
    return PairContext(grouping, changes.get("observation_ids", ("A", "B")))


def test_blank_packet_export_is_private_immutable_and_contains_no_review(
    packet, tmp_path
):
    path = tmp_path / "preparation.json"
    export_review_packet(packet, path)
    assert load_review_packet(path) == packet
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text())
    assert "submissions" not in payload and "expected_answer" not in path.read_text()
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        export_review_packet(packet, path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".review-preparation-*"))


def test_export_refuses_symlink_target_without_changing_referenced_file(
    packet, tmp_path
):
    original = tmp_path / "historical.json"
    original.write_text("preserve history")
    target = tmp_path / "new.json"
    target.symlink_to(original)
    with pytest.raises(FileExistsError):
        export_review_packet(packet, target)
    assert original.read_text() == "preserve history"


@pytest.mark.parametrize(
    "mode,custody",
    [
        ("real_review", "development"),
        ("fictional_preparation", "final"),
        ("final_test", "development"),
    ],
)
def test_real_or_final_scope_cannot_be_frozen(packet, mode, custody):
    with pytest.raises(ValueError, match="fictional development"):
        freeze_review_packet(
            packet.cases,
            candidate_release_hash=RELEASE,
            sampling_rule="fixture",
            mode=mode,
            custody=custody,
        )


@pytest.mark.parametrize(
    "mutation",
    ["text", "hash", "field", "mode", "duplicate_json", "sequence", "schema_bool"],
)
def test_tampered_or_unsupported_packet_rejected(packet, tmp_path, mutation):
    path = tmp_path / "packet.json"
    export_review_packet(packet, path)
    value = json.loads(path.read_text())
    if mutation == "text":
        value["cases"][0]["evidence"][0]["value"] = "Tampered fictional text"
    elif mutation == "hash":
        value["packet_hash"] = "0" * 64
    elif mutation == "field":
        value["expected_answer"] = "supported_distinct"
    elif mutation == "mode":
        value["custody"] = "final"
    elif mutation == "sequence":
        value["cases"][0]["required_competencies"] = "fictional_latin"
    elif mutation == "schema_bool":
        value["schema_version"] = True
    else:
        path.write_text('{"mode":"fictional_preparation","mode":"final"}')
        with pytest.raises(ValueError, match="duplicate JSON"):
            load_review_packet(path)
        return
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_review_packet(path)


def test_fixture_summary_does_not_manufacture_real_human_reviews(packet, actors):
    assert review_summary(packet)["pending_submission_cases"] == 1
    submissions = (
        submission(packet),
        submission(packet, actor="reviewer-2", outcome="insufficient_evidence"),
    )
    adjudications = (adjudication(packet, submissions),)
    result = review_summary(packet, submissions, adjudications, actors)
    assert result["fixture_submission_count"] == 2
    assert result["fixture_disagreement_cases"] == 1
    assert result["fixture_adjudicated_cases"] == 1
    assert result["fixture_independent_adjudications"] == 1
    assert result["human_reviews_performed"] == 0
    assert result["usable_real_labels"] == 0
    assert result["real_review_minimum_met"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_id": "unknown"},
        {"origin": "ai"},
        {"packet_hash": "f" * 64},
        {"case_id": "another-case"},
        {"evidence_refs": ("unknown-proof",)},
        {"evidence_refs": ("name-a", "name-b")},
        {"uncertain": True},
        {"conflict_declared": True},
    ],
)
def test_submission_requires_human_actor_bound_evidence_and_resolved_claim(
    packet, actors, changes
):
    with pytest.raises(ValueError):
        validate_submissions(packet, (replace(submission(packet), **changes),), actors)


@pytest.mark.parametrize(
    "actor_change",
    [
        {"kind": "ai"},
        {"competencies": ("unrelated_language",)},
        {"roles": ("adjudicate",)},
    ],
)
def test_ai_or_unqualified_registry_actor_cannot_impersonate_reviewer(
    packet, actors, actor_change
):
    changed = (replace(actors[0], **actor_change), *actors[1:])
    with pytest.raises(ValueError):
        validate_submissions(packet, (submission(packet),), changed)


def test_replayed_review_cannot_increase_counts(packet, actors):
    first = submission(packet)
    with pytest.raises(ValueError, match="duplicate/replayed"):
        review_summary(
            packet, (first, replace(first, submission_id="replay")), actors=actors
        )


def test_adjudication_cannot_ignore_disagreement_or_precede_reviews(packet, actors):
    submissions = (
        submission(packet),
        submission(packet, actor="reviewer-2", outcome="insufficient_evidence"),
    )
    resolved = adjudication(packet, submissions)
    for invalid in (
        replace(resolved, submission_ids=(submissions[0].submission_id,)),
        replace(resolved, created_at="2026-10-24T10:00:00+00:00"),
    ):
        with pytest.raises(ValueError):
            validate_adjudications(packet, submissions, (invalid,), actors)
    validate_adjudications(
        packet, submissions, (resolved,), actors, require_independent=True
    )


def test_independent_adjudication_requires_different_actor(packet, actors):
    submissions = (submission(packet),)
    resolved = replace(adjudication(packet, submissions), actor_id="reviewer-1")
    with pytest.raises(ValueError, match="different approved actor"):
        validate_adjudications(
            packet, submissions, (resolved,), actors, require_independent=True
        )


def test_agreement_does_not_automatically_create_adjudication_or_label(packet, actors):
    submissions = (submission(packet), submission(packet, actor="reviewer-2"))
    result = assess_pair_use(
        packet,
        "case-1",
        submissions,
        (),
        actors,
        purpose="hard_negative",
        context=context(packet),
    )
    assert not result.fixture_contract_satisfied
    assert "missing_adjudication" in result.reasons
    assert not result.usable_real_label


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"family_ids": ("family-a", "family-a")}, "incompatible_leakage_families"),
        ({"quarantined": True}, "quarantined_or_uncertain_link"),
        ({"reviewed_relation": "uncertain"}, "quarantined_or_uncertain_link"),
        ({"reviewed_relation": "same"}, "unsupported_reviewed_relation"),
    ],
)
def test_hard_negatives_reject_family_or_uncertain_link_leakage(
    packet, actors, changes, reason
):
    submissions = (submission(packet),)
    result = assess_pair_use(
        packet,
        "case-1",
        submissions,
        (adjudication(packet, submissions),),
        actors,
        purpose="hard_negative",
        context=context(packet, **changes),
    )
    assert reason in result.reasons
    assert not result.fixture_contract_satisfied


def test_valid_fixture_negative_still_never_releases_a_real_label(packet, actors):
    submissions = (submission(packet),)
    result = assess_pair_use(
        packet,
        "case-1",
        submissions,
        (adjudication(packet, submissions),),
        actors,
        purpose="hard_negative",
        context=context(packet),
    )
    assert result.fixture_contract_satisfied
    assert result.reasons == ()
    assert result.usable_real_label is False


def test_weak_alias_requires_explicit_purpose_specific_adjudication(packet, actors):
    case = packet.cases[0]
    evidence = (replace(case.evidence[0], strength="weak"), *case.evidence[1:])
    weak_packet = freeze_review_packet(
        (replace(case, evidence=evidence),),
        candidate_release_hash=RELEASE,
        sampling_rule="authored weak-alias test",
    )
    submissions = (submission(weak_packet),)
    resolved = adjudication(weak_packet, submissions)
    result = assess_pair_use(
        weak_packet,
        "case-1",
        submissions,
        (resolved,),
        actors,
        purpose="hard_negative",
        context=context(weak_packet),
    )
    assert "weak_alias_needs_purpose_specific_resolution" in result.reasons
    resolved = replace(resolved, weak_alias_approvals=(("name-a", "hard_negative"),))
    result = assess_pair_use(
        weak_packet,
        "case-1",
        submissions,
        (resolved,),
        actors,
        purpose="hard_negative",
        context=context(weak_packet),
    )
    assert result.fixture_contract_satisfied
    with pytest.raises(ValueError, match="conflicts"):
        validate_adjudications(
            weak_packet,
            submissions,
            (replace(resolved, weak_alias_approvals=(("name-a", "positive"),)),),
            actors,
        )


def test_positive_requires_supported_same_and_same_reviewed_family(packet, actors):
    submissions = (submission(packet, outcome="supported_same"),)
    resolved = adjudication(packet, submissions, outcome="supported_same")
    result = assess_pair_use(
        packet,
        "case-1",
        submissions,
        (resolved,),
        actors,
        purpose="positive",
        context=context(
            packet, reviewed_relation="same", family_ids=("family-a", "family-a")
        ),
    )
    assert result.fixture_contract_satisfied
    assert not result.usable_real_label


def test_context_from_another_release_or_pair_cannot_authorize_use(packet, actors):
    submissions = (submission(packet),)
    for changes in (
        {"candidate_release_hash": "c" * 64},
        {"observation_ids": ("B", "A")},
    ):
        with pytest.raises(ValueError, match="another release or pair"):
            assess_pair_use(
                packet,
                "case-1",
                submissions,
                (adjudication(packet, submissions),),
                actors,
                purpose="hard_negative",
                context=context(packet, **changes),
            )


def test_conflicting_lineage_across_evidence_is_rejected(packet):
    case = packet.cases[0]
    evidence = (
        *case.evidence[:2],
        replace(case.evidence[2], snapshot_id="different-snapshot"),
    )
    with pytest.raises(ValueError, match="lineage conflicts"):
        freeze_review_packet(
            (replace(case, evidence=evidence),),
            candidate_release_hash=RELEASE,
            sampling_rule="conflicting fixture",
        )


def test_cli_only_prepares_fictional_questions_and_audits_them(tmp_path, capsys):
    path = tmp_path / "fixture.json"
    assert main(["prepare-fictional", "--output", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["human_reviews_performed"] == 0
    assert report["fixture_submission_count"] == 0
    assert main(["audit-preparation", "--packet", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_naive_times_and_boolean_uncertainty_coercion_rejected(packet):
    with pytest.raises(ValueError, match="timezone"):
        replace(submission(packet), created_at="2026-10-25T10:00:00")
    with pytest.raises(ValueError, match="booleans"):
        replace(submission(packet), uncertain=1)


def test_source_qualifiers_survive_frozen_packet_without_reinterpreting_strength(
    packet, tmp_path
):
    case = packet.cases[0]
    evidence = (
        replace(
            case.evidence[0], attributes=(("strong", "false"), ("type", "alternative"))
        ),
        *case.evidence[1:],
    )
    changed = freeze_review_packet(
        (replace(case, evidence=evidence),),
        candidate_release_hash=RELEASE,
        sampling_rule="fictional qualifier example",
    )
    path = tmp_path / "qualifiers.json"
    export_review_packet(changed, path)
    loaded = load_review_packet(path)
    assert loaded.cases[0].evidence[0].attributes == (
        ("strong", "false"),
        ("type", "alternative"),
    )
    assert loaded.cases[0].evidence[0].strength == "unknown"


def test_one_name_cannot_be_reviewed_as_a_pair(packet):
    case = packet.cases[0]
    with pytest.raises(ValueError, match="two name-evidence"):
        replace(
            case,
            observation_ids=("A", "A"),
            evidence=(case.evidence[0], case.evidence[2]),
        )


def test_same_actor_adjudication_is_not_reported_as_independent(packet, actors):
    submissions = (submission(packet),)
    resolved = replace(adjudication(packet, submissions), actor_id="reviewer-1")
    result = review_summary(packet, submissions, (resolved,), actors)
    assert result["fixture_independent_adjudications"] == 0
    assert result["human_reviews_performed"] == 0


def test_quarantine_and_relation_cannot_be_spoofed_with_a_genuine_grouping_hash(
    packet, actors
):
    actual = context(packet, quarantined=True)
    assert actual.quarantined
    with pytest.raises(TypeError):
        replace(actual, quarantined=False)
    with pytest.raises(TypeError):
        replace(actual, reviewed_relation="distinct")
    changed_groups = tuple(
        replace(group, quarantined=False) for group in actual.grouping.groups
    )
    with pytest.raises(ValueError, match="content/hash mismatch"):
        replace(actual.grouping, groups=changed_groups)
    submissions = (submission(packet),)
    result = assess_pair_use(
        packet,
        "case-1",
        submissions,
        (adjudication(packet, submissions),),
        actors,
        purpose="hard_negative",
        context=actual,
    )
    assert not result.fixture_contract_satisfied
    assert "quarantined_or_uncertain_link" in result.reasons


@pytest.mark.parametrize(
    "source,field,attributes,weak",
    [
        ("ofac_sdn", "sdnEntry.akaList.aka.lastName", (("category", "weak"),), True),
        (
            "un_consolidated",
            "ENTITY.ENTITY_ALIAS.ALIAS_NAME",
            (("QUALITY", "Low"),),
            True,
        ),
        ("opensanctions_un", "properties.weakAlias", (), True),
        ("eu_consolidated", "nameAlias.wholeName", (("strong", "false"),), False),
    ],
)
def test_source_weak_evidence_cannot_hide_behind_unknown_strength(
    packet, actors, source, field, attributes, weak
):
    evidence = tuple(
        replace(
            item,
            source_record_key=(source, "fictional-record-a"),
            **(
                {"field": field, "attributes": attributes}
                if item.kind == "name"
                else {}
            ),
        )
        if item.observation_id == "A"
        else item
        for item in packet.cases[0].evidence
    )
    changed = freeze_review_packet(
        (replace(packet.cases[0], evidence=evidence),),
        candidate_release_hash=RELEASE,
        sampling_rule="authored source weak-flag test",
    )
    submissions = (submission(changed),)
    resolved = adjudication(changed, submissions)
    result = assess_pair_use(
        changed,
        "case-1",
        submissions,
        (resolved,),
        actors,
        purpose="hard_negative",
        context=context(changed),
    )
    assert result.fixture_contract_satisfied is not weak
    if weak:
        assert "weak_alias_needs_purpose_specific_resolution" in result.reasons
        resolved = replace(
            resolved, weak_alias_approvals=(("name-a", "hard_negative"),)
        )
        assert assess_pair_use(
            changed,
            "case-1",
            submissions,
            (resolved,),
            actors,
            purpose="hard_negative",
            context=context(changed),
        ).fixture_contract_satisfied
        with pytest.raises(ValueError, match="contradicts"):
            replace(evidence[0], strength="nonweak")


@pytest.mark.parametrize("kind", ["review_packet", "grouping_result"])
def test_readiness_boundary_rejects_fictional_release_objects(packet, kind):
    candidate = packet if kind == "review_packet" else context(packet).grouping
    assert candidate.candidate_release_hash == RELEASE
    with pytest.raises(readiness_review.ReviewError):
        readiness_review.assemble_review_packets(candidate, c1_manifest_sha256=RELEASE)


def test_readiness_boundary_cannot_be_recast_as_a_fictional_release(tmp_path):
    c1_payloads = fictional_c1_payloads(tmp_path)
    manifest_hash = digest(c1_payloads["manifest.json"])
    prepared = readiness_review.assemble_review_packets(
        c1_payloads, c1_manifest_sha256=manifest_hash
    )
    blank = json.loads(prepared["duplicate.jsonl"].splitlines()[0])
    assert blank["outcome"] is None
    assert blank["status"] == "blocked_unresolved"
    assert "candidate_release_hash" not in blank
    path = tmp_path / "attempted-fictional-release.json"
    for candidate in (
        blank,
        {**blank, "candidate_release_hash": manifest_hash},
    ):
        path.write_text(json.dumps(candidate))
        with pytest.raises(ValueError, match="unexpected review packet fields"):
            load_review_packet(path)
        with pytest.raises(ValueError, match="expected a review preparation packet"):
            review_summary(candidate)
        with pytest.raises(ValueError, match="expected a candidate grouping result"):
            PairContext(candidate, tuple(blank["observation_ids"]))


def test_readiness_ledger_boundary_rejects_fictional_review_decisions(packet, tmp_path):
    c1_payloads = fictional_c1_payloads(tmp_path)
    prepared = readiness_review.assemble_review_packets(
        c1_payloads,
        c1_manifest_sha256=digest(c1_payloads["manifest.json"]),
        fictional=True,
    )
    artifacts = tmp_path / "readiness-ledger"
    artifacts.mkdir(mode=0o700)
    packet_path = artifacts / "packets"
    packet_hash = readiness_review.write_fictional_packet(
        prepared, packet_path, project_root=tmp_path, guard=safe_guard()
    )
    ledger_path = artifacts / "ledger"
    head = readiness_review.create_ledger(
        packet_path,
        ledger_path,
        expected_packet_sha256=packet_hash,
        project_root=tmp_path,
        guard=safe_guard(),
    )
    arguments = {
        "packet_path": packet_path,
        "expected_packet_sha256": packet_hash,
        "expected_head": head,
        "project_root": tmp_path,
        "guard": safe_guard(),
    }
    before = readiness_review.replay_ledger(ledger_path, **arguments)
    old_submission = replace(submission(packet), packet_hash=packet_hash)
    old_adjudication = replace(
        adjudication(packet, (old_submission,)), packet_hash=packet_hash
    )
    for append, decision in (
        (readiness_review.append_submission, old_submission),
        (readiness_review.append_adjudication, old_adjudication),
    ):
        with pytest.raises(
            readiness_review.ReviewError, match="invalid_review_event_fields"
        ):
            append(ledger_path, decision, **arguments)
    after = readiness_review.replay_ledger(ledger_path, **arguments)
    assert after == before
    assert (
        after["event_count"]
        == after["accepted_labels"]
        == after["identity_merges"]
        == 0
    )
    assert after["accepted_corpus_release"] is False
    with pytest.raises(ValueError, match="expected a review preparation packet"):
        review_summary(after)
    with pytest.raises(ValueError, match="expected a candidate grouping result"):
        PairContext(after, ("observation-a", "observation-b"))
