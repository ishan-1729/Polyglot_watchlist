"""Fictional review preparation and validation; never perform a human review.

This first implementation supports authored fixtures only. Actor/approval
references are declarations checked against a supplied registry, not proof of
identity or independence. Real review ingestion and final material are disabled.
"""

import argparse
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from watchlist.ingest.link_records import (
    GroupingResult,
    reviewed_pair_relation,
    validate_grouping_result,
)


OUTCOMES = frozenset(
    {"supported_same", "supported_distinct", "insufficient_evidence", "ineligible"}
)
PURPOSES = frozenset({"positive", "hard_negative"})
MAX_PREPARATION_BYTES = 16_000_000


def _text(value: object, label: str) -> None:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be nonblank unpadded text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must contain valid Unicode") from exc


def _strings(value: object, label: str, *, nonempty: bool = False) -> None:
    if type(value) is not tuple or (nonempty and not value):
        raise ValueError(f"{label} must be an immutable tuple")
    for item in value:
        _text(item, label)
    if len(value) != len(set(value)):
        raise ValueError(f"duplicate {label}")


def _choice(value: object, choices: frozenset[str], label: str) -> None:
    if type(value) is not str or value not in choices:
        raise ValueError(f"invalid {label}")


def _hash(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid SHA-256 reference")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _time(value: str) -> datetime:
    _text(value, "event time")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("event time must be ISO 8601") from exc
    if result.tzinfo is None:
        raise ValueError("event time must include a timezone")
    return result


@dataclass(frozen=True)
class ReviewEvidence:
    evidence_id: str
    observation_id: str
    source_record_key: tuple[str, str]
    snapshot_id: str
    value: str
    field: str
    kind: str = "name"
    language: str | None = None
    strength: str = "unknown"
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.evidence_id,
            self.observation_id,
            self.snapshot_id,
            self.value,
            self.field,
        ):
            _text(value, "evidence field")
        if (
            type(self.source_record_key) is not tuple
            or len(self.source_record_key) != 2
        ):
            raise ValueError("source record key must be a two-part tuple")
        for value in self.source_record_key:
            _text(value, "source record key")
        if self.language is not None:
            _text(self.language, "supplied language")
        _choice(self.kind, frozenset({"name", "identity_support"}), "evidence kind")
        _choice(
            self.strength, frozenset({"weak", "nonweak", "unknown"}), "alias strength"
        )
        if type(self.attributes) is not tuple:
            raise ValueError("source attributes must be immutable pairs")
        for attribute in self.attributes:
            if type(attribute) is not tuple or len(attribute) != 2:
                raise ValueError("source attributes require key/value pairs")
            _text(attribute[0], "attribute key")
            if type(attribute[1]) is not str:
                raise ValueError("source attribute values must remain text")
            try:
                attribute[1].encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "source attributes must contain valid Unicode"
                ) from exc
        keys = [key for key, _ in self.attributes]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate source attribute key")
        if self.strength == "nonweak" and _source_marks_weak(self):
            raise ValueError(
                "nonweak classification contradicts explicit source evidence"
            )


def _source_marks_weak(evidence: ReviewEvidence) -> bool:
    source = evidence.source_record_key[0]
    attributes = dict(evidence.attributes)
    if source == "ofac_sdn":
        return attributes.get("category", "").strip().casefold() == "weak"
    if source == "un_consolidated":
        return attributes.get("QUALITY", "").strip().casefold() == "low"
    if source == "opensanctions_un":
        return evidence.field.rsplit(".", 1)[-1] == "weakAlias"
    return False


def _weak_name(evidence: ReviewEvidence) -> bool:
    return evidence.kind == "name" and (
        evidence.strength == "weak" or _source_marks_weak(evidence)
    )


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    candidate_kind: str
    observation_ids: tuple[str, str]
    evidence: tuple[ReviewEvidence, ...]
    required_competencies: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.case_id, "case ID")
        _choice(
            self.candidate_kind,
            frozenset({"proposed_positive", "negative_candidate", "link_candidate"}),
            "candidate kind",
        )
        if type(self.observation_ids) is not tuple or len(self.observation_ids) != 2:
            raise ValueError("review requires exactly two observation endpoints")
        for value in self.observation_ids:
            _text(value, "observation endpoint")
        if type(self.evidence) is not tuple or not self.evidence:
            raise ValueError("review evidence must be a nonempty tuple")
        if any(type(item) is not ReviewEvidence for item in self.evidence):
            raise ValueError("invalid evidence object")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate case evidence ID")
        if any(
            item.observation_id not in self.observation_ids for item in self.evidence
        ):
            raise ValueError("evidence belongs to another observation")
        named = {item.observation_id for item in self.evidence if item.kind == "name"}
        if not set(self.observation_ids) <= named:
            raise ValueError("each endpoint requires original name evidence")
        if sum(item.kind == "name" for item in self.evidence) < 2:
            raise ValueError("pair review requires two name-evidence items")
        _strings(self.required_competencies, "required competency", nonempty=True)


@dataclass(frozen=True)
class ReviewPacket:
    candidate_release_hash: str
    sampling_rule: str
    cases: tuple[ReviewCase, ...]
    packet_hash: str
    schema_version: int = 1
    mode: str = "fictional_preparation"
    custody: str = "development"

    def __post_init__(self) -> None:
        validate_packet(self)


def _packet_payload(packet: ReviewPacket) -> dict:
    payload = asdict(packet)
    del payload["packet_hash"]
    return payload


def validate_packet(packet: ReviewPacket) -> None:
    """Verify fixture scope and frozen content; a digest is not a secrecy proof."""
    if type(packet) is not ReviewPacket:
        raise ValueError("expected a review preparation packet")
    if type(packet.schema_version) is not int or packet.schema_version != 1:
        raise ValueError("unsupported review preparation schema")
    if packet.mode != "fictional_preparation" or packet.custody != "development":
        raise ValueError(
            "only fictional development preparation; final material is forbidden"
        )
    _hash(packet.candidate_release_hash)
    _hash(packet.packet_hash)
    _text(packet.sampling_rule, "sampling rule")
    if type(packet.cases) is not tuple or not packet.cases:
        raise ValueError("packet must contain an immutable nonempty case tuple")
    case_ids: set[str] = set()
    evidence_by_id: dict[str, ReviewEvidence] = {}
    observation_keys: dict[str, tuple[str, tuple[str, str]]] = {}
    for case in packet.cases:
        if type(case) is not ReviewCase or case.case_id in case_ids:
            raise ValueError("invalid or duplicate review case")
        case_ids.add(case.case_id)
        for evidence in case.evidence:
            if (
                evidence.evidence_id in evidence_by_id
                and evidence_by_id[evidence.evidence_id] != evidence
            ):
                raise ValueError("conflicting evidence ID across cases")
            evidence_by_id[evidence.evidence_id] = evidence
            key = (evidence.snapshot_id, evidence.source_record_key)
            if (
                evidence.observation_id in observation_keys
                and observation_keys[evidence.observation_id] != key
            ):
                raise ValueError("observation lineage conflicts across evidence")
            observation_keys[evidence.observation_id] = key
    if (
        hashlib.sha256(_canonical(_packet_payload(packet))).hexdigest()
        != packet.packet_hash
    ):
        raise ValueError("review packet content/hash mismatch")


def freeze_review_packet(
    cases: Sequence[ReviewCase],
    *,
    candidate_release_hash: str,
    sampling_rule: str,
    mode: str = "fictional_preparation",
    custody: str = "development",
) -> ReviewPacket:
    """Freeze a fictional question packet with no expected answers or reviews."""
    if any(type(case) is not ReviewCase for case in cases):
        raise ValueError("cases must be ReviewCase objects")
    ordered = tuple(sorted(cases, key=lambda case: case.case_id))
    payload = {
        "candidate_release_hash": candidate_release_hash,
        "sampling_rule": sampling_rule,
        "cases": [asdict(case) for case in ordered],
        "schema_version": 1,
        "mode": mode,
        "custody": custody,
    }
    return ReviewPacket(
        candidate_release_hash,
        sampling_rule,
        ordered,
        hashlib.sha256(_canonical(payload)).hexdigest(),
        mode=mode,
        custody=custody,
    )


def export_review_packet(packet: ReviewPacket, destination: Path) -> None:
    """Atomically create a private fixture packet; refuse all overwrites."""
    validate_packet(packet)
    destination = Path(destination)
    payload = _canonical(asdict(packet)) + b"\n"
    if len(payload) > MAX_PREPARATION_BYTES:
        raise ValueError("fictional preparation packet exceeds byte limit")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".review-preparation-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def load_review_packet(path: Path) -> ReviewPacket:
    """Validate exact fictional packet fields and digest before returning it."""
    with Path(path).open("rb") as stream:
        payload = stream.read(MAX_PREPARATION_BYTES + 1)
    if len(payload) > MAX_PREPARATION_BYTES:
        raise ValueError("fictional preparation packet exceeds byte limit")
    value = json.loads(payload, object_pairs_hook=_unique_object)
    expected = set(ReviewPacket.__dataclass_fields__)
    if type(value) is not dict or set(value) != expected:
        raise ValueError("unexpected review packet fields")
    if type(value["cases"]) is not list:
        raise ValueError("packet cases must be an array")
    cases = []
    try:
        for raw_case in value["cases"]:
            if type(raw_case) is not dict or set(raw_case) != set(
                ReviewCase.__dataclass_fields__
            ):
                raise ValueError("unexpected case fields")
            if any(
                type(raw_case[field]) is not list
                for field in ("observation_ids", "evidence", "required_competencies")
            ):
                raise ValueError("case sequences must be arrays")
            evidence = []
            for item in raw_case["evidence"]:
                if type(item) is not dict or set(item) != set(
                    ReviewEvidence.__dataclass_fields__
                ):
                    raise ValueError("unexpected evidence fields")
                if type(item["source_record_key"]) is not list:
                    raise ValueError("source key must be an array")
                if type(item["attributes"]) is not list or any(
                    type(attribute) is not list for attribute in item["attributes"]
                ):
                    raise ValueError("source attributes must be arrays of pairs")
                evidence.append(
                    ReviewEvidence(
                        **{
                            **item,
                            "source_record_key": tuple(item["source_record_key"]),
                            "attributes": tuple(
                                tuple(attribute) for attribute in item["attributes"]
                            ),
                        }
                    )
                )
            cases.append(
                ReviewCase(
                    raw_case["case_id"],
                    raw_case["candidate_kind"],
                    tuple(raw_case["observation_ids"]),
                    tuple(evidence),
                    tuple(raw_case["required_competencies"]),
                )
            )
        return ReviewPacket(**{**value, "cases": tuple(cases)})
    except (TypeError, KeyError) as exc:
        raise ValueError("malformed review preparation packet") from exc


@dataclass(frozen=True)
class ReviewActor:
    actor_id: str
    kind: str
    authorization_ref: str
    competencies: tuple[str, ...]
    roles: tuple[str, ...] = ("review",)

    def __post_init__(self) -> None:
        _text(self.actor_id, "actor ID")
        _text(self.authorization_ref, "actor authorization reference")
        _choice(self.kind, frozenset({"human", "ai"}), "actor kind")
        _strings(self.competencies, "actor competency", nonempty=True)
        _strings(self.roles, "actor role", nonempty=True)
        if not set(self.roles) <= {"review", "adjudicate"}:
            raise ValueError("unsupported actor role")


@dataclass(frozen=True)
class ReviewSubmission:
    submission_id: str
    packet_hash: str
    case_id: str
    actor_id: str
    outcome: str
    rationale: str
    evidence_refs: tuple[str, ...]
    created_at: str
    origin: str = "human"
    uncertain: bool = False
    conflict_declared: bool = False

    def __post_init__(self) -> None:
        for value in (self.submission_id, self.case_id, self.actor_id, self.rationale):
            _text(value, "submission field")
        _hash(self.packet_hash)
        _choice(self.outcome, OUTCOMES, "review outcome")
        _strings(self.evidence_refs, "submission evidence", nonempty=True)
        _time(self.created_at)
        if type(self.uncertain) is not bool or type(self.conflict_declared) is not bool:
            raise ValueError("uncertainty/conflict flags must be booleans")


@dataclass(frozen=True)
class Adjudication:
    adjudication_id: str
    packet_hash: str
    case_id: str
    actor_id: str
    submission_ids: tuple[str, ...]
    outcome: str
    rationale: str
    evidence_refs: tuple[str, ...]
    created_at: str
    origin: str = "human"
    weak_alias_approvals: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.adjudication_id,
            self.case_id,
            self.actor_id,
            self.rationale,
        ):
            _text(value, "adjudication field")
        _hash(self.packet_hash)
        _choice(self.outcome, OUTCOMES, "adjudication outcome")
        _strings(self.submission_ids, "adjudication submission", nonempty=True)
        _strings(self.evidence_refs, "adjudication evidence", nonempty=True)
        _time(self.created_at)
        if type(self.weak_alias_approvals) is not tuple:
            raise ValueError("weak-alias approvals must be immutable")
        for approval in self.weak_alias_approvals:
            if type(approval) is not tuple or len(approval) != 2:
                raise ValueError("weak-alias approval requires evidence ID and purpose")
            _text(approval[0], "weak evidence ID")
            _choice(approval[1], PURPOSES, "weak-alias purpose")
        if len(set(self.weak_alias_approvals)) != len(self.weak_alias_approvals):
            raise ValueError("duplicate weak-alias approval")


def _validate_actor(
    actor: ReviewActor, case: ReviewCase, role: str, origin: str
) -> None:
    if actor.kind != "human" or origin != "human":
        raise ValueError("AI output cannot claim human review origin")
    if role not in actor.roles:
        raise ValueError("actor lacks required review role")
    if not set(case.required_competencies) <= set(actor.competencies):
        raise ValueError("reviewer lacks declared required competence")


def _validate_evidence(case: ReviewCase, refs: tuple[str, ...], outcome: str) -> None:
    evidence = {item.evidence_id: item for item in case.evidence}
    if not set(refs) <= evidence.keys():
        raise ValueError("unknown or cross-case review evidence")
    if outcome.startswith("supported_") and not any(
        evidence[ref].kind == "identity_support" for ref in refs
    ):
        raise ValueError("name similarity alone cannot support an identity decision")


def validate_submissions(
    packet: ReviewPacket,
    submissions: Sequence[ReviewSubmission],
    actors: Sequence[ReviewActor],
) -> None:
    """Check fixture declarations and provenance, without authenticating humans."""
    validate_packet(packet)
    actor_map = {}
    for actor in actors:
        if type(actor) is not ReviewActor or actor.actor_id in actor_map:
            raise ValueError("invalid or duplicate actor registry entry")
        actor_map[actor.actor_id] = actor
    cases = {case.case_id: case for case in packet.cases}
    seen_ids: set[str] = set()
    seen_actors: set[tuple[str, str]] = set()
    for submission in submissions:
        if type(submission) is not ReviewSubmission:
            raise ValueError("invalid submission object")
        if (
            submission.packet_hash != packet.packet_hash
            or submission.case_id not in cases
        ):
            raise ValueError("submission belongs to another packet or case")
        if (
            submission.submission_id in seen_ids
            or (submission.case_id, submission.actor_id) in seen_actors
        ):
            raise ValueError(
                "duplicate/replayed review; revisions need a new explicit version"
            )
        seen_ids.add(submission.submission_id)
        seen_actors.add((submission.case_id, submission.actor_id))
        if submission.actor_id not in actor_map:
            raise ValueError("unregistered reviewer")
        case = cases[submission.case_id]
        _validate_actor(
            actor_map[submission.actor_id], case, "review", submission.origin
        )
        _validate_evidence(case, submission.evidence_refs, submission.outcome)
        if submission.conflict_declared:
            raise ValueError("declared reviewer conflict requires separate resolution")
        if submission.uncertain and submission.outcome.startswith("supported_"):
            raise ValueError(
                "uncertain evidence cannot yield a supported identity outcome"
            )


def validate_adjudications(
    packet: ReviewPacket,
    submissions: Sequence[ReviewSubmission],
    adjudications: Sequence[Adjudication],
    actors: Sequence[ReviewActor],
    *,
    require_independent: bool = False,
) -> None:
    """Validate explicit resolutions; never infer one from reviewer agreement."""
    validate_submissions(packet, submissions, actors)
    if type(require_independent) is not bool:
        raise ValueError("independence requirement must be boolean")
    actor_map = {actor.actor_id: actor for actor in actors}
    cases = {case.case_id: case for case in packet.cases}
    submission_map = {item.submission_id: item for item in submissions}
    seen_cases: set[str] = set()
    seen_ids: set[str] = set()
    for adjudication in adjudications:
        if type(adjudication) is not Adjudication:
            raise ValueError("invalid adjudication object")
        if (
            adjudication.packet_hash != packet.packet_hash
            or adjudication.case_id not in cases
        ):
            raise ValueError("adjudication belongs to another packet/case")
        if (
            adjudication.case_id in seen_cases
            or adjudication.adjudication_id in seen_ids
        ):
            raise ValueError(
                "multiple active adjudications; preserve revisions separately"
            )
        seen_cases.add(adjudication.case_id)
        seen_ids.add(adjudication.adjudication_id)
        if adjudication.actor_id not in actor_map:
            raise ValueError("unregistered adjudicator")
        case = cases[adjudication.case_id]
        _validate_actor(
            actor_map[adjudication.actor_id], case, "adjudicate", adjudication.origin
        )
        expected = {
            item.submission_id for item in submissions if item.case_id == case.case_id
        }
        if not expected or set(adjudication.submission_ids) != expected:
            raise ValueError("adjudication must cover every submission for its case")
        reviews = [submission_map[ref] for ref in adjudication.submission_ids]
        if require_independent and adjudication.actor_id in {
            review.actor_id for review in reviews
        }:
            raise ValueError(
                "independent adjudication requires a different approved actor"
            )
        if any(
            _time(review.created_at) > _time(adjudication.created_at)
            for review in reviews
        ):
            raise ValueError("adjudication predates its supporting reviews")
        _validate_evidence(case, adjudication.evidence_refs, adjudication.outcome)
        weak = {item.evidence_id for item in case.evidence if _weak_name(item)}
        for evidence_id, purpose in adjudication.weak_alias_approvals:
            if evidence_id not in weak or evidence_id not in adjudication.evidence_refs:
                raise ValueError("weak-alias approval lacks the named evidence")
            expected_outcome = (
                "supported_same" if purpose == "positive" else "supported_distinct"
            )
            if adjudication.outcome != expected_outcome:
                raise ValueError(
                    "weak-alias approval conflicts with the reviewed purpose"
                )


@dataclass(frozen=True)
class PairContext:
    """Derive pair facts from a complete, hash-verified grouping result."""

    grouping: GroupingResult
    observation_ids: tuple[str, str]

    def __post_init__(self) -> None:
        validate_grouping_result(self.grouping)
        if type(self.observation_ids) is not tuple or len(self.observation_ids) != 2:
            raise ValueError("pair context requires two immutable endpoints")
        for value in self.observation_ids:
            _text(value, "pair-context endpoint")
        reviewed_pair_relation(self.grouping, *self.observation_ids)

    @property
    def candidate_release_hash(self) -> str:
        return self.grouping.candidate_release_hash

    @property
    def grouping_hash(self) -> str:
        return self.grouping.manifest_hash

    @property
    def family_ids(self) -> tuple[str, str]:
        owners = {
            member: group.group_id
            for group in self.grouping.groups
            for member in group.members
        }
        return tuple(owners[member] for member in self.observation_ids)

    @property
    def reviewed_relation(self) -> str:
        return reviewed_pair_relation(self.grouping, *self.observation_ids)

    @property
    def quarantined(self) -> bool:
        return any(
            group.quarantined and set(group.members).intersection(self.observation_ids)
            for group in self.grouping.groups
        )


@dataclass(frozen=True)
class PurposeAssessment:
    fixture_contract_satisfied: bool
    reasons: tuple[str, ...]
    usable_real_label: bool = False


def assess_pair_use(
    packet: ReviewPacket,
    case_id: str,
    submissions: Sequence[ReviewSubmission],
    adjudications: Sequence[Adjudication],
    actors: Sequence[ReviewActor],
    *,
    purpose: str,
    context: PairContext,
) -> PurposeAssessment:
    """Exercise positive/hard-negative gates without releasing a real label."""
    _choice(purpose, PURPOSES, "pair purpose")
    validate_adjudications(packet, submissions, adjudications, actors)
    cases = {case.case_id: case for case in packet.cases}
    if case_id not in cases or type(context) is not PairContext:
        raise ValueError("unknown case or invalid grouping context")
    validate_grouping_result(context.grouping)
    case = cases[case_id]
    if (
        context.candidate_release_hash != packet.candidate_release_hash
        or context.observation_ids != case.observation_ids
    ):
        raise ValueError("grouping context belongs to another release or pair")
    reasons = []
    if context.quarantined or context.reviewed_relation == "uncertain":
        reasons.append("quarantined_or_uncertain_link")
    expected_relation = "same" if purpose == "positive" else "distinct"
    if context.reviewed_relation != expected_relation:
        reasons.append("unsupported_reviewed_relation")
    same_family = context.family_ids[0] == context.family_ids[1]
    if same_family != (purpose == "positive"):
        reasons.append("incompatible_leakage_families")
    if (
        purpose == "hard_negative"
        and case.observation_ids[0] == case.observation_ids[1]
    ):
        reasons.append("same_observation_cannot_be_negative")
    decision = next((item for item in adjudications if item.case_id == case_id), None)
    expected_outcome = (
        "supported_same" if purpose == "positive" else "supported_distinct"
    )
    if decision is None:
        reasons.append("missing_adjudication")
    elif decision.outcome != expected_outcome:
        reasons.append("adjudication_does_not_support_purpose")
    weak = {item.evidence_id for item in case.evidence if _weak_name(item)}
    approvals = set(decision.weak_alias_approvals) if decision else set()
    if any((evidence_id, purpose) not in approvals for evidence_id in weak):
        reasons.append("weak_alias_needs_purpose_specific_resolution")
    return PurposeAssessment(not reasons, tuple(reasons))


def review_summary(
    packet: ReviewPacket,
    submissions: Sequence[ReviewSubmission] = (),
    adjudications: Sequence[Adjudication] = (),
    actors: Sequence[ReviewActor] = (),
) -> dict:
    """Count fixture preparation separately; report zero real reviews/labels."""
    validate_adjudications(packet, submissions, adjudications, actors)
    outcomes: dict[str, list[str]] = {}
    for submission in submissions:
        outcomes.setdefault(submission.case_id, []).append(submission.outcome)
    reviewed = set(outcomes)
    adjudicated = {item.case_id for item in adjudications}
    compared = [values for values in outcomes.values() if len(values) >= 2]
    return {
        "mode": packet.mode,
        "packet_hash": packet.packet_hash,
        "prepared_cases": len(packet.cases),
        "candidate_kind_counts": dict(
            sorted(Counter(case.candidate_kind for case in packet.cases).items())
        ),
        "fixture_submission_count": len(submissions),
        "fixture_reviewed_cases": len(reviewed),
        "fixture_adjudicated_cases": len(adjudicated),
        "fixture_independent_adjudications": sum(
            item.actor_id
            not in {
                review.actor_id
                for review in submissions
                if review.case_id == item.case_id
            }
            for item in adjudications
        ),
        "pending_submission_cases": len(packet.cases) - len(reviewed),
        "pending_adjudication_cases": len(packet.cases) - len(adjudicated),
        "fixture_compared_cases": len(compared),
        "fixture_disagreement_cases": sum(len(set(values)) > 1 for values in compared),
        "fixture_outcome_counts": dict(
            sorted(Counter(item.outcome for item in adjudications).items())
        ),
        "human_reviews_performed": 0,
        "usable_real_labels": 0,
        "real_review_minimum_met": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare-fictional", help="write a blank authored fixture packet"
    )
    prepare.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser(
        "audit-preparation", help="validate a fictional preparation packet"
    )
    audit.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-fictional":
            evidence = tuple(
                ReviewEvidence(
                    f"fictional-name-{number}",
                    f"fictional-observation-{number}",
                    ("fictional_source", str(number)),
                    "fictional_snapshot",
                    name,
                    "primary_name",
                )
                for number, name in (
                    (1, "Lumen Orchard Workshop"),
                    (2, "Velvet Compass Studio"),
                )
            )
            case = ReviewCase(
                "fictional-question-1",
                "negative_candidate",
                tuple(item.observation_id for item in evidence),
                evidence,
                ("fictional_latin",),
            )
            packet = freeze_review_packet(
                (case,),
                candidate_release_hash="0" * 64,
                sampling_rule="authored fictional preparation example; no expected answer",
            )
            export_review_packet(packet, args.output)
        else:
            packet = load_review_packet(args.packet)
        print(json.dumps(review_summary(packet), indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
