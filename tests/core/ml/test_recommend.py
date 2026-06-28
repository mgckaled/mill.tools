"""Unit tests for src/core/ml/recommend.py — related + in_corpus (numpy-pure)."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml.recommend import in_corpus, related
from src.core.ml.types import DocumentMatrix
from src.core.rag.store import VectorStore
from src.core.rag.types import ChunkMeta


def _dm(rows: list[tuple[str, list[float]]]) -> DocumentMatrix:
    """Build an L2-normalized DocumentMatrix from ``(source_path, vector)`` pairs."""
    X = np.array([v for _, v in rows], dtype=np.float32)
    if len(X):
        X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-8)
    return DocumentMatrix(
        X=X.astype(np.float32),
        source_paths=[s for s, _ in rows],
        kinds=["transcription"] * len(rows),
    )


@pytest.mark.unit
def test_related_returns_nearest_first_excluding_self():
    dm = _dm(
        [
            ("a.txt", [1.0, 0.0, 0.0]),
            ("near.txt", [0.99, 0.1, 0.0]),  # closest to a
            ("mid.txt", [0.7, 0.7, 0.0]),
            ("far.txt", [0.0, 0.0, 1.0]),  # orthogonal
        ]
    )
    out = related(dm, "a.txt", k=3)

    assert [p for p, _ in out] == ["near.txt", "mid.txt", "far.txt"]
    assert "a.txt" not in [p for p, _ in out]  # never recommends itself
    assert out[0][1] > out[1][1] > out[2][1]  # descending cosine


@pytest.mark.unit
def test_related_respects_k():
    dm = _dm([(f"d{i}.txt", [1.0, i * 0.01, 0.0]) for i in range(6)])
    assert len(related(dm, "d0.txt", k=2)) == 2


@pytest.mark.unit
def test_related_returns_all_when_k_exceeds_corpus():
    # k larger than the number of other docs → loop exhausts without breaking.
    dm = _dm([("a.txt", [1.0, 0.0]), ("b.txt", [0.9, 0.1])])
    out = related(dm, "a.txt", k=10)
    assert [p for p, _ in out] == ["b.txt"]  # only the single other doc


@pytest.mark.unit
def test_related_raises_for_unknown_document():
    dm = _dm([("a.txt", [1.0, 0.0])])
    with pytest.raises(ValueError, match="not in the index"):
        related(dm, "ghost.txt")


def _store_one(vec: list[float]) -> VectorStore:
    store = VectorStore(dim=len(vec))
    store.add(
        np.array([vec], dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "text")],
    )
    return store


@pytest.mark.unit
def test_in_corpus_true_above_threshold():
    store = _store_one([1.0, 0.0, 0.0])
    covered, score = in_corpus(
        np.array([1.0, 0.0, 0.0], dtype=np.float32), store, threshold=0.5
    )
    assert covered is True
    assert score == pytest.approx(1.0, abs=1e-5)


@pytest.mark.unit
def test_in_corpus_false_below_threshold():
    store = _store_one([1.0, 0.0, 0.0])
    # orthogonal query → cosine ~0 < threshold
    covered, score = in_corpus(
        np.array([0.0, 1.0, 0.0], dtype=np.float32), store, threshold=0.35
    )
    assert covered is False
    assert score < 0.35


@pytest.mark.unit
def test_in_corpus_empty_store():
    covered, score = in_corpus(np.ones(3, dtype=np.float32), VectorStore(dim=3))
    assert covered is False
    assert score == 0.0


@pytest.mark.unit
def test_document_texts_groups_in_first_seen_order():
    from src.core.ml.features import document_texts

    store = VectorStore(dim=2)
    store.add(
        np.ones((3, 2), dtype=np.float32),
        [
            ChunkMeta("a.txt", "transcription", 1.0, 0, "hello"),
            ChunkMeta("b.txt", "document", 1.0, 0, "world"),
            ChunkMeta("a.txt", "transcription", 1.0, 1, "again"),
        ],
    )
    texts = document_texts(store)
    # a.txt first-seen → its two chunks joined; b.txt second.
    assert texts == ["hello\nagain", "world"]
