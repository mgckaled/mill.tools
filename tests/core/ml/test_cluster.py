"""Unit tests for src/core/ml/cluster.py — HDBSCAN / k-means over doc vectors."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("sklearn")

from src.core.ml.cluster import cluster_documents  # noqa: E402
from src.core.ml.types import DocumentMatrix  # noqa: E402


def _dm(vectors: np.ndarray, *, kinds: list[str] | None = None) -> DocumentMatrix:
    """Build an L2-normalized DocumentMatrix from raw row vectors."""
    x = vectors.astype(np.float32)
    x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)
    n = len(x)
    return DocumentMatrix(
        X=x.astype(np.float32),
        source_paths=[f"d{i}.txt" for i in range(n)],
        kinds=kinds or ["transcription"] * n,
    )


def _two_blobs(n_per: int = 10, *, jitter: float = 0.01, seed: int = 0) -> np.ndarray:
    """Two tight blobs around orthogonal directions in 5D."""
    rng = np.random.default_rng(seed)
    e0 = np.zeros(5)
    e0[0] = 1.0
    e1 = np.zeros(5)
    e1[1] = 1.0
    a = e0 + rng.normal(0, jitter, (n_per, 5))
    b = e1 + rng.normal(0, jitter, (n_per, 5))
    return np.vstack([a, b])


def _n_blobs(
    n_groups: int, n_per: int, *, dim: int, jitter: float = 0.01, seed: int = 0
) -> np.ndarray:
    """``n_groups`` tight blobs around orthogonal directions in ``dim``-D."""
    rng = np.random.default_rng(seed)
    groups = []
    for i in range(n_groups):
        e = np.zeros(dim)
        e[i] = 1.0
        groups.append(e + rng.normal(0, jitter, (n_per, dim)))
    return np.vstack(groups)


@pytest.mark.unit
def test_hdbscan_finds_two_separated_blobs():
    dm = _dm(_two_blobs(n_per=10))
    result = cluster_documents(dm, method="hdbscan", min_cluster_size=5)
    assert result.method == "hdbscan"
    assert result.n_clusters == 2
    # The two blobs land in distinct (non-noise) clusters.
    assert len(set(result.labels.tolist()) - {-1}) == 2


@pytest.mark.unit
def test_hdbscan_marks_outliers_as_noise():
    blobs = _two_blobs(n_per=10)
    outlier = np.zeros((1, 5))
    outlier[0, 2] = 1.0  # third orthogonal direction, alone → noise
    dm = _dm(np.vstack([blobs, outlier]))
    result = cluster_documents(dm, method="hdbscan", min_cluster_size=5)
    assert result.n_noise >= 1
    assert result.labels[-1] == -1  # the lone outlier is noise


@pytest.mark.unit
def test_hdbscan_default_min_cluster_size():
    # No min_cluster_size → the max(2, M//50) heuristic kicks in.
    dm = _dm(_two_blobs(n_per=10))
    result = cluster_documents(dm, method="hdbscan")
    assert result.method == "hdbscan"
    assert result.n_clusters >= 1


@pytest.mark.unit
def test_kmeans_with_fixed_k():
    dm = _dm(_two_blobs(n_per=8))
    result = cluster_documents(dm, method="kmeans", k=2)
    assert result.method == "kmeans"
    assert result.n_clusters == 2
    assert result.n_noise == 0  # k-means has no noise label


@pytest.mark.unit
def test_too_few_docs_for_min_cluster_size_are_all_noise():
    dm = _dm(np.eye(5)[:1])  # single document
    result = cluster_documents(dm, method="hdbscan", min_cluster_size=5)
    assert result.n_clusters == 0
    assert result.n_noise == 1
    assert result.labels.tolist() == [-1]


@pytest.mark.unit
def test_empty_matrix_returns_empty_result():
    dm = DocumentMatrix(X=np.empty((0, 5), dtype=np.float32), source_paths=[], kinds=[])
    result = cluster_documents(dm)
    assert result.n_clusters == 0
    assert result.n_noise == 0
    assert result.labels.shape == (0,)


@pytest.mark.unit
def test_unknown_method_raises():
    dm = _dm(_two_blobs(n_per=4))
    with pytest.raises(ValueError, match="Unknown clustering method"):
        cluster_documents(dm, method="spectral")


@pytest.mark.unit
def test_kmeans_without_k_raises():
    dm = _dm(_two_blobs(n_per=4))
    with pytest.raises(ValueError, match="requires a positive"):
        cluster_documents(dm, method="kmeans")


@pytest.mark.unit
def test_kmeans_none_k_raises_when_corpus_too_small_for_auto():
    # 8 docs is well below _MIN_FOR_AUTO_K (20) -- k stays a required argument,
    # same behavior as before auto-k existed (test_kmeans_without_k_raises
    # covers the message itself; this pins the "too small" reasoning).
    dm = _dm(_two_blobs(n_per=4))
    with pytest.raises(ValueError, match="too few for automatic"):
        cluster_documents(dm, method="kmeans", k=None)


@pytest.mark.unit
def test_kmeans_explicit_zero_k_raises():
    dm = _dm(_two_blobs(n_per=15))  # large enough that auto-k would apply for None
    with pytest.raises(ValueError, match="requires a positive"):
        cluster_documents(dm, method="kmeans", k=0)


@pytest.mark.unit
def test_auto_k_respects_range_upper_guard_below_min_for_auto():
    # Direct call bypassing _kmeans' _MIN_FOR_AUTO_K guard: with m=5, the
    # candidate range (up to 10) must stop once k >= m, per the defensive
    # "k >= m: break" -- exercised here since _MIN_FOR_AUTO_K (20) is above
    # _AUTO_K_RANGE's own ceiling and never triggers it through cluster_documents.
    from src.core.ml.cluster import _auto_k

    dm_vectors = _n_blobs(2, 3, dim=3)  # 6 rows total, but call with m=5 directly
    k = _auto_k(dm_vectors[:5], m=5)
    assert 2 <= k < 5


@pytest.mark.unit
def test_kmeans_auto_selects_k_for_well_separated_blobs():
    # 4 tight orthogonal blobs, 24 docs total (>= _MIN_FOR_AUTO_K) -- silhouette
    # over the candidate range should land on the true k.
    dm = _dm(_n_blobs(4, 6, dim=4))
    result = cluster_documents(dm, method="kmeans", k=None)
    assert result.method == "kmeans"
    assert result.n_clusters == 4
    assert result.n_noise == 0


@pytest.mark.unit
def test_gate_blocks_when_ml_extra_missing(mocker):
    dm = _dm(_two_blobs(n_per=4))
    mocker.patch("src.core.ml.cluster.is_available", return_value=False)
    with pytest.raises(RuntimeError):
        cluster_documents(dm)
