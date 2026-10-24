"""Check transformation mechanics without assuming retrieval success."""
from watchlist.perturbations import variants, script_category


def test_deterministic_operations_and_skip_reasons():
    rows = variants('Copper Kite Guild', 'alias', 42)
    assert rows == variants('Copper Kite Guild', 'alias', 42)
    by = {r['kind']: r for r in rows}
    assert len(by['deletion']['text']) == len('Copper Kite Guild') - 1
    assert sorted(by['adjacent_swap']['text']) == sorted('Copper Kite Guild')
    assert len(by['missing_word']['text'].split()) == 2
    assert by['word_order']['text'] == 'Guild Kite Copper'
    assert next(r for r in variants('A', 'x') if r['kind']=='word_order')['text'] is None


def test_script_categories_are_not_language_detection():
    assert script_category('Élo 12') == 'LATIN'
    assert script_category('Мира') == 'CYRILLIC'
    assert script_category('سيرا') == 'ARABIC'
    assert script_category('Mira Мира') == 'CYRILLIC+LATIN'
    assert script_category('123') == 'NONE'
    assert script_category('東京') == 'OTHER'
