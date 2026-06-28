"""Extractive summary via an in-house TextRank — self-contained, no nltk download.

Off-the-shelf TextRank (``sumy``) usually downloads ``nltk`` punkt data at
runtime, which breaks the app's offline, local-first promise. Instead this builds
the graph itself: split into sentences with a regex, vectorize them with the
``[ml]`` ``TfidfVectorizer``, form the sentence-by-sentence cosine similarity
graph, and rank by power-iteration PageRank. The top sentences are returned **in
original order** so the summary reads naturally.

O(S²) in sentences, so the count is capped before building the matrix. No new
dependency: TF-IDF comes from scikit-learn, already pulled by the ``[ml]`` extra.
"""

from __future__ import annotations

import re

import numpy as np

SETUP_HINT = "Instale o extra de ML: uv sync --extra ml"

# Cap on sentences fed to the O(S²) graph; longer documents are truncated to the
# first ``_MAX_SENTENCES`` (a summary of the opening is still useful and bounded).
_MAX_SENTENCES = 400

# Sentence boundary: end punctuation followed by whitespace. Deliberately simple
# (no nltk) — good enough for prose; abbreviations may over-split, which only
# costs a slightly shorter candidate sentence, never a crash.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def is_available() -> bool:
    """True if scikit-learn is importable (the ``[ml]`` extra provides TF-IDF)."""
    try:
        import sklearn  # noqa: F401  (presence probe only)

        return True
    except ImportError:
        return False


def split_sentences(text: str) -> list[str]:
    """Split *text* into trimmed, non-empty sentences (whitespace collapsed)."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return []
    return [s.strip() for s in _SENT_BOUNDARY.split(collapsed) if s.strip()]


def extractive_summary(text: str, *, sentences: int = 5, lang: str = "pt") -> list[str]:
    """Return the ``sentences`` most central sentences, in original order.

    Args:
        text: The full document text.
        sentences: How many sentences the summary should contain.
        lang: Accepted for API symmetry with the other engines; TextRank is
            language-agnostic (TF-IDF over the document's own vocabulary).

    Returns:
        The top sentences in their original document order; all sentences when
        the document already has at most ``sentences`` of them; ``[]`` for blank
        text.

    Raises:
        RuntimeError: if scikit-learn (the ``[ml]`` extra) is not installed.
    """
    if not is_available():
        raise RuntimeError(SETUP_HINT)

    sents = split_sentences(text)
    if len(sents) <= sentences:
        return sents

    work = sents[:_MAX_SENTENCES]
    scores = _textrank_scores(work)
    # Highest-scoring indices, then restored to original order for readability.
    top = sorted(int(i) for i in np.argsort(scores)[::-1][:sentences])
    return [work[i] for i in top]


def _textrank_scores(sentences: list[str]) -> np.ndarray:
    """PageRank over the TF-IDF cosine sentence graph (deterministic)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    try:
        tfidf = TfidfVectorizer().fit_transform(sentences)
    except ValueError:
        # Empty vocabulary (e.g. only punctuation) → uniform importance.
        return np.ones(len(sentences), dtype=float)

    sim = (tfidf @ tfidf.T).toarray()
    np.fill_diagonal(sim, 0.0)
    row_sums = sim.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0.0] = 1.0  # isolated sentence → avoid divide-by-zero
    transition = sim / row_sums

    n = len(sentences)
    scores = np.full(n, 1.0 / n)
    damping = 0.85
    for _ in range(100):
        updated = (1.0 - damping) / n + damping * (transition.T @ scores)
        if np.abs(updated - scores).sum() < 1e-6:
            scores = updated
            break
        scores = updated
    return scores
