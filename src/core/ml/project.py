"""Project pooled document vectors to 2D for the semantic map.

PCA is the default: linear, instantaneous, deterministic and already in
scikit-learn (the ``[ml]`` extra) — but it can blur local structure. UMAP
(behind the optional ``[ml-viz]`` extra) preserves local+global structure and is
the modern default for embeddings; following the web survey, the vectors are
optionally pre-reduced with PCA (→ ``pre_pca_dims``) before UMAP for speed and
stability. Output is always ``(M, 2)`` float32.

t-SNE is a third option that, unlike UMAP, needs no extra beyond ``[ml]``
(``sklearn.manifold.TSNE`` ships with scikit-learn itself) — the "free" upgrade
over PCA for separating clusters visually when ``[ml-viz]`` isn't installed.
Its ``metric="euclidean"`` default is left alone rather than set to
``"cosine"``: the document vectors are already L2-normalized, and euclidean
distance over unit vectors is monotone in cosine (the same reasoning
``cluster.py`` uses for HDBSCAN). Its one hard constraint is
``perplexity < n_samples``; the perplexity is derived from the corpus size
instead of using scikit-learn's fixed default, which would error out below 31
documents.

Determinism: PCA gets an explicit sign convention (fix each axis so its
largest-magnitude sample is positive), so two runs are bit-identical regardless
of the SVD solver's sign choice; UMAP and t-SNE run with a fixed ``random_state``
(t-SNE's optimization is otherwise stochastic).
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
        method: ``"pca"`` (default, sklearn, deterministic), ``"tsne"``
            (sklearn, better cluster separation, no extra beyond ``[ml]``) or
            ``"umap"`` (gated by ``[ml-viz]``, better local structure).
        random_state: seed for reproducibility (UMAP/t-SNE; PCA is already
            determinate).
        pre_pca_dims: for UMAP/t-SNE, pre-reduce to this many dims first
            (speed/stability).

    Returns:
        2D coordinates, one row per document (first-seen order).

    Raises:
        RuntimeError: if the required extra (``[ml]`` for PCA/t-SNE,
            ``[ml-viz]`` for UMAP) is not installed.
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
    if method == "tsne":
        if not is_available():
            raise RuntimeError(SETUP_HINT)
        return _tsne_2d(dm.X, random_state, pre_pca_dims)
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


def _maybe_pre_reduce(
    x: np.ndarray, pre_pca_dims: int, random_state: int
) -> np.ndarray:
    """PCA-prereduce ``x`` to ``pre_pca_dims`` when it's smaller than both axes.

    Shared by UMAP and t-SNE: both are costlier and less stable on the raw
    768-dim embeddings than on a quick PCA pre-reduction (a well-established
    practice for both algorithms).
    """
    if pre_pca_dims and x.shape[1] > pre_pca_dims and x.shape[0] > pre_pca_dims:
        from sklearn.decomposition import PCA

        return PCA(n_components=pre_pca_dims, random_state=random_state).fit_transform(
            x
        )
    return x


def _umap_2d(  # pragma: no cover — requires the optional [ml-viz] (umap) extra
    x: np.ndarray, random_state: int, pre_pca_dims: int
) -> np.ndarray:
    """UMAP to 2D, optionally PCA-prereduced first for speed/stability."""
    x_pre = _maybe_pre_reduce(x, pre_pca_dims, random_state)

    from umap import UMAP

    reducer = UMAP(n_components=2, random_state=random_state, metric="cosine")
    return reducer.fit_transform(x_pre).astype(np.float32)


def _tsne_perplexity(n_samples: int) -> float:
    """Perplexity clamped to stay strictly below ``n_samples`` (a hard sklearn
    constraint) while following the community heuristic ``min(30, (n-1)/3)``
    for datasets too small for the library's own 30.0 default. Floored at 1.0
    rather than sklearn's suggested 5, since the floor must hold even for a
    2-document corpus (``n_samples=2`` → ``(n-1)/3=0.33``, which a 5.0 floor
    would push back above the ``n_samples`` ceiling).
    """
    return min(30.0, max(1.0, (n_samples - 1) / 3))


def _tsne_2d(x: np.ndarray, random_state: int, pre_pca_dims: int) -> np.ndarray:
    """t-SNE to 2D, optionally PCA-prereduced first; perplexity fit to the corpus size."""
    x_pre = _maybe_pre_reduce(x, pre_pca_dims, random_state)

    from sklearn.manifold import TSNE

    reducer = TSNE(
        n_components=2,
        random_state=random_state,
        perplexity=_tsne_perplexity(len(x)),
        init="pca",
    )
    return reducer.fit_transform(x_pre).astype(np.float32)
