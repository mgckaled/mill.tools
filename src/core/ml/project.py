"""Project pooled document vectors to 2D for the semantic map.

PCA is the default: linear, instantaneous, deterministic and already in
scikit-learn (the ``[ml]`` extra) — but it can blur local structure. UMAP
(behind the optional ``[ml-viz]`` extra) preserves local+global structure and is
the modern default for embeddings; following the web survey, the vectors are
optionally pre-reduced with PCA (→ ``pre_pca_dims``) before UMAP for speed and
stability. Output is always ``(M, 2)`` float32.

Determinism: PCA gets an explicit sign convention (fix each axis so its
largest-magnitude sample is positive), so two runs are bit-identical regardless
of the SVD solver's sign choice; UMAP runs with a fixed ``random_state``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.core.ml.deps import (
    SETUP_HINT,
    UMAP_SETUP_HINT,
    is_available,
    umap_available,
)

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix

_RANDOM_STATE = 42


def project_2d(
    dm: DocumentMatrix,
    *,
    method: str = "pca",
    random_state: int = _RANDOM_STATE,
    pre_pca_dims: int = 50,
) -> np.ndarray:
    """Project the document vectors to a ``(M, 2)`` float32 array.

    Args:
        dm: pooled, L2-normalized document matrix.
        method: ``"pca"`` (default, sklearn, deterministic) or ``"umap"``
            (gated by ``[ml-viz]``, better local structure).
        random_state: seed for reproducibility (UMAP; PCA is already determinate).
        pre_pca_dims: for UMAP, pre-reduce to this many dims first (speed/stability).

    Returns:
        2D coordinates, one row per document (first-seen order).

    Raises:
        RuntimeError: if the required extra (``[ml]`` for PCA, ``[ml-viz]`` for
            UMAP) is not installed.
        ValueError: for an unknown ``method``.
    """
    m = len(dm.source_paths)
    if m == 0:
        return np.empty((0, 2), dtype=np.float32)
    if m == 1:
        return np.zeros((1, 2), dtype=np.float32)

    if method == "pca":
        if not is_available():
            raise RuntimeError(SETUP_HINT)
        return _pca_2d(dm.X, random_state)
    if method == "umap":
        if not umap_available():
            raise RuntimeError(UMAP_SETUP_HINT)
        return _umap_2d(dm.X, random_state, pre_pca_dims)  # pragma: no cover ([ml-viz])
    raise ValueError(f"Unknown projection method: {method!r}")


def _fix_signs(coords: np.ndarray) -> np.ndarray:
    """Flip each column so its largest-magnitude entry is positive (determinism)."""
    for col in range(coords.shape[1]):
        anchor = coords[np.argmax(np.abs(coords[:, col])), col]
        if anchor < 0:
            coords[:, col] = -coords[:, col]
    return coords


def _pca_2d(x: np.ndarray, random_state: int) -> np.ndarray:
    """PCA to (at most) 2D, padded to 2 columns and sign-normalized."""
    from sklearn.decomposition import PCA

    n_comp = min(2, x.shape[0], x.shape[1])
    coords = PCA(n_components=n_comp, random_state=random_state).fit_transform(x)
    if coords.shape[1] < 2:  # degenerate (e.g. rank-1 input) → pad a zero axis
        coords = np.column_stack([coords, np.zeros(len(coords))])
    return _fix_signs(coords).astype(np.float32)


def _umap_2d(  # pragma: no cover — requires the optional [ml-viz] (umap) extra
    x: np.ndarray, random_state: int, pre_pca_dims: int
) -> np.ndarray:
    """UMAP to 2D, optionally PCA-prereduced first for speed/stability."""
    x_pre = x
    if pre_pca_dims and x.shape[1] > pre_pca_dims and x.shape[0] > pre_pca_dims:
        from sklearn.decomposition import PCA

        x_pre = PCA(n_components=pre_pca_dims, random_state=random_state).fit_transform(
            x
        )

    from umap import UMAP

    reducer = UMAP(n_components=2, random_state=random_state, metric="cosine")
    return reducer.fit_transform(x_pre).astype(np.float32)
