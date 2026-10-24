"""Frozen evaluation views, labeled query ancestry and conservative overlap checks."""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Sequence

from watchlist.entities import Alias, Entity, Provenance
from watchlist.normalize import normalize_name
from watchlist.perturbations import script_category, variants


def fingerprint(value: object) -> str:
    """Hash canonical JSON rather than process-dependent Python hashes."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _validate_legacy_partitions(entities: Sequence[Entity], assignments: dict) -> None:
    """Require exact ID coverage and one partition per explicit provider group."""
    ids = [e.entity_id for e in entities]
    if len(ids) != len(set(ids)) or set(ids) != set(assignments):
        raise ValueError("partition coverage or duplicate entity ID error")
    groups: dict[str, set[str]] = {}
    allowed = {"train", "development", "test", "calibration_fit", "threshold_selection", "ambiguity"}
    for item in assignments.values():
        if item.get("partition") not in allowed or not item.get("group_id"):
            raise ValueError("invalid partition or group")
        groups.setdefault(item["group_id"], set()).add(item["partition"])
    if any(len(parts) != 1 for parts in groups.values()):
        raise ValueError("entity group leakage across partitions")


def _build_legacy_payload(entities: Sequence[Entity], assignments: dict, *, seed: int = 42,
                    absent: list[dict] | None = None) -> tuple[dict, list[dict], dict]:
    """Create full/held-out views before retrieval; ambiguous overlaps stay diagnostic.

    One alias per eligible entity is held out, selected by stable alias ID. All
    normalized-equivalent copies are removed. All remaining aliases generate
    perturbations; only development/test/ambiguity groups generate queries.
    """
    _validate_legacy_partitions(entities, assignments)
    ordered = tuple(replace(e, aliases=tuple(sorted(e.aliases, key=lambda a: a.alias_id)))
                    for e in sorted(entities, key=lambda e: e.entity_id))
    source_hash = fingerprint([asdict(e) for e in ordered])
    held, held_view = {}, []
    for entity in ordered:
        aliases = sorted(entity.aliases, key=lambda a: a.alias_id)
        if len({normalize_name(a.name) for a in aliases}) > 1:
            chosen = aliases[-1]
            held[entity.entity_id] = chosen
            aliases = [a for a in aliases if normalize_name(a.name) != normalize_name(chosen.name)]
        held_view.append(replace(entity, aliases=tuple(aliases)))
    views = {"full": ordered, "heldout": tuple(held_view)}
    names: dict[str, set[str]] = {}
    for entity in ordered:
        for alias in entity.aliases:
            names.setdefault(normalize_name(alias.name), set()).add(entity.entity_id)
    queries, skipped = [], []
    for entity in ordered:
        assignment = assignments[entity.entity_id]
        if assignment["partition"] not in {"development", "test", "ambiguity"}:
            continue
        cases = [(a, v, "full") for a in sorted(entity.aliases, key=lambda a: a.alias_id)
                 for v in variants(a.name, a.alias_id, seed)]
        if entity.entity_id in held:
            a = held[entity.entity_id]
            cases.append((a, {"kind": "heldout_alias", "text": a.name,
                              "operation": "remove normalized equivalent aliases from target reference"}, "heldout"))
        else:
            skipped.append({"entity_id": entity.entity_id, "kind": "heldout_alias", "reason": "only one normalized name"})
        for alias, variant, view in cases:
            base = {"entity_id": entity.entity_id, "alias_id": alias.alias_id, "kind": variant["kind"]}
            if variant["text"] is None:
                skipped.append({**base, "reason": variant["operation"]})
                continue
            try:
                normalized = normalize_name(variant["text"])
            except ValueError as exc:
                skipped.append({**base, "reason": str(exc)})
                continue
            kind = variant["kind"]
            if kind not in {"exact", "formatting", "heldout_alias"} and normalized == normalize_name(alias.name):
                skipped.append({**base, "reason": "no normalized change"})
                continue
            collisions = sorted(names.get(normalized, set()) - {entity.entity_id})
            in_index = sorted(e.entity_id for e in views[view]
                              if any(normalize_name(a.name) == normalized for a in e.aliases))
            diagnostic = bool(collisions) or assignment["partition"] == "ambiguity"
            reason = "ambiguous record name" if diagnostic else None
            if kind not in {"exact", "formatting"} and in_index and not diagnostic:
                diagnostic, reason = True, "query already appears in reference"
            query = {"query_id": fingerprint([source_hash, base, seed, view]),
                     "text": variant["text"], "normalized": normalized, "target_id": entity.entity_id,
                     "group_id": assignment["group_id"], "partition": assignment["partition"],
                     "alias_id": alias.alias_id, "base_text": alias.name, "kind": kind,
                     "operation": variant["operation"], "seed": seed, "view": view,
                     "script": script_category(variant["text"]),
                     "reference_scripts": sorted({script_category(a.name) for e in views[view]
                                                   if e.entity_id == entity.entity_id for a in e.aliases}),
                     "status": "diagnostic" if diagnostic else "positive", "reason": reason,
                     "colliding_entity_ids": collisions, "index_exact_ids": in_index,
                     "source_fingerprint": source_hash, "source": entity.source,
                     "provenance": asdict(entity.provenance) if entity.provenance else None}
            queries.append(query)
    for item in absent or []:
        normalized = normalize_name(item["text"])
        if normalized in names:
            raise ValueError("absent query collides with a reference alias")
        queries.append({"query_id": fingerprint([source_hash, "absent", item]), "text": item["text"],
                        "normalized": normalized, "target_id": None, "group_id": item["id"],
                        "partition": "absent", "alias_id": None, "base_text": item["text"],
                        "kind": "absent", "operation": "authored absent target", "seed": seed,
                        "view": "full", "script": script_category(item["text"]), "reference_scripts": [],
                        "status": "absent", "reason": None, "colliding_entity_ids": [], "index_exact_ids": [],
                        "source_fingerprint": source_hash, "source": "authored-fictional-absent", "provenance": None})
    # Repeated strings across independent partitions are not allowed in headline metrics.
    owners: dict[str, set[str]] = {}
    for q in queries:
        owners.setdefault(q["normalized"], set()).add(q["partition"])
    seen = set()
    for q in queries:
        if len(owners[q["normalized"]]) > 1:
            q.update(status="diagnostic", reason="normalized query crosses partitions")
        key = (q["partition"], q["target_id"], q["kind"], q["view"], q["normalized"])
        if key in seen:
            q.update(status="diagnostic", reason="duplicate normalized query within slice")
        seen.add(key)
    _audit_legacy_ancestry(queries, views, assignments)
    audit = {"source_fingerprint": source_hash, "skipped": skipped,
             "shared_aliases": [{"normalized": n, "entity_ids": sorted(ids)} for n, ids in sorted(names.items()) if len(ids)>1],
             "view_fingerprints": {k: fingerprint([asdict(e) for e in v]) for k,v in views.items()},
             "assignments": assignments}
    return views, queries, audit


def _audit_legacy_ancestry(queries: list[dict], views: dict, assignments: dict) -> None:
    """Reject broken ancestry, leaked withheld aliases, and mislabeled targets."""
    if len({q["query_id"] for q in queries}) != len(queries):
        raise ValueError("duplicate query IDs")
    for q in queries:
        target = q["target_id"]
        if target is None:
            continue
        if target not in assignments or q["partition"] != assignments[target]["partition"] or q["group_id"] != assignments[target]["group_id"]:
            raise ValueError("query ancestry leakage")
        entity = next((e for e in views[q["view"]] if e.entity_id == target), None)
        if entity is None:
            raise ValueError("positive target missing from reference")
        if q["kind"] == "heldout_alias" and any(normalize_name(a.name) == q["normalized"] for a in entity.aliases):
            raise ValueError("held-out alias leakage")


PROTOCOL_VERSION = 'evaluation-v2'


def _canonical(value: object) -> str:
    """Use finite JSON for new contracts without changing historical hashes."""
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
        encoded.encode('utf-8')
        return encoded
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError('benchmark data must have a finite JSON representation') from exc


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{label} must be a nonblank unpadded string')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError(f'{label} must be UTF-8 text') from exc
    return value


def _normalized_text(value: object) -> str:
    """Validate original Unicode text before normalization or fingerprinting."""
    if not isinstance(value, str):
        raise ValueError('benchmark name must be text')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('benchmark name must be valid UTF-8 text') from exc
    return normalize_name(value)


def _ordered_source(entities: Sequence[Entity]) -> tuple[Entity, ...]:
    """Check global alias ownership and freeze the complete original records."""
    if not isinstance(entities, Sequence) or isinstance(entities, (str, bytes)):
        raise ValueError('benchmark source must be a sequence of Entity records')
    seen_entities, seen_aliases = set(), set()
    ordered = []
    for entity in entities:
        if not isinstance(entity, Entity):
            raise ValueError('benchmark source must contain Entity records')
        identifier = _identifier(entity.entity_id, 'entity ID')
        if identifier in seen_entities:
            raise ValueError('duplicate entity ID')
        seen_entities.add(identifier)
        _normalized_text(entity.name)
        _identifier(entity.source, 'source')
        if (not isinstance(entity.entity_type, str)
                or entity.entity_type not in {'person', 'organisation', 'legal_entity'}
                or type(entity.synthetic) is not bool):
            raise ValueError('invalid source entity type or origin')
        if entity.provenance is not None and not isinstance(entity.provenance, Provenance):
            raise ValueError('source provenance must be an owned Provenance record')
        if not isinstance(entity.aliases, (list, tuple)) or not entity.aliases:
            raise ValueError('source entity must have an owned alias')
        for alias in entity.aliases:
            if not isinstance(alias, Alias):
                raise ValueError('source aliases must be owned Alias records')
            alias_id = _identifier(alias.alias_id, 'alias ID')
            if alias_id in seen_aliases:
                raise ValueError('alias ID has duplicate ownership')
            seen_aliases.add(alias_id)
            _normalized_text(alias.name)
        ordered.append(replace(entity, aliases=tuple(sorted(entity.aliases, key=lambda alias: alias.alias_id))))
    result = tuple(sorted(ordered, key=lambda entity: entity.entity_id))
    _canonical([asdict(entity) for entity in result])
    return result


def validate_partitions(entities: Sequence[Entity], assignments: dict) -> None:
    """Validate the five independent partition roles and owned source IDs."""
    from watchlist.splits import validate_assignments
    ordered = _ordered_source(entities)
    validate_assignments([entity.entity_id for entity in ordered], assignments)


def _view_data(views: dict) -> dict:
    try:
        return {name: [asdict(entity) for entity in entities] for name, entities in views.items()}
    except (TypeError, AttributeError) as exc:
        raise ValueError('invalid benchmark reference view') from exc


def _retained_display(entity: Entity) -> Entity:
    """Prevent display metadata from revealing an alias absent from this view."""
    retained = {normalize_name(alias.name) for alias in entity.aliases}
    display = entity.name if normalize_name(entity.name) in retained else entity.aliases[0].name
    return replace(entity, name=display)


def _validate_views(entities: tuple[Entity, ...], views: dict, *, legacy: bool = False) -> dict[str, tuple[Entity, ...]]:
    """Validate owned subsets, then derive a display name from retained aliases.

    Historical display names remain unchanged only for explicit legacy replay.
    New retrieval views must not expose a removed alias through ``Entity.name``.
    """
    if not isinstance(views, dict) or not views:
        raise ValueError('benchmark requires named reference views')
    originals = {entity.entity_id: entity for entity in entities}
    result = {}
    for name, members in views.items():
        _identifier(name, 'view name')
        if not isinstance(members, (list, tuple)):
            raise ValueError('reference view must be a sequence of Entity records')
        seen, checked = set(), []
        for member in members:
            if not isinstance(member, Entity) or member.entity_id not in originals or member.entity_id in seen:
                raise ValueError('reference view contains an unknown or duplicate entity')
            seen.add(member.entity_id)
            original = originals[member.entity_id]
            if (replace(member, aliases=original.aliases) != original
                    or not isinstance(member.aliases, (list, tuple)) or not member.aliases
                    or any(not isinstance(alias, Alias) for alias in member.aliases)):
                raise ValueError('reference view changed entity metadata or removed all aliases')
            aliases = {alias.alias_id: alias for alias in original.aliases}
            if len({alias.alias_id for alias in member.aliases}) != len(member.aliases):
                raise ValueError('reference view duplicates an alias')
            if any(aliases.get(alias.alias_id) != alias for alias in member.aliases):
                raise ValueError('reference view changed alias ownership or text')
            reference = replace(member, aliases=tuple(member.aliases))
            checked.append(reference if legacy else _retained_display(reference))
        result[name] = tuple(checked)
    return result


@dataclass(frozen=True)
class _AuditContext:
    """Immutable evaluator evidence; this is an integrity contract, not a sandbox."""
    protocol_version: str
    regression_only: bool
    original_json: str
    assignments_json: str
    views_json: str
    queries_json: tuple[tuple[str, str], ...]


class BenchmarkViews(dict):
    """Reference views with a sealed source/query manifest kept by the evaluator.

    Search functions receive only the selected tuple of Entity records. The
    private manifest contains withheld ancestry and labels and must never be
    passed to a retriever. Arbitrary Python reflection is outside this contract.
    """
    __slots__ = ('__audit_context',)

    def __init__(self, views: dict, context: _AuditContext):
        super().__init__(views)
        self.__audit_context = context

    @property
    def protocol_version(self) -> str:
        return self.__audit_context.protocol_version

    @property
    def regression_only(self) -> bool:
        return self.__audit_context.regression_only

    def _context(self) -> _AuditContext:
        return self.__audit_context


def _bind(entities: tuple[Entity, ...], assignments: dict, views: dict, queries: list[dict], *, legacy: bool) -> BenchmarkViews:
    ids = [query['query_id'] for query in queries]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate query IDs')
    context = _AuditContext('phase3-v1' if legacy else PROTOCOL_VERSION, legacy,
                            _canonical([asdict(entity) for entity in entities]),
                            _canonical(assignments), _canonical(_view_data(views)),
                            tuple((query['query_id'], _canonical(query)) for query in queries))
    return BenchmarkViews(views, context)


def audit_queries(queries: list[dict], views: dict, assignments: dict | None = None, *,
                  regression_only: bool = False) -> None:
    """Check every row, including absent rows, against immutable creation evidence.

    Valid subsets and reorderings are allowed. The caller cannot approve changed
    labels or views by recomputing their public hashes or changing assignments.
    Legacy rows require an explicit regression-only context and opt-in.
    """
    if not isinstance(views, BenchmarkViews):
        raise ValueError('benchmark requires a bound immutable audit context')
    context = views._context()
    if type(regression_only) is not bool or context.regression_only != regression_only:
        raise ValueError('legacy benchmark requires explicit regression_only=True')
    if _canonical(_view_data(views)) != context.views_json:
        raise ValueError('held-out/reference view changed from its immutable audit context')
    if assignments is not None and _canonical(assignments) != context.assignments_json:
        raise ValueError('query ancestry assignments changed from their immutable context')
    if not isinstance(queries, (list, tuple)) or any(not isinstance(query, dict) for query in queries):
        raise ValueError('queries must be a sequence of query objects')
    expected = dict(context.queries_json)
    seen = set()
    for query in queries:
        query_id = query.get('query_id')
        if not isinstance(query_id, str) or query_id in seen:
            raise ValueError('invalid or duplicate query IDs')
        seen.add(query_id)
        if query_id not in expected or _canonical(query) != expected[query_id]:
            raise ValueError('query ancestry, labels or generation differ from immutable source evidence')


def query_labels(query: dict, *, regression_only: bool = False) -> dict[str, str]:
    """Expose independent label axes; legacy diagnostics are not adjudications."""
    if not isinstance(query, dict) or type(regression_only) is not bool:
        raise ValueError('labels require a query object and an explicit boolean legacy mode')
    if query.get('protocol_version') == PROTOCOL_VERSION:
        presence, ambiguity = query.get('presence'), query.get('ambiguity')
        if (not isinstance(presence, str) or presence not in {'present', 'absent'}
                or not isinstance(ambiguity, str) or ambiguity not in {'unambiguous', 'ambiguous', 'unlabelable'}):
            raise ValueError('invalid presence or ambiguity label')
        if (query.get('target_id') is None) != (presence == 'absent'):
            raise ValueError('presence label contradicts target ownership')
        status = 'diagnostic' if ambiguity != 'unambiguous' else 'positive' if presence == 'present' else 'absent'
        if query.get('status') != status:
            raise ValueError('status conflicts with independent labels')
    elif regression_only and 'protocol_version' not in query:
        status = query.get('status')
        if status not in {'positive', 'absent', 'diagnostic'}:
            raise ValueError('unsupported legacy label')
        presence = 'absent' if query.get('target_id') is None else 'present'
        ambiguity = 'unlabelable' if status == 'diagnostic' else 'unambiguous'
        if status == 'positive' and presence != 'present' or status == 'absent' and presence != 'absent':
            raise ValueError('legacy label contradicts target presence')
    else:
        raise ValueError('unsupported query protocol; legacy labels require regression_only=True')
    return {'presence': presence, 'ambiguity': ambiguity, 'status': status}


def _validate_absent(absent: list[dict], entities: tuple[Entity, ...], assignments: dict, *, legacy: bool) -> None:
    """Validate authored absence relative to this fixed source, not world identity."""
    from watchlist.splits import PARTITION_NAMES
    if not isinstance(absent, list):
        raise ValueError('absent declarations must be a list of query objects')
    forbidden_ids = set(assignments) | {item['group_id'] for item in assignments.values()}
    names = {normalize_name(alias.name) for entity in entities for alias in entity.aliases}
    seen_ids, seen_names = set(), set()
    for item in absent:
        allowed = {'id', 'text'} if legacy else {'id', 'text', 'partition'}
        if not isinstance(item, dict) or set(item) != allowed:
            raise ValueError('absent query requires explicit id, text and partition in the current protocol')
        identifier = _identifier(item['id'], 'absent group ID')
        normalized = _normalized_text(item['text'])
        if identifier in forbidden_ids or identifier in seen_ids:
            raise ValueError('absent query group collides with another family or declaration')
        if normalized in names or normalized in seen_names:
            raise ValueError('absent query collides with a reference alias or another absent declaration')
        if not legacy and (not isinstance(item['partition'], str) or item['partition'] not in PARTITION_NAMES):
            raise ValueError('absent query must have an independent partition role')
        seen_ids.add(identifier)
        seen_names.add(normalized)


def _decorate(query: dict, entities: tuple[Entity, ...], views: dict, *, generator: str) -> dict:
    from watchlist.scripts import script_set
    result = dict(query)
    result.pop('query_id', None)
    target = result['target_id']
    selected = views[result['view']]
    scripts = sorted(script_set(result['text']))
    result.update(protocol_version=PROTOCOL_VERSION,
                  presence='absent' if target is None else 'present',
                  scripts=scripts, script='+'.join(scripts) or 'NONE',
                  reference_scripts=sorted({script for entity in selected if entity.entity_id == target
                                            for alias in entity.aliases for script in script_set(alias.name)}),
                  view_fingerprint=fingerprint([asdict(entity) for entity in selected]),
                  generation={'generator': generator, 'parent_alias_id': result['alias_id'],
                              'seed': result['seed'] if generator == 'deterministic-variants-v1' else None,
                              'operation': result['operation']})
    names: dict[str, set[str]] = {}
    for entity in entities:
        for alias in entity.aliases:
            names.setdefault(normalize_name(alias.name), set()).add(entity.entity_id)
    result['colliding_entity_ids'] = sorted(names.get(result['normalized'], set()) - {target})
    result['base_colliding_entity_ids'] = sorted(names.get(normalize_name(result['base_text']), set()) - {target})
    result['index_exact_ids'] = sorted(entity.entity_id for entity in selected
                                     if any(normalize_name(alias.name) == result['normalized'] for alias in entity.aliases))
    return result


def _label_queries(queries: list[dict]) -> None:
    """Derive exclusions from the complete authored corpus before taking subsets."""
    partitions, targets, seen = {}, {}, set()
    for query in queries:
        partitions.setdefault(query['normalized'], set()).add(query['partition'])
        targets.setdefault(query['normalized'], set()).add(query['target_id'])
    for query in queries:
        related = targets[query['normalized']]
        reasons = []
        ambiguous = bool(query['colliding_entity_ids'] or query['base_colliding_entity_ids'] or len(related - {None}) > 1)
        if ambiguous:
            reasons.append('ambiguous record name')
        if query.get('legacy_partition') == 'ambiguity':
            reasons.append('legacy ambiguity retained only as development diagnostic')
        if None in related and len(related) > 1:
            reasons.append('conflicting authored presence labels')
        if len(partitions[query['normalized']]) > 1:
            reasons.append('normalized query crosses partitions')
        if query['kind'] not in {'exact', 'formatting'} and query['index_exact_ids'] and not ambiguous:
            reasons.append('query already appears in reference')
        key = (query['partition'], query['target_id'], query['kind'], query['view'], query['normalized'])
        if key in seen:
            reasons.append('duplicate normalized query within slice')
        seen.add(key)
        query['ambiguity'] = 'ambiguous' if ambiguous else 'unlabelable' if reasons else 'unambiguous'
        query['status'] = 'diagnostic' if reasons else 'positive' if query['presence'] == 'present' else 'absent'
        query['reason'] = reasons[0] if reasons else None
        query['exclusion_reasons'] = reasons
        query['query_id'] = fingerprint([PROTOCOL_VERSION, query])


def _current_result(entities: tuple[Entity, ...], assignments: dict, views: dict, queries: list[dict], skipped: list) -> tuple[dict, list[dict], dict]:
    from watchlist.scripts import SCRIPT_METHOD, UNICODE_VERSION
    _label_queries(queries)
    bound = _bind(entities, assignments, views, queries, legacy=False)
    audit_queries(queries, bound, assignments)
    names: dict[str, set[str]] = {}
    for entity in entities:
        for alias in entity.aliases:
            names.setdefault(normalize_name(alias.name), set()).add(entity.entity_id)
    audit = {'protocol_version': PROTOCOL_VERSION, 'usage': 'research_evaluation',
             'script_analysis': {'method': SCRIPT_METHOD, 'unicode_version': UNICODE_VERSION},
             'source_fingerprint': fingerprint([asdict(entity) for entity in entities]),
             'queries_fingerprint': fingerprint(queries), 'skipped': skipped,
             'shared_aliases': [{'normalized': name, 'entity_ids': sorted(ids)} for name, ids in sorted(names.items()) if len(ids) > 1],
             'view_fingerprints': {name: fingerprint([asdict(entity) for entity in members]) for name, members in views.items()},
             'assignments': json.loads(_canonical(assignments)),
             'legacy_partition_mappings': [{'target_id': query['target_id'], 'original_partition': query['legacy_partition'],
                                            'partition': query['partition'], 'usage': 'diagnostic'}
                                           for query in queries if 'legacy_partition' in query]}
    return bound, queries, audit


def build_benchmark(entities: Sequence[Entity], assignments: dict, *, seed: int = 42,
                    absent: list[dict] | None = None,
                    legacy_partitions: dict[str, str] | None = None) -> tuple[dict, list[dict], dict]:
    """Build development/test queries with independent presence/ambiguity labels.

    Reserved training/calibration/threshold families remain in the reference
    but never generate evaluation rows. An explicit legacy ambiguity mapping
    may retain old exposed examples only as development diagnostics.
    """
    from watchlist.splits import validate_seed
    validate_seed(seed)
    ordered = _ordered_source(entities)
    validate_partitions(ordered, assignments)
    authored_absent = [] if absent is None else absent
    _validate_absent(authored_absent, ordered, assignments, legacy=False)
    legacy_roles = {} if legacy_partitions is None else legacy_partitions
    if not isinstance(legacy_roles, dict) or any(
        entity_id not in assignments or original != 'ambiguity'
        or assignments[entity_id]['partition'] != 'development'
        for entity_id, original in legacy_roles.items()
    ):
        raise ValueError('legacy ambiguity may only be explicitly mapped to development diagnostics')
    views, generated, audit = _build_legacy_payload(ordered, assignments, seed=seed)
    views = _validate_views(ordered, views)
    for query in generated:
        if query['target_id'] in legacy_roles:
            query['legacy_partition'] = legacy_roles[query['target_id']]
    queries = [_decorate(query, ordered, views,
                         generator='heldout-alias-v1' if query['kind'] == 'heldout_alias' else 'deterministic-variants-v1')
               for query in generated]
    for item in authored_absent:
        if item['partition'] not in {'development', 'test'}:
            audit['skipped'].append({'group_id': item['id'], 'partition': item['partition'], 'kind': 'absent',
                                     'reason': 'partition reserved from development/test evaluation'})
            continue
        query = {'text': item['text'], 'normalized': normalize_name(item['text']), 'target_id': None,
                 'group_id': item['id'], 'partition': item['partition'], 'alias_id': None,
                 'base_text': item['text'], 'kind': 'absent', 'operation': 'authored absent target',
                 'seed': seed, 'view': 'full', 'script': script_category(item['text']),
                 'source_fingerprint': audit['source_fingerprint'], 'source': 'authored-fictional-absent', 'provenance': None}
        queries.append(_decorate(query, ordered, views, generator='authored-absence-v1'))
    return _current_result(ordered, assignments, views, queries, audit['skipped'])


def build_legacy_benchmark(entities: Sequence[Entity], assignments: dict, *, seed: int = 42,
                           absent: list[dict] | None = None) -> tuple[dict, list[dict], dict]:
    """Reproduce historical rows/hashes exactly, solely for explicit regression."""
    from watchlist.splits import validate_seed
    validate_seed(seed)
    ordered = _ordered_source(entities)
    _validate_legacy_partitions(ordered, assignments)
    authored_absent = [] if absent is None else absent
    _validate_absent(authored_absent, ordered, assignments, legacy=True)
    views, queries, audit = _build_legacy_payload(ordered, assignments, seed=seed, absent=authored_absent)
    bound = _bind(ordered, assignments, views, queries, legacy=True)
    audit_queries(queries, bound, assignments, regression_only=True)
    return bound, queries, audit


def _authored_operation(base: str, text: str, kind: str) -> str:
    """Verify an authored transform against its owned parent without guessing RNG."""
    if kind in {'exact', 'cross_script', 'heldout_alias'} and text == base:
        return {'exact': 'unchanged', 'cross_script': 'owned alias in a disjoint-script view',
                'heldout_alias': 'remove normalized equivalent aliases from target reference'}[kind]
    tokens = base.split()
    if kind == 'formatting' and text == '  ' + '   '.join(tokens).upper() + '  ':
        return 'uppercase and whitespace'
    if kind == 'deletion':
        matches = [index for index, char in enumerate(base) if char.isalpha() and text == base[:index] + base[index + 1:]]
    elif kind == 'adjacent_swap':
        matches = [index for index in range(len(base) - 1)
                   if base[index].isalpha() and base[index + 1].isalpha() and base[index] != base[index + 1]
                   and text == base[:index] + base[index + 1] + base[index] + base[index + 2:]]
    elif kind == 'missing_word' and len(tokens) >= 2:
        matches = [index for index in range(len(tokens)) if text == ' '.join(tokens[:index] + tokens[index + 1:])]
        if matches:
            return f'drop token {matches[0]}'
    elif kind == 'word_order' and len(tokens) >= 2 and text == ' '.join([tokens[-1], *tokens[1:-1], tokens[0]]):
        return 'swap first and last token'
    else:
        matches = []
    if matches:
        return f'character position {matches[0]}'
    raise ValueError('authored query text does not follow its owned generation ancestry')


def _authored_ancestor(spec: dict, entities: tuple[Entity, ...], assignments: dict, views: dict) -> tuple[Entity, Alias, str]:
    from watchlist.scripts import disjoint_scripts, script_set
    if not isinstance(spec, dict):
        raise ValueError('authored query must be an object')
    for field in ('target_id', 'alias_id', 'kind', 'view'):
        _identifier(spec.get(field), field)
    target = next((entity for entity in entities if entity.entity_id == spec.get('target_id')), None)
    if target is None or spec.get('view') not in views:
        raise ValueError('authored query has an unknown target or reference view')
    alias = next((alias for alias in target.aliases if alias.alias_id == spec.get('alias_id')), None)
    if alias is None:
        raise ValueError('authored alias is not owned by its target')
    text, kind = spec.get('text'), spec.get('kind')
    _normalized_text(text)
    operation = _authored_operation(alias.name, text, kind)
    selected = next((entity for entity in views[spec['view']] if entity.entity_id == target.entity_id), None)
    if selected is None:
        raise ValueError('positive target missing from reference view')
    if kind == 'heldout_alias' and any(normalize_name(other.name) == normalize_name(text) for other in selected.aliases):
        raise ValueError('held-out alias leakage')
    if kind == 'cross_script':
        reference = {script for other in selected.aliases for script in script_set(other.name)}
        if not disjoint_scripts(script_set(text), reference):
            raise ValueError('cross-script reference overlaps the query script set or has unknown scripts')
    return target, alias, operation


def build_authored_benchmark(entities: Sequence[Entity], assignments: dict, views: dict,
                             query_specs: list[dict], *, seed: int = 42) -> tuple[dict, list[dict], dict]:
    """Derive development/test rows from owned parent/transform/view declarations."""
    from watchlist.splits import validate_seed
    validate_seed(seed)
    ordered = _ordered_source(entities)
    validate_partitions(ordered, assignments)
    checked = _validate_views(ordered, views)
    source_hash = fingerprint([asdict(entity) for entity in ordered])
    if not isinstance(query_specs, list):
        raise ValueError('authored query specifications must be a list')
    queries, skipped = [], []
    for spec in query_specs:
        required = {'target_id', 'alias_id', 'kind', 'text', 'view'}
        if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {'pair_type', 'legacy_partition'}:
            raise ValueError('authored query specification has unexpected or missing fields')
        target, alias, operation = _authored_ancestor(spec, ordered, assignments, checked)
        assignment = assignments[target.entity_id]
        if 'pair_type' in spec:
            _identifier(spec['pair_type'], 'pair type')
        if 'legacy_partition' in spec and (spec['legacy_partition'] != 'ambiguity' or assignment['partition'] != 'development'):
            raise ValueError('legacy ambiguity may only be explicitly mapped to development diagnostics')
        if assignment['partition'] not in {'development', 'test'}:
            skipped.append({'entity_id': target.entity_id, 'alias_id': alias.alias_id,
                            'partition': assignment['partition'], 'kind': spec['kind'],
                            'reason': 'partition reserved from development/test evaluation'})
            continue
        query = {**spec, 'normalized': normalize_name(spec['text']), 'group_id': assignment['group_id'],
                 'partition': assignment['partition'], 'base_text': alias.name, 'operation': operation,
                 'seed': seed, 'script': script_category(spec['text']), 'source_fingerprint': source_hash,
                 'source': target.source, 'provenance': asdict(target.provenance) if target.provenance else None}
        queries.append(_decorate(query, ordered, checked, generator='authored-transform-v1'))
    return _current_result(ordered, assignments, checked, queries, skipped)


def bind_legacy_authored_benchmark(entities: Sequence[Entity], assignments: dict, views: dict,
                                  source_queries: list[dict]) -> tuple[dict, list[dict]]:
    """Verify an authored historical registry, retaining its exact row fields.

    The only derived historical addition is reference_scripts, matching the old
    multilingual reader. Its coarse labels remain regression-only diagnostics.
    """
    ordered = _ordered_source(entities)
    _validate_legacy_partitions(ordered, assignments)
    checked = _validate_views(ordered, views, legacy=True)
    if not isinstance(source_queries, list):
        raise ValueError('historical authored queries must be a list')
    queries = []
    for original in source_queries:
        required = {'query_id', 'target_id', 'group_id', 'partition', 'text', 'normalized',
                    'base_text', 'alias_id', 'kind', 'view', 'script', 'pair_type', 'status',
                    'reason', 'source', 'provenance'}
        if (not isinstance(original, dict) or not required <= set(original)
                or set(original) - required - {'reference_scripts'}):
            raise ValueError('historical authored query has unexpected or missing fields')
        target, alias, _ = _authored_ancestor(original, ordered, assignments, checked)
        _identifier(original.get('query_id'), 'query ID')
        expected = {'group_id': assignments[target.entity_id]['group_id'],
                    'partition': assignments[target.entity_id]['partition'], 'base_text': alias.name,
                    'normalized': normalize_name(original['text']), 'script': script_category(original['text']),
                    'source': target.source, 'provenance': asdict(target.provenance) if target.provenance else None,
                    'status': 'diagnostic' if assignments[target.entity_id]['partition'] == 'ambiguity' else 'positive'}
        if any(original.get(key) != value for key, value in expected.items()):
            raise ValueError('historical authored query conflicts with its original ancestry or label')
        query = json.loads(_canonical(original))
        reference_scripts = sorted({script_category(alias.name) for entity in checked[query['view']]
                                    if entity.entity_id == target.entity_id for alias in entity.aliases})
        if 'reference_scripts' in query and query['reference_scripts'] != reference_scripts:
            raise ValueError('historical reference script labels differ from owned aliases')
        query['reference_scripts'] = reference_scripts
        queries.append(query)
    bound = _bind(ordered, assignments, checked, queries, legacy=True)
    audit_queries(queries, bound, assignments, regression_only=True)
    return bound, queries
