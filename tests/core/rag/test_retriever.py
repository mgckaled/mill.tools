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
def test_retrieve_empty_store_skips_embed_query_fn():
    """An empty store has nothing to search — retrieve must not pay for the
    embed_query_fn round-trip (a real Ollama call in production) just to
    discard the result."""
    from src.core.rag.retriever import retrieve
    from src.core.rag.store import VectorStore

    calls: list[str] = []

    def embed_query(q: str):
        calls.append(q)
        return np.zeros(3, dtype=np.float32)

    hits = retrieve("pergunta", VectorStore(dim=3), embed_query, k=6)

    assert hits == []
    assert calls == []


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
def test_retrieve_scope_returns_full_k_even_when_outranked_globally():
    """Regression: a selective scope must not lose recall to an unscoped cutoff.

    Before the pre-filter fix, ``retrieve`` widened to k*3 candidates globally
    and only then filtered by scope — so a document whose chunks all score
    below the top k*3 globally could come back with fewer than k hits, or none,
    even though it has plenty of relevant content.
    """
    from src.core.rag.retriever import retrieve

    # Many chunks from other documents score near-perfectly against the query...
    other_docs = [([0.99, 0.01 * i, 0], _meta(f"other_{i}.txt", 0)) for i in range(20)]
    # ...while the scoped document's chunks score far lower, but there are only 3.
    scoped_docs = [
        ([0.1, 0.9, 0], _meta("doc_a.txt", 0)),
        ([0.05, 0.95, 0], _meta("doc_a.txt", 1)),
        ([0.0, 1.0, 0], _meta("doc_a.txt", 2)),
    ]
    store = _store_with(other_docs + scoped_docs)

    hits = retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
        scope="doc_a.txt",
    )
    assert len(hits) == 3
    assert {h.meta.source_path for h in hits} == {"doc_a.txt"}


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


@pytest.mark.unit
def test_retrieve_hybrid_surfaces_lexical_match_dense_alone_would_miss():
    """A chunk with the weakest dense similarity but an exact match for a rare
    query term should still make the top-k via BM25 fusion — pure dense
    retrieval (by construction here) would rank it dead last and drop it."""
    import math

    from src.core.rag.retriever import retrieve

    def _vec(deg: float) -> list[float]:
        rad = math.radians(deg)
        return [math.cos(rad), math.sin(rad), 0.0]

    store = _store_with(
        [
            (_vec(0), _meta("d0.txt", 0, text="unrelated filler about gardening")),
            (_vec(10), _meta("d1.txt", 0, text="another unrelated passage about cars")),
            (_vec(20), _meta("d2.txt", 0, text="yet another bit about trains")),
            (
                _vec(30),
                _meta("d3.txt", 0, text="more filler text about clouds and rain"),
            ),
            (
                _vec(80),
                _meta("target.txt", 0, text="zephyrion quasar appears exactly here"),
            ),
        ]
    )
    hits = retrieve(
        "zephyrion quasar",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
    )
    sources = [h.meta.source_path for h in hits]
    assert "target.txt" in sources


@pytest.mark.unit
def test_retrieve_skips_rrf_fusion_when_bm25_has_no_signal():
    """A query with zero vocabulary overlap with the corpus gets an all-zero
    BM25 vector. Fusing it in anyway would still rank it via RRF's tie-break
    (earlier index wins ties), which can outrank the true best dense match
    with a document that merely happens to sit earlier in the store — pure
    insertion-order bias. retrieve() must fall back to dense-only ranking
    when lexical.max() <= 0.

    These three cosine values + insertion order are a known case (found by a
    brute-force search) where naive RRF fusion picks d0.txt as the top hit
    even though d2.txt has the clearly highest dense cosine (0.997) — dense
    -only ranking must pick d2.txt instead.
    """
    import math

    from src.core.rag.retriever import retrieve

    def _vec(cosine: float) -> list[float]:
        return [cosine, math.sqrt(1 - cosine**2), 0.0]

    store = _store_with(
        [
            (_vec(0.61538511), _meta("d0.txt", text="zzz yyy xxx")),
            (_vec(0.38367755), _meta("d1.txt", text="zzz yyy xxx")),
            (_vec(0.99720994), _meta("d2.txt", text="zzz yyy xxx")),
        ]
    )
    hits = retrieve(
        "totally unrelated gibberish not in corpus",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
    )
    assert hits[0].meta.source_path == "d2.txt"


@pytest.mark.unit
def test_retrieve_score_is_dense_cosine_not_fused_value():
    """`.score` stays the dense cosine (in [-1, 1]) even under hybrid retrieval —
    the out-of-scope check compares it against a cosine threshold, so its meaning
    must not silently change to a tiny RRF fraction."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [([1, 0, 0], _meta("a", text="x")), ([0, 1, 0], _meta("b", text="x"))]
    )
    hits = retrieve("q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=2)
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)
