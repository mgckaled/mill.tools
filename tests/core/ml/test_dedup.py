"""Unit tests for src/core/ml/dedup.py — near-duplicate grouping (numpy-pure)."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml.dedup import near_duplicates
from src.core.ml.types import DocumentMatrix


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
def test_identical_documents_group_together():
    dm = _dm(
        [
            ("a.txt", [1.0, 0.0, 0.0]),
            ("b.txt", [1.0, 0.0, 0.0]),  # identical to a
            ("c.txt", [0.0, 1.0, 0.0]),  # orthogonal → alone
        ]
    )
    groups = near_duplicates(dm, threshold=0.95)
    assert len(groups) == 1
    assert sorted(groups[0].source_paths) == ["a.txt", "b.txt"]
    assert groups[0].score == pytest.approx(1.0, abs=1e-5)


@pytest.mark.unit
def test_pairs_below_threshold_do_not_group():
    # cos between (1,0) and (0.7,0.7-ish) ~0.7 < 0.95 → no group.
    dm = _dm([("a.txt", [1.0, 0.0]), ("b.txt", [1.0, 1.0])])
    assert near_duplicates(dm, threshold=0.95) == []


@pytest.mark.unit
def test_transitive_chain_forms_single_component():
    # A≈B, B≈C (all very close) ⇒ one group {A,B,C} via connected components.
    dm = _dm(
        [
            ("A.txt", [1.0, 0.0, 0.0]),
            ("B.txt", [0.999, 0.045, 0.0]),
            ("C.txt", [0.999, 0.0, 0.045]),
        ]
    )
    groups = near_duplicates(dm, threshold=0.99)
    assert len(groups) == 1
    assert sorted(groups[0].source_paths) == ["A.txt", "B.txt", "C.txt"]


@pytest.mark.unit
def test_score_is_min_pairwise_cosine_in_group():
    dm = _dm(
        [
            ("A.txt", [1.0, 0.0, 0.0]),
            ("B.txt", [0.999, 0.045, 0.0]),
            ("C.txt", [0.999, 0.0, 0.045]),
        ]
    )
    [group] = near_duplicates(dm, threshold=0.99)
    # The min pairwise cosine is below 1.0 (B vs C are the least similar pair).
    pairwise_bc = float(np.dot(dm.X[1], dm.X[2]))
    assert group.score == pytest.approx(pairwise_bc, abs=1e-5)
    assert group.score < 1.0


@pytest.mark.unit
def test_two_separate_groups_ordered_by_score_desc():
    dm = _dm(
        [
            ("a1.txt", [1.0, 0.0, 0.0, 0.0]),
            ("a2.txt", [1.0, 0.0, 0.0, 0.0]),  # perfect pair → score 1.0
            ("b1.txt", [0.0, 1.0, 0.0, 0.0]),
            ("b2.txt", [0.0, 0.98, 0.2, 0.0]),  # slightly weaker pair
        ]
    )
    groups = near_duplicates(dm, threshold=0.95)
    assert len(groups) == 2
    assert groups[0].score >= groups[1].score  # highest score first
    assert sorted(groups[0].source_paths) == ["a1.txt", "a2.txt"]


@pytest.mark.unit
def test_empty_matrix_returns_empty():
    assert near_duplicates(_dm([])) == []


@pytest.mark.unit
def test_single_document_returns_empty():
    assert near_duplicates(_dm([("only.txt", [1.0, 0.0])])) == []


@pytest.mark.unit
def test_max_docs_guard_aborts_with_warning(caplog):
    import logging

    dm = _dm([(f"d{i}.txt", [1.0, 0.0]) for i in range(5)])
    with caplog.at_level(logging.WARNING):
        result = near_duplicates(dm, threshold=0.95, max_docs=3)
    assert result == []
    assert any("max_docs" in r.message for r in caplog.records)
