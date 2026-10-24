"""Conservative Unicode cleanup without transliteration or accent removal."""

import unicodedata

MAX_NAME_LENGTH = 200


def normalize_name(name: str) -> str:
    """Validate a name and return a stable form for character comparisons.

    Limits count Unicode code points, not bytes. NFKC standardizes compatible
    forms; casefold handles case; a second NFKC recomposes casefold output.
    Splitting and joining trims and collapses Unicode whitespace. The caller
    keeps the original text for display. No translation or token sorting occurs.
    """
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"name must contain at most {MAX_NAME_LENGTH} characters")

    normalized = unicodedata.normalize("NFKC", name)
    normalized = unicodedata.normalize("NFKC", normalized.casefold())
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError("name must not be blank")
    if len(normalized) > MAX_NAME_LENGTH:
        raise ValueError(
            f"normalized name must contain at most {MAX_NAME_LENGTH} characters"
        )
    return normalized
