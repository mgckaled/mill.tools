"""Cluster the pooled document vectors — HDBSCAN (default) or k-means.

Operates on ``features.document_matrix`` (Plan 3): the rows are L2-normalized, so
Euclidean distance over them is monotone in cosine (``||a-b||^2 = 2 - 2·cos`` for
unit vectors), letting HDBSCAN's default euclidean metric stand in for cosine
without a custom metric. HDBSCAN discovers the number of clusters on its own and
marks outliers ``-1`` (reused as "isolated/orphan content"); k-means is the
alternative when a fixed number of groups is wanted. scikit-learn is imported
lazily and gated by ``deps.is_available()`` (the ``[ml]`` extra).
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
        method: ``"hdbscan"`` (auto-k, noise=-1) or ``"kmeans"`` (needs ``k``).
        min_cluster_size: HDBSCAN smoothing threshold; defaults to a heuristic.
        k: number of clusters for k-means (ignored by HDBSCAN).

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


def _kmeans(x: np.ndarray, k: int | None, m: int) -> np.ndarray:
    """Run k-means; ``k`` is required and clamped to the corpus size."""
    if not k or k < 1:
        raise ValueError("k-means requires a positive --k.")
    from sklearn.cluster import KMeans

    model = KMeans(n_clusters=min(k, m), random_state=_RANDOM_STATE, n_init="auto")
    return model.fit_predict(x).astype(int)
