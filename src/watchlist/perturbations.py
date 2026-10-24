"""Small deterministic spelling experiments; no language or identity inference."""

import hashlib
import unicodedata


def script_category(text: str) -> str:
    """Label alphabetic Unicode names conservatively, not the spoken language."""
    scripts = set()
    for char in text:
        if char.isalpha():
            name = unicodedata.name(char, "")
            scripts.add(next((s for s in ("LATIN", "ARABIC", "CYRILLIC") if s in name), "OTHER"))
    return "+".join(sorted(scripts)) or "NONE"


def variants(text: str, key: str, seed: int = 42) -> list[dict]:
    """Return transformations with positions; inapplicable operations are explicit."""
    position = int(hashlib.sha256(f"{seed}:{key}".encode()).hexdigest(), 16)
    letters = [i for i, char in enumerate(text) if char.isalpha()]
    swaps = [i for i in range(len(text) - 1)
             if text[i].isalpha() and text[i + 1].isalpha() and text[i] != text[i + 1]]
    tokens = text.split()
    output = [{"kind": "exact", "text": text, "operation": "unchanged"},
              {"kind": "formatting", "text": "  " + "   ".join(tokens).upper() + "  ",
               "operation": "uppercase and whitespace"}]
    for kind, positions in (("deletion", letters), ("adjacent_swap", swaps)):
        if not positions:
            output.append({"kind": kind, "text": None, "operation": "no eligible characters"})
            continue
        i = positions[position % len(positions)]
        changed = (text[:i] + text[i + 1:] if kind == "deletion" else
                   text[:i] + text[i + 1] + text[i] + text[i + 2:])
        output.append({"kind": kind, "text": changed, "operation": f"character position {i}"})
    for kind in ("missing_word", "word_order"):
        if len(tokens) < 2:
            output.append({"kind": kind, "text": None, "operation": "fewer than two tokens"})
            continue
        i = position % len(tokens)
        changed = (tokens[:i] + tokens[i + 1:] if kind == "missing_word" else
                   [tokens[-1], *tokens[1:-1], tokens[0]])
        output.append({"kind": kind, "text": " ".join(changed),
                       "operation": f"drop token {i}" if kind == "missing_word" else "swap first and last token"})
    return output
