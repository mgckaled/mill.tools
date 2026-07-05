"""Near-duplicate image detection over difference hashes (Hamming distance).

Mirrors ``core/ml/dedup.py::near_duplicates`` — same connected-components-by-
threshold algorithm, duplicated rather than imported (``core/library`` stays
independent of ``core/ml``, the same rationale already applied to ``core/text``
and the MMR helper). The only real difference is the metric: Hamming distance
is an integer where *smaller* means closer, the opposite of cosine similarity.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.image.dhash import dhash, hamming_distance
from src.core.library.types import ImageDuplicateGroup

# Of 64 bits (``hash_size=8``) — the conventional cutoff (shared by pHash/dHash
# community practice) for "same image, lightly re-encoded/cropped".
DEFAULT_MAX_DISTANCE = 8


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


def near_duplicate_images(
    paths: list[Path],
    *,
    max_distance: int = DEFAULT_MAX_DISTANCE,
    max_images: int = 5000,
) -> list[ImageDuplicateGroup]:
    """Group perceptually-identical images by Hamming distance between dHashes.

    Pairs with a Hamming distance ``<= max_distance`` become edges and the
    connected components are the duplicate groups. Each group's
    ``max_distance`` is the *largest* pairwise distance within it (its
    worst-case closeness), and groups are ordered by ascending distance
    (tightest matches first).

    Quadratic guard: pairwise comparison is ``O(n^2)``; above ``max_images``
    the function aborts with a warning and returns ``[]``, same convention as
    ``ml.dedup.near_duplicates``.

    Args:
        paths: Image files to compare.
        max_distance: Maximum Hamming distance for two images to be
            considered duplicates.
        max_images: Quadratic-cost guard; above this the run is skipped.

    Returns:
        Duplicate groups (each with >=2 images), ordered by ascending
        ``max_distance``; empty when nothing duplicates or the guard trips.

    Corrupted/unreadable images are skipped individually (logged as a
    warning) instead of aborting the whole batch — one bad file shouldn't
    hide duplicates among the rest, same convention as ``image.transform``'s
    ``contact_sheet``.
    """
    n = len(paths)
    if n < 2:
        return []
    if n > max_images:
        logging.warning(
            "[!] near_duplicate_images skipped: %d images exceeds max_images=%d "
            "(O(n^2) cost). Raise max_images or split the folder.",
            n,
            max_images,
        )
        return []

    valid_paths: list[Path] = []
    hashes = []
    for p in paths:
        try:
            hashes.append(dhash(p))
            valid_paths.append(p)
        except Exception as exc:
            logging.warning("[!] Skipping unreadable image for dedup: %s (%s)", p, exc)

    m = len(valid_paths)
    if m < 2:
        return []

    edges = [
        (i, j)
        for i in range(m)
        for j in range(i + 1, m)
        if hamming_distance(hashes[i], hashes[j]) <= max_distance
    ]
    if not edges:
        return []

    groups: list[ImageDuplicateGroup] = []
    for component in _connected_components(m, edges):
        if len(component) < 2:
            continue
        idx = sorted(component)
        worst = max(
            hamming_distance(hashes[idx[a]], hashes[idx[b]])
            for a in range(len(idx))
            for b in range(a + 1, len(idx))
        )
        groups.append(
            ImageDuplicateGroup(paths=[valid_paths[i] for i in idx], max_distance=worst)
        )

    groups.sort(key=lambda g: g.max_distance)
    return groups
