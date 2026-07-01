"""Query-time retrieval over the vector store.

Pure: the query embedding is injected as ``embed_query_fn`` so the top-k logic
and scope filtering can be tested without a running Ollama.

Hybrid retrieval: dense (cosine over embeddings) is strong on meaning but weak
on exact terms — proper nouns, acronyms, numbers — a well-documented gap of
purely dense RAG. This module blends dense with BM25 (lexical) via Reciprocal
Rank Fusion (RRF), which combines rankings by *position* rather than raw score
magnitude — cosine lives in ``[-1, 1]`` and BM25 is unbounded, so fusing by
score would need an ad-hoc normalization; RRF sidesteps that entirely.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from src.core.rag.store import VectorStore
from src.core.rag.types import RetrievedChunk

# Standard RRF constant (Cormack, Clarke & Buettcher, SIGIR 2009) — not tuned
# per corpus; the paper found results insensitive to this value in the range
# that matters, so it isn't exposed as a parameter.
_RRF_K = 60


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


def retrieve(
    query: str,
    store: VectorStore,
    embed_query_fn: Callable[[str], np.ndarray],
    *,
    k: int = 6,
    scope: str | None = None,
) -> list[RetrievedChunk]:
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
        Up to ``k`` retrieved chunks, ordered by the fused dense+BM25 ranking.
        Each chunk's ``score`` is its dense cosine similarity (not the fused
        value) — callers such as the out-of-scope check compare it against a
        cosine threshold, so its meaning stays unchanged by hybrid retrieval.
    """
    mask = None
    if scope:
        mask = np.array(
            [m.source_path == scope or m.kind == scope for m in store.meta], dtype=bool
        )
    dense = store.dense_scores(embed_query_fn(query), mask=mask)
    if len(dense) == 0:
        return []
    lexical = store.bm25_scores(query, mask=mask)
    fused = _reciprocal_rank_fusion(dense, lexical)
    top = np.argsort(fused)[::-1][:k]
    top = top[np.isfinite(dense[top])]  # drop masked-out rows in a too-small scope
    return [RetrievedChunk(store.meta[i], float(dense[i])) for i in top]
