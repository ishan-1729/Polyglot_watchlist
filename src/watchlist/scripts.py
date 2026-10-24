"""Conservative writing-script evidence from the runtime Unicode database.

This is a documented name/category approximation for Latin, Arabic, Cyrillic
and Han, not a complete Unicode Script or Script_Extensions implementation and
not language detection. Unsupported letters, controls and unrecognized marks
produce UNKNOWN rather than an invented script. Punctuation and digits do not
establish a script. Recognized script-specific marks contribute their script,
so a detached Arabic mark cannot hide shared Arabic evidence in Latin text.
Marks or symbols without any recognized letters cannot establish disjointness.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import unicodedata


SUPPORTED_SCRIPTS = frozenset({'LATIN', 'ARABIC', 'CYRILLIC', 'HAN'})
UNKNOWN = 'UNKNOWN'
UNICODE_VERSION = unicodedata.unidata_version
SCRIPT_METHOD = 'unicode-name-category-conservative-v1'
_VALID_SCRIPTS = SUPPORTED_SCRIPTS | {UNKNOWN}


@dataclass(frozen=True)
class ScriptProfile:
    """Immutable script evidence and character-category counts.

    ``unknown`` counts unsupported/unclassified characters and may overlap
    another category, for example a Greek letter counted in both ``letters``
    and ``unknown``. UNKNOWN also flags script-bearing marks/symbols without
    recognized letters, even when each character has an identified script.
    """

    scripts: frozenset[str]
    letters: int
    digits: int
    marks: int
    punctuation: int
    symbols: int
    whitespace: int
    unknown: int


def _named_script(character: str) -> str | None:
    """Recognize only supported names; unfamiliar names remain unclassified."""
    # Despite its name, ARABIC TATWEEL is a shared extender, not proof of Arabic.
    if character == '\u0640':
        return None
    name = unicodedata.name(character, '')
    words = name.split()
    for script in ('LATIN', 'ARABIC', 'CYRILLIC'):
        if script in words:
            return script
    if (name.startswith(('CJK UNIFIED IDEOGRAPH-', 'CJK COMPATIBILITY IDEOGRAPH-',
                         'CJK RADICAL ', 'KANGXI RADICAL '))
            or name in {'IDEOGRAPHIC NUMBER ZERO', 'IDEOGRAPHIC ITERATION MARK',
                        'VERTICAL IDEOGRAPHIC ITERATION MARK'}):
        return 'HAN'
    return None


def _neutral_mark(character: str) -> bool:
    """Recognize the basic inherited diacritics and variation-selector blocks.

    Other unrecognized marks remain uncertain. This deliberately favors
    rejecting a cross-script claim over guessing from a mark's appearance.
    """
    codepoint = ord(character)
    return (0x0300 <= codepoint <= 0x036F or 0xFE00 <= codepoint <= 0xFE0F
            or 0xE0100 <= codepoint <= 0xE01EF)


def script_profile(text: str) -> ScriptProfile:
    """Inspect original valid Unicode text without normalizing away evidence."""
    if not isinstance(text, str):
        raise ValueError('script analysis requires text')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError('script analysis requires valid Unicode text') from exc
    scripts: set[str] = set()
    letter_scripts: set[str] = set()
    counts = dict(letters=0, digits=0, marks=0, punctuation=0, symbols=0,
                  whitespace=0, unknown=0)
    for character in text:
        category = unicodedata.category(character)
        named = _named_script(character)
        if character.isspace():
            counts['whitespace'] += 1
        elif category.startswith('L') or category == 'Nl':
            counts['letters'] += 1
            if named is None:
                counts['unknown'] += 1
            else:
                scripts.add(named)
                letter_scripts.add(named)
        elif category.startswith('N'):
            counts['digits'] += 1
        elif category.startswith('M'):
            counts['marks'] += 1
            if named is not None:
                scripts.add(named)
            elif not _neutral_mark(character):
                counts['unknown'] += 1
        elif category.startswith('P'):
            counts['punctuation'] += 1
        elif category.startswith('S'):
            counts['symbols'] += 1
            if named is not None:
                scripts.add(named)
        else:
            counts['unknown'] += 1
    if counts['unknown'] or scripts and not letter_scripts:
        scripts.add(UNKNOWN)
    return ScriptProfile(scripts=frozenset(scripts), **counts)


def script_set(text: str) -> frozenset[str]:
    """Return supported script tokens plus UNKNOWN when evidence is uncertain."""
    return script_profile(text).scripts


def _checked_scripts(value: Collection[str]) -> frozenset[str]:
    """Accept actual token collections, never a coarse/composite label string."""
    if (isinstance(value, (str, bytes, bytearray, Mapping))
            or not isinstance(value, Collection)):
        raise ValueError('scripts must be a collection of script tokens')
    if any(not isinstance(script, str) or script not in _VALID_SCRIPTS for script in value):
        raise ValueError('scripts contain an unsupported or composite script token')
    return frozenset(value)


def disjoint_scripts(left: Collection[str], right: Collection[str]) -> bool:
    """Require nonempty, known, nonoverlapping script evidence on both sides.

    For a target with several retained aliases, callers must union every alias's
    script set first. A single overlapping or unknown alias prevents the claim.
    """
    first, second = _checked_scripts(left), _checked_scripts(right)
    return bool(first and second and UNKNOWN not in first and UNKNOWN not in second
                and first.isdisjoint(second))
