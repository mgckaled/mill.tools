"""Related documents + out-of-corpus detection (numpy-pure, no scikit-learn).

Both operate on the already-pooled, L2-normalized document vectors (``dm.X``)
or the persisted ``VectorStore``, so cosine similarity is just an inner product
of unit vectors. No new dependency and no gate — this is the "free" half of the
4A semantic layer, like ``dedup`` was for Plan 3.
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


def related(
    dm: DocumentMatrix, source_path: str, *, k: int = 5
) -> list[tuple[str, float]]:
    """Return the top-``k`` documents most similar to ``source_path``.

    Cosine similarity is the inner product of the unit document vectors. The
    query document itself is excluded; ties keep matrix (first-seen) order.

    Args:
        dm: pooled, L2-normalized document matrix (from ``features``).
        source_path: the document to find neighbours for; must be in ``dm``.
        k: how many neighbours to return.

    Returns:
        ``(source_path, cosine)`` pairs, highest similarity first.

    Raises:
        ValueError: if ``source_path`` is not present in ``dm``.
    """
    try:
        i = dm.source_paths.index(source_path)
    except ValueError as exc:
        raise ValueError(f"Document not in the index: {source_path}") from exc

    scores = dm.X @ dm.X[i]
    order = np.argsort(scores)[::-1]  # descending similarity
    out: list[tuple[str, float]] = []
    for j in order:
        if j == i:
            continue  # never recommend the document to itself
        out.append((dm.source_paths[j], float(scores[j])))
        if len(out) >= k:
            break
    return out


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
