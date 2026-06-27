"""Unit tests for src/core/ml/features.py — the embedding accessor.

numpy-pure (no scikit-learn, no Ollama): synthetic chunk vectors with known
``source_path`` are pooled and the mean/normalization/order/dtype is asserted.
``load_document_matrix`` round-trips a real persisted ``VectorStore``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml.features import chunk_matrix, document_matrix, load_document_matrix
from src.core.rag.store import VectorStore
from src.core.rag.types import ChunkMeta


def _store(rows: list[tuple[str, list[float]]], *, dim: int = 4) -> VectorStore:
    """Build a store from ``(source_path, vector)`` pairs (all kind=transcription)."""
    store = VectorStore(dim=dim)
    vecs = np.array([v for _, v in rows], dtype=np.float32)
    metas = [
        ChunkMeta(src, "transcription", 1.0, i, f"text {i}")
        for i, (src, _) in enumerate(rows)
    ]
    if rows:
        store.add(vecs, metas)
    return store


@pytest.mark.unit
def test_document_matrix_pools_mean_per_source():
    # a.txt has two chunks → mean; b.txt has one chunk → itself.
    store = _store(
        [
            ("a.txt", [2.0, 0.0, 0.0, 0.0]),
            ("a.txt", [0.0, 0.0, 0.0, 0.0]),
            ("b.txt", [0.0, 3.0, 0.0, 0.0]),
        ]
    )
    dm = document_matrix(store, l2_normalize=False)

    assert dm.source_paths == ["a.txt", "b.txt"]  # first-seen order
    assert dm.kinds == ["transcription", "transcription"]
    # a.txt mean = (1, 0, 0, 0); b.txt = (0, 3, 0, 0)
    np.testing.assert_allclose(dm.X[0], [1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(dm.X[1], [0.0, 3.0, 0.0, 0.0])


@pytest.mark.unit
def test_document_matrix_l2_normalizes_rows():
    store = _store([("a.txt", [3.0, 4.0, 0.0, 0.0])])
    dm = document_matrix(store, l2_normalize=True)

    # (3,4) has norm 5 → unit row.
    norm = float(np.linalg.norm(dm.X[0]))
    assert norm == pytest.approx(1.0, abs=1e-5)
    np.testing.assert_allclose(dm.X[0], [0.6, 0.8, 0.0, 0.0], atol=1e-6)


@pytest.mark.unit
def test_document_matrix_single_chunk_is_normalized_self():
    store = _store([("only.txt", [0.0, 0.0, 5.0, 0.0])])
    dm = document_matrix(store)
    np.testing.assert_allclose(dm.X[0], [0.0, 0.0, 1.0, 0.0], atol=1e-6)


@pytest.mark.unit
def test_document_matrix_preserves_float32():
    store = _store([("a.txt", [1.0, 2.0, 3.0, 4.0])])
    dm = document_matrix(store)
    assert dm.X.dtype == np.float32


@pytest.mark.unit
def test_document_matrix_empty_store_yields_empty_matrix():
    store = VectorStore(dim=4)
    dm = document_matrix(store)
    assert dm.X.shape == (0, 4)
    assert dm.source_paths == []
    assert dm.kinds == []
    assert len(dm) == 0


@pytest.mark.unit
def test_document_matrix_first_seen_order_independent_of_interleaving():
    # b.txt appears first → must lead, even though a.txt has more chunks later.
    store = _store(
        [
            ("b.txt", [1.0, 0.0, 0.0, 0.0]),
            ("a.txt", [0.0, 1.0, 0.0, 0.0]),
            ("a.txt", [0.0, 1.0, 0.0, 0.0]),
        ]
    )
    dm = document_matrix(store)
    assert dm.source_paths == ["b.txt", "a.txt"]


@pytest.mark.unit
def test_chunk_matrix_returns_store_references():
    store = _store([("a.txt", [1.0, 0.0, 0.0, 0.0])])
    vecs, metas = chunk_matrix(store)
    assert vecs is store.vectors
    assert metas is store.meta


@pytest.mark.unit
def test_load_document_matrix_round_trips_persisted_store(tmp_path):
    # Persist a 768-dim store, then load+pool it through the accessor.
    store = VectorStore(dim=768)
    store.add(
        np.ones((2, 768), dtype=np.float32),
        [
            ChunkMeta("doc.txt", "document", 1.0, 0, "a"),
            ChunkMeta("doc.txt", "document", 1.0, 1, "b"),
        ],
    )
    store.persist(tmp_path)

    dm = load_document_matrix(tmp_path)
    assert dm.source_paths == ["doc.txt"]
    assert dm.kinds == ["document"]
    assert dm.X.shape == (1, 768)
    # Mean of two identical all-ones rows, then L2-normalized.
    assert float(np.linalg.norm(dm.X[0])) == pytest.approx(1.0, abs=1e-5)


@pytest.mark.unit
def test_load_document_matrix_absent_index_is_empty(tmp_path):
    dm = load_document_matrix(tmp_path / "nope")
    assert len(dm) == 0
    assert dm.X.shape == (0, 768)
