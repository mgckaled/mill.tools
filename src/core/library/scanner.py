"""Filesystem scanner that turns output/ into a typed, filterable index."""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.library.types import (
    KIND_AUDIO,
    KIND_DOCUMENT,
    KIND_IMAGE,
    KIND_TRANSCRIPTION,
    KIND_VIDEO,
    LibraryItem,
)
from src.utils import (
    AUDIO_PROCESSED_DIR,
    AUDIO_SOURCE_DIR,
    DOCUMENT_PROCESSED_DIR,
    DOCUMENT_SOURCE_DIR,
    IMAGE_PROCESSED_DIR,
    IMAGE_SOURCE_DIR,
    TRANSCRIPTIONS_ANALYSIS_DIR,
    TRANSCRIPTIONS_DIGEST_DIR,
    TRANSCRIPTIONS_TEXT_DIR,
    VIDEO_PROCESSED_DIR,
    VIDEO_SOURCE_DIR,
)


def _library_roots() -> list[tuple[Path, str, str]]:
    """Build the (directory, kind, category) table from utils.py constants.

    Resolved lazily on each call so tests can monkeypatch the underlying
    ``src.utils`` path constants and still see the new values (a module-level
    list would capture the originals at import time).
    """
    return [
        (AUDIO_SOURCE_DIR, KIND_AUDIO, "source"),
        (AUDIO_PROCESSED_DIR, KIND_AUDIO, "processed"),
        (VIDEO_SOURCE_DIR, KIND_VIDEO, "source"),
        (VIDEO_PROCESSED_DIR, KIND_VIDEO, "processed"),
        (IMAGE_SOURCE_DIR, KIND_IMAGE, "source"),
        (IMAGE_PROCESSED_DIR, KIND_IMAGE, "processed"),
        (DOCUMENT_SOURCE_DIR, KIND_DOCUMENT, "source"),
        (DOCUMENT_PROCESSED_DIR, KIND_DOCUMENT, "processed"),
        (TRANSCRIPTIONS_TEXT_DIR, KIND_TRANSCRIPTION, "text"),
        (TRANSCRIPTIONS_ANALYSIS_DIR, KIND_TRANSCRIPTION, "analysis"),
        (TRANSCRIPTIONS_DIGEST_DIR, KIND_TRANSCRIPTION, "digest"),
    ]


def classify_path(path: Path) -> tuple[str, str] | None:
    """Return (kind, category) for a path under a known output directory.

    Pure and unit-testable: derives the logical kind from the directory the
    file lives in, independent of file extension. Returns None when the path
    is not under any known output root.
    """
    for root, kind, category in _library_roots():
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return kind, category
    return None


def scan_library(
    roots: list[tuple[Path, str, str]] | None = None,
) -> list[LibraryItem]:
    """Walk every output directory and build a flat, mtime-desc list of items.

    Missing directories are skipped silently (a fresh install has none yet).
    Unreadable files are skipped with a debug log instead of raising.
    """
    if roots is None:
        roots = _library_roots()

    items: list[LibraryItem] = []
    for root, kind, category in roots:
        if not root.exists():
            continue
        for p in root.iterdir():
            if not p.is_file():
                continue
            # Skip hidden/placeholder files (.gitkeep, .DS_Store, …) — these
            # keep empty output dirs in git but are not user artifacts.
            if p.name.startswith("."):
                continue
            try:
                st = p.stat()
            except OSError:
                logging.debug("[d] Skipping unreadable file: %s", p)
                continue
            items.append(
                LibraryItem(
                    path=p,
                    kind=kind,
                    category=category,
                    size_bytes=st.st_size,
                    modified=st.st_mtime,
                    stem=p.stem,
                    suffix=p.suffix.lower(),
                )
            )
    items.sort(key=lambda it: it.modified, reverse=True)
    return items


def filter_items(
    items: list[LibraryItem],
    *,
    kinds: set[str] | None = None,
    query: str | None = None,
    since: float | None = None,
) -> list[LibraryItem]:
    """Pure filter: by kind set, case-insensitive name substring, and min mtime."""
    out = items
    if kinds:
        out = [it for it in out if it.kind in kinds]
    if query:
        q = query.casefold()
        out = [it for it in out if q in it.path.name.casefold()]
    if since is not None:
        out = [it for it in out if it.modified >= since]
    return out


def sort_items(
    items: list[LibraryItem],
    *,
    by: str = "modified",
    desc: bool = True,
) -> list[LibraryItem]:
    """Pure sort by 'modified' | 'name' | 'size'."""
    keys = {
        "modified": lambda it: it.modified,
        "name": lambda it: it.path.name.casefold(),
        "size": lambda it: it.size_bytes,
    }
    return sorted(items, key=keys.get(by, keys["modified"]), reverse=desc)
