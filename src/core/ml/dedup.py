"""Near-duplicate detection over pooled document vectors (numpy-pure).

The proof-of-life capability of the ML foundation: it exercises the whole
RAG→ML path (load store → pool → similarity) without scikit-learn. Documents
whose pooled embeddings are mutually above a cosine threshold are grouped into
connected components — so a transcription and its lightly edited copy land in
the same group. Reused by the Library "duplicates/related" surface in Plan 4.
"""

from __future__ import annotations

import logging

import numpy as np

from src.core.ml.types import DocumentMatrix, DuplicateGroup


def _connected_components(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    """Group node indices ``0..n-1`` into connected components via union-find."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    groups: dict[int, list[int]] = {}
    for node in range(n):
        groups.setdefault(find(node), []).append(node)
    return list(groups.values())


def near_duplicates(
    dm: DocumentMatrix, *, threshold: float = 0.95, max_docs: int = 5000
) -> list[DuplicateGroup]:
    """Group near-identical documents by cosine similarity over pooled vectors.

    ``S = dm.X @ dm.X.T`` (the rows are already L2-normalized, so the inner
    product is the cosine); pairs with ``S[i, j] >= threshold`` (``i < j``)
    become edges and the connected components are the duplicate groups. Each
    group's ``score`` is the minimum pairwise cosine within it (its worst-case
    closeness), and groups are ordered by descending score.

    Quadratic guard: ``S`` is ``O(M^2 * D)``; above ``max_docs`` the function
    aborts with a warning and returns ``[]``. Blocking / ANN (``sqlite-vec``) is
    the documented seam for larger corpora — not implemented here.

    Args:
        dm: Pooled, L2-normalized document matrix.
        threshold: Minimum cosine for two documents to be considered duplicates.
        max_docs: Quadratic-cost guard; above this the run is skipped.

    Returns:
        Duplicate groups (each with ≥2 documents), ordered by descending score;
        an empty list when nothing duplicates, the matrix is empty, or the guard
        trips.
    """
    m = len(dm.source_paths)
    if m < 2:
        return []
    if m > max_docs:
        logging.warning(
            "[!] near_duplicates skipped: %d documents exceeds max_docs=%d "
            "(O(M^2) cost). Raise max_docs or block the corpus.",
            m,
            max_docs,
        )
        return []

    sim = dm.X @ dm.X.T
    iu, ju = np.triu_indices(m, k=1)
    mask = sim[iu, ju] >= threshold
    edges = list(zip(iu[mask].tolist(), ju[mask].tolist()))
    if not edges:
        return []

    groups: list[DuplicateGroup] = []
    for component in _connected_components(m, edges):
        if len(component) < 2:
            continue
        # Worst-case closeness = the smallest pairwise cosine inside the group.
        idx = np.array(sorted(component))
        sub = sim[np.ix_(idx, idx)]
        pi, pj = np.triu_indices(len(idx), k=1)
        score = float(sub[pi, pj].min())
        groups.append(
            DuplicateGroup(source_paths=[dm.source_paths[i] for i in idx], score=score)
        )

    groups.sort(key=lambda g: -g.score)
    return groups
