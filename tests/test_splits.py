"""Entity-group separation is checked without training or benchmark metrics."""

from pathlib import Path
from copy import deepcopy

import pytest

from watchlist.ingest.import_source import import_snapshot
from watchlist.splits import assign_groups, create_manifest
from watchlist import splits


def test_explicit_links_stay_together_and_order_does_not_matter() -> None:
    records = [{"id": "a", "referents": ["old"]}, {"id": "b", "referents": ["old"]},
               {"id": "c", "referents": ["b"]}, {"id": "unrelated", "referents": []}]
    first = assign_groups(records)
    assert first == assign_groups(list(reversed(records)))
    assert first["a"] == first["b"] == first["c"]
    assert first["unrelated"]["group_id"] != first["a"]["group_id"]


def test_duplicate_ids_cannot_enter_splitter() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        assign_groups([{"id": "a"}, {"id": "a"}])


def test_manifest_covers_each_entity_and_flags_shared_names(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures/opensanctions_synthetic.ftm.json"
    db = tmp_path / "sample.sqlite"
    import_snapshot(fixture, fixture.with_name("opensanctions_synthetic.metadata.json"), db, sample=True)
    manifest = create_manifest(db)
    assert manifest == create_manifest(db)
    assert set(manifest["assignments"]) == {"fixture-001", "fixture-002", "fixture-003"}
    assert sum(manifest["entity_counts"].values()) == 3
    assert manifest["shared_normalized_names"] == [
        {"normalized_name": "moonberry loom", "entity_ids": ["fixture-001", "fixture-003"]}
    ]
    groups = {}
    for assignment in manifest["assignments"].values():
        groups.setdefault(assignment["group_id"], set()).add(assignment["partition"])
    assert all(len(partitions) == 1 for partitions in groups.values())


@pytest.mark.parametrize('seed', [True, False, None, 42.0, '42', [], {}, float('nan')])
def test_split_seed_requires_an_integer(seed):
    with pytest.raises(ValueError, match='seed'):
        assign_groups([{'id': 'fictional'}], seed)


@pytest.mark.parametrize('seed', [True, None, 42.0, '42'])
def test_manifest_rejects_bad_seed_before_database_access(tmp_path, monkeypatch, seed):
    accessed = []

    def unexpected_load(path):
        accessed.append(path)
        raise AssertionError('invalid seed reached a source database')

    monkeypatch.setattr(splits, 'load_database', unexpected_load)
    with pytest.raises(ValueError, match='seed'):
        create_manifest(tmp_path / 'absent.sqlite', seed)
    assert accessed == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('records', [
    None, {}, 'fictional', ({'id': 'a'},), [None], [42], [{}],
    [{'id': None}], [{'id': 1}], [{'id': True}], [{'id': ''}], [{'id': ' '}],
    [{'id': ' a'}], [{'id': '\ud800'}], [{'id': 'a', 'referents': None}],
    [{'id': 'a', 'referents': 'old'}], [{'id': 'a', 'referents': [1]}],
    [{'id': 'a', 'referents': ['']}], [{'id': 'a', 'referents': [' old']}],
    [{'id': 'a', 'referents': ['\ud800']}],
])
def test_splitter_rejects_malformed_provider_records(records):
    with pytest.raises(ValueError):
        assign_groups(records)


def test_valid_membership_and_negative_seed_remain_unchanged():
    records = [{'id': 'a', 'referents': ['old']}, {'id': 'b', 'referents': ['old']},
               {'id': 'c', 'referents': ['b']}, {'id': 'unrelated', 'referents': []}]
    saved = deepcopy(records)
    expected = {key: {'group_id': 'a', 'partition': 'train'} for key in ('a', 'b', 'c')}
    expected['unrelated'] = {'group_id': 'unrelated', 'partition': 'test'}
    assert assign_groups(records) == expected
    negative = {key: {'group_id': 'a', 'partition': 'development'} for key in ('a', 'b', 'c')}
    negative['unrelated'] = {'group_id': 'unrelated', 'partition': 'train'}
    assert assign_groups(records, -7) == negative
    assert records == saved
    assert assign_groups([]) == {}


def test_provider_links_are_transitive_but_equal_names_are_not_links():
    records = [
        {'id': 'one', 'referents': ['old-one'], 'name': 'Fictional Shared Name'},
        {'id': 'two', 'referents': ['old-one', 'old-two']},
        {'id': 'three', 'referents': ['old-two']},
        {'id': 'separate', 'name': 'Fictional Shared Name'},
    ]
    assignments = assign_groups(records)
    assert assignments['one'] == assignments['two'] == assignments['three']
    assert assignments['separate']['group_id'] != assignments['one']['group_id']
    splits.validate_assignments([r['id'] for r in records], assignments)


def test_assignment_partition_axis_has_only_the_five_owned_partitions():
    assert splits.PARTITION_NAMES == frozenset({
        'train', 'development', 'calibration_fit', 'threshold_selection', 'test',
    })
    for partition in splits.PARTITION_NAMES:
        splits.validate_assignments(['a'], {'a': {'group_id': 'provider-group', 'partition': partition}})
    splits.validate_assignments([], {})


@pytest.mark.parametrize('partition', ['absent', 'ambiguity', 'positive', 'present',
                                       'diagnostic', '', None, 1, ['test']])
def test_presence_or_ambiguity_cannot_be_used_as_a_partition(partition):
    with pytest.raises(ValueError, match='partition'):
        splits.validate_assignments(['a'], {'a': {'group_id': 'a', 'partition': partition}})


@pytest.mark.parametrize('assignments', [
    None, [], {}, {'b': {'group_id': 'b', 'partition': 'test'}},
    {'a': None}, {'a': []}, {'a': {'partition': 'test'}},
    {'a': {'group_id': 'a'}}, {'a': {'group_id': '', 'partition': 'test'}},
    {'a': {'group_id': 1, 'partition': 'test'}},
    {'a': {'group_id': ' a', 'partition': 'test'}},
    {'a': {'group_id': 'a', 'partition': 'test', 'presence': 'absent'}},
    {'a': {'group_id': 'a', 'partition': 'test', 'ambiguity': 'unambiguous'}},
])
def test_assignment_validator_rejects_malformed_coverage_groups_or_axes(assignments):
    with pytest.raises(ValueError):
        splits.validate_assignments(['a'], assignments)


@pytest.mark.parametrize('ids', [None, 'a', {'a': 'value'}, ['a', 'a'], [1], [' a'], ['\ud800']])
def test_assignment_validator_rejects_invalid_entity_ids(ids):
    with pytest.raises(ValueError):
        splits.validate_assignments(ids, {'a': {'group_id': 'a', 'partition': 'test'}})


def test_one_provider_group_cannot_cross_partitions():
    assignments = {'a': {'group_id': 'provider', 'partition': 'train'},
                   'b': {'group_id': 'provider', 'partition': 'test'}}
    saved = deepcopy(assignments)
    with pytest.raises(ValueError, match='leakage'):
        splits.validate_assignments(['a', 'b'], assignments)
    assert assignments == saved
