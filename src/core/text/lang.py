"""Tiny PT/EN language heuristic — no dependency, just stopword overlap.

The textual engines need a language hint (YAKE's ``lan``, the spaCy model). A
full language-detection library is overkill for a corpus that is almost always
Portuguese or English, so this counts a handful of unambiguous function words and
picks the winner. Defaults to ``"pt"`` (the app's primary language) on a tie or
empty text.
"""

from __future__ import annotations

import re

# "do" and "as" used to be here too, but both are also top-100 English words
# ("do you", "as well") — that overlap systematically biased English text
# toward "pt" whenever it happened to use either. Replaced with markers that
# have no English reading.
_PT_MARKERS = frozenset(
    {
        "de",
        "que",
        "não",
        "uma",
        "para",
        "com",
        "como",
        "mas",
        "os",
        "da",
        "é",
        "já",
        "então",
        "também",
    }
)
_EN_MARKERS = frozenset(
    {"the", "and", "of", "to", "is", "that", "with", "for", "are", "this", "was", "it"}
)

_WORD = re.compile(r"[a-zA-ZÀ-ÿ]+")


def detect_lang(text: str) -> str:
    """Return ``"pt"`` or ``"en"`` from stopword overlap (PT on tie/empty)."""
    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return "pt"
    pt = sum(w in _PT_MARKERS for w in words)
    en = sum(w in _EN_MARKERS for w in words)
    return "en" if en > pt else "pt"
