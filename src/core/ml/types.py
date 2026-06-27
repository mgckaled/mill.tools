"""Typed models for the ML foundation layer.

Frozen + slots, matching the rest of the project's core dataclasses. numpy is a
base dependency, so it is imported directly; the arrays are never hashed, so a
frozen dataclass holding an ``np.ndarray`` field is fine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class DocumentMatrix:
    """One pooled embedding vector per source document.

    Produced by ``features.document_matrix`` from the chunk-level RAG store: the
    chunk rows of each ``source_path`` are mean-pooled into a single row, then
    (by default) L2-normalized so downstream cosine/SVM/k-means operate on the
    unit sphere. ``X``, ``source_paths`` and ``kinds`` are parallel: row ``d`` of
    ``X`` describes document ``source_paths[d]`` of kind ``kinds[d]``.
    """

    X: np.ndarray  # (M, D) float32, L2-normalized (one row per document)
    source_paths: list[str]  # length M, parallel to X rows (first-seen order)
    kinds: list[str]  # length M, the document kind

    def __len__(self) -> int:
        """Number of documents (rows in ``X``)."""
        return len(self.source_paths)


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """A set of near-identical documents found by cosine similarity."""

    source_paths: list[str]  # documents mutually above the threshold
    score: float  # min pairwise cosine within the group (worst-case closeness)
