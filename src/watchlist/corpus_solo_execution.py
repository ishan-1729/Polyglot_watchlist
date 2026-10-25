"""SOLO-E: explicitly authorized, private single-owner development intake.

SOLO-I stays immutable and disabled. This module admits its original packet,
without changing evidence mode/origin, and keeps a separately pinned ledger.
Local owner attestation is attribution, not independent authentication or truth.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import sys

from watchlist import corpus, corpus_readiness as readiness
from watchlist import corpus_solo_review as solo
from watchlist import readiness_review as review
from watchlist.ingest.resource_guard import ResourceGuard, ResourceStop, _artifact_size
from watchlist.scripts import script_set

SCOPE = "08-SOLO-E-development-execution-v1"
LIMITS = {
    "max_new_artifact_bytes": 16_000_000,
    "max_cases": 40,
    "review_seconds": 14_400,
    "session_seconds": 1800,
    "first_case_seconds": 1200,
    "machine_seconds": 3600,
    "max_events": 10_000,
    "max_event_bytes": 65_536,
}
RETENTION = "private-until-project-closure-or-requested-deletion-review-v1"
PERMISSIONS = {**solo.RESTRICTIONS, "human_review_execution_allowed": True}


class ExecutionError(ValueError):
    """A policy, evidence, time, access or ledger gate failed closed."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _qualified(case: dict, value: dict, owner: dict) -> bool:
    """Do not equate Urdu literacy with Arabic-language competence.

    Record-level support inherits the whole-case script gate. Arabic-script
    competence is supplied by Urdu only when every such witness is tagged Urdu.
    Linguistic claims also need declared languages on both selected witnesses;
    unknown language tags do not become a translation competence by inference.
    """
    if not owner["record_review"]:
        return False
    aliases = [a for o in case["observations"] for a in o["aliases"]]
    available = {"record_review"}
    languages = owner["languages"]
    if languages.get("en") == "fluent":
        available.add("script:LATIN")
    arabic = [a for a in aliases if "ARABIC" in script_set(a["value"])]
    if (
        languages.get("ur") == "fluent"
        and arabic
        and all((a["language"] or "").lower() == "ur" for a in arabic)
    ):
        available.add("script:ARABIC")
    if not set(case["required_competencies"]) <= available:
        return False
    if (
        value["relationship_annotation"] != "unresolved"
        or value["direction"]["adequacy"] != "unresolved"
    ):
        selected = {
            value["direction"]["query_evidence_id"],
            value["direction"]["reference_evidence_id"],
        }
        witnesses = [a for a in aliases if a["evidence_id"] in selected]
        if len(witnesses) != 2 or any(
            languages.get((a["language"] or "").lower()) != "fluent" for a in witnesses
        ):
            return False
    return True


def _policy(path: Path, pin: str, root: Path) -> tuple[dict, bytes]:
    review._hash(pin)
    solo._private(path)
    raw = corpus._read_saved(path, 2_000_000, "SOLO-E policy")
    if solo._sha(raw) != pin:
        raise ExecutionError("execution_policy_pin_mismatch")
    decoded = solo._json(raw)
    p = solo._fields(
        decoded,
        {
            "schema_version",
            "scope",
            "mode",
            "packet",
            "source_config",
            "closure",
            "artifact_roots",
            "output_root",
            "owner",
            "retention",
            "approval_ref",
            "created_at",
            "limits",
            "permissions",
            "code_pins",
        }
        | ({"ledger_name"} if "ledger_name" in decoded else set()),
    )
    if p.get("ledger_name", "ledger") not in {"ledger", "ledger-v2"}:
        raise ExecutionError("unapproved_execution_ledger_name")
    if (
        type(p["schema_version"]) is not int
        or p["schema_version"] != 1
        or p["scope"] != SCOPE
        or p["limits"] != LIMITS
        or any(type(v) is not int for v in p["limits"].values())
        or p["permissions"] != PERMISSIONS
        or any(type(v) is not bool for v in p["permissions"].values())
    ):
        raise ExecutionError("unapproved_execution_scope_or_limits")
    if p["retention"] != RETENTION or p["mode"] not in {
        "development_blank",
        "fictional_fixture",
    }:
        raise ExecutionError("invalid_execution_retention_or_mode")
    solo._utc(p["created_at"])
    owner = solo._fields(
        p["owner"],
        {
            "actor_id",
            "uid",
            "account_owner_attested",
            "record_review",
            "languages",
            "domain",
            "attestation_ref",
        },
    )
    if (
        type(owner["uid"]) is not int
        or owner["uid"] != os.getuid()
        or owner["account_owner_attested"] is not True
        or owner["record_review"] is not True
    ):
        raise ExecutionError("owner_access_or_attestation_missing")
    if (
        owner["languages"]
        != {
            "en": "fluent",
            "ur": "fluent",
            "ar": "none",
            "ru": "none",
            "zh": "none",
            "ja": "none",
        }
        or owner["domain"] != "self-learning-ML-no-professional-sanctions-expertise"
    ):
        raise ExecutionError("competence_declaration_mismatch")
    for key in ("actor_id", "attestation_ref"):
        review._text(owner[key])
    if p["mode"] == "development_blank":
        if (
            owner["actor_id"] != "solo-owner-01"
            or p["approval_ref"] != "user-approved-SOLO-E-and-declarations-2026-10-25"
        ):
            raise ExecutionError("real_owner_or_approval_mismatch")
        config = solo._json(
            readiness._reference(root, p["source_config"], maximum=2_000_000)
        )
        closure = solo._json(
            readiness._reference(root, p["closure"], maximum=2_000_000)
        )
        if (
            closure.get("solo_i_acceptance_complete") is not True
            or closure.get("step08_complete") is not False
        ):
            raise ExecutionError("solo_i_not_closed")
        expected = set(config["artifact_roots"]) | {p["output_root"]}
        if (
            set(p["artifact_roots"]) != expected
            or p["packet"]["path"] != config["output_path"] + "/manifest.json"
        ):
            raise ExecutionError("unapproved_execution_source_or_roots")
    elif (
        not owner["actor_id"].startswith("fictional-")
        or p["approval_ref"] != "fictional-test-only"
        or p["source_config"] is not None
        or p["closure"] is not None
    ):
        raise ExecutionError("fictional_execution_boundary")
    roots = review._strings(p["artifact_roots"], nonempty=True)
    output = root / readiness._relative(p["output_root"])
    if p["output_root"] not in roots:
        raise ExecutionError("unmonitored_execution_root")
    for name in roots:
        other = root / readiness._relative(name)
        if other != output and (
            other.is_relative_to(output) or output.is_relative_to(other)
        ):
            raise ExecutionError("overlapping_execution_root")
    pins = p["code_pins"]
    if type(pins) is not list or not pins:
        raise ExecutionError("missing_execution_code_pins")
    for ref in pins:
        readiness._reference(root, ref, maximum=2_000_000)
    return p, raw


def _context(policy_path: Path, pin: str, root: Path, guard: ResourceGuard | None):
    root = root.absolute()
    policy_path = readiness._path(root, policy_path)
    p, raw = _policy(policy_path, pin, root)
    output = root / p["output_root"]
    solo._private(output, directory=True)
    guard = review._guard(root, p["artifact_roots"], output, guard)
    packet_path = (root / readiness._relative(p["packet"]["path"])).parent
    if Path(p["packet"]["path"]).name != "manifest.json":
        raise ExecutionError("invalid_execution_packet_path")
    _, _, packet, source_recheck, guard = solo._context(
        packet_path, p["packet"]["sha256"], root, guard
    )
    if (
        packet["mode"] != p["mode"]
        or len(packet["cases"]) > LIMITS["max_cases"]
        or p["mode"] == "development_blank"
        and len(packet["cases"]) != 40
    ):
        raise ExecutionError("execution_packet_mode_or_count")
    if solo._utc(p["created_at"]) < solo._utc(packet["metadata"]["created_at"]):
        raise ExecutionError("execution_predates_packet")
    if _artifact_size(output, required=True) > LIMITS["max_new_artifact_bytes"]:
        raise ExecutionError("execution_artifact_limit")
    guard.reserve_artifact(0)
    # SOLO-I accounts its inherited inputs. Charge this additional root too.
    guard.normalized_bytes += _artifact_size(output, required=True)
    if guard.normalized_bytes > guard.limits.max_normalized_bytes:
        raise ResourceStop("normalized_byte_limit")
    output_fd = corpus._open_directory(output)
    try:
        output_identity = os.fstat(output_fd)
    finally:
        os.close(output_fd)

    def recheck():
        source_recheck()
        solo._private(output, directory=True)
        current = output.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            output_identity.st_dev,
            output_identity.st_ino,
        ):
            raise ExecutionError("execution_root_changed")
        if _policy(policy_path, pin, root)[1] != raw:
            raise ExecutionError("execution_policy_changed")

    return p, packet, output, guard, recheck


def _header(p: dict, pin: str) -> bytes:
    return solo._canonical(
        {
            "schema_version": 1,
            "scope": SCOPE,
            "policy_sha256": pin,
            "packet": p["packet"],
            "owner": p["owner"],
            "created_at": p["created_at"],
            "retention": p["retention"],
            "permissions": PERMISSIONS,
            "accepted_labels": 0,
            "review_label": solo.REVIEW_LABEL,
        }
    )


def activate(
    policy_path: Path,
    *,
    policy_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> str:
    """Publish a new empty ledger; header is its final completion marker."""
    p, _, output, guard, recheck = _context(
        policy_path, policy_sha256, project_root, guard
    )
    raw = _header(p, policy_sha256)
    ledger = output / p.get("ledger_name", "ledger")
    parent = corpus._open_directory(output)
    directory = None
    try:
        solo._reserve(output, 2 * len(raw), guard)
        readiness._same_directory(output, parent)
        os.mkdir(ledger.name, 0o700, dir_fd=parent)
        directory = os.open(
            ledger.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        os.mkdir("events", 0o700, dir_fd=directory)
        lock = os.open(
            ".lock",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.fsync(lock)
        os.close(lock)
        guard.check()
        recheck()
        readiness._same_directory(ledger, directory)
        solo._private(ledger, directory=True)
        solo._private(ledger / "events", directory=True)
        solo._private(ledger / ".lock")
        if set(os.listdir(directory)) != {"events", ".lock"} or os.listdir(
            ledger / "events"
        ):
            raise ExecutionError("activation_directory_changed")
        solo._write_payload(directory, "header.json", raw)
        os.fsync(parent)
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    return solo._sha(raw)


def _validate_response(value: dict, packet: dict, policy: dict) -> dict:
    """Validate attribution, evidence scope and competence without deciding truth."""
    pin = policy["packet"]["sha256"]
    owner = policy["owner"]
    fictional = policy["mode"] == "fictional_fixture"
    prefix = "fictional-solo-" if fictional else "solo-"
    cases = {c["case_id"]: c for c in packet["cases"]}
    case = cases.get(value.get("case_id"))
    if case is None:
        raise ExecutionError("unknown_solo_case")
    solo._fields(value, set(solo._template(packet, case, pin)))
    if (
        value["packet_sha256"] != pin
        or value["case_sha256"] != case["case_sha256"]
        or value["actor_id"] != owner["actor_id"]
    ):
        raise ExecutionError("stale_solo_packet_case_or_owner")
    if not review._text(value["submission_id"]).startswith(prefix):
        raise ExecutionError("fictional_submission_id_required")
    if (
        value["evidence_origin"] != case["evidence_origin"]
        or value["review_origin"] != "single_human"
        or value["review_label"] != solo.REVIEW_LABEL
        or value["origin"] != ("fictional_human" if fictional else "human")
    ):
        raise ExecutionError("solo_provenance_misclassification")
    if (
        value["outcome"] not in review.OUTCOMES
        or value["target_scope"]
        not in {"publisher_record", "cross_record_identity", "unresolved"}
        or type(value["uncertain"]) is not bool
        or type(value["conflict_declared"]) is not bool
        or type(value["duration_seconds"]) is not int
        or not 1 <= value["duration_seconds"] <= 86400
    ):
        raise ExecutionError("invalid_solo_outcome_context")
    review._text(value["rationale"])
    if solo._utc(value["created_at"]) < solo._utc(policy["created_at"]):
        raise ExecutionError("submission_predates_owner_declaration")
    refs = review._strings(value["evidence_refs"], nonempty=True)
    if not set(refs) <= set(case["evidence_refs"]):
        raise ExecutionError("unknown_or_cross_case_solo_evidence")
    if value["evidence_versions"] != {
        ref: case["evidence_versions"][ref] for ref in refs
    }:
        raise ExecutionError("stale_or_missing_solo_evidence_versions")
    relation = value["relationship_annotation"]
    if relation not in review.RELATIONSHIPS:
        raise ExecutionError("invalid_solo_relationship")
    direction = solo._fields(
        value["direction"], {"query_evidence_id", "reference_evidence_id", "adequacy"}
    )
    if direction["adequacy"] not in {"unresolved", "adequate", "inadequate"}:
        raise ExecutionError("invalid_solo_direction_adequacy")
    q, r = direction["query_evidence_id"], direction["reference_evidence_id"]
    aliases = {a["evidence_id"] for o in case["observations"] for a in o["aliases"]}
    if q is None or r is None:
        if q is not None or r is not None or direction["adequacy"] != "unresolved":
            raise ExecutionError("incomplete_solo_direction_evidence")
    elif q == r or not {q, r} <= set(refs) & aliases:
        raise ExecutionError("invalid_solo_direction_evidence")
    supported = value["outcome"].startswith("supported_")
    linguistic_judgment = (
        relation != "unresolved" or direction["adequacy"] != "unresolved"
    )
    if supported or linguistic_judgment:
        if not _qualified(case, value, owner):
            raise ExecutionError("unqualified_solo_owner")
    if value["conflict_declared"] or value["uncertain"]:
        if supported or linguistic_judgment:
            raise ExecutionError("uncertain_or_conflicted_supported_solo_claim")
    if linguistic_judgment and not supported:
        raise ExecutionError("unresolved_outcome_cannot_establish_relationship")
    if relation != "unresolved" and (q is None or r is None):
        raise ExecutionError("relationship_requires_two_cited_names")
    if supported:
        if value["target_scope"] == "unresolved":
            raise ExecutionError("supported_solo_target_scope_required")
        restrictions = {item["evidence_id"] for item in case["restrictions"]}
        if restrictions & set(refs):
            raise ExecutionError("restricted_name_requires_later_policy")
        observations = case["observations"]
        if len(observations) == 1:
            if (
                value["target_scope"] != "publisher_record"
                or value["outcome"] != "supported_same"
            ):
                raise ExecutionError("publisher_assertion_cannot_establish_distinction")
            if len(set(refs) & aliases) < 2:
                raise ExecutionError("both_publisher_name_forms_required")
        elif len(observations) == 2:
            if value["target_scope"] != "cross_record_identity":
                raise ExecutionError("cross_record_target_scope_required")
            if any(
                not set(refs)
                & set(case["identity_evidence_refs"].get(o["observation_id"], []))
                for o in observations
            ):
                raise ExecutionError(
                    "positive_documentary_identity_evidence_required_for_both_records"
                )
        else:
            raise ExecutionError("unsupported_solo_record_scope")
    if value["supersedes"] is None:
        if value["correction_reason"] is not None:
            raise ExecutionError("initial_solo_response_has_correction_reason")
    else:
        if not review._text(value["supersedes"]).startswith(prefix):
            raise ExecutionError("invalid_solo_supersession_id")
        review._text(value["correction_reason"])
    return value


def _state(packet: dict) -> dict:
    return {
        "case_states": {
            c["case_id"]: {
                "status": "unreviewed",
                "active_submission_id": None,
                "outcome": None,
                "release_blocked": True,
            }
            for c in packet["cases"]
        },
        "responses": {},
        "session": None,
        "session_ids": [],
        "reserved_review_seconds": 0,
        "reported_review_seconds": 0,
        "first_checked": False,
        "first_submission_id": None,
        "last_response_time": None,
    }


def _apply_event(event: dict, state: dict, packet: dict, p: dict) -> None:
    """Replay policy/time constraints, including the first-case checkpoint."""
    kind, payload = event["kind"], event["payload"]
    timestamp = solo._utc(event["created_at"])
    if kind == "session_started":
        solo._fields(payload, {"session_id", "seconds", "actor_id"})
        if (
            not re.fullmatch(r"session-[A-Za-z0-9-]{1,80}", payload["session_id"])
            or payload["session_id"] in state["session_ids"]
            or payload["actor_id"] != p["owner"]["actor_id"]
        ):
            raise ExecutionError("invalid_or_duplicate_review_session")
        seconds = payload["seconds"]
        limit = (
            LIMITS["session_seconds"]
            if state["first_checked"]
            else LIMITS["first_case_seconds"]
        )
        if (
            type(seconds) is not int
            or not 1 <= seconds <= limit
            or state["reserved_review_seconds"] + seconds > LIMITS["review_seconds"]
        ):
            raise ExecutionError("review_time_allowance_exceeded")
        state["reserved_review_seconds"] += seconds
        state["session_ids"].append(payload["session_id"])
        state["session"] = {
            **payload,
            "started_at": event["created_at"],
            "expires_at": (timestamp + timedelta(seconds=seconds)).isoformat(),
            "used_seconds": 0,
            "first_only": not state["first_checked"],
            "event_sha256": event["event_sha256"],
        }
    elif kind == "submission":
        solo._fields(payload, {"session_id", "response"})
        session = state["session"]
        if session is None or payload["session_id"] != session["session_id"]:
            raise ExecutionError("review_session_required")
        value = _validate_response(payload["response"], packet, p)
        created = solo._utc(value["created_at"])
        if (
            not solo._utc(session["started_at"])
            <= created
            <= solo._utc(session["expires_at"])
            or created > timestamp
        ):
            raise ExecutionError("response_outside_review_session")
        if state["last_response_time"] is not None and created < solo._utc(
            state["last_response_time"]
        ):
            raise ExecutionError("backdated_review_response")
        if value["submission_id"] in state["responses"]:
            raise ExecutionError("duplicate_solo_submission_id")
        elapsed = (created - solo._utc(session["started_at"])).total_seconds()
        if session["used_seconds"] + value["duration_seconds"] > min(
            session["seconds"], elapsed
        ):
            raise ExecutionError("reported_review_time_exceeds_session")
        first_id = packet["cases"][0]["case_id"]
        if (not state["first_checked"] or session["first_only"]) and value[
            "case_id"
        ] != first_id:
            raise ExecutionError("first_case_verification_required")
        solo._apply(value, state["case_states"], state["responses"])
        session["used_seconds"] += value["duration_seconds"]
        state["reported_review_seconds"] += value["duration_seconds"]
        state["last_response_time"] = value["created_at"]
        if state["first_submission_id"] is None:
            state["first_submission_id"] = value["submission_id"]
    elif kind == "first_case_verified":
        solo._fields(payload, {"submission_id", "validation"})
        first = state["case_states"][packet["cases"][0]["case_id"]][
            "active_submission_id"
        ]
        if (
            first is None
            or payload
            != {
                "submission_id": first,
                "validation": "schema-evidence-and-ledger-replay-not-label-truth",
            }
            or state["first_checked"]
        ):
            raise ExecutionError("invalid_first_case_checkpoint")
        state["first_checked"] = True
    else:
        raise ExecutionError("unknown_execution_event_kind")


def _replay(
    ledger: Path,
    eventfd: int,
    packet: dict,
    p: dict,
    pin: str,
    expected_head: str,
    guard: ResourceGuard,
):
    review._hash(expected_head)
    raw = corpus._read_saved(ledger / "header.json", 2_000_000, "execution header")
    if raw != _header(p, pin):
        raise ExecutionError("execution_header_mismatch")
    names = sorted(os.listdir(eventfd))
    if len(names) > LIMITS["max_events"] or names != [
        f"{i:012d}.json" for i in range(1, len(names) + 1)
    ]:
        raise ExecutionError("execution_event_gap_or_extra_file")
    state, saved = _state(packet), [("header.json", raw)]
    head, timestamp = solo._sha(raw), solo._utc(p["created_at"])
    for sequence, name in enumerate(names, 1):
        guard.check()
        raw = corpus._read_saved(
            ledger / "events" / name, LIMITS["max_event_bytes"], "execution event"
        )
        event = solo._fields(
            solo._json(raw),
            {
                "schema_version",
                "sequence",
                "previous_sha256",
                "created_at",
                "kind",
                "payload",
                "event_sha256",
            },
        )
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        current_time = solo._utc(event["created_at"])
        if (
            type(event["schema_version"]) is not int
            or event["schema_version"] != 1
            or type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["previous_sha256"] != head
            or event["event_sha256"] != solo._sha(solo._canonical(body))
            or raw != solo._canonical(event)
            or current_time < timestamp
        ):
            raise ExecutionError("corrupt_execution_chain")
        _apply_event(event, state, packet, p)
        head, timestamp = event["event_sha256"], current_time
        saved.append(("events/" + name, raw))
    if head != expected_head:
        raise ExecutionError("execution_head_mismatch_or_truncation")
    return state, saved, timestamp


def _summary(state: dict, head: str, count: int, p: dict) -> dict:
    active = [
        state["responses"][s["active_submission_id"]]
        for s in state["case_states"].values()
        if s["active_submission_id"] is not None
    ]
    counts = Counter(v["outcome"] for v in active)
    return {
        "scope": SCOPE,
        "head_sha256": head,
        "event_count": count,
        "submission_count": len(state["responses"]),
        "inspected_case_count": len(active),
        "correction_count": sum(
            v["supersedes"] is not None for v in state["responses"].values()
        ),
        "outcome_counts": dict(counts),
        "reserved_review_seconds": state["reserved_review_seconds"],
        "remaining_unreserved_review_seconds": LIMITS["review_seconds"]
        - state["reserved_review_seconds"],
        "reported_review_seconds": state["reported_review_seconds"],
        "session": state["session"],
        "first_case_verified": state["first_checked"],
        "actual_submissions": len(state["responses"])
        if p["mode"] == "development_blank"
        else 0,
        "accepted_labels": 0,
        "identity_merges": 0,
        "independent_human_reviews": 0,
        "inter_reviewer_agreement": "not_measured",
        "review_label": solo.REVIEW_LABEL,
        "accepted_corpus_release": False,
    }


def operate(
    policy_path: Path,
    *,
    policy_sha256: str,
    project_root: Path,
    expected_head: str,
    action: str = "status",
    session_id: str | None = None,
    seconds: int | None = None,
    submission_path: Path | None = None,
    guard: ResourceGuard | None = None,
) -> dict:
    """Replay/read or append one bounded event, with a separately trusted head.

    A session reserves its whole wall-time window, including idle/expired time;
    this conservative reservation never refunds failed or interrupted work.
    Responses retain their actual human provenance and original evidence hash.
    """
    p, packet, output, guard, recheck = _context(
        policy_path, policy_sha256, project_root, guard
    )
    ledger = output / p.get("ledger_name", "ledger")
    draft = raw_draft = None
    if submission_path is not None:
        draft = readiness._path(project_root.absolute(), submission_path)
        if draft.parent != output / "incoming":
            raise ExecutionError("submission_requires_private_incoming_directory")
        solo._private(draft.parent, directory=True)
        solo._private(draft)
        raw_draft = corpus._read_saved(draft, LIMITS["max_event_bytes"], "owner draft")
    with review._locked(ledger) as (_, eventfd, check_lock):
        state, saved, last_time = _replay(
            ledger, eventfd, packet, p, policy_sha256, expected_head, guard
        )
        if action == "status":
            guard.check()
            recheck()
            solo._verify_ledger(ledger, eventfd, saved)
            check_lock()
            return _summary(state, expected_head, len(saved) - 1, p)
        now = _now()
        if now < last_time:
            raise ExecutionError("system_clock_precedes_ledger")
        if action == "start-session":
            kind, payload = (
                "session_started",
                {
                    "session_id": session_id,
                    "seconds": seconds,
                    "actor_id": p["owner"]["actor_id"],
                },
            )
        elif action == "submit":
            if raw_draft is None:
                raise ExecutionError("owner_download_required")
            kind, payload = (
                "submission",
                {"session_id": session_id, "response": solo._json(raw_draft)},
            )
        elif action == "confirm-first":
            first = state["case_states"][packet["cases"][0]["case_id"]][
                "active_submission_id"
            ]
            kind, payload = (
                "first_case_verified",
                {
                    "submission_id": first,
                    "validation": "schema-evidence-and-ledger-replay-not-label-truth",
                },
            )
        else:
            raise ExecutionError("unknown_execution_action")
        sequence = len(saved)
        if sequence > LIMITS["max_events"]:
            raise ExecutionError("execution_event_limit")
        body = {
            "schema_version": 1,
            "sequence": sequence,
            "previous_sha256": expected_head,
            "created_at": now.isoformat(),
            "kind": kind,
            "payload": payload,
        }
        head = solo._sha(solo._canonical(body))
        event = {**body, "event_sha256": head}
        _apply_event(event, state, packet, p)
        raw = solo._canonical(event)
        if len(raw) > LIMITS["max_event_bytes"]:
            raise ExecutionError("execution_event_byte_limit")
        solo._reserve(output, 2 * len(raw), guard)
        guard.check()
        recheck()
        if draft is not None:
            solo._private(draft.parent, directory=True)
            solo._private(draft)
            if (
                corpus._read_saved(draft, LIMITS["max_event_bytes"], "owner draft")
                != raw_draft
            ):
                raise ExecutionError("owner_draft_changed")
        solo._verify_ledger(ledger, eventfd, saved)
        check_lock()
        solo._write_payload(eventfd, f"{sequence:012d}.json", raw)
        return _summary(state, head, sequence, p)


def stage_download(
    source: Path,
    policy_path: Path,
    *,
    policy_sha256: str,
    project_root: Path,
    guard: ResourceGuard | None = None,
) -> dict:
    """Copy one explicitly selected owner draft privately, without ledger ingestion.

    Downloads may initially be owner-readable mode 0644; the destination is
    private 0400 beneath 0700. Never change or remove the original download.
    """
    source = Path(source).absolute()
    if ".." in source.parts:
        raise ExecutionError("unsafe_download_path")
    info = source.lstat()
    if info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ExecutionError("download_owner_or_link_mismatch")
    p, packet, output, guard, recheck = _context(
        policy_path, policy_sha256, project_root, guard
    )
    raw = corpus._read_saved(
        source, LIMITS["max_event_bytes"], "selected owner download"
    )
    _validate_response(solo._json(raw), packet, p)
    incoming = output / "incoming"
    solo._private(incoming, directory=True)
    name = "draft-" + solo._sha(raw) + ".json"
    destination = incoming / name
    directory = corpus._open_directory(incoming)
    try:
        solo._reserve(output, 2 * len(raw), guard)
        guard.check()
        recheck()
        current = source.lstat()
        if (current.st_dev, current.st_ino, current.st_uid, current.st_nlink) != (
            info.st_dev,
            info.st_ino,
            info.st_uid,
            info.st_nlink,
        ) or corpus._read_saved(
            source, LIMITS["max_event_bytes"], "selected owner download"
        ) != raw:
            raise ExecutionError("owner_download_changed")
        readiness._same_directory(incoming, directory)
        if destination.exists() or destination.is_symlink():
            solo._private(destination)
            if (
                corpus._read_saved(
                    destination, LIMITS["max_event_bytes"], "staged draft"
                )
                != raw
            ):
                raise ExecutionError("staged_download_corrupted")
        else:
            solo._write_payload(directory, name, raw)
    finally:
        os.close(directory)
    return {
        "status": "staged_not_ingested",
        "path": str(destination),
        "sha256": solo._sha(raw),
        "bytes": len(raw),
    }


def main(argv: list[str] | None = None) -> int:
    """Offline CLI; no network, no inferred approval, and no unpinned operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument(
        "action",
        choices=(
            "activate",
            "status",
            "start-session",
            "submit",
            "confirm-first",
            "stage",
        ),
    )
    parser.add_argument("--expected-head")
    parser.add_argument("--session-id")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    os.umask(0o077)
    sys.addaudithook(solo.deny_network)
    try:
        if args.action == "activate":
            result = {
                "status": "activated_empty",
                "head_sha256": activate(
                    args.policy,
                    policy_sha256=args.policy_sha256,
                    project_root=args.project_root,
                ),
            }
        elif args.action == "stage":
            if args.source is None:
                raise ExecutionError("selected_download_required")
            result = stage_download(
                args.source,
                args.policy,
                policy_sha256=args.policy_sha256,
                project_root=args.project_root,
            )
        else:
            result = operate(
                args.policy,
                policy_sha256=args.policy_sha256,
                project_root=args.project_root,
                expected_head=args.expected_head,
                action=args.action,
                session_id=args.session_id,
                seconds=args.seconds,
                submission_path=args.submission,
            )
        print(solo._canonical(result).decode(), end="")
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(
            solo._canonical(
                {
                    "status": "failed_closed",
                    "error_type": type(exc).__name__,
                    "reason": str(exc)
                    if isinstance(
                        exc, (ExecutionError, ResourceStop, solo.SoloReviewError)
                    )
                    else "invalid_or_inaccessible_execution_artifact",
                }
            ).decode(),
            end="",
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
