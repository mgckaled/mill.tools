"""Query-time retrieval over the vector store.

Pure: the query embedding is injected as ``embed_query_fn`` so the top-k logic
and scope filtering can be tested without a running Ollama.

Hybrid retrieval: dense (cosine over embeddings) is strong on meaning but weak
on exact terms — proper nouns, acronyms, numbers — a well-documented gap of
purely dense RAG. This module blends dense with BM25 (lexical) via Reciprocal
Rank Fusion (RRF), which combines rankings by *position* rather than raw score
magnitude — cosine lives in ``[-1, 1]`` and BM25 is unbounded, so fusing by
score would need an ad-hoc normalization; RRF sidesteps that entirely.

Pool + MMR (Fase 3, ``PLANO_CONVERSA_MULTITURNO.md``): the RRF ranking above
feeds a wider candidate pool, which is then diversified down to ``k`` by
Maximal Marginal Relevance — reusing ``core/ml/recommend._mmr`` rather than a
third copy (``core/text/summarize.py`` already has its own for a different
domain). Chunking's overlap makes sibling chunks of the same document
near-duplicates by construction; without diversification they can crowd out
most of the answer's context.

Relevance floor (``PLANO_FONTES_E_PISO_RELEVANCIA.md``, Fase 2): between the
fused ranking and MMR, pool candidates whose dense cosine falls more than
:data:`_RELEVANCE_FLOOR_DELTA` below the pool's best are dropped — a corpus-
imbalance guard, with a BM25 top-1 exemption so it doesn't undo the hybrid
rescue (see :func:`_apply_relevance_floor`). It can leave fewer than ``k`` hits;
``pool_max_score`` is still measured over the *whole* scope, before the cut, so
the coverage flag keeps gauging the corpus and not the floor.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from src.core.ml.recommend import _mmr
from src.core.rag.store import VectorStore
from src.core.rag.types import RetrievalResult, RetrievedChunk

# Standard RRF constant (Cormack, Clarke & Buettcher, SIGIR 2009) — not tuned
# per corpus; the paper found results insensitive to this value in the range
# that matters, so it isn't exposed as a parameter.
_RRF_K = 60

# The candidate pool ranked by RRF before MMR diversifies it down to k (Fase 3,
# PLANO_CONVERSA_MULTITURNO.md). With the chunker's 150-char overlap, sibling
# chunks of the same document are near-duplicates by construction — at k alone
# they can crowd out 2-3 of 6 context slots. 4x gives MMR enough room to trade
# redundant siblings for a different (still-relevant) document without paying
# for an unbounded pairwise-similarity matrix (O(pool^2 * D), same bound
# `recommend.related` uses via `_MMR_POOL_SIZE`).
_POOL_MULTIPLIER = 4

# More conservative than recommend.py's document-level 0.6: within a single
# answer's context, relevance to the question matters more than topical
# variety — MMR here trades away near-duplicate chunks, not distinct topics.
_MMR_LAMBDA = 0.7

# Relevance floor (PLANO_FONTES_E_PISO_RELEVANCIA.md, Fase 2): after the fused
# ranking picks the pool, a candidate whose *dense cosine* sits more than this
# far below the pool's best dense score is dropped BEFORE MMR — a corpus-
# imbalance guard so chunks from an unrelated but voluminous document (the
# many Dune chunks riding along an Ollama question) can't crowd the context
# just by being the 2nd–6th best. See _apply_relevance_floor for the BM25
# top-1 exemption that keeps the floor from fighting the hybrid rescue.
#
# δ=0.05 is PROVISIONAL — a starting point from the threshold calibration's
# spread (covered questions 0.7356–0.8684, out-of-corpus ≤0.7115). It must be
# validated/tuned against `ai eval` before being treated as final (Fase 4); do
# not harden it on intuition alone.
_RELEVANCE_FLOOR_DELTA = 0.05


def _reciprocal_rank_fusion(*score_arrays: np.ndarray) -> np.ndarray:
    """Fuse same-shape per-row score arrays into one ranking score, by rank position.

    Each array is ranked independently (descending, ties broken by the earlier
    original index — ``-inf`` always sorts last, so masked-out rows get the worst
    rank) and contributes ``1/(k + rank + 1)`` to the fused total — the standard
    RRF formula. Tie-breaking matters: a naive ``argsort(...)[::-1]`` flips tie
    order on reversal, which can let a fully uninformative signal (e.g. BM25 with
    no lexical match at all) cancel out a clear preference from the other signal
    when there are very few candidates — ``lexsort`` avoids that.
    """
    n = len(score_arrays[0])
    idx = np.arange(n)
    fused = np.zeros(n)
    for scores in score_arrays:
        order = np.lexsort((idx, -scores))  # descending by score, ties -> earlier index
        ranks = np.empty(n, dtype=np.int64)
        ranks[order] = np.arange(n)  # rank 0 = best
        fused += 1.0 / (
            _RRF_K + ranks + 1
        )  # +1: 1-indexed rank, as in the original paper
    return fused


def _is_single_document_scope(scope: str | None, store: VectorStore) -> bool:
    """True when ``scope`` pins one specific source document, not a kind or
    the whole corpus.

    MMR is skipped for this case (Fase 3.2): a single document's chunks are
    near-duplicate siblings by construction (chunking overlap) — diversifying
    would push out the most relevant ones instead of surfacing unrelated
    variety, which is the opposite of what a document-scoped question wants.
    """
    return bool(scope) and any(m.source_path == scope for m in store.meta)


def _apply_relevance_floor(
    pool: np.ndarray, dense: np.ndarray, lexical: np.ndarray
) -> np.ndarray:
    """Drop pool candidates whose dense cosine is more than
    :data:`_RELEVANCE_FLOOR_DELTA` below the pool's best dense score, exempting
    the single strongest BM25 (lexical) match (PLANO_FONTES_E_PISO_RELEVANCIA.md,
    Fase 2).

    The exemption is the deliberate reconciliation of two contracts that would
    otherwise collide (see the plan's impasse note):

    * The **dense floor** must stay a *pure dense* cut for its own goal — the
      Dune-imbalance chunks it targets often match the question's generic
      Portuguese words (no BM25 stopwords, a known gap kept out of this plan),
      so exempting anything with ``lexical > 0`` would let them survive and make
      the floor a no-op on the very case that motivated it.
    * The **hybrid BM25 rescue** must survive — a rare term / proper noun with an
      exact match (the retriever's whole reason for blending in BM25) is
      dense-far yet exactly on-topic, and a naive dense floor would kill it.

    A rare-term rescue is *concentrated*: the rescued chunk is the top of the
    BM25 ranking. Diffuse generic-word noise is not. So exempting **only** the
    single top-1 BM25 match separates the two worlds: the deep 0.17-cosine
    rescue survives, the ~0.65 Dune chunks (never top-1 lexical when the rare
    term points elsewhere) still fall. Worst case — a question with no rare term
    at all — the top-1 BM25 is a spurious generic match and *one* off-topic chunk
    survives the floor; the fused ranking tends to bury it and, if the model
    doesn't cite it, Fase 1 already shows it only as "consultada, não citada".

    ``keep = dense >= best_dense - δ  OR  (is the pool's top-1 BM25 and
    lexical.max() > 0)`` — the exemption covers at most one chunk per query. The
    pool's best dense score always survives (``δ >= 0``), so the result is never
    empty for a non-empty pool. Order among survivors is preserved (the fused
    rank the pool arrived in).

    Future refinement (do NOT implement without the numbers): if the eval shows
    spurious top-1 matches leaking systematically, condition the exemption on the
    top-1 BM25 being *distinctive* — clearly detached from the rest of the
    lexical distribution — rather than merely first.
    """
    if len(pool) == 0:
        return pool
    pool_dense = dense[pool]
    best = float(pool_dense.max())
    keep = pool_dense >= best - _RELEVANCE_FLOOR_DELTA
    pool_lexical = lexical[pool]
    if float(pool_lexical.max()) > 0:  # exempt the single strongest lexical match
        keep[int(np.argmax(pool_lexical))] = True
    return pool[keep]


def retrieve(
    query: str,
    store: VectorStore,
    embed_query_fn: Callable[[str], np.ndarray],
    *,
    k: int = 6,
    scope: str | None = None,
) -> RetrievalResult:
    """Embed the query and return the top-``k`` chunks, optionally scoped.

    Args:
        query: Natural-language question.
        store: The vector store to search.
        embed_query_fn: Maps the query string to a (D,) vector (injected so the
            function stays testable without Ollama).
        k: Number of chunks to return.
        scope: ``None`` searches the whole corpus. A source path restricts to
            that single document; a kind string restricts to one kind. The scope
            is applied as a mask *before* ranking (not a post-hoc filter over an
            unscoped top-k'), so a selective scope — e.g. one document among
            thousands of chunks — still returns up to ``k`` hits instead of
            risking fewer when its chunks don't make an unscoped candidate pool.

    Returns:
        A ``RetrievalResult(hits, pool_max_score)``. ``hits`` holds up to
        ``k`` chunks: a candidate pool (~``k`` * :data:`_POOL_MULTIPLIER`) is
        first ranked by the fused dense+BM25 RRF score, then passed through the
        relevance floor (:func:`_apply_relevance_floor`; skipped for a single-
        document scope) and finally diversified down to ``k`` by MMR (skipped
        when the pool already fits within ``k``, or the scope pins a single
        document — see :func:`_is_single_document_scope`) so near-duplicate
        sibling chunks stop crowding out the rest of the context. The floor can
        leave **fewer than ``k``** hits (an intended contract — never empty for
        a non-empty scope). Each hit's ``.score`` is still its dense cosine
        similarity (not the fused or MMR-adjusted value) — unchanged contract
        for the out-of-scope check. ``pool_max_score`` is the best dense cosine
        among every scope-respecting candidate (not just the returned hits, and
        computed **before** the floor) — MMR can trade the single best match
        away for diversity and the floor can drop candidates, so the out-of-
        scope signal needs the true best coverage to stay stable under the
        narrow 0.72 threshold gap (Fase 0.3/3.2).
    """
    if len(store) == 0:  # nothing to search — skip the embed_query_fn round-trip
        return RetrievalResult([], 0.0)

    mask = None
    if scope:
        mask = np.array(
            [m.source_path == scope or m.kind == scope for m in store.meta], dtype=bool
        )
    dense = store.dense_scores(embed_query_fn(query), mask=mask)
    if len(dense) == 0:
        return RetrievalResult([], 0.0)

    finite_dense = dense[np.isfinite(dense)]
    pool_max_score = float(finite_dense.max()) if len(finite_dense) else 0.0

    lexical = store.bm25_scores(query, mask=mask)
    # A query whose terms match none of the corpus's vocabulary gets an
    # all-zero (or, with a mask, all-zero-or--inf) BM25 vector — no lexical
    # signal at all. Fusing it in anyway would still rank it: ties in
    # _reciprocal_rank_fusion break on the earlier index, so BM25 would
    # inject a pure insertion-order bias into the result on top of the
    # dense ranking. Skip the fusion and fall back to dense-only ranking.
    fused = _reciprocal_rank_fusion(dense, lexical) if lexical.max() > 0 else dense

    order = np.argsort(fused)[::-1]
    order = order[
        np.isfinite(dense[order])
    ]  # drop masked-out rows in a too-small scope
    pool = order[: max(k, k * _POOL_MULTIPLIER)]

    # Relevance floor before MMR, but never for a single-document scope: there
    # every candidate is a sibling chunk of the *same* file by construction, so a
    # dense-gap cut would just trim the document's own less-central chunks and
    # reduce within-document recall — the same reason MMR is skipped below. The
    # floor's target is cross-document imbalance, which a single-doc scope can't
    # have. It can drop the pool below k (an intended contract: build_context /
    # the source card / run_batch all tolerate fewer than k hits).
    single_doc = _is_single_document_scope(scope, store)
    if not single_doc:
        pool = _apply_relevance_floor(pool, dense, lexical)

    if len(pool) <= k or single_doc:
        top = pool[:k]
    else:
        # MMR ranks by the *fused* score, not raw dense cosine: it's what got
        # each candidate into the pool in the first place (a strong lexical-
        # only match can rank ahead of several higher-cosine chunks there),
        # and re-selecting by dense relevance alone would silently undo that
        # — dropping the exact BM25-rescued hit hybrid retrieval exists for.
        relevance = fused[pool]
        vectors = store.normalized_vectors()[pool]
        similarity = vectors @ vectors.T
        selected = _mmr(relevance, similarity, k, lambda_=_MMR_LAMBDA)
        top = pool[selected]

    hits = [RetrievedChunk(store.meta[i], float(dense[i])) for i in top]
    return RetrievalResult(hits, pool_max_score)
