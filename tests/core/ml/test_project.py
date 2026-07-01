"""Unit tests for src/core/ml/project.py — 2D projection (PCA default, UMAP opt)."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml.types import DocumentMatrix


def _dm(vectors: np.ndarray) -> DocumentMatrix:
    x = vectors.astype(np.float32)
    x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-8)
    n = len(x)
    return DocumentMatrix(
        X=x.astype(np.float32),
        source_paths=[f"d{i}.txt" for i in range(n)],
        kinds=["transcription"] * n,
    )


@pytest.mark.unit
def test_empty_matrix_returns_empty_2d():
    from src.core.ml.project import project_2d

    dm = DocumentMatrix(X=np.empty((0, 5), dtype=np.float32), source_paths=[], kinds=[])
    coords = project_2d(dm)
    assert coords.shape == (0, 2)


@pytest.mark.unit
def test_single_doc_returns_origin():
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:1])
    coords = project_2d(dm)
    assert coords.shape == (1, 2)
    np.testing.assert_array_equal(coords, np.zeros((1, 2), dtype=np.float32))


@pytest.mark.unit
def test_unknown_method_raises():
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:3])
    with pytest.raises(ValueError, match="Unknown projection"):
        project_2d(dm, method="lda")


@pytest.mark.unit
def test_pca_gate_blocks_without_ml(mocker):
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:3])
    mocker.patch("src.core.ml.project.is_available", return_value=False)
    with pytest.raises(RuntimeError):
        project_2d(dm, method="pca")


@pytest.mark.unit
def test_umap_gate_blocks_without_extra(mocker):
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:3])
    mocker.patch("src.core.ml.project.umap_available", return_value=False)
    with pytest.raises(RuntimeError):
        project_2d(dm, method="umap")


@pytest.mark.unit
def test_tsne_gate_blocks_without_ml(mocker):
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:3])
    mocker.patch("src.core.ml.project.is_available", return_value=False)
    with pytest.raises(RuntimeError):
        project_2d(dm, method="tsne")


@pytest.mark.unit
@pytest.mark.parametrize(
    "n_samples,expected",
    [
        (2, 1.0),  # floor holds even at the smallest possible corpus
        (4, 1.0),
        (10, 3.0),
        (91, 30.0),  # (91-1)/3 = 30 exactly
        (1000, 30.0),  # capped at the library's own upper guidance
    ],
)
def test_tsne_perplexity_clamp(n_samples, expected):
    from src.core.ml.project import _tsne_perplexity

    assert _tsne_perplexity(n_samples) == pytest.approx(expected)


# --- PCA proper (needs sklearn) ---------------------------------------------

pytest.importorskip("sklearn")


def _blobs() -> np.ndarray:
    rng = np.random.default_rng(0)
    e0 = np.zeros(6)
    e0[0] = 1.0
    e1 = np.zeros(6)
    e1[1] = 1.0
    return np.vstack(
        [e0 + rng.normal(0, 0.05, (8, 6)), e1 + rng.normal(0, 0.05, (8, 6))]
    )


@pytest.mark.unit
def test_pca_shape_is_m_by_2():
    from src.core.ml.project import project_2d

    coords = project_2d(_dm(_blobs()), method="pca")
    assert coords.shape == (16, 2)
    assert coords.dtype == np.float32


@pytest.mark.unit
def test_pca_pads_degenerate_to_two_columns():
    from src.core.ml.project import project_2d

    # 1-dimensional features → PCA yields a single component, padded to (M, 2).
    dm = DocumentMatrix(
        X=np.array([[1.0], [2.0], [3.0]], dtype=np.float32),
        source_paths=["a.txt", "b.txt", "c.txt"],
        kinds=["transcription"] * 3,
    )
    coords = project_2d(dm, method="pca")
    assert coords.shape == (3, 2)
    np.testing.assert_array_equal(coords[:, 1], np.zeros(3, dtype=np.float32))


@pytest.mark.unit
def test_pca_is_deterministic_across_runs():
    from src.core.ml.project import project_2d

    dm = _dm(_blobs())
    a = project_2d(dm, method="pca")
    b = project_2d(dm, method="pca")
    np.testing.assert_array_equal(a, b)  # sign convention → bit-identical


@pytest.mark.unit
def test_umap_projection_shape():
    pytest.importorskip("umap")
    from src.core.ml.project import project_2d

    coords = project_2d(_dm(_blobs()), method="umap")
    assert coords.shape == (16, 2)


@pytest.mark.unit
def test_tsne_projection_shape():
    from src.core.ml.project import project_2d

    coords = project_2d(_dm(_blobs()), method="tsne")
    assert coords.shape == (16, 2)
    assert coords.dtype == np.float32


@pytest.mark.unit
def test_tsne_pre_reduces_high_dimensional_input():
    # Exercises _maybe_pre_reduce's actual PCA branch (dims > pre_pca_dims);
    # the D=6 _blobs() fixture never triggers it since pre_pca_dims defaults
    # to 50.
    from src.core.ml.project import project_2d

    rng = np.random.default_rng(0)
    x = rng.normal(size=(20, 60))
    coords = project_2d(_dm(x), method="tsne", pre_pca_dims=10)
    assert coords.shape == (20, 2)


@pytest.mark.unit
def test_tsne_handles_tiny_corpus_without_error():
    # perplexity must stay < n_samples even at the smallest sizes project_2d
    # actually dispatches to a method for (m=2, since m<=1 short-circuits earlier).
    from src.core.ml.project import project_2d

    dm = _dm(np.eye(5)[:2])
    coords = project_2d(dm, method="tsne")
    assert coords.shape == (2, 2)
