"""Difference hash (dHash) — a lightweight, dependency-free perceptual hash.

Tolerant to light recompression/resize, unlike a cryptographic hash (MD5/SHA),
which breaks on a single differing pixel. Uses only Pillow + numpy — both
already hard dependencies — so near-duplicate image detection needs no new
extra.

Chosen deliberately over the popular ``imagehash`` package's DCT-based
``phash()``: that package transitively pulls ``scipy`` (for the DCT) and
``PyWavelets`` (for its ``whash``), both compiled dependencies — a real cost
for a personal app that already avoids exactly this class of dependency
elsewhere (see the BM25 choice in ``core/rag/bm25.py``). dHash needs neither,
and is also reported as *more* robust than pHash specifically against
resize/recompress duplicates — the mill.tools use case (a photo saved twice,
lightly re-encoded/cropped) — not merely "good enough".
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def dhash(path: Path, *, hash_size: int = 8) -> np.ndarray:
    """Difference hash of the image at ``path``, as a flat boolean bit array.

    Resizes to ``(hash_size + 1, hash_size)`` grayscale, then sets bit
    ``(row, col)`` when pixel ``(row, col)`` is brighter than its right
    neighbor ``(row, col + 1)`` — the classic dHash gradient comparison.
    ``hash_size=8`` (the default) gives a 64-bit hash.
    """
    with Image.open(path) as im:
        small = im.convert("L").resize(
            (hash_size + 1, hash_size), Image.Resampling.LANCZOS
        )
        pixels = np.asarray(small, dtype=np.int16)
    return (pixels[:, :-1] > pixels[:, 1:]).flatten()


def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """Count of differing bits between two same-shaped hashes."""
    return int(np.count_nonzero(a != b))
