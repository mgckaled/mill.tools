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


@dataclass(frozen=True, slots=True)
class Classification:
    """The predicted analysis profile for a document and its confidence.

    Produced by ``classify``: either a zero-shot nearest-prototype match or, once
    enough user corrections have accumulated, a trained linear model's prediction.
    ``margin`` (top-1 minus top-2 score) is the uncertainty signal the GUI shows
    as "sugestão incerta" when it is small.
    """

    profile_id: str  # winning analysis-profile id (e.g. "lecture")
    confidence: float  # top-1 cosine (zero-shot) or calibrated proba (supervised)
    margin: float  # top1 - top2 score (small = ambiguous)
    method: str  # "zeroshot" | "supervised"


@dataclass(frozen=True, slots=True)
class ClusterResult:
    """The outcome of clustering the pooled document vectors.

    ``labels[d]`` is the cluster id of document ``d`` (parallel to the
    ``DocumentMatrix`` rows). HDBSCAN marks outliers/noise with ``-1``, which we
    reuse as "isolated/orphan content"; ``n_clusters`` and ``n_noise`` exclude
    and count that label respectively.
    """

    labels: np.ndarray  # (M,) int; -1 = noise/outlier (HDBSCAN)
    method: str  # "hdbscan" | "kmeans"
    n_clusters: int  # distinct labels excluding -1
    n_noise: int  # count of label == -1


@dataclass(frozen=True, slots=True)
class SemanticMap:
    """Everything needed to draw and navigate the semantic map of the corpus.

    ``coords`` are the 2D projection of each document; ``labels`` the cluster id;
    ``cluster_names`` maps a cluster id to its top discriminative terms (c-TF-IDF,
    excluding ``-1``). ``coords``/``labels``/``source_paths``/``kinds`` are all
    parallel, one entry per document, in the accessor's first-seen order.
    """

    coords: np.ndarray  # (M, 2) float32 — 2D projection for the scatter map
    labels: np.ndarray  # (M,) int — cluster id per document (-1 = orphan)
    cluster_names: dict[int, list[str]]  # cluster id → top terms (no -1)
    source_paths: list[str]  # length M, parallel to coords rows
    kinds: list[str]  # length M, the document kind

    def __len__(self) -> int:
        """Number of documents on the map (rows in ``coords``)."""
        return len(self.source_paths)
