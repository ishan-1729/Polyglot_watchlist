"""Offline link preparation; nominations never establish identity or labels.

Callers supply reviewed actor/evidence/adjudication references explicitly. Their
existence is a contract check, not authentication of a human or legal clearance.
This module writes no corpus, partitions, review decisions or real labels.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import re
import unicodedata


RELATIONS = frozenset(
    {
        "record_equivalent",
        "same_entity",
        "dependent_example",
        "related_entity",
        "distinct_entity",
        "dismissed_candidate",
        "unresolved",
    }
)
IDENTITY_RELATIONS = frozenset({"record_equivalent", "same_entity"})
DEPENDENCE_RELATIONS = IDENTITY_RELATIONS | {"dependent_example"}
METHODS = frozenset(
    {"exact_name", "source_referent", "source_key_continuity", "manual_evidence"}
)
READINESS_NORMALIZATION_VERSION = "nfkc-casefold-nfkc-whitespace-v1"
READINESS_NOMINATION_VERSION = "readiness-name-equality-v1"
READINESS_UNICODE_VERSION = unicodedata.unidata_version
READINESS_METHODS = frozenset({"exact_name", "normalized_name"})


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be nonblank unpadded text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be valid Unicode") from exc
    return value


def _strings(value: object, label: str, *, allow_empty: bool = True) -> None:
    if type(value) is not tuple or (not value and not allow_empty):
        raise ValueError(f"{label} must be an immutable tuple")
    for item in value:
        _text(item, label)
    if len(set(value)) != len(value):
        raise ValueError(f"duplicate {label}")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _hash(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("candidate release hash must be a lowercase SHA-256")


@dataclass(frozen=True)
class LinkName:
    evidence_id: str
    value: str

    def __post_init__(self) -> None:
        _text(self.evidence_id, "name evidence ID")
        _text(self.value, "original name")


@dataclass(frozen=True)
class LinkRecord:
    observation_id: str
    source_record_key: tuple[str, str]
    snapshot_id: str
    aliases: tuple[LinkName, ...]
    referents: tuple[tuple[str, str], ...] = ()
    exposure_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.observation_id, "observation ID")
        _text(self.snapshot_id, "snapshot ID")
        for key in (self.source_record_key, *self.referents):
            if type(key) is not tuple or len(key) != 2:
                raise ValueError("source keys must be (source ID, provider ID) tuples")
            for part in key:
                _text(part, "source key part")
        if type(self.referents) is not tuple:
            raise ValueError("referents must be a tuple of qualified keys")
        if len(set(self.referents)) != len(self.referents):
            raise ValueError("duplicate referent")
        if type(self.aliases) is not tuple or not self.aliases:
            raise ValueError("aliases must be a nonempty immutable tuple")
        if any(type(name) is not LinkName for name in self.aliases):
            raise ValueError("aliases must contain LinkName evidence")
        _strings(self.exposure_events, "exposure event")


@dataclass(frozen=True)
class LinkCandidate:
    candidate_id: str
    left: str
    right: str
    method: str
    evidence_refs: tuple[str, ...]
    candidate_release_hash: str

    def __post_init__(self) -> None:
        _text(self.candidate_id, "candidate ID")
        _text(self.left, "left observation")
        _text(self.right, "right observation")
        if self.left >= self.right:
            raise ValueError("candidate endpoints must be distinct and sorted")
        if self.method not in METHODS:
            raise ValueError("unknown nomination method")
        _strings(self.evidence_refs, "nomination evidence", allow_empty=False)
        _hash(self.candidate_release_hash)


def _readiness_hash(value: object, label: str) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")


@dataclass(frozen=True, order=True)
class ReadinessLinkWitness:
    """One equality reason, referencing both complete original name entries."""

    method: str
    left_evidence_id: str
    right_evidence_id: str
    left_original_sha256: str
    right_original_sha256: str

    def __post_init__(self) -> None:
        if type(self.method) is not str or self.method not in READINESS_METHODS:
            raise ValueError("unsupported readiness nomination method")
        _text(self.left_evidence_id, "left name evidence ID")
        _text(self.right_evidence_id, "right name evidence ID")
        if self.left_evidence_id == self.right_evidence_id:
            raise ValueError("readiness witnesses require distinct name evidence")
        _readiness_hash(self.left_original_sha256, "left original name hash")
        _readiness_hash(self.right_original_sha256, "right original name hash")
        if (
            self.method == "exact_name"
            and self.left_original_sha256 != self.right_original_sha256
        ):
            raise ValueError("exact-name witness original hashes must agree")


@dataclass(frozen=True)
class ReadinessLinkNomination:
    """An unreviewed preparation pair, distinct from any corpus-release record.

    A pair can have several name witnesses and both equality methods. It carries
    no identity relation, reviewer origin, label or publication authorization.
    """

    nomination_id: str
    left: str
    right: str
    witnesses: tuple[ReadinessLinkWitness, ...]
    preparation_input_sha256: str
    normalization_version: str = READINESS_NORMALIZATION_VERSION
    nomination_version: str = READINESS_NOMINATION_VERSION
    unicode_version: str = READINESS_UNICODE_VERSION

    def __post_init__(self) -> None:
        _text(self.left, "left observation")
        _text(self.right, "right observation")
        if self.left >= self.right:
            raise ValueError("readiness endpoints must be distinct and sorted")
        _readiness_hash(self.preparation_input_sha256, "preparation input hash")
        if (
            self.normalization_version != READINESS_NORMALIZATION_VERSION
            or self.nomination_version != READINESS_NOMINATION_VERSION
            or self.unicode_version != READINESS_UNICODE_VERSION
        ):
            raise ValueError("unsupported readiness normalization/nomination version")
        if (
            type(self.witnesses) is not tuple
            or not self.witnesses
            or any(type(item) is not ReadinessLinkWitness for item in self.witnesses)
        ):
            raise ValueError("readiness requires immutable typed name witnesses")
        if tuple(sorted(set(self.witnesses))) != self.witnesses:
            raise ValueError("readiness witnesses must be unique and sorted")
        normalized = {
            (
                item.left_evidence_id,
                item.right_evidence_id,
                item.left_original_sha256,
                item.right_original_sha256,
            )
            for item in self.witnesses
            if item.method == "normalized_name"
        }
        if any(
            (
                item.left_evidence_id,
                item.right_evidence_id,
                item.left_original_sha256,
                item.right_original_sha256,
            )
            not in normalized
            for item in self.witnesses
        ):
            raise ValueError("exact readiness witnesses must be a normalized subset")
        if self.nomination_id != _readiness_nomination_id(
            self.left, self.right, self.witnesses, self.preparation_input_sha256
        ):
            raise ValueError("readiness nomination content/hash mismatch")

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(sorted({item.method for item in self.witnesses}))

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    evidence_id
                    for item in self.witnesses
                    for evidence_id in (item.left_evidence_id, item.right_evidence_id)
                }
            )
        )


def _readiness_nomination_id(
    left: str,
    right: str,
    witnesses: tuple[ReadinessLinkWitness, ...],
    preparation_input_sha256: str,
) -> str:
    return "readiness-nomination-" + _digest(
        {
            "preparation_input_sha256": preparation_input_sha256,
            "normalization_version": READINESS_NORMALIZATION_VERSION,
            "nomination_version": READINESS_NOMINATION_VERSION,
            "unicode_version": READINESS_UNICODE_VERSION,
            "left": left,
            "right": right,
            "witnesses": [asdict(item) for item in witnesses],
        }
    )


@dataclass(frozen=True)
class LinkDecision:
    decision_id: str
    left: str
    right: str
    relation: str
    actor_id: str
    adjudication_ref: str
    evidence_refs: tuple[str, ...]
    candidate_release_hash: str
    origin: str = "human"

    def __post_init__(self) -> None:
        for value in (
            self.decision_id,
            self.left,
            self.right,
            self.actor_id,
            self.adjudication_ref,
        ):
            _text(value, "decision reference")
        if self.left >= self.right:
            raise ValueError("decision endpoints must be distinct and sorted")
        if self.relation not in RELATIONS or self.origin != "human":
            raise ValueError("decision requires a known relation and human origin")
        _strings(self.evidence_refs, "decision evidence", allow_empty=False)
        _hash(self.candidate_release_hash)


@dataclass(frozen=True)
class LinkReviewAttestation:
    """A supplied adjudication reference bound to one release, pair and relation."""

    adjudication_id: str
    left: str
    right: str
    relation: str
    actor_id: str
    candidate_release_hash: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (self.adjudication_id, self.left, self.right, self.actor_id):
            _text(value, "attestation reference")
        if (
            self.left >= self.right
            or type(self.relation) is not str
            or self.relation not in RELATIONS
        ):
            raise ValueError("invalid attested pair or relation")
        _hash(self.candidate_release_hash)
        _strings(self.evidence_refs, "attested evidence", allow_empty=False)


@dataclass(frozen=True)
class ReviewRegistry:
    """Externally established references; this object does not authenticate people."""

    actor_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    adjudication_ids: tuple[str, ...] = ()
    attestations: tuple[LinkReviewAttestation, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.actor_ids, self.evidence_ids, self.adjudication_ids):
            _strings(value, "review registry reference")
        if type(self.attestations) is not tuple or any(
            type(item) is not LinkReviewAttestation for item in self.attestations
        ):
            raise ValueError("invalid adjudication attestations")
        ids = [item.adjudication_id for item in self.attestations]
        if len(ids) != len(set(ids)) or set(ids) != set(self.adjudication_ids):
            raise ValueError(
                "each registered adjudication requires one scoped attestation"
            )


@dataclass(frozen=True)
class PreparedGroup:
    group_id: str
    members: tuple[str, ...]
    exposure_events: tuple[str, ...]
    quarantined: bool


@dataclass(frozen=True)
class QuarantineComponent:
    members: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GroupingResult:
    candidate_release_hash: str
    relation_kind: str
    groups: tuple[PreparedGroup, ...]
    quarantine: tuple[QuarantineComponent, ...]
    manifest_hash: str
    decisions: tuple[LinkDecision, ...] = ()
    candidates: tuple[LinkCandidate, ...] = ()
    review_attestations: tuple[LinkReviewAttestation, ...] = ()
    accepted_reviewed_corpus: bool = False

    def __post_init__(self) -> None:
        validate_grouping_result(self)


def validate_grouping_result(result: GroupingResult) -> None:
    """Bind returned memberships/quarantine and reviewed provenance to the digest."""
    if (
        type(result) is not GroupingResult
        or result.accepted_reviewed_corpus is not False
    ):
        raise ValueError("expected a candidate grouping result")
    _hash(result.candidate_release_hash)
    _hash(result.manifest_hash)
    if result.relation_kind not in {"record_equivalence", "leakage_family"}:
        raise ValueError("unsupported grouping relation kind")
    for values, expected_type in (
        (result.groups, PreparedGroup),
        (result.quarantine, QuarantineComponent),
        (result.decisions, LinkDecision),
        (result.candidates, LinkCandidate),
        (result.review_attestations, LinkReviewAttestation),
    ):
        if type(values) is not tuple or any(
            type(item) is not expected_type for item in values
        ):
            raise ValueError("grouping contents must be immutable typed tuples")
    payload = {
        "algorithm": "reviewed-link-preparation-v1",
        "release": result.candidate_release_hash,
        "kind": result.relation_kind,
        "groups": [asdict(group) for group in result.groups],
        "quarantine": [asdict(item) for item in result.quarantine],
        "decisions": [asdict(item) for item in result.decisions],
        "candidates": [asdict(item) for item in result.candidates],
        "review_attestations": [asdict(item) for item in result.review_attestations],
    }
    if _digest(payload) != result.manifest_hash:
        raise ValueError("grouping content/hash mismatch")


def reviewed_pair_relation(result: GroupingResult, left: str, right: str) -> str:
    """Derive identity support from the hashed decisions, never from caller flags."""
    validate_grouping_result(result)
    if result.relation_kind != "leakage_family":
        raise ValueError("pair context requires leakage families")
    members = tuple(member for group in result.groups for member in group.members)
    if left not in members or right not in members:
        raise ValueError("unknown grouping pair endpoint")
    identity = _Components(members)
    for decision in result.decisions:
        if decision.relation in IDENTITY_RELATIONS:
            identity.join(decision.left, decision.right)
    if identity.root(left) == identity.root(right):
        return "same"
    wanted = {identity.root(left), identity.root(right)}
    if any(
        decision.relation == "distinct_entity"
        and {identity.root(decision.left), identity.root(decision.right)} == wanted
        for decision in result.decisions
    ):
        return "distinct"
    return "uncertain"


def _records(records: Sequence[LinkRecord]) -> dict[str, LinkRecord]:
    result: dict[str, LinkRecord] = {}
    observations: set[tuple[str, tuple[str, str]]] = set()
    evidence: set[str] = set()
    for record in records:
        if type(record) is not LinkRecord:
            raise ValueError("records must be LinkRecord objects")
        key = (record.snapshot_id, record.source_record_key)
        if record.observation_id in result or key in observations:
            raise ValueError("duplicate observation or source key within snapshot")
        result[record.observation_id] = record
        observations.add(key)
        for alias in record.aliases:
            if alias.evidence_id in evidence:
                raise ValueError("name evidence IDs must be unique across observations")
            evidence.add(alias.evidence_id)
    if evidence & result.keys():
        raise ValueError("observation and name evidence IDs must not collide")
    return result


def readiness_name_key(value: str) -> str:
    """Normalize complete text for equality nomination, without truncation.

    NFKC folds Unicode compatibility forms; casefold ignores letter case; the
    second NFKC restores normalization after casefold. Whitespace runs become
    one ordinary space. Punctuation, accents and scripts remain meaningful.
    This comparison key never replaces the original source name evidence.
    """
    if type(value) is not str:
        raise ValueError("readiness name must be text")
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(unicodedata.normalize("NFKC", value).split())


def nominate_readiness_links(
    records: Sequence[LinkRecord],
    *,
    preparation_input_sha256: str,
    max_records: int = 20_000,
    max_names: int = 100_000,
    max_pairs: int = 100_000,
    max_witnesses: int = 1_000_000,
    max_name_characters: int = 100_000,
    max_total_name_characters: int = 10_000_000,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[ReadinessLinkNomination, ...]:
    """Bound equality work and retain every witness for each unordered pair.

    All exact witnesses are also normalized witnesses. Counts refer to distinct
    observation pairs, never inferred identities. Limits reject work rather than
    dropping names or witnesses; a checkpoint may raise to stop resource use.
    Qualified source keys remain separate, even when provider IDs are equal.
    """
    _readiness_hash(preparation_input_sha256, "preparation input hash")
    for limit in (
        max_records,
        max_names,
        max_pairs,
        max_witnesses,
        max_name_characters,
        max_total_name_characters,
    ):
        if type(limit) is not int or limit < 0:
            raise ValueError("readiness limits must be finite nonnegative integers")
    if checkpoint is not None and not callable(checkpoint):
        raise ValueError("readiness checkpoint must be callable")
    if not isinstance(records, Sequence):
        raise ValueError("readiness records must be a bounded sequence")
    if len(records) > max_records:
        raise ValueError("readiness record limit exceeded")
    if checkpoint is not None:
        checkpoint()
    work_units = 0

    def tick() -> None:
        nonlocal work_units
        work_units += 1
        if checkpoint is not None and work_units % 256 == 0:
            checkpoint()

    name_count = 0
    character_count = 0
    for record in records:
        if type(record) is not LinkRecord:
            raise ValueError("records must be LinkRecord objects")
        name_count += len(record.aliases)
        if name_count > max_names:
            raise ValueError("readiness name limit exceeded")
        for alias in record.aliases:
            size = len(alias.value)
            character_count += size
            if (
                size > max_name_characters
                or character_count > max_total_name_characters
            ):
                raise ValueError("readiness name character limit exceeded")
            tick()
    indexed = _records(records)
    names: dict[str, dict[str, list[tuple[LinkName, str]]]] = {}
    for record in indexed.values():
        for alias in record.aliases:
            key = readiness_name_key(alias.value)
            if not key:
                raise ValueError("readiness normalization produced an empty name")
            original_hash = hashlib.sha256(alias.value.encode("utf-8")).hexdigest()
            names.setdefault(key, {}).setdefault(record.observation_id, []).append(
                (alias, original_hash)
            )
            tick()
    proposals: dict[tuple[str, str], list[ReadinessLinkWitness]] = {}
    witness_count = 0
    for matches in names.values():
        for left, right in itertools.combinations(sorted(matches), 2):
            pair = (left, right)
            if pair not in proposals:
                if len(proposals) >= max_pairs:
                    raise ValueError("readiness pair limit exceeded")
                proposals[pair] = []
            for (first, first_hash), (second, second_hash) in itertools.product(
                matches[left], matches[right]
            ):
                methods = (
                    ("exact_name", "normalized_name")
                    if first.value == second.value
                    else ("normalized_name",)
                )
                witness_count += len(methods)
                if witness_count > max_witnesses:
                    raise ValueError("readiness witness limit exceeded")
                for method in methods:
                    proposals[pair].append(
                        ReadinessLinkWitness(
                            method,
                            first.evidence_id,
                            second.evidence_id,
                            first_hash,
                            second_hash,
                        )
                    )
                tick()
    result = []
    for (left, right), evidence in sorted(proposals.items()):
        witnesses = tuple(sorted(evidence))
        result.append(
            ReadinessLinkNomination(
                _readiness_nomination_id(
                    left, right, witnesses, preparation_input_sha256
                ),
                left,
                right,
                witnesses,
                preparation_input_sha256,
            )
        )
        tick()
    if checkpoint is not None:
        checkpoint()
    return tuple(result)


def validate_readiness_links(
    records: Sequence[LinkRecord],
    nominations: Sequence[ReadinessLinkNomination],
    *,
    preparation_input_sha256: str,
    max_records: int = 20_000,
    max_names: int = 100_000,
    max_pairs: int = 100_000,
    max_witnesses: int = 1_000_000,
    max_name_characters: int = 100_000,
    max_total_name_characters: int = 10_000_000,
    checkpoint: Callable[[], None] | None = None,
) -> None:
    """Reject stale, missing or altered equality nominations by recomputation."""
    if not isinstance(nominations, Sequence):
        raise ValueError("readiness nominations must be a bounded sequence")
    if type(max_pairs) is not int or max_pairs < 0 or len(nominations) > max_pairs:
        raise ValueError("readiness pair limit exceeded")
    if type(max_witnesses) is not int or max_witnesses < 0:
        raise ValueError("readiness witness limit must be a nonnegative integer")
    witness_count = 0
    for item in nominations:
        if type(item) is not ReadinessLinkNomination:
            raise ValueError("readiness requires preparation nominations")
        if item.preparation_input_sha256 != preparation_input_sha256:
            raise ValueError("readiness nomination belongs to another preparation")
        witness_count += len(item.witnesses)
        if witness_count > max_witnesses:
            raise ValueError("readiness witness limit exceeded")
    expected = nominate_readiness_links(
        records,
        preparation_input_sha256=preparation_input_sha256,
        max_records=max_records,
        max_names=max_names,
        max_pairs=max_pairs,
        max_witnesses=max_witnesses,
        max_name_characters=max_name_characters,
        max_total_name_characters=max_total_name_characters,
        checkpoint=checkpoint,
    )
    if tuple(sorted(nominations, key=lambda item: (item.left, item.right))) != expected:
        raise ValueError("readiness nominations do not match complete source evidence")


def nominate_links(
    records: Sequence[LinkRecord], *, candidate_release_hash: str
) -> tuple[LinkCandidate, ...]:
    """Nominate exact names, qualified referents and continuity; never merge."""
    _hash(candidate_release_hash)
    indexed = _records(records)
    names: dict[str, list[tuple[str, str]]] = defaultdict(list)
    keys: dict[tuple[str, str], list[str]] = defaultdict(list)
    proposals: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in indexed.values():
        keys[record.source_record_key].append(record.observation_id)
        for alias in record.aliases:
            names[alias.value].append((record.observation_id, alias.evidence_id))
    for matches in names.values():
        for (left, first), (right, second) in itertools.combinations(matches, 2):
            if left != right:
                a, b = sorted((left, right))
                proposals[(a, b, "exact_name")].update((first, second))
    for matches in keys.values():
        for left, right in itertools.combinations(sorted(matches), 2):
            proposals[(left, right, "source_key_continuity")].update((left, right))
    for record in indexed.values():
        for referent in record.referents:
            for target in keys.get(referent, ()):
                if target != record.observation_id:
                    left, right = sorted((record.observation_id, target))
                    proposals[(left, right, "source_referent")].update((left, right))
    return tuple(
        LinkCandidate(
            "nomination-" + _digest([candidate_release_hash, key, sorted(evidence)]),
            *key,
            tuple(sorted(evidence)),
            candidate_release_hash,
        )
        for key, evidence in sorted(proposals.items())
    )


def validate_link_decisions(
    records: Sequence[LinkRecord],
    candidates: Sequence[LinkCandidate],
    decisions: Sequence[LinkDecision],
    *,
    candidate_release_hash: str,
    registry: ReviewRegistry = ReviewRegistry(),
) -> None:
    """Reject stale, unsupported or duplicate active decisions before closure.

    Rejection of a nomination is not a distinct-entity label. Supporting review
    evidence must be registered separately from the names that nominated it.
    """
    _hash(candidate_release_hash)
    indexed = _records(records)
    if type(registry) is not ReviewRegistry:
        raise ValueError("an explicit review registry is required")
    observation_evidence = set(indexed)
    for record in indexed.values():
        observation_evidence.update(name.evidence_id for name in record.aliases)
    if observation_evidence & set(registry.evidence_ids):
        raise ValueError("review support must be separate from nomination evidence")
    pairs: set[tuple[str, str]] = set()
    candidate_ids: set[str] = set()
    for candidate in candidates:
        if type(candidate) is not LinkCandidate:
            raise ValueError("invalid nomination object")
        if candidate.candidate_id in candidate_ids:
            raise ValueError("duplicate nomination ID")
        candidate_ids.add(candidate.candidate_id)
        if candidate.candidate_release_hash != candidate_release_hash:
            raise ValueError("nomination belongs to another candidate release")
        if not {candidate.left, candidate.right} <= indexed.keys():
            raise ValueError("nomination has unknown endpoints")
        if not set(candidate.evidence_refs) <= observation_evidence | set(
            registry.evidence_ids
        ):
            raise ValueError("unknown nomination evidence")
        pairs.add((candidate.left, candidate.right))
    seen_pairs: set[tuple[str, str]] = set()
    decision_ids: set[str] = set()
    for decision in decisions:
        if type(decision) is not LinkDecision:
            raise ValueError("invalid reviewed decision object")
        pair = (decision.left, decision.right)
        if (
            pair not in pairs
            or decision.candidate_release_hash != candidate_release_hash
        ):
            raise ValueError("decision is not bound to this nominated release/pair")
        if pair in seen_pairs or decision.decision_id in decision_ids:
            raise ValueError("multiple active decisions; preserve revisions separately")
        seen_pairs.add(pair)
        decision_ids.add(decision.decision_id)
        if decision.actor_id not in registry.actor_ids:
            raise ValueError("unregistered human reviewer")
        if decision.adjudication_ref not in registry.adjudication_ids:
            raise ValueError("missing registered adjudication")
        if not set(decision.evidence_refs) <= set(registry.evidence_ids):
            raise ValueError("decision lacks registered supporting review evidence")
        attestation = next(
            item
            for item in registry.attestations
            if item.adjudication_id == decision.adjudication_ref
        )
        expected = LinkReviewAttestation(
            decision.adjudication_ref,
            decision.left,
            decision.right,
            decision.relation,
            decision.actor_id,
            decision.candidate_release_hash,
            decision.evidence_refs,
        )
        if attestation != expected:
            raise ValueError("adjudication attestation does not cover this decision")


class _Components:
    def __init__(self, members: Sequence[str]) -> None:
        self.parent = {member: member for member in members}

    def root(self, member: str) -> str:
        while self.parent[member] != member:
            self.parent[member] = self.parent[self.parent[member]]
            member = self.parent[member]
        return member

    def join(self, left: str, right: str) -> None:
        a, b = sorted((self.root(left), self.root(right)))
        self.parent[b] = a

    def groups(self) -> tuple[tuple[str, ...], ...]:
        result: dict[str, list[str]] = defaultdict(list)
        for member in sorted(self.parent):
            result[self.root(member)].append(member)
        return tuple(sorted(tuple(group) for group in result.values()))


def _build_groups(
    records: Sequence[LinkRecord],
    candidates: Sequence[LinkCandidate],
    decisions: Sequence[LinkDecision],
    *,
    candidate_release_hash: str,
    registry: ReviewRegistry,
    relation_kind: str,
) -> GroupingResult:
    validate_link_decisions(
        records,
        candidates,
        decisions,
        candidate_release_hash=candidate_release_hash,
        registry=registry,
    )
    indexed = _records(records)
    group_components = _Components(tuple(indexed))
    identity = _Components(tuple(indexed))
    affected = _Components(tuple(indexed))
    decision_map = {(item.left, item.right): item for item in decisions}
    unresolved: set[str] = set()
    for decision in decisions:
        if decision.relation in IDENTITY_RELATIONS:
            identity.join(decision.left, decision.right)
        if decision.relation in DEPENDENCE_RELATIONS:
            affected.join(decision.left, decision.right)
        if decision.relation == "record_equivalent" or (
            relation_kind == "leakage_family"
            and decision.relation in DEPENDENCE_RELATIONS
        ):
            group_components.join(decision.left, decision.right)
    for candidate in candidates:
        decision = decision_map.get((candidate.left, candidate.right))
        if decision is None or decision.relation == "unresolved":
            affected.join(candidate.left, candidate.right)
            unresolved.update((candidate.left, candidate.right))
    conflicting: set[str] = set()
    for decision in decisions:
        if decision.relation == "distinct_entity" and identity.root(
            decision.left
        ) == identity.root(decision.right):
            conflicting.update((decision.left, decision.right))
    quarantines = []
    exposure_by_member: dict[str, tuple[str, ...]] = {}
    quarantine_members: set[str] = set()
    for members in affected.groups():
        events = tuple(
            sorted(
                {
                    event
                    for member in members
                    for event in indexed[member].exposure_events
                }
            )
        )
        for member in members:
            exposure_by_member[member] = events
        reasons = []
        if unresolved.intersection(members):
            reasons.append("unresolved_duplicate_link")
        if conflicting.intersection(members):
            reasons.append("transitive_identity_conflict")
        if reasons:
            quarantines.append(QuarantineComponent(members, tuple(reasons)))
            quarantine_members.update(members)
    groups = tuple(
        PreparedGroup(
            relation_kind
            + "-"
            + _digest([candidate_release_hash, relation_kind, members]),
            members,
            tuple(
                sorted(
                    {
                        event
                        for member in members
                        for event in exposure_by_member[member]
                    }
                )
            ),
            bool(quarantine_members.intersection(members)),
        )
        for members in group_components.groups()
    )
    payload = {
        "algorithm": "reviewed-link-preparation-v1",
        "release": candidate_release_hash,
        "kind": relation_kind,
        "groups": [asdict(group) for group in groups],
        "quarantine": [asdict(item) for item in quarantines],
        "decisions": [
            asdict(item)
            for item in sorted(decisions, key=lambda item: item.decision_id)
        ],
        "candidates": [
            asdict(item)
            for item in sorted(candidates, key=lambda item: item.candidate_id)
        ],
        "review_attestations": [
            asdict(item)
            for item in sorted(
                registry.attestations, key=lambda item: item.adjudication_id
            )
        ],
    }
    return GroupingResult(
        candidate_release_hash,
        relation_kind,
        groups,
        tuple(quarantines),
        _digest(payload),
        decisions=tuple(sorted(decisions, key=lambda item: item.decision_id)),
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        review_attestations=tuple(
            sorted(registry.attestations, key=lambda item: item.adjudication_id)
        ),
    )


def build_record_groups(
    records: Sequence[LinkRecord],
    candidates: Sequence[LinkCandidate],
    decisions: Sequence[LinkDecision] = (),
    *,
    candidate_release_hash: str,
    registry: ReviewRegistry = ReviewRegistry(),
) -> GroupingResult:
    """Prepare record-copy components, preserving quarantine and exposure."""
    return _build_groups(
        records,
        candidates,
        decisions,
        candidate_release_hash=candidate_release_hash,
        registry=registry,
        relation_kind="record_equivalence",
    )


def build_leakage_families(
    records: Sequence[LinkRecord],
    candidates: Sequence[LinkCandidate],
    decisions: Sequence[LinkDecision] = (),
    *,
    candidate_release_hash: str,
    registry: ReviewRegistry = ReviewRegistry(),
) -> GroupingResult:
    """Prepare conservative dependent families without assigning partitions."""
    return _build_groups(
        records,
        candidates,
        decisions,
        candidate_release_hash=candidate_release_hash,
        registry=registry,
        relation_kind="leakage_family",
    )
