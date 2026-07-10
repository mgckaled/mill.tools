"""Unit tests for src/core/rag/retriever.py — top-k order, scope filtering,
and pool+MMR diversification (Fase 3, PLANO_CONVERSA_MULTITURNO.md).

``retrieve()`` returns a ``RetrievalResult(hits, pool_max_score)`` NamedTuple
— every test unpacks it (``hits, _ = retrieve(...)``), matching how the real
callers (``batch.py``, ``recipes/registry/ai.py``, ``cli/ai.py``, the GUI
worker) use it.
"""

from __future__ import annotations

import numpy as np
import pytest


def _meta(source: str, idx: int = 0, *, kind: str = "transcription", text: str = "x"):
    from src.core.rag.types import ChunkMeta

    return ChunkMeta(source_path=source, kind=kind, mtime=1.0, chunk_idx=idx, text=text)


def _store_with(rows, *, dim: int = 3):
    """Build a VectorStore from a list of (vector, meta) pairs."""
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=dim)
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

    hits, pool_max = retrieve("pergunta", VectorStore(dim=3), embed_query, k=6)

    assert hits == []
    assert pool_max == 0.0
    assert calls == []


@pytest.mark.unit
def test_retrieve_orders_by_similarity_to_query():
    from src.core.rag.retriever import retrieve

    # Both rows sit within the relevance floor's band of the query (cosine 1.0
    # and 0.96) so this test isolates the *ordering* contract from the floor —
    # the floor's own cut is exercised by the dedicated tests below.
    store = _store_with(
        [
            ([1, 0, 0], _meta("near", kind="transcription")),
            ([0.96, 0.28, 0], _meta("far", kind="transcription")),  # cosine ≈ 0.96
        ]
    )
    # Query vector points exactly at the first row.
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=2
    )
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
    hits, _ = retrieve(
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
    hits, _ = retrieve(
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

    hits, _ = retrieve(
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
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 1, 0], dtype=np.float32), k=2
    )
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
    hits, _ = retrieve(
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
    hits, _ = retrieve(
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
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=2
    )
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)


# ── pool + MMR diversification (Fase 3, PLANO_CONVERSA_MULTITURNO.md) ─────────


@pytest.mark.unit
def test_retrieve_diversifies_near_duplicate_sibling_chunks():
    """Mirrors ``test_related_diversifies_near_duplicate_candidates``
    (core/ml/recommend.py) at the retriever level: with the chunker's overlap,
    sibling chunks of the same/adjacent content are near-duplicates by
    construction and can crowd out the rest of the context — MMR trades the
    redundant one away for a still-relevant, more diverse chunk."""
    from src.core.rag.retriever import retrieve

    # diverse.txt stays comfortably inside the relevance floor's band (cosine
    # 0.87, well above 0.90 − δ) so the floor keeps all three and this test
    # isolates MMR diversification — not the floor's boundary.
    store = _store_with(
        [
            ([0.9, 0.4359, 0.0], _meta("dup1.txt", text="x")),  # cosine to q = 0.90
            ([0.89, 0.4560, 0.0], _meta("dup2.txt", text="x")),  # cosine to q = 0.89
            ([0.87, 0.0, 0.493], _meta("diverse.txt", text="x")),  # cosine to q = 0.87
        ]
    )
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=2
    )
    paths = [h.meta.source_path for h in hits]

    assert paths[0] == "dup1.txt"  # most relevant still wins the first slot
    assert "diverse.txt" in paths  # MMR picks it over the redundant dup2.txt
    assert "dup2.txt" not in paths


@pytest.mark.unit
def test_retrieve_matches_plain_top_k_when_pool_covers_the_whole_store():
    """Fase 3.3 regression: when the pool already contains every valid
    candidate (a small store), the result must be identical to the pre-MMR
    plain fused top-k — MMR only changes anything when the pool holds more
    candidates than the ``k`` it must narrow down to."""
    from src.core.rag.retriever import retrieve

    # Cosines 1.0 / 0.98 / 0.96 — all within the relevance floor's band, so the
    # floor is a no-op here and the test isolates the plain-top-k contract.
    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("a.txt", text="x")),
            ([0.98, 0.199, 0.0], _meta("b.txt", text="x")),
            ([0.96, 0.28, 0.0], _meta("c.txt", text="x")),
        ]
    )
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=3
    )
    assert [h.meta.source_path for h in hits] == ["a.txt", "b.txt", "c.txt"]


@pytest.mark.unit
def test_retrieve_skips_mmr_for_single_document_scope(mocker):
    """Fase 3.2: a document-scoped question (Library's "Conversar sobre" bridge)
    gets mostly near-duplicate sibling chunks by construction — diversifying
    would push out the most relevant ones. MMR must not even run in that case,
    regardless of how many siblings the pool holds."""
    import src.core.rag.retriever as retriever
    from src.core.ml.recommend import _mmr as real_mmr

    mmr_spy = mocker.patch.object(retriever, "_mmr", side_effect=real_mmr)
    # 10 near-identical siblings of the same document — well over k, which
    # would normally force MMR to run for a non-document scope.
    store = _store_with([([1, 0, 0], _meta("doc_a.txt", i)) for i in range(10)])

    hits, _ = retriever.retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=3,
        scope="doc_a.txt",
    )

    mmr_spy.assert_not_called()
    assert len(hits) == 3


@pytest.mark.unit
def test_retrieve_calls_mmr_when_pool_exceeds_k_for_non_document_scope(mocker):
    """Companion to the skip test above: MMR does run for a corpus-wide (or
    kind-scoped) question once the pool holds more than k candidates."""
    import src.core.rag.retriever as retriever
    from src.core.ml.recommend import _mmr as real_mmr

    mmr_spy = mocker.patch.object(retriever, "_mmr", side_effect=real_mmr)
    # 10 distinct documents at increasing angles from the query — a pool with
    # plenty of room for MMR to trade relevance against diversity.
    store = _store_with(
        [([1, 0.02 * i, 0], _meta(f"doc_{i}.txt", 0)) for i in range(1, 11)]
    )

    hits, _ = retriever.retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=3
    )

    mmr_spy.assert_called_once()
    assert len(hits) == 3


@pytest.mark.unit
def test_retrieve_pool_max_score_can_exceed_the_returned_hits_max():
    """Fase 3.2: MMR ranks by the fused (not dense) score, so a strongly
    lexical-but-weakly-dense chunk can win the single returned slot over a
    chunk with a much higher raw cosine that simply lost the lexical race.
    ``pool_max_score`` must still report that higher cosine — the out-of-scope
    signal needs the true best coverage, not just what MMR kept."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            # D and C: filler, no lexical overlap with the query.
            ([0.50, 0.866, 0.0], _meta("D.txt", text="filler about gardening tools")),
            ([0.60, 0.8, 0.0], _meta("C.txt", text="filler about cooking pans")),
            # A: the best raw cosine (0.95) of the pool, but no lexical overlap.
            ([0.95, 0.312, 0.0], _meta("A.txt", text="filler about car engines")),
            # B: weaker cosine (0.70) but the only exact lexical match — wins
            # the fused ranking (and the sole k=1 slot) over A.
            (
                [0.70, 0.714, 0.0],
                _meta("B.txt", text="zephyrion quasar appears exactly here"),
            ),
        ]
    )
    hits, pool_max = retrieve(
        "zephyrion quasar",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=1,
    )

    assert hits[0].meta.source_path == "B.txt"
    assert hits[0].score == pytest.approx(0.70, abs=1e-2)
    assert pool_max == pytest.approx(0.95, abs=1e-2)
    assert pool_max > max(h.score for h in hits)


@pytest.mark.unit
def test_retrieve_pool_max_score_respects_scope():
    """``pool_max_score`` must only consider scope-respecting candidates —
    otherwise a document-scoped conversation could report false confidence
    from a chunk outside the bound document."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("other.txt")),  # perfect match, out of scope
            ([0.2, 0.98, 0.0], _meta("doc_a.txt")),  # weak match, in scope
        ]
    )
    _, pool_max = retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=1,
        scope="doc_a.txt",
    )
    assert pool_max == pytest.approx(0.2, abs=1e-2)


# ── relevance floor (Fase 2, PLANO_FONTES_E_PISO_RELEVANCIA.md) ───────────────


@pytest.mark.unit
def test_relevance_floor_drops_dense_far_candidate():
    """A candidate whose dense cosine is more than δ below the pool's best is
    dropped before MMR — the corpus-imbalance guard. Retrieval may then return
    fewer than k hits (an intended contract)."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("a.txt", text="x")),  # cosine 1.00
            ([0.98, 0.199, 0.0], _meta("b.txt", text="x")),  # cosine 0.98 (kept)
            ([0.6, 0.8, 0.0], _meta("c.txt", text="x")),  # cosine 0.60 (dropped)
        ]
    )
    hits, pool_max = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=6
    )
    sources = {h.meta.source_path for h in hits}
    assert sources == {"a.txt", "b.txt"}  # c.txt fell below the floor
    assert len(hits) == 2  # fewer than k — the floor trimmed the pool
    assert pool_max == pytest.approx(1.0, abs=1e-3)  # measured before the floor


@pytest.mark.unit
def test_relevance_floor_always_keeps_the_best_even_when_all_else_is_far():
    """The pool's single best dense candidate always survives the floor — the
    result is never empty for a non-empty scope, however wide the gap."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("best.txt", text="x")),  # cosine 1.00
            ([0.5, 0.866, 0.0], _meta("far1.txt", text="x")),  # cosine 0.50
            ([0.4, 0.916, 0.0], _meta("far2.txt", text="x")),  # cosine 0.40
        ]
    )
    hits, _ = retrieve(
        "q", store, lambda _q: np.array([1, 0, 0], dtype=np.float32), k=6
    )
    assert [h.meta.source_path for h in hits] == ["best.txt"]


@pytest.mark.unit
def test_relevance_floor_exempts_top1_bm25_rescue():
    """The deliberate reconciliation (Fase 2 impasse): the dense floor drops
    dense-far chunks, but the single strongest BM25 match is exempt — so a
    rare-term exact match (dense cosine ~0.17) survives while an equally
    dense-far chunk with no lexical hit is still cut."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("filler1.txt", text="notes about gardening")),
            ([0.98, 0.199, 0.0], _meta("filler2.txt", text="notes about cooking")),
            # Dense-far AND no lexical overlap — the floor must drop it.
            ([0.55, 0.835, 0.0], _meta("noise.txt", text="unrelated car engines")),
            # Dense-far but the only exact match — the top-1 BM25 exemption saves it.
            ([0.17, 0.985, 0.0], _meta("target.txt", text="zephyrion quasar exactly")),
        ]
    )
    hits, _ = retrieve(
        "zephyrion quasar",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=6,
    )
    sources = {h.meta.source_path for h in hits}
    assert "target.txt" in sources  # rescued by the BM25 top-1 exemption
    assert "noise.txt" not in sources  # dense-far, no lexical hit → dropped


@pytest.mark.unit
def test_relevance_floor_skipped_for_single_document_scope():
    """Within a single-document scope every candidate is a sibling chunk of the
    same file — the floor is skipped (like MMR) so it can't trim the document's
    own less-central chunks and cut within-document recall."""
    from src.core.rag.retriever import retrieve

    store = _store_with(
        [
            ([1.0, 0.0, 0.0], _meta("doc_a.txt", 0)),  # cosine 1.00
            ([0.9, 0.436, 0.0], _meta("doc_a.txt", 1)),  # cosine 0.90
            ([0.7, 0.714, 0.0], _meta("doc_a.txt", 2)),  # cosine 0.70 (kept anyway)
        ]
    )
    hits, _ = retrieve(
        "q",
        store,
        lambda _q: np.array([1, 0, 0], dtype=np.float32),
        k=6,
        scope="doc_a.txt",
    )
    # All three siblings survive — a whole-corpus floor would have cut the 0.70.
    assert len(hits) == 3
    assert {h.meta.source_path for h in hits} == {"doc_a.txt"}
