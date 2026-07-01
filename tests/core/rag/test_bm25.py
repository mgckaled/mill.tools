"""Unit tests for src/core/rag/bm25.py — BM25 lexical scoring."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.mark.unit
def test_bm25_score_ranks_exact_term_match_highest():
    from src.core.rag.bm25 import bm25_score, build_bm25_index

    texts = [
        "the quick brown fox jumps over the lazy dog",
        "artigo quinto da constituicao federal",
        "completely unrelated content about cooking recipes",
    ]
    index = build_bm25_index(texts)
    scores = bm25_score(index, "artigo quinto")

    assert scores.shape == (3,)
    assert np.argmax(scores) == 1


@pytest.mark.unit
def test_bm25_score_no_match_returns_zeros():
    from src.core.rag.bm25 import bm25_score, build_bm25_index

    index = build_bm25_index(["hello world", "foo bar baz"])
    scores = bm25_score(index, "nonexistent query terms")

    np.testing.assert_array_equal(scores, np.zeros(2))


@pytest.mark.unit
def test_bm25_score_is_case_insensitive():
    # BM25's IDF is log((N - n + 0.5) / (n + 0.5)) for a term in n of N documents —
    # it hits exactly 0 (or goes negative) once the term isn't a minority across the
    # corpus. A 2-doc corpus with a 1-doc match already lands exactly on 0, so this
    # needs >=3 documents for the matching term to score above its non-matches.
    from src.core.rag.bm25 import bm25_score, build_bm25_index

    index = build_bm25_index(
        ["Artigo Quinto da Lei", "conteudo totalmente diferente", "mais texto qualquer"]
    )
    scores = bm25_score(index, "ARTIGO quinto")

    assert scores[0] > scores[1]
    assert scores[0] > scores[2]
