"""Unit tests for src/core/rag/retriever.py — top-k order and scope filtering."""

from __future__ import annotations

import numpy as np
import pytest


def _meta(source: str, idx: int = 0, *, kind: str = "transcription", text: str = "x"):
    from src.core.rag.types import ChunkMeta

    return ChunkMeta(source_path=source, kind=kind, mtime=1.0, chunk_idx=idx, text=text)


def _store_with(rows):
    """Build a VectorStore from a list of (vector, meta) pairs."""
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    vecs = np.array([v for v, _ in rows], dtype=np.float32)
    store.add(vecs, [m for _, m in rows])
    return store


@pytest.mark.unit
def test_retrieve_orders_by_similarity_to_query():
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1, 0, 0], _meta("near", kind="transcription")),
            ([0, 1, 0], _meta("far", kind="transcription")),
        ]
    )
    # Query vector points exactly at the first row.
    hits = retrieve("q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=2)
    assert [h.meta.source_path for h in hits] == ["near", "far"]


@pytest.mark.unit
def test_retrieve_scope_by_single_document():
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1, 0, 0], _meta("doc_a.txt", 0)),
            ([0.9, 0.1, 0], _meta("doc_b.txt", 0)),
            ([0.8, 0.2, 0], _meta("doc_a.txt", 1)),
        ]
    )
    hits = retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
        scope="doc_a.txt",
    )
    assert {h.meta.source_path for h in hits} == {"doc_a.txt"}
    assert len(hits) == 2


@pytest.mark.unit
def test_retrieve_scope_by_kind():
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1, 0, 0], _meta("a.txt", 0, kind="transcription")),
            ([0.95, 0.05, 0], _meta("b.txt", 0, kind="document")),
            ([0.9, 0.1, 0], _meta("c.txt", 0, kind="document")),
        ]
    )
    hits = retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
        scope="document",
    )
    assert {h.meta.kind for h in hits} == {"document"}


@pytest.mark.unit
def test_retrieve_no_scope_searches_whole_corpus():
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1, 0, 0], _meta("a.txt", 0, kind="transcription")),
            ([0, 1, 0], _meta("b.txt", 0, kind="document")),
        ]
    )
    hits = retrieve("q", store, lambda _q: np.array([1, 1, 0], dtype=np.float32), k=2)
    assert len(hits) == 2
