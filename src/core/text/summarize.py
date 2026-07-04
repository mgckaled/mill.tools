"""Extractive summary via an in-house TextRank — self-contained, no nltk download.

Off-the-shelf TextRank (``sumy``) usually downloads ``nltk`` punkt data at
runtime, which breaks the app's offline, local-first promise. Instead this builds
the graph itself: split into sentences with a regex, vectorize them with the
``[ml]`` ``TfidfVectorizer`` (sublinear TF, so a few repeated words don't
dominate the similarity graph), form the sentence-by-sentence cosine similarity
graph, rank by power-iteration PageRank blended with a lead-position prior
(transcripts/articles tend to state the topic up front, which plain TextRank
ignores), and pick the summary sentences via Maximal Marginal Relevance so two
near-identical high-scoring sentences don't both make the cut. The result is
returned **in original order** so the summary reads naturally.

O(S²) in sentences, so a very long document is downsampled before building the
matrix — evenly across its **full length** (see ``_sample_indices``), not
truncated to the head, so a topic that only resurfaces in the back half of a
long transcript is still reachable. No new dependency: TF-IDF comes from
scikit-learn, already pulled by the ``[ml]`` extra.
"""

from __future__ import annotations

import re

import numpy as np

SETUP_HINT = "Instale o extra de ML: uv sync --extra ml"

# Cap on sentences fed to the O(S²) graph. Longer documents are downsampled
# evenly across their full length (``_sample_indices``) rather than truncated
# to the first ``_MAX_SENTENCES`` — a 2h lecture's second half used to be
# structurally invisible to the summary no matter how central its content.
_MAX_SENTENCES = 400

# Sentence boundary: end punctuation followed by whitespace. Deliberately simple
# (no nltk) — good enough for prose; abbreviations may over-split, which only
# costs a slightly shorter candidate sentence, never a crash.
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# MMR (Carbonell & Goldstein, 1998): balances centrality (PageRank score)
# against redundancy with sentences already picked. Duplicated from
# core/ml/recommend.py's _mmr — core/text stays independent of core/ml.
_MMR_LAMBDA = 0.6

# Lead-position prior blended into the PageRank score (Biased/PositionRank-style):
# plain TextRank ignores sentence position, but transcripts/articles tend to
# state the topic up front.
_POSITION_BIAS_WEIGHT = 0.15


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

    idx = _sample_indices(len(sents), _MAX_SENTENCES)
    work = [sents[i] for i in idx]
    sim = _sentence_similarity(work)
    scores = _textrank_scores(sim)
    order = _mmr(scores, sim, sentences)
    # Restored to original order for readability.
    return [work[i] for i in sorted(order)]


def _sample_indices(n: int, cap: int) -> list[int]:
    """Return up to ``cap`` positions, evenly spaced across ``range(n)``.

    A systematic sample instead of a head slice: it keeps the last index
    reachable, so a document far longer than ``cap`` sentences doesn't lose
    its entire back half to truncation before the ranking matrix is even built.
    """
    if n <= cap:
        return list(range(n))
    return sorted({int(i) for i in np.linspace(0, n - 1, num=cap)})


def _mmr(
    relevance: np.ndarray,
    similarity: np.ndarray,
    k: int,
    *,
    lambda_: float = _MMR_LAMBDA,
) -> list[int]:
    """Greedy Maximal Marginal Relevance selection (see core/ml/recommend.py).

    Picks up to ``k`` indices balancing ``relevance`` against redundancy with
    already-picked candidates (``similarity``, the pairwise matrix). Ties break
    by the lowest index for determinism. With no redundancy in the pool, this
    reduces to plain top-k by relevance.
    """
    n = len(relevance)
    k = min(k, n)
    selected: list[int] = []
    remaining = list(range(n))
    for _ in range(k):
        if not selected:
            scores = relevance
        else:
            redundancy = similarity[:, selected].max(axis=1)
            scores = lambda_ * relevance - (1 - lambda_) * redundancy
        best = max(remaining, key=lambda i: (scores[i], -i))
        selected.append(best)
        remaining.remove(best)
    return selected


def _sentence_similarity(sentences: list[str]) -> np.ndarray:
    """Cosine similarity matrix between sentences via sublinear TF-IDF.

    ``sublinear_tf`` replaces raw term frequency with ``1 + log(tf)`` so a
    sentence repeating one word doesn't dominate the similarity graph;
    ``ngram_range=(1, 2)`` lets short shared phrases (not just single words)
    count towards similarity.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    try:
        tfidf = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2)).fit_transform(
            sentences
        )
    except ValueError:
        # Empty vocabulary (e.g. only punctuation) → no similarity signal.
        return np.zeros((len(sentences), len(sentences)))

    sim = (tfidf @ tfidf.T).toarray()
    np.fill_diagonal(sim, 0.0)
    return sim


def _textrank_scores(sim: np.ndarray) -> np.ndarray:
    """PageRank over the sentence similarity graph, blended with a lead-position prior."""
    n = len(sim)
    row_sums = sim.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0.0] = 1.0  # isolated sentence → avoid divide-by-zero
    transition = sim / row_sums

    scores = np.full(n, 1.0 / n)
    damping = 0.85
    for _ in range(100):
        updated = (1.0 - damping) / n + damping * (transition.T @ scores)
        if np.abs(updated - scores).sum() < 1e-6:
            scores = updated
            break
        scores = updated

    # Earlier sentences get a decreasing positional prior (Biased/PositionRank).
    position_bias = 1.0 / (1.0 + np.arange(n))
    position_bias /= position_bias.sum()
    return (
        1.0 - _POSITION_BIAS_WEIGHT
    ) * scores + _POSITION_BIAS_WEIGHT * position_bias
