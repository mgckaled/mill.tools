"""BM25 lexical scoring — the sparse half of the RAG's hybrid retrieval.

Dense embeddings are strong on meaning but weak on exact terms (proper nouns,
acronyms, numbers) — a well-documented gap of purely dense RAG. `rank_bm25` was
chosen over the faster `bm25s` deliberately: `bm25s` pulls `scipy` (a compiled
dependency) for a speedup that only matters past ~1M documents, far beyond a
personal corpus; `rank_bm25` needs only `numpy`, already a hard dependency.
"""

from __future__ import annotations

import numpy as np
from rank_bm25 import BM25Okapi


def build_bm25_index(texts: list[str]) -> BM25Okapi:
    """Build a BM25 index over `texts`. Callers must guard against an empty list —
    BM25Okapi divides by the average document length, which is undefined for zero docs."""
    tokenized = [text.lower().split() for text in texts]
    return BM25Okapi(tokenized)


def bm25_score(index: BM25Okapi, query: str) -> np.ndarray:
    """BM25 relevance of `query` against every document `index` was built from.

    Tokenization is a plain `.lower().split()` — good enough for lexical matching;
    richer NLP tokenization belongs to `core/text`, not here.
    """
    return index.get_scores(query.lower().split())
