"""Cluster the pooled document vectors — HDBSCAN (default) or k-means.

Operates on ``features.document_matrix`` (Plan 3): the rows are L2-normalized, so
Euclidean distance over them is monotone in cosine (``||a-b||^2 = 2 - 2·cos`` for
unit vectors), letting HDBSCAN's default euclidean metric stand in for cosine
without a custom metric. HDBSCAN discovers the number of clusters on its own and
marks outliers ``-1`` (reused as "isolated/orphan content"); k-means is the
alternative when a fixed number of groups is wanted. scikit-learn is imported
lazily and gated by ``deps.is_available()`` (the ``[ml]`` extra).

k-means' ``k`` can also be picked automatically via ``sklearn.metrics.
silhouette_score`` over a small candidate range — but only once the corpus is
large enough (``_MIN_FOR_AUTO_K``) for the score to mean anything: it is
documented as unstable/biased below roughly 15-20 samples per candidate
cluster, and is O(n²) besides (irrelevant at this project's volumes, but a
reason not to test a wide k range). Below that floor, ``k`` stays a required,
explicit argument — the same behavior as before this existed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.core.ml.deps import SETUP_HINT, is_available
from src.core.ml.types import ClusterResult

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix

# k-means is seeded so the same corpus always yields the same partition.
_RANDOM_STATE = 42

# Auto-k only activates at/above this corpus size; silhouette_score is
# unreliable/biased below roughly 15-20 samples per candidate cluster.
_MIN_FOR_AUTO_K = 20

# Candidate k values tried for auto-selection (kept small: silhouette is O(n²)
# per candidate, and there is little reason to consider more than ~10 groups
# for a personal document map).
_AUTO_K_RANGE = range(2, 11)


def _default_min_cluster_size(m: int) -> int:
    """Heuristic minimum cluster size: ~2% of the corpus, never below 2."""
    return max(2, m // 50)


def cluster_documents(
    dm: DocumentMatrix,
    *,
    method: str = "hdbscan",
    min_cluster_size: int | None = None,
    k: int | None = None,
) -> ClusterResult:
    """Cluster the pooled document vectors.

    Args:
        dm: pooled, L2-normalized document matrix.
        method: ``"hdbscan"`` (auto-k, noise=-1) or ``"kmeans"``.
        min_cluster_size: HDBSCAN smoothing threshold; defaults to a heuristic.
        k: number of clusters for k-means (ignored by HDBSCAN). ``None`` picks
            k automatically via silhouette score, but only when the corpus is
            large enough (``_MIN_FOR_AUTO_K``); below that it's a required
            argument.

    Returns:
        A ``ClusterResult`` with one label per document (``-1`` = orphan).

    Raises:
        RuntimeError: if the ``[ml]`` extra is not installed.
        ValueError: for an unknown ``method`` or k-means without a valid ``k``.
    """
    if not is_available():
        raise RuntimeError(SETUP_HINT)

    m = len(dm.source_paths)
    if m == 0:
        return ClusterResult(
            labels=np.empty((0,), dtype=int), method=method, n_clusters=0, n_noise=0
        )

    if method == "hdbscan":
        labels = _hdbscan(dm.X, min_cluster_size or _default_min_cluster_size(m))
    elif method == "kmeans":
        labels = _kmeans(dm.X, k, m)
    else:
        raise ValueError(f"Unknown clustering method: {method!r}")

    n_noise = int(np.count_nonzero(labels == -1))
    n_clusters = int(len({int(label) for label in labels} - {-1}))
    return ClusterResult(
        labels=labels, method=method, n_clusters=n_clusters, n_noise=n_noise
    )


def _hdbscan(x: np.ndarray, min_cluster_size: int) -> np.ndarray:
    """Run HDBSCAN; with fewer than 2 docs everything is noise (cannot cluster)."""
    if len(x) < 2:
        return np.full(len(x), -1, dtype=int)
    from sklearn.cluster import HDBSCAN

    # copy=True: never mutate the caller's (shared) matrix in place. It also
    # pins the future default (sklearn 1.10 flips it) so no FutureWarning fires.
    model = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean", copy=True)
    return model.fit_predict(x).astype(int)


def _auto_k(x: np.ndarray, m: int) -> int:
    """Pick k via silhouette score over ``_AUTO_K_RANGE``, highest score wins.

    Only called once the caller has confirmed ``m >= _MIN_FOR_AUTO_K``; the
    ``k >= m`` guard below is a defensive belt in case that floor is ever
    lowered under ``_AUTO_K_RANGE``'s upper end.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    best_k, best_score = _AUTO_K_RANGE.start, -1.0
    for k in _AUTO_K_RANGE:
        if k >= m:
            break
        labels = KMeans(
            n_clusters=k, random_state=_RANDOM_STATE, n_init="auto"
        ).fit_predict(x)
        score = silhouette_score(x, labels)
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def _kmeans(x: np.ndarray, k: int | None, m: int) -> np.ndarray:
    """Run k-means; ``k`` is required unless the corpus is large enough for auto-selection."""
    from sklearn.cluster import KMeans

    if k is None:
        if m < _MIN_FOR_AUTO_K:
            raise ValueError(
                f"k-means requires a positive k below {_MIN_FOR_AUTO_K} "
                "documents (too few for automatic k selection)."
            )
        k = _auto_k(x, m)
    elif k < 1:
        raise ValueError("k-means requires a positive k.")

    model = KMeans(n_clusters=min(k, m), random_state=_RANDOM_STATE, n_init="auto")
    return model.fit_predict(x).astype(int)
