"""BM25 lexical scoring — the sparse half of the RAG's hybrid retrieval.

Dense embeddings are strong on meaning but weak on exact terms (proper nouns,
acronyms, numbers) — a well-documented gap of purely dense RAG. `rank_bm25` was
chosen over the faster `bm25s` deliberately: `bm25s` pulls `scipy` (a compiled
dependency) for a speedup that only matters past ~1M documents, far beyond a
personal corpus; `rank_bm25` needs only `numpy`, already a hard dependency.
"""

from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

# Word-character runs (Unicode-aware — matches accented PT-BR letters too),
# not `.split()` on whitespace: a plain split leaves punctuation glued to the
# adjacent token ("dog." != "dog"), silently missing matches at sentence
# boundaries. Richer NLP tokenization (stemming, stopwords) belongs to
# `core/text`, not here — this is just enough to stop punctuation from
# corrupting lexical matching.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def build_bm25_index(texts: list[str]) -> BM25Okapi:
    """Build a BM25 index over `texts`. Callers must guard against an empty list —
    BM25Okapi divides by the average document length, which is undefined for zero docs."""
    tokenized = [_tokenize(text) for text in texts]
    return BM25Okapi(tokenized)


def bm25_score(index: BM25Okapi, query: str) -> np.ndarray:
    """BM25 relevance of `query` against every document `index` was built from."""
    return index.get_scores(_tokenize(query))
