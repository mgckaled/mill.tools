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


@pytest.mark.unit
def test_related_diversifies_near_duplicate_candidates():
    # dup1/dup2 live in the same 2D subspace as the anchor and are near-
    # identical to each other (cosine ~0.9998); "diverse" sits on its own axis,
    # slightly less relevant than dup2 but with much lower redundancy against
    # dup1. Plain top-k by raw cosine would return {dup1, dup2}; MMR should
    # prefer "diverse" for the second slot instead of the redundant dup2.
    dm = _dm(
        [
            ("a.txt", [1.0, 0.0, 0.0]),
            ("dup1.txt", [0.9, 0.4359, 0.0]),  # cosine to anchor = 0.9
            ("dup2.txt", [0.89, 0.4560, 0.0]),  # cosine to anchor = 0.89
            ("diverse.txt", [0.85, 0.0, 0.5268]),  # cosine to anchor = 0.85
        ]
    )
    out = related(dm, "a.txt", k=2)
    paths = [p for p, _ in out]

    assert paths[0] == "dup1.txt"  # most relevant still wins the first slot
    assert "diverse.txt" in paths  # MMR picks it over the redundant dup2.txt
    assert "dup2.txt" not in paths


@pytest.mark.unit
def test_related_matches_plain_top_k_without_redundancy():
    # b/c/d each sit on their own axis (only sharing the anchor direction), and
    # their relevances are well-separated — MMR's redundancy term never flips
    # the ranking, so this must reduce to plain top-k by relevance.
    dm = _dm(
        [
            ("a.txt", [1.0, 0.0, 0.0, 0.0]),
            ("b.txt", [0.8660, 0.5, 0.0, 0.0]),  # cosine to anchor = 0.866
            ("c.txt", [0.5, 0.0, 0.8660, 0.0]),  # cosine to anchor = 0.5
            ("d.txt", [0.1736, 0.0, 0.0, 0.9848]),  # cosine to anchor = 0.1736
        ]
    )
    out = related(dm, "a.txt", k=2)
    assert [p for p, _ in out] == ["b.txt", "c.txt"]


@pytest.mark.unit
def test_related_pool_size_bounds_candidates_before_mmr():
    """M4: candidates outside the top-pool_size (by plain cosine) never enter
    the MMR step — bounds the O(pool^2) pairwise matrix regardless of corpus
    size, at the cost of the least-relevant candidates never getting a shot
    at diversifying the result."""
    import math

    def _vec(deg: float) -> list[float]:
        rad = math.radians(deg)
        return [math.cos(rad), math.sin(rad)]

    dm = _dm(
        [
            ("anchor.txt", [1.0, 0.0]),
            ("close1.txt", _vec(5)),
            ("close2.txt", _vec(10)),
            ("close3.txt", _vec(15)),
            ("far.txt", _vec(89)),  # far worse cosine — excluded by the pool
        ]
    )
    out = related(dm, "anchor.txt", k=4, pool_size=3)
    sources = [p for p, _ in out]
    assert "far.txt" not in sources
    assert len(sources) == 3  # only the 3 pooled candidates were ever available


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
