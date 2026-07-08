"""Shared text-cleaning layer for the textual engines — single source for
stripping PDF-extraction noise before ``summarize``/``keywords`` (and the
Insights panel) ever see the text.

Root cause this fixes: a PDF's extracted text is dominated by structural
artifacts that plain prose never has — page-break markers, unpunctuated front
matter (title/author/date/section headers), and dashed list items with no
terminal punctuation. TextRank's lead-position prior and YAKE's frequency
statistics both reward whatever comes first/most often, so this noise used to
win over the actual content (PLANO_INSIGHTS_QUALIDADE.md).

Deliberately excludes ``entities()`` (NER): front matter often carries
genuine ORG/PER/DATE entities ("Anthropic", "January 2024") that spaCy
benefits from seeing, unlike TextRank/YAKE which are actively misled by it.
The Insights panel opts entities into the cleaned text anyway, for a
consistent view across its three engines — see ``gui/views/insights_panel.py``.

Every function here is pure and idempotent-ish: cleaning already-clean text
is a harmless no-op, so a caller that already cleaned (e.g. the Insights
panel, once, for all three engines) never needs to worry about an engine
that also cleans internally (``summarize``, ``keywords``) double-processing.
"""

from __future__ import annotations

import re

# --- Page markers ------------------------------------------------------------
# core/document/converter.py is the only *producer* (via page_marker()); this
# module is the only *consumer* that parses the format back out — one shared
# template instead of two independently-maintained copies of the same string.
_PAGE_MARKER_TEMPLATE = "--- Página {page} ---"
_PAGE_MARKER_RE = re.compile(r"\n*[ \t]*--- Página \d+ ---[ \t]*\n*")


def page_marker(page: int) -> str:
    """Build the PDF page-break marker line for 1-indexed page ``page``."""
    return _PAGE_MARKER_TEMPLATE.format(page=page)


def strip_page_markers(text: str) -> str:
    """Remove PDF page-break marker lines, collapsing the blank lines around
    each one into a single paragraph break."""
    return _PAGE_MARKER_RE.sub("\n\n", text)


# --- Abbreviation masking ------------------------------------------------------
# Protects a small, fixed list of abbreviations from a naive `[.!?]`-based
# sentence-boundary split (summarize.split_sentences). Scoped to sentence
# splitting specifically -- keywords/entities don't split on punctuation, so
# they have no use for this.
_ABBREVIATIONS = ("e.g.", "i.e.", "et al.", "Dr.", "Sr.", "Sra.", "p. ex.")
# Private Use Area character: never appears in real text, so it round-trips
# through mask -> split -> unmask without colliding with document content.
_ABBR_DOT = ""


def mask_abbreviations(text: str) -> str:
    """Replace the dot(s) in known abbreviations with a placeholder so a
    naive sentence-boundary split never cuts inside one. Call
    :func:`unmask_abbreviations` on each resulting piece to restore it."""
    for abbr in _ABBREVIATIONS:
        text = text.replace(abbr, abbr.replace(".", _ABBR_DOT))
    return text


def unmask_abbreviations(text: str) -> str:
    """Restore the dots hidden by :func:`mask_abbreviations`."""
    return text.replace(_ABBR_DOT, ".")


# --- List-item boundaries ------------------------------------------------------
# A list line without terminal punctuation ("- Helpful") otherwise fuses with
# whatever follows once whitespace is collapsed for sentence splitting -- the
# next real sentence's start gets swallowed into the same run-on "sentence".
_LIST_ITEM_RE = re.compile(r"^([ \t]*[-–•][ \t]+)(.+?)[ \t]*$", re.MULTILINE)
_TERMINAL_PUNCT = (".", "!", "?", ":", ";")


def _terminate_list_items(text: str) -> str:
    """Ensure every dashed/bulleted list line ends with terminal punctuation."""

    def _terminate(match: re.Match[str]) -> str:
        prefix, item = match.group(1), match.group(2)
        if item and item[-1] not in _TERMINAL_PUNCT:
            item += "."
        return f"{prefix}{item}"

    return _LIST_ITEM_RE.sub(_terminate, text)


# --- Non-prose line filter ------------------------------------------------------
# Conservative: on the fence, keep. A false negative (mislabeling metadata as
# prose) just leaves a stray candidate in the pool for the length/graph
# filters downstream to sort out; a false positive (dropping a real sentence)
# loses content outright.
_MIN_PROSE_WORDS = 4


def is_prose_line(line: str) -> bool:
    """Heuristic: does *line* read like a sentence, not front-matter metadata?

    A line is treated as prose when it either ends in terminal punctuation
    (regardless of length -- a short but punctuated line is still a real
    sentence) or has at least ``_MIN_PROSE_WORDS`` words (long enough that
    it's more likely a merged paragraph fragment than a title/author/date
    line). Short **and** unpunctuated is the only case flagged as metadata --
    exactly the shape of a PDF title page ("Claude's Constitution", "January
    2024", a lone page number).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[-1] in _TERMINAL_PUNCT:
        return True
    return len(stripped.split()) >= _MIN_PROSE_WORDS


def filter_non_prose(text: str) -> str:
    """Drop lines that look like front matter rather than prose (see
    :func:`is_prose_line`), preserving the order of the rest. Blank lines are
    kept so paragraph breaks survive."""
    kept = [
        line for line in text.split("\n") if not line.strip() or is_prose_line(line)
    ]
    return "\n".join(kept)


def clean_document_text(text: str) -> str:
    """Strip PDF-extraction noise before ``summarize``/``keywords`` see the text.

    Pipeline: drop page markers -> punctuate bare list items -> drop
    non-prose lines. Does **not** mask abbreviations -- that is
    ``summarize.split_sentences``'s own concern, applied only where a naive
    punctuation split is actually happening.
    """
    text = strip_page_markers(text)
    text = _terminate_list_items(text)
    text = filter_non_prose(text)
    return text
