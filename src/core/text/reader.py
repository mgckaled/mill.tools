"""Read a document's full text — header-stripped, the unit the engines work on.

Mirrors the RAG indexer's body extraction (``rag/indexer._read_indexable_text``):
transcription files carry a metadata header separated by a 64-dash line, which is
dropped so the textual engines (keywords/summary/entities) see only the body.
Other text kinds have no header and are returned whole. Kept tiny and pure so the
CLI/GUI can feed a path to the engines without re-deriving the convention.
"""

from __future__ import annotations

from pathlib import Path

# Transcription metadata header separator (see analyzer._extract_transcription_body).
_HEADER_SEP = "-" * 64

# The real header (title/channel/date/duration/language/tags/url) is a handful
# of short lines, always well under this. Bounding the search to a prefix
# window avoids treating a coincidental run of 64 dashes deep in a plain
# document's own body (e.g. a markdown rule) as a header separator, which
# would silently discard everything before it as "metadata".
_HEADER_SEARCH_WINDOW = 4096


def read_document_text(path: str | Path) -> str:
    """Return the plain-text body of a document (transcription header stripped)."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    idx = raw.find(_HEADER_SEP)
    if 0 <= idx <= _HEADER_SEARCH_WINDOW:
        return raw[idx + len(_HEADER_SEP) :].strip()
    return raw.strip()
