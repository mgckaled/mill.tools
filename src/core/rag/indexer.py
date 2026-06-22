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
# of 64 dashes (see analyzer._extract_transcription_body). Other text kinds have
# no header, so the whole file is indexed.
_HEADER_SEP = "-" * 64


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
    if _HEADER_SEP in raw:
        return raw.split(_HEADER_SEP, 1)[1].strip()
    return raw.strip()


def _text_for(item: LibraryItem, card_fn: Callable[[LibraryItem], str] | None) -> str:
    """Resolve the text to chunk for an item: a data card or the file body."""
    if item.kind in DATA_KINDS:
        return card_fn(item) if card_fn is not None else ""
    return _read_indexable_text(item)


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
        key = (str(item.path), item.modified)
        if key in indexed:  # unchanged → skip
            if progress_cb:
                progress_cb(n, total)
            continue

        # Resolve the text first (a data card may hit DuckDB); a failure leaves
        # any existing chunks intact rather than dropping then failing to re-add.
        try:
            text = _text_for(item, card_fn)
        except Exception as exc:  # bad/locked data file — skip, don't crash index
            logging.warning("[!] Could not build text for %s: %s", item.path.name, exc)
            if progress_cb:
                progress_cb(n, total)
            continue

        store.drop_source(str(item.path))  # changed → replace stale chunks
        chunks = [
            c
            for c in split_text(
                text,
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
            )
            if c.strip()
        ]
        if chunks:
            vecs = embed_fn(chunks)
            metas = [
                ChunkMeta(
                    source_path=str(item.path),
                    kind=item.kind,
                    mtime=item.modified,
                    chunk_idx=i,
                    text=c,
                )
                for i, c in enumerate(chunks)
            ]
            store.add(vecs, metas)
            logging.debug("[d] Indexed %s → %d chunk(s)", item.path.name, len(chunks))
        if progress_cb:
            progress_cb(n, total)

    # Reconciliation: drop chunks whose source no longer exists on disk.
    alive = {str(it.path) for it in items}
    for gone in {m.source_path for m in store.meta} - alive:
        logging.debug("[d] Reconciling removed source: %s", gone)
        store.drop_source(gone)

    return store
