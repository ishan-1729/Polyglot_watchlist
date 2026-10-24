"""Script claims use character evidence, including uncertainty, not label equality."""

from dataclasses import FrozenInstanceError

import pytest

from watchlist.scripts import disjoint_scripts, script_profile, script_set


@pytest.mark.parametrize(('text', 'expected'), [
    ('Lúma Vesper', {'LATIN'}),
    ('Ｌｕｍａ', {'LATIN'}),
    ('ليلى', {'ARABIC'}),
    ('ﻟﻴﻠﻰ', {'ARABIC'}),
    ('Лума', {'CYRILLIC'}),
    ('月織', {'HAN'}),
    ('\U00020000', {'HAN'}),
    ('\uf900', {'HAN'}),
    ('々〇', {'HAN'}),
    ('Luma ليلى Лума 月織', {'LATIN', 'ARABIC', 'CYRILLIC', 'HAN'}),
    ('Luma-123', {'LATIN'}),
    ('Luma،٤٥', {'LATIN'}),
    ('', set()),
    (' \t123-٤٥!🙂', set()),
    ('\u0301\ufe0f', set()),
    ('A\u0301', {'LATIN'}),
    ('لَ', {'ARABIC'}),
    ('A\u2de0', {'LATIN', 'CYRILLIC'}),
    ('A\u064e', {'LATIN', 'ARABIC'}),
    ('\u064e', {'ARABIC', 'UNKNOWN'}),
    ('ـ', {'UNKNOWN'}),
    ('Ω', {'UNKNOWN'}),
    ('א', {'UNKNOWN'}),
    ('ম', {'UNKNOWN'}),
    ('AΩ', {'LATIN', 'UNKNOWN'}),
    ('\U0001d400', {'UNKNOWN'}),
    ('\u0378', {'UNKNOWN'}),
    ('\ue000', {'UNKNOWN'}),
    ('A\u200d', {'LATIN', 'UNKNOWN'}),
    ('A\u05b0', {'LATIN', 'UNKNOWN'}),
])
def test_supported_scripts_and_neutral_or_unsupported_characters(text, expected):
    assert script_set(text) == frozenset(expected)
    assert isinstance(script_set(text), frozenset)


def test_profile_keeps_categories_and_uncertainty_visible():
    profile = script_profile('AشБ中1٤-!\u0301 🙂Ω')
    assert profile.scripts == frozenset({'LATIN', 'ARABIC', 'CYRILLIC', 'HAN', 'UNKNOWN'})
    assert profile.letters == 5
    assert profile.digits == 2
    assert profile.punctuation == 2
    assert profile.marks == 1
    assert profile.whitespace == 1
    assert profile.symbols == 1
    assert profile.unknown == 1
    with pytest.raises(FrozenInstanceError):
        profile.letters = 0


@pytest.mark.parametrize(('left', 'right', 'expected'), [
    ({'LATIN'}, {'ARABIC'}, True),
    ({'CYRILLIC'}, {'HAN'}, True),
    ({'LATIN', 'ARABIC'}, {'CYRILLIC', 'HAN'}, True),
    ({'LATIN', 'ARABIC'}, {'LATIN'}, False),
    ({'LATIN'}, {'LATIN', 'ARABIC'}, False),
    ({'LATIN', 'ARABIC'}, {'ARABIC', 'CYRILLIC'}, False),
    ({'UNKNOWN'}, {'LATIN'}, False),
    ({'LATIN', 'UNKNOWN'}, {'ARABIC'}, False),
    ({'ARABIC'}, {'LATIN', 'UNKNOWN'}, False),
    (set(), {'LATIN'}, False),
    ({'LATIN'}, set(), False),
    (set(), set(), False),
])
def test_disjoint_script_sets_require_positive_known_evidence(left, right, expected):
    assert disjoint_scripts(left, right) is expected
    assert disjoint_scripts(right, left) is expected


def test_reference_union_detects_one_shared_script_in_any_alias():
    query = script_set('Luma ليلى')
    reference = frozenset().union(*(script_set(alias) for alias in ('Лума', 'Luma')))
    assert not disjoint_scripts(query, reference)
    assert not disjoint_scripts(script_set('123'), script_set('ليلى'))
    assert not disjoint_scripts(script_set('\u064e'), script_set('Luma'))
    assert not disjoint_scripts(script_set('A\u064e'), script_set('ليلى'))


@pytest.mark.parametrize('value', [None, 1, True, b'Luma', ['Luma'], {}, '\ud800'])
def test_script_analysis_rejects_nontext_and_invalid_unicode(value):
    with pytest.raises(ValueError, match='text|Unicode'):
        script_set(value)


@pytest.mark.parametrize('value', [None, 'LATIN', ['LATIN+ARABIC'], ['OTHER'], ['latin'],
                                  [1], {'LATIN': 1}, 42])
def test_disjoint_predicate_rejects_labels_and_malformed_script_sets(value):
    with pytest.raises(ValueError, match='script'):
        disjoint_scripts(value, {'ARABIC'})
    with pytest.raises(ValueError, match='script'):
        disjoint_scripts({'ARABIC'}, value)


def test_disjoint_predicate_accepts_serialized_lists_without_mutation():
    left, right = ['LATIN', 'LATIN'], ['ARABIC']
    assert disjoint_scripts(left, right)
    assert left == ['LATIN', 'LATIN'] and right == ['ARABIC']
