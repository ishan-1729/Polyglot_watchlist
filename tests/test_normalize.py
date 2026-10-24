"""Known Unicode examples and validation boundaries."""

import pytest

from watchlist.normalize import normalize_name


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("  LUMA\t VESPER\n", "luma vesper"),
        ("Ｌｕｍａ　Ｖｅｓｐｅｒ", "luma vesper"),
        ("E\u0301lo Nivara", "élo nivara"),
        ("ÉLO NIVARA", "élo nivara"),
        ("Straße", "strasse"),
        ("Мира\u00a0ВЕЛУНЕ", "мира велуне"),
        ("  سيرا   لومين ", "سيرا لومين"),
        ("L. Vesper", "l. vesper"),
        ("Luma-Vesper", "luma-vesper"),
        ("ΐ", "ΐ"),
        ("\ufb03", "ffi"),
    ],
)
def test_known_normalizations_are_idempotent(original: str, expected: str) -> None:
    assert normalize_name(original) == expected
    assert normalize_name(expected) == expected


def test_accents_and_scripts_are_not_erased() -> None:
    assert normalize_name("Élo") != normalize_name("Elo")
    assert normalize_name("Мира") != normalize_name("Mira")


@pytest.mark.parametrize("name", ["", " \t\n", "\u00a0\u3000"])
def test_blank_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        normalize_name(name)


def test_non_string_is_rejected() -> None:
    with pytest.raises(TypeError, match="string"):
        normalize_name(None)  # type: ignore[arg-type]


def test_input_length_boundary() -> None:
    assert normalize_name("a" * 200) == "a" * 200
    with pytest.raises(ValueError, match="at most 200"):
        normalize_name("a" * 201)


def test_normalization_expansion_obeys_length_limit() -> None:
    assert normalize_name("\ufb03" * 66) == "ffi" * 66
    with pytest.raises(ValueError, match="normalized name"):
        normalize_name("\ufb03" * 67)
