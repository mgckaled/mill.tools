"""Incremental indexing of the Library corpus into the vector store.

Consumes the typed items from ``scan_library()`` (PR6), keeps only the textual
kinds, chunks them with the project's shared ``split_text`` and embeds the new or
changed ones. Embedding is injected as ``embed_fn`` so the indexing logic stays
unit-testable without a running Ollama.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.core.rag.store import VectorStore
from src.core.rag.types import ChunkMeta
from src.llm_utils import split_text

if TYPE_CHECKING:
    import numpy as np

    from src.core.library.types import LibraryItem

# Library kinds that carry indexable plain text. For "image" only the
# `_description.txt` files match the suffix filter below — never the images
# themselves; for "document" only extracted/OCR text, never the PDFs.
TEXT_KINDS = {"transcription", "document", "image"}
TEXT_SUFFIXES = {".txt", ".md"}
# Data kinds are indexed via a *data card* (a textual description built by
# ``card_fn``), never by reading the file as text — so they match by kind alone,
# regardless of suffix (.csv/.json/.parquet/.xlsx).
DATA_KINDS = {"data"}
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Transcription files keep a metadata header separated from the body by a line
# of 64 dashes (see src.transcript_io.split_header_body, the shared owner of
# this same split for the analyzer/formatter/prompter pipeline). Other text
# kinds have no header, so the whole file is indexed.
_HEADER_SEP = "-" * 64

# The real header is a handful of short lines, always well under this. Bounds
# the separator search to a prefix window so a coincidental run of 64 dashes
# deep in a plain document's own body isn't mistaken for a header and doesn't
# silently drop everything before it.
_HEADER_SEARCH_WINDOW = 4096


def index_dir() -> Path:
    """Return the canonical on-disk index location (~/.mill-tools/rag/).

    Shared by the GUI worker and the CLI so both read and write the same store.
    Created lazily by ``VectorStore.persist`` — not here.
    """
    return Path.home() / ".mill-tools" / "rag"


def _is_indexable(item: LibraryItem) -> bool:
    """True if the indexer knows how to embed this item (text or data card)."""
    if item.kind in TEXT_KINDS and item.suffix in TEXT_SUFFIXES:
        return True
    return item.kind in DATA_KINDS


def indexable_items(items: list[LibraryItem]) -> list[LibraryItem]:
    """Filter a scan to the items the indexer knows how to embed.

    Text kinds (``.txt``/``.md``) are read directly; data kinds are turned into a
    textual *data card* by the injected ``card_fn`` (see :func:`build_index`).
    """
    return [it for it in items if _is_indexable(it)]


def _read_indexable_text(item: LibraryItem) -> str:
    """Return the plain-text body of a Library item (header stripped if present)."""
    raw = Path(item.path).read_text(encoding="utf-8", errors="replace")
    idx = raw.find(_HEADER_SEP)
    if 0 <= idx <= _HEADER_SEARCH_WINDOW:
        return raw[idx + len(_HEADER_SEP) :].strip()
    return raw.strip()


def _text_for(item: LibraryItem, card_fn: Callable[[LibraryItem], str] | None) -> str:
    """Resolve the text to chunk for an item: a data card or the file body."""
    if item.kind in DATA_KINDS:
        return card_fn(item) if card_fn is not None else ""
    return _read_indexable_text(item)


def _index_one(
    item: LibraryItem,
    store: VectorStore,
    embed_fn: Callable[[list[str]], np.ndarray],
    card_fn: Callable[[LibraryItem], str] | None,
) -> None:
    """Chunk, embed and store one item, replacing any of its existing chunks.

    Shared by :func:`index_files` and :func:`build_index` — their per-item
    bodies were verbatim duplicates. A failure is logged and skipped rather
    than raised, so one bad item never aborts the whole indexing run:

    - A text-building failure (bad/locked file, or a data card hitting a
      broken DuckDB read) happens *before* ``drop_source`` runs, so the
      item's existing chunks are left intact.
    - An embed failure (e.g. Ollama restarting mid-job) happens *after*
      ``drop_source`` — the item is left de-indexed until a future
      successful reindex, same outcome as if its content had gone blank.

    ``ChunkMeta.source_path`` is the item's path *resolved* (``Path.resolve()``),
    not the raw scanner path — this must match ``classify.record_label``'s own
    ``Path(...).resolve()``, or the two silently diverge on Windows and
    ``classify._training_xy``'s join against recorded labels matches zero
    documents (M6). ``build_index``'s incremental/reconciliation checks
    resolve the same way, so this stays consistent across the module.
    """
    try:
        text = _text_for(item, card_fn)
    except Exception as exc:  # bad/locked file — skip, don't crash
        logging.warning("[!] Could not build text for %s: %s", item.path.name, exc)
        return

    resolved_path = str(Path(item.path).resolve())
    store.drop_source(resolved_path)  # replace any previous chunks
    chunks = [
        c
        for c in split_text(text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        if c.strip()
    ]
    if not chunks:
        return

    try:
        vecs = embed_fn(chunks)
    except Exception as exc:  # e.g. Ollama down mid-batch — skip, don't crash
        logging.warning("[!] Could not embed %s: %s", item.path.name, exc)
        return

    metas = [
        ChunkMeta(
            source_path=resolved_path,
            kind=item.kind,
            mtime=item.modified,
            chunk_idx=i,
            text=c,
        )
        for i, c in enumerate(chunks)
    ]
    store.add(vecs, metas)
    logging.debug("[d] Indexed %s → %d chunk(s)", item.path.name, len(chunks))


def index_files(
    items: list[LibraryItem],
    store: VectorStore,
    embed_fn: Callable[[list[str]], np.ndarray],
    *,
    progress_cb: Callable[[int, int], None] | None = None,
    card_fn: Callable[[LibraryItem], str] | None = None,
) -> VectorStore:
    """Index a specific set of items into the store — additive, no reconciliation.

    Unlike :func:`build_index`, this never drops sources that are absent from
    *items* (so it can index a single file the user picked without wiping the
    rest of the index) and always re-embeds the given files (the user asked for
    it explicitly). Each item's stale chunks are replaced. Returns the store.
    """
    total = len(items)
    for n, item in enumerate(items, 1):
        _index_one(item, store, embed_fn, card_fn)
        if progress_cb:
            progress_cb(n, total)
    return store


def build_index(
    items: list[LibraryItem],
    store: VectorStore,
    embed_fn: Callable[[list[str]], np.ndarray],
    *,
    progress_cb: Callable[[int, int], None] | None = None,
    card_fn: Callable[[LibraryItem], str] | None = None,
) -> VectorStore:
    """Embed new/changed items, skip unchanged, drop deleted. Returns store.

    Incremental contract:
    - An item is *unchanged* when ``(path, mtime)`` already exists in the store —
      it is skipped without re-embedding.
    - An item is *changed* when its path is present but the mtime differs — its
      old chunks are dropped and it is re-embedded.
    - Items whose source no longer exists are reconciled away at the end.

    Args:
        items: The full ``scan_library()`` result (filtered internally).
        store: The vector store to grow/refresh in place.
        embed_fn: Maps a list of chunk strings to an (M, D) matrix.
        progress_cb: Optional ``(current, total)`` callback, one call per item
            processed (drives the GUI/CLI progress bar).
        card_fn: Builds the textual *data card* for a ``kind="data"`` item. When
            absent, data items are silently skipped (text kinds still index).

    Returns:
        The same ``store``, mutated.
    """
    indexed = {(m.source_path, m.mtime) for m in store.meta}
    text_items = indexable_items(items)
    total = len(text_items)

    for n, item in enumerate(text_items, 1):
        # Resolved the same way _index_one stores it (M6) — comparing a raw
        # scanner path against a resolved ChunkMeta.source_path would treat
        # every already-indexed item as "changed" on every run.
        key = (str(Path(item.path).resolve()), item.modified)
        if key not in indexed:  # new or changed → (re)index
            _index_one(item, store, embed_fn, card_fn)
        if progress_cb:
            progress_cb(n, total)

    # Reconciliation: drop chunks whose source no longer exists on disk.
    alive = {str(Path(it.path).resolve()) for it in items}
    for gone in {m.source_path for m in store.meta} - alive:
        logging.debug("[d] Reconciling removed source: %s", gone)
        store.drop_source(gone)

    return store
