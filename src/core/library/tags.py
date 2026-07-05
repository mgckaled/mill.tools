"""Auto-tags for Library items — cached keyphrases that become searchable.

Each textual item (``.txt``/``.md``) gets a handful of keyphrases (YAKE, via
``core/text/keywords``) that the Library can match in its search box, so a file
surfaces by *content* and not only by filename. The result is deterministic, so
it is cached on disk keyed by ``(path, mtime)`` — the same convention as the data
``assess``/``datacard`` caches — and recomputed only when the file changes.

Pure core: gate-aware (returns ``[]`` when the ``[nlp]`` extra is absent), so the
feature degrades silently instead of breaking the Library scan.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.text import keywords
from src.core.text.lang import detect_lang
from src.core.text.reader import read_document_text

if TYPE_CHECKING:
    from src.core.library.types import LibraryItem

# Only plain-text outputs carry searchable content; media/data are tagged by kind
# elsewhere. Keep the tag set small — these are search hints, not a summary.
_TEXT_SUFFIXES = {".txt", ".md"}
_TOP_N = 6


def is_taggable(item: LibraryItem) -> bool:
    """True if the item is a plain-text file worth extracting keyphrases from."""
    return item.suffix in _TEXT_SUFFIXES


def tags_for_text(text: str, *, top_n: int = _TOP_N, lang: str = "pt") -> list[str]:
    """Return up to ``top_n`` keyphrase tags for *text* (``[]`` if YAKE is absent)."""
    if not keywords.is_available() or not text.strip():
        return []
    return [phrase for phrase, _ in keywords.keyphrases(text, lang=lang, top_n=top_n)]


# ---------------------------------------------------------------------------
# Cache: ~/.mill-tools/library_tags.json, keyed by absolute path → {mtime, tags}.
# ---------------------------------------------------------------------------


def _cache_file() -> Path:
    """Return the on-disk tag cache path (~/.mill-tools/library_tags.json)."""
    return Path.home() / ".mill-tools" / "library_tags.json"


def _load_cache(cache_file: Path) -> dict:
    """Load the cache dict, tolerating a missing or malformed file."""
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_cached_tags(path: Path, *, cache_file: Path | None = None) -> list[str] | None:
    """Return cached tags for *path* if present and still fresh (mtime match)."""
    path = Path(path)
    cache_file = cache_file or _cache_file()
    entry = _load_cache(cache_file).get(str(path.resolve()))
    if not entry:
        return None
    try:
        if Path(path).stat().st_mtime != entry.get("mtime"):
            return None
    except OSError:
        return None
    tags = entry.get("tags")
    return tags if isinstance(tags, list) else None


def save_tags(path: Path, tags: list[str], *, cache_file: Path | None = None) -> None:
    """Cache *tags* for *path*, stamped with its current mtime."""
    path = Path(path)
    cache_file = cache_file or _cache_file()
    try:
        mtime = Path(path).stat().st_mtime
    except OSError as exc:
        logging.debug("[d] Cannot stat %s for tag cache: %s", path, exc)
        return
    data = _load_cache(cache_file)
    data[str(path.resolve())] = {"mtime": mtime, "tags": tags}
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logging.debug("[d] Could not write tag cache: %s", exc)


def tags_for_item(item: LibraryItem, *, cache_file: Path | None = None) -> list[str]:
    """Return (and cache) the keyphrase tags for a Library item.

    Non-text items yield ``[]``. A cached entry is reused until the file's mtime
    changes; otherwise the body is read (transcription header stripped) and tagged.
    """
    if not is_taggable(item):
        return []
    cached = load_cached_tags(item.path, cache_file=cache_file)
    if cached is not None:
        return cached
    try:
        text = read_document_text(item.path)
    except OSError as exc:
        logging.debug("[d] Could not read %s for tags: %s", item.path, exc)
        return []
    tags = tags_for_text(text, lang=detect_lang(text))
    # Only persist a result computed with the [nlp] extra actually present. A
    # gate-off "[]" is not a real extraction — caching it would poison the
    # entry: the mtime doesn't change when the user later installs [nlp], so
    # the stale "[]" would keep being served forever. A gate-on "[]" (genuinely
    # empty text) is a legitimate result and still gets cached below.
    if keywords.is_available():
        save_tags(item.path, tags, cache_file=cache_file)
    return tags
