"""Small authored records make leakage and ambiguity hand-checkable."""
from copy import deepcopy
from dataclasses import replace
import pytest
from watchlist.entities import Entity, Alias
from watchlist.evaluation_data import (
    audit_queries, bind_legacy_authored_benchmark, build_authored_benchmark,
    build_benchmark, build_legacy_benchmark, fingerprint, query_labels,
    validate_partitions,
)


def records():
    return [Entity('a','Moon Loom','organisation',(Alias('a1','Moon Loom'),Alias('a2','Moon Textile')),True,'fixture'),
            Entity('b','Moon Loom','organisation',(Alias('b1','Moon Loom'),Alias('b2','Moon Workshop')),True,'fixture')]


def assignments():
    return {'a':{'group_id':'a','partition':'development'},'b':{'group_id':'b','partition':'test'}}


def test_reordered_inputs_produce_identical_queries_and_views():
    first = build_benchmark(records(), assignments())
    reversed_records = [replace(e, aliases=tuple(reversed(e.aliases))) for e in reversed(records())]
    second = build_benchmark(reversed_records, assignments())
    # Canonical alias ordering is part of the protocol.
    assert first == second


def test_shared_names_keep_ids_and_are_not_headline_positives():
    views, queries, audit = build_benchmark(records(), assignments())
    assert len(views['full']) == 2
    assert audit['shared_aliases'][0]['entity_ids'] == ['a','b']
    shared = [q for q in queries if q['normalized']=='moon loom']
    assert shared and all(q['status']=='diagnostic' for q in shared)
    assert {q['target_id'] for q in shared} == {'a','b'}


def test_group_and_query_ancestry_leakage_fail():
    bad = assignments();bad['b']['group_id']='a'
    with pytest.raises(ValueError, match='leakage'):
        validate_partitions(records(),bad)
    views,queries,_=build_benchmark(records(),assignments())
    queries[0]['partition']='train'
    with pytest.raises(ValueError,match='ancestry'):
        audit_queries(queries,views,assignments())


def test_withheld_aliases_cannot_leak_back():
    views,queries,_=build_benchmark(records(),assignments())
    held=[q for q in queries if q['kind']=='heldout_alias']
    assert len(held)==2
    views['heldout']=views['full']
    with pytest.raises(ValueError,match='held-out'):
        audit_queries(held,views,assignments())


def test_absent_collision_and_missing_partition_rejected():
    with pytest.raises(ValueError,match='absent query'):
        build_benchmark(records(),assignments(),absent=[{'id':'abs','text':'Moon Loom'}])
    with pytest.raises(ValueError,match='coverage'):
        validate_partitions(records(),{})


def test_single_alias_skip_and_reserved_groups():
    entities=[replace(records()[0],aliases=(Alias('a1','Moon Loom'),))]
    _,q,a=build_benchmark(entities,{'a':assignments()['a']})
    assert any(x['kind']=='heldout_alias' for x in a['skipped'])
    _,q,_=build_benchmark(entities,{'a':{'group_id':'a','partition':'train'}})
    assert q==[]


@pytest.mark.parametrize('field,value', [
    ('alias_id', 'b1'), ('base_text', 'Invented fictional ancestor'),
    ('text', 'Invented fictional query'), ('normalized', 'invented normalized text'),
    ('operation', 'unrecorded transformation'), ('seed', 99),
    ('script', 'ARABIC'), ('reference_scripts', ['ARABIC']),
    ('source_fingerprint', '0' * 64), ('source', 'unowned source'),
    ('status', 'absent'), ('colliding_entity_ids', ['unowned-record']),
])
def test_e1_owned_query_fields_cannot_be_relabelled(field, value):
    views, queries, _ = build_benchmark(records(), assignments())
    query = deepcopy(next(q for q in queries if q['target_id'] == 'a' and q['kind'] == 'exact'))
    query[field] = value
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments())


@pytest.mark.parametrize('field,value', [
    ('text', 'Moon Loom'), ('normalized', 'moon loom'), ('alias_id', 'a1'),
    ('target_id', 'a'), ('view', 'missing-view'), ('script', 'ARABIC'),
    ('source_fingerprint', '0' * 64), ('status', 'positive'),
])
def test_e1_absent_rows_receive_the_same_full_audit(field, value):
    views, queries, _ = build_benchmark(records(), assignments(), absent=[
        {'id': 'fictional-absent', 'text': 'Zori Dapple', 'partition': 'test'},
    ])
    query = deepcopy(next(q for q in queries if q['target_id'] is None))
    query[field] = value
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments())


def test_e1_query_and_caller_assignment_cannot_move_together():
    owned = assignments()
    views, queries, _ = build_benchmark(records(), owned)
    query = deepcopy(next(q for q in queries if q['target_id'] == 'a'))
    owned['a'] = {'group_id': 'replacement-group', 'partition': 'test'}
    query.update(owned['a'])
    with pytest.raises(ValueError):
        audit_queries([query], views, owned)


def test_e1_unmodified_query_cannot_use_a_replaced_reference():
    views, queries, _ = build_benchmark(records(), assignments())
    query = deepcopy(next(q for q in queries if q['target_id'] == 'a' and q['kind'] == 'exact'))
    views['full'] = tuple(replace(entity, aliases=(Alias(entity.entity_id + '-replacement', 'Invented View'),))
                          for entity in views['full'])
    with pytest.raises(ValueError):
        audit_queries([query], views, assignments())


def test_e1_alias_identity_cannot_be_owned_by_two_entities():
    first, second = records()
    second = replace(second, aliases=(Alias('a1', 'Other Authored Name'),))
    with pytest.raises(ValueError):
        build_benchmark([first, second], assignments())


def single_record():
    entity = Entity('solo', 'Maple Loom', 'organisation',
                    (Alias('solo-en', 'Maple Loom'), Alias('solo-ar', 'منسج القيقب')),
                    True, 'fixture')
    return entity, {'solo': {'group_id': 'solo-family', 'partition': 'development'}}


def authored_case(**changes):
    return {'target_id': 'solo', 'alias_id': 'solo-en', 'kind': 'exact',
            'text': 'Maple Loom', 'view': 'full', **changes}


@pytest.mark.parametrize('partition', ['development', 'test'])
def test_current_absence_has_an_independent_partition(partition):
    views, queries, audit = build_benchmark(records(), assignments(), absent=[
        {'id': 'fictional-absent', 'text': 'Zori Dapple', 'partition': partition},
    ])
    row = next(query for query in queries if query['target_id'] is None)
    assert row['partition'] == partition
    assert query_labels(row) == {'presence': 'absent', 'ambiguity': 'unambiguous', 'status': 'absent'}
    assert audit['protocol_version'] == views.protocol_version == 'evaluation-v2'
    audit_queries([row], views)


@pytest.mark.parametrize('partition', ['train', 'calibration_fit', 'threshold_selection'])
def test_reserved_absent_families_are_recorded_but_not_evaluated(partition):
    _, queries, audit = build_benchmark(records(), assignments(), absent=[
        {'id': 'reserved-absent', 'text': 'Zori Dapple', 'partition': partition},
    ])
    assert not any(query['target_id'] is None for query in queries)
    assert {'group_id': 'reserved-absent', 'partition': partition, 'kind': 'absent',
            'reason': 'partition reserved from development/test evaluation'} in audit['skipped']


@pytest.mark.parametrize('absent', [
    {}, '', 1, [None], [{'id': 'abs', 'text': 'Zori Dapple'}],
    [{'id': 'abs', 'text': 'Zori Dapple', 'partition': 'absent'}],
    [{'id': 'a', 'text': 'Zori Dapple', 'partition': 'test'}],
    [{'id': 'abs', 'text': None, 'partition': 'test'}],
    [{'id': 'abs', 'text': 'Zori\ud800', 'partition': 'test'}],
    [{'id': 'abs', 'text': '  MOON   LOOM  ', 'partition': 'test'}],
    [{'id': 'abs', 'text': 'Moon Textile', 'partition': 'test'}],
    [{'id': 'abs', 'text': 'Zori Dapple', 'partition': []}],
    [{'id': 'abs', 'text': 'Zori Dapple', 'partition': 'test', 'status': 'absent'}],
    [{'id': 'abs', 'text': 'Zori Dapple', 'partition': 'test'},
     {'id': 'other', 'text': '  ZORI   DAPPLE ', 'partition': 'development'}],
    [{'id': 'abs', 'text': 'Zori Dapple', 'partition': 'test'},
     {'id': 'abs', 'text': 'Other Fictional Name', 'partition': 'test'}],
])
def test_current_absence_rejects_unverifiable_declarations(absent):
    with pytest.raises(ValueError):
        build_benchmark(records(), assignments(), absent=absent)


def test_absent_group_cannot_reuse_a_separately_named_source_family():
    entity, assigned = single_record()
    with pytest.raises(ValueError, match='group'):
        build_benchmark([entity], assigned, absent=[
            {'id': 'solo-family', 'text': 'Zori Dapple', 'partition': 'test'},
        ])


def test_absence_and_generated_typo_conflict_stays_out_of_headline_metrics():
    entity, assigned = single_record()
    _, original, _ = build_benchmark([entity], assigned)
    typo = next(row for row in original if row['kind'] == 'deletion')
    _, queries, _ = build_benchmark([entity], assigned, absent=[
        {'id': 'fictional-absent', 'text': typo['text'], 'partition': 'development'},
    ])
    conflict = [row for row in queries if row['normalized'] == typo['normalized']]
    assert {row['presence'] for row in conflict} == {'present', 'absent'}
    assert all(row['ambiguity'] == 'unlabelable' and row['status'] == 'diagnostic' for row in conflict)
    assert all('conflicting authored presence labels' in row['exclusion_reasons'] for row in conflict)


def test_current_audit_accepts_only_registered_subsets_and_reorderings():
    views, queries, _ = build_benchmark(records(), assignments())
    audit_queries(list(reversed(queries)), views)
    audit_queries(queries[::3], views)
    with pytest.raises(ValueError, match='duplicate'):
        audit_queries([queries[0], deepcopy(queries[0])], views)
    with pytest.raises(ValueError, match='immutable'):
        audit_queries(queries, dict(views))


@pytest.mark.parametrize('field,value', [
    ('presence', 'absent'), ('ambiguity', 'unambiguous'), ('scripts', ['ARABIC']),
    ('view_fingerprint', '0' * 64), ('generation', {'generator': 'unowned'}),
])
def test_current_axes_and_generation_receipt_cannot_be_rewritten(field, value):
    views, queries, _ = build_benchmark(records(), assignments())
    row = deepcopy(next(query for query in queries if query['base_text'] == 'Moon Loom'))
    row[field] = value
    with pytest.raises(ValueError, match='ancestry'):
        audit_queries([row], views)


def test_legacy_builder_preserves_recorded_hashes_and_requires_opt_in():
    views, queries, audit = build_legacy_benchmark(records(), assignments(), absent=[
        {'id': 'fictional-absent', 'text': 'Zori Dapple'},
    ])
    # Recorded by the unmodified Completion 04 source before this contract changed.
    assert len(queries) == 27
    assert fingerprint(queries) == '9d9af6687b948301eaf36c3d98a7a5ecfa7cd589f698045110f145b78d41ec44'
    assert fingerprint(audit) == '49426596ddb392eec52d987baaff07e1888c38f40d5936e916f18da967aee999'
    assert views.regression_only is True
    with pytest.raises(ValueError, match='regression_only'):
        audit_queries(queries, views)
    audit_queries(queries, views, regression_only=True)
    diagnostic = next(query for query in queries if query['status'] == 'diagnostic')
    assert query_labels(diagnostic, regression_only=True)['ambiguity'] == 'unlabelable'
    with pytest.raises(ValueError, match='regression_only'):
        query_labels(diagnostic)


@pytest.mark.parametrize('kind,text,operation', [
    ('exact', 'Maple Loom', 'unchanged'),
    ('formatting', '  MAPLE   LOOM  ', 'uppercase and whitespace'),
    ('deletion', 'Mple Loom', 'character position 1'),
    ('adjacent_swap', 'Mpal eLoom', None),
    ('adjacent_swap', 'Mapel Loom', 'character position 3'),
    ('missing_word', 'Maple', 'drop token 1'),
    ('word_order', 'Loom Maple', 'swap first and last token'),
])
def test_authored_transforms_prove_their_parent(kind, text, operation):
    entity, assigned = single_record()
    if operation is None:
        with pytest.raises(ValueError, match='generation ancestry'):
            build_authored_benchmark([entity], assigned, {'full': (entity,)}, [authored_case(kind=kind, text=text)])
        return
    views, queries, _ = build_authored_benchmark([entity], assigned, {'full': (entity,)}, [
        authored_case(kind=kind, text=text),
    ])
    assert queries[0]['operation'] == operation
    assert queries[0]['base_text'] == 'Maple Loom'
    assert queries[0]['generation']['parent_alias_id'] == 'solo-en'
    audit_queries(queries, views)


@pytest.mark.parametrize('changes', [
    {'alias_id': 'unowned'}, {'text': 'Different Name'}, {'kind': 'unknown'},
    {'text': None}, {'text': 'Bad\ud800'}, {'view': 'missing'},
    {'kind': 'heldout_alias'}, {'status': 'positive'}, {'base_text': 'False Parent'},
])
def test_authored_queries_reject_unowned_or_claimed_ancestry(changes):
    entity, assigned = single_record()
    with pytest.raises(ValueError):
        build_authored_benchmark([entity], assigned, {'full': (entity,)}, [authored_case(**changes)])


def test_authored_cross_script_uses_actual_target_script_sets():
    entity, assigned = single_record()
    arabic = replace(entity, aliases=(entity.aliases[1],))
    views, queries, _ = build_authored_benchmark([entity], assigned, {'arabic': (arabic,)}, [
        authored_case(kind='cross_script', view='arabic'),
    ])
    assert queries[0]['scripts'] == ['LATIN']
    assert queries[0]['reference_scripts'] == ['ARABIC']
    audit_queries(queries, views)
    with pytest.raises(ValueError, match='cross-script'):
        build_authored_benchmark([entity], assigned, {'full': (entity,)}, [authored_case(kind='cross_script')])


@pytest.mark.parametrize('generated', [False, True])
def test_explicit_legacy_ambiguity_mapping_always_stays_diagnostic(generated):
    entity, assigned = single_record()
    if generated:
        _, queries, audit = build_benchmark([entity], assigned, legacy_partitions={'solo': 'ambiguity'})
    else:
        _, queries, audit = build_authored_benchmark([entity], assigned, {'full': (entity,)}, [
            authored_case(legacy_partition='ambiguity'),
        ])
    assert all(row['partition'] == 'development' and row['legacy_partition'] == 'ambiguity' for row in queries)
    assert all(row['status'] == 'diagnostic' and row['ambiguity'] == 'unlabelable' for row in queries)
    assert audit['legacy_partition_mappings']


@pytest.mark.parametrize('entity_change', [
    {'aliases': ('not-an-alias',)}, {'aliases': None}, {'name': None},
    {'name': 'Bad\ud800'}, {'provenance': {'unowned': 'metadata'}},
])
def test_invalid_source_records_fail_before_hashing(entity_change):
    entity, assigned = single_record()
    with pytest.raises(ValueError):
        build_benchmark([replace(entity, **entity_change)], assigned)


def test_current_han_labels_match_script_evidence_while_legacy_stays_frozen():
    entity = Entity('han', '青杉图书馆', 'organisation', (Alias('han-name', '青杉图书馆'),), True, 'fixture')
    assigned = {'han': {'group_id': 'han', 'partition': 'development'}}
    _, current, _ = build_benchmark([entity], assigned)
    _, historical, _ = build_legacy_benchmark([entity], assigned)
    assert current[0]['scripts'] == ['HAN']
    assert current[0]['script'] == 'HAN'
    assert current[0]['reference_scripts'] == ['HAN']
    assert historical[0]['script'] == 'OTHER'


@pytest.mark.parametrize('partition', ['train', 'calibration_fit', 'threshold_selection'])
def test_authored_reserved_roles_do_not_create_evaluation_rows(partition):
    entity, assigned = single_record()
    assigned['solo']['partition'] = partition
    _, queries, audit = build_authored_benchmark([entity], assigned, {'full': (entity,)}, [authored_case()])
    assert queries == []
    assert audit['skipped'] == [{'entity_id': 'solo', 'alias_id': 'solo-en', 'partition': partition,
                                 'kind': 'exact', 'reason': 'partition reserved from development/test evaluation'}]


def legacy_authored_case():
    return {'query_id': 'original-authored-query', 'target_id': 'solo', 'group_id': 'solo-family',
            'partition': 'development', 'text': 'Maple Loom', 'normalized': 'maple loom',
            'base_text': 'Maple Loom', 'alias_id': 'solo-en', 'kind': 'exact', 'view': 'full',
            'script': 'LATIN', 'pair_type': 'translation', 'status': 'positive', 'reason': None,
            'source': 'fixture', 'provenance': None}


def test_legacy_authored_binder_preserves_raw_fields_and_seals_added_scripts():
    entity, assigned = single_record()
    raw = legacy_authored_case()
    views, queries = bind_legacy_authored_benchmark([entity], assigned, {'full': (entity,)}, [raw])
    assert queries == [{**raw, 'reference_scripts': ['ARABIC', 'LATIN']}]
    assert 'reference_scripts' not in raw
    audit_queries(queries, views, assigned, regression_only=True)
    queries[0]['source'] = 'unowned'
    with pytest.raises(ValueError, match='ancestry'):
        audit_queries(queries, views, assigned, regression_only=True)


@pytest.mark.parametrize('field,value', [
    ('target_id', 'unknown'), ('alias_id', 'unknown'), ('base_text', 'Fake Parent'),
    ('normalized', 'fake normalized'), ('partition', 'test'), ('group_id', 'fake-group'),
    ('script', 'ARABIC'), ('status', 'diagnostic'), ('source', 'unowned'),
    ('provenance', {'invented': True}), ('reference_scripts', ['HAN']),
    ('unexpected', 'unowned field'),
])
def test_legacy_authored_binder_rejects_modified_ancestry(field, value):
    entity, assigned = single_record()
    raw = {**legacy_authored_case(), field: value}
    with pytest.raises(ValueError):
        bind_legacy_authored_benchmark([entity], assigned, {'full': (entity,)}, [raw])


def test_current_withheld_display_name_cannot_reveal_the_hidden_alias():
    entity = Entity('solo', 'Maple Loom', 'organisation',
                    (Alias('a-arabic', 'منسج القيقب'), Alias('z-english', 'Maple Loom')),
                    True, 'fixture')
    assigned = {'solo': {'group_id': 'solo', 'partition': 'development'}}
    current, queries, _ = build_benchmark([entity], assigned)
    legacy, _, _ = build_legacy_benchmark([entity], assigned)
    heldout = current['heldout'][0]
    assert heldout.name == 'منسج القيقب'
    assert all(alias.name != 'Maple Loom' for alias in heldout.aliases)
    assert legacy['heldout'][0].name == 'Maple Loom'
    audit_queries([row for row in queries if row['kind'] == 'heldout_alias'], current)


def test_current_cross_script_display_name_comes_from_the_selected_view():
    entity, assigned = single_record()
    arabic = replace(entity, aliases=(entity.aliases[1],))
    views, rows, _ = build_authored_benchmark([entity], assigned, {'arabic': (arabic,)}, [
        authored_case(kind='cross_script', view='arabic'),
    ])
    assert views['arabic'][0].name == 'منسج القيقب'
    assert rows[0]['text'] == 'Maple Loom'
    assert entity.name == 'Maple Loom'
    audit_queries(rows, views)


@pytest.mark.parametrize('builder', [build_benchmark, build_legacy_benchmark])
def test_existing_legal_entity_source_type_is_preserved(builder):
    entity, assigned = single_record()
    # Mimic the existing public parser's schema using entirely fictional names.
    source = replace(entity, entity_type='legal_entity', synthetic=False)
    views, _, _ = builder([source], assigned)
    assert views['full'][0].entity_type == 'legal_entity'
    assert views['full'][0].synthetic is False


def test_unrelated_script_distractor_does_not_change_target_direction():
    target, assigned = single_record()
    distractor = Entity('distractor', 'مقهى القمر', 'organisation',
                        (Alias('distractor-ar', 'مقهى القمر'),), True, 'fixture')
    assigned['distractor'] = {'group_id': 'distractor', 'partition': 'development'}
    selected = replace(target, aliases=(target.aliases[0],))
    views, queries, _ = build_authored_benchmark([target, distractor], assigned,
                                                {'mixed': (selected, distractor)}, [
        authored_case(alias_id='solo-ar', kind='cross_script', text='منسج القيقب', view='mixed'),
    ])
    assert queries[0]['scripts'] == ['ARABIC']
    assert queries[0]['reference_scripts'] == ['LATIN']
    assert queries[0]['status'] == 'positive'
    audit_queries(queries, views)
