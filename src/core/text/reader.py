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


def read_document_text(path: str | Path) -> str:
    """Return the plain-text body of a document (transcription header stripped)."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    if _HEADER_SEP in raw:
        return raw.split(_HEADER_SEP, 1)[1].strip()
    return raw.strip()
