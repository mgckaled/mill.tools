"""
transcript_io.py: Split a transcription file into its metadata header and body.

The three LLM pipeline stages (analyzer/formatter/prompter) each parsed the
64-dash header separator independently, with diverging semantics — formatter
and prompter had no bound on the search, so a coincidental run of 64 dashes
deep in a plain document's own body could be mistaken for the separator and
silently amputate the body. This module is the single owner of SEPARATOR and
the parsing logic; analyzer's windowed guard is now applied everywhere.
"""

from __future__ import annotations

SEPARATOR = "-" * 64

# The real metadata header is a handful of short lines, always well under
# this. Bounds the separator search to a prefix window so a coincidental run
# of 64 dashes deep in a plain document's own body isn't mistaken for a
# header — which would silently drop everything before it as "metadata".
HEADER_SEARCH_WINDOW = 4096


def split_header_body(raw_text: str) -> tuple[str, str]:
    """Split *raw_text* into (header_text, body_text) at the SEPARATOR line.

    Args:
        raw_text: Full file content, optionally including a metadata header
            followed by a line of 64 dashes.

    Returns:
        Tuple of (header_text, body_text). header_text excludes the
        separator itself and is "" when no separator is found within the
        header search window — body_text is then the whole, stripped input.
    """
    idx = raw_text.find(SEPARATOR)
    if not (0 <= idx <= HEADER_SEARCH_WINDOW):
        return "", raw_text.strip()
    return raw_text[:idx], raw_text[idx + len(SEPARATOR) :].strip()


def parse_header_meta(header_text: str) -> dict:
    """Parse "key: value" lines from a transcription header into a dict.

    Args:
        header_text: The header portion returned by split_header_body
            (may be "").

    Returns:
        Dictionary of metadata fields. Lines without a colon, or with an
        empty key/value after stripping, are skipped.
    """
    meta = {}
    for line in header_text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                meta[key] = value
    return meta
