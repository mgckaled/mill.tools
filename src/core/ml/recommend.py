"""Related documents + out-of-corpus detection (numpy-pure, no scikit-learn).

Both operate on the already-pooled, L2-normalized document vectors (``dm.X``)
or the persisted ``VectorStore``, so cosine similarity is just an inner product
of unit vectors. No new dependency and no gate — this is the "free" half of the
4A semantic layer, like ``dedup`` was for Plan 3.

``related`` reranks its cosine-similarity candidates with Maximal Marginal
Relevance (MMR) so a tight cluster of near-duplicate documents doesn't crowd
out otherwise-relevant results — still numpy-pure, no new dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix
    from src.core.rag.store import VectorStore

# Default cosine floor for "the corpus covers this question". It is
# embedding-model dependent (calibrated for nomic-embed), so it is exposed as a
# parameter/config rather than hard-coded into the flow — a conservative start.
DEFAULT_IN_CORPUS_THRESHOLD = 0.35

# MMR (Carbonell & Goldstein, 1998) balances relevance to the anchor against
# redundancy with already-picked results — plain top-k can surface several
# near-duplicate documents when the corpus has a tight cluster around a topic.
_MMR_LAMBDA = 0.6


def _mmr(
    relevance: np.ndarray,
    similarity: np.ndarray,
    k: int,
    *,
    lambda_: float = _MMR_LAMBDA,
) -> list[int]:
    """Greedy Maximal Marginal Relevance selection over candidate indices.

    Picks up to ``k`` indices balancing ``relevance`` (similarity to the
    anchor) against redundancy with already-picked candidates (``similarity``,
    the pairwise matrix among candidates). Ties break by the lowest index for
    determinism. With no redundancy in the pool, this reduces to plain top-k
    by relevance (the redundancy term is ~0 for every candidate).
    """
    n = len(relevance)
    k = min(k, n)
    selected: list[int] = []
    remaining = list(range(n))
    for _ in range(k):
        if not selected:
            scores = relevance
        else:
            redundancy = similarity[:, selected].max(axis=1)
            scores = lambda_ * relevance - (1 - lambda_) * redundancy
        best = max(remaining, key=lambda i: (scores[i], -i))
        selected.append(best)
        remaining.remove(best)
    return selected


def related(
    dm: DocumentMatrix,
    source_path: str,
    *,
    k: int = 5,
    lambda_: float = _MMR_LAMBDA,
) -> list[tuple[str, float]]:
    """Return the top-``k`` documents most similar to ``source_path``, diversified.

    Cosine similarity is the inner product of the unit document vectors;
    candidates are then reranked by Maximal Marginal Relevance so a tight
    cluster of near-duplicates doesn't crowd out other relevant documents. The
    query document itself is excluded.

    Args:
        dm: pooled, L2-normalized document matrix (from ``features``).
        source_path: the document to find neighbours for; must be in ``dm``.
        k: how many neighbours to return.
        lambda_: MMR relevance/diversity trade-off (higher favors plain top-k
            by relevance; lower favors diversity).

    Returns:
        ``(source_path, cosine)`` pairs — cosine to the anchor, MMR-ordered.

    Raises:
        ValueError: if ``source_path`` is not present in ``dm``.
    """
    try:
        i = dm.source_paths.index(source_path)
    except ValueError as exc:
        raise ValueError(f"Document not in the index: {source_path}") from exc

    candidates = [j for j in range(len(dm.source_paths)) if j != i]
    if not candidates:
        return []

    cand_X = dm.X[candidates]
    query_sim = cand_X @ dm.X[i]
    pairwise_sim = cand_X @ cand_X.T
    order = _mmr(query_sim, pairwise_sim, k, lambda_=lambda_)
    return [(dm.source_paths[candidates[o]], float(query_sim[o])) for o in order]


def in_corpus(
    query_vec: np.ndarray,
    store: VectorStore,
    *,
    threshold: float = DEFAULT_IN_CORPUS_THRESHOLD,
) -> tuple[bool, float]:
    """Report whether the corpus likely covers ``query_vec``.

    Uses the best single-chunk cosine (``VectorStore.search`` top-1): a question
    whose closest chunk is below ``threshold`` is probably out of corpus, so the
    GUI can warn before answering. Returns ``(covered, best_score)``; an empty
    store yields ``(False, 0.0)``.
    """
    hits = store.search(query_vec, k=1)
    if not hits:
        return (False, 0.0)
    best = hits[0].score
    return (best >= threshold, best)
