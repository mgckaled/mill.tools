"""Name each cluster by its most discriminative terms (class-based TF-IDF).

Naive per-cluster TF-IDF surfaces globally common words; c-TF-IDF (the BERTopic
formulation) instead treats each *cluster* as one document and scores terms that
are frequent **in** the cluster yet rare **across** clusters — exactly what tells
one theme from another. Built on ``CountVectorizer`` + the c-TF-IDF formula, so
no BERTopic dependency is pulled; scikit-learn is lazy and gated by the ``[ml]``
extra. A small built-in PT/EN stopword list keeps function words out without a
new dependency.

``ngram_range=(1, 3)`` lets short discriminative phrases ("aprendizado de
máquina"), not just single words, surface as cluster labels — BERTopic's own
guidance for short-text corpora. The class term-frequency also gets
``reduce_frequent_words`` (BERTopic's square-root dampening) before the IDF
weighting, softening residual stopwords that survive the list.
"""

from __future__ import annotations

import numpy as np

from src.core.ml.deps import SETUP_HINT, is_available

# Minimal PT/EN stopword list — function words that would otherwise dominate the
# counts. Deliberately small (no NLTK/spaCy dependency); extend as needed.
_STOPWORDS = frozenset(
    {
        # Portuguese
        "a",
        "o",
        "e",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "um",
        "uma",
        "uns",
        "umas",
        "que",
        "com",
        "por",
        "para",
        "se",
        "os",
        "as",
        "ao",
        "aos",
        "mais",
        "como",
        "mas",
        "ou",
        "foi",
        "ser",
        "este",
        "esta",
        "isso",
        "ele",
        "ela",
        "você",
        "voce",
        "sua",
        "seu",
        "são",
        "sao",
        "não",
        "nao",
        "está",
        "esta",
        "pra",
        "tem",
        "já",
        "ja",
        "também",
        "tambem",
        "muito",
        "lá",
        "la",
        "aqui",
        # English
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "this",
        "that",
        "these",
        "those",
        "with",
        "as",
        "at",
        "by",
        "from",
        "but",
        "not",
        "you",
        "your",
        "we",
        "they",
        "he",
        "she",
        "i",
        "so",
        "if",
        "then",
        "than",
        "do",
        "does",
        "did",
        "can",
        "will",
        "would",
        "there",
        "their",
        "what",
        "which",
    }
)


def label_clusters(
    doc_texts: list[str], labels: np.ndarray, *, top_n: int = 5
) -> dict[int, list[str]]:
    """Return the top-``n`` discriminative terms per cluster via c-TF-IDF.

    Each cluster's document texts are concatenated into one pseudo-document; a
    term's score is its in-cluster frequency weighted by how rare it is across
    clusters. The noise cluster ``-1`` is ignored.

    Args:
        doc_texts: one text per document, parallel to ``labels`` (from
            ``features.document_texts``).
        labels: cluster id per document (``-1`` = noise).
        top_n: how many terms to keep per cluster.

    Returns:
        ``{cluster_id: [term, ...]}`` for every non-noise cluster (possibly empty
        lists when a cluster has no scorable terms).

    Raises:
        RuntimeError: if the ``[ml]`` extra is not installed.
    """
    if not is_available():
        raise RuntimeError(SETUP_HINT)

    clusters = sorted({int(label) for label in labels} - {-1})
    if not clusters:
        return {}

    # One pseudo-document per cluster: concatenate that cluster's doc texts.
    corpus = [
        " ".join(t for t, label in zip(doc_texts, labels) if int(label) == c)
        for c in clusters
    ]

    from sklearn.feature_extraction.text import CountVectorizer

    vectorizer = CountVectorizer(stop_words=list(_STOPWORDS), ngram_range=(1, 3))
    try:
        counts = vectorizer.fit_transform(corpus).toarray().astype(float)
    except ValueError:
        # Empty vocabulary (e.g. only stopwords/numbers) → no labels.
        return {c: [] for c in clusters}

    terms = vectorizer.get_feature_names_out()
    scores = _ctfidf(counts)

    result: dict[int, list[str]] = {}
    for i, c in enumerate(clusters):
        ranked = np.argsort(scores[i])[::-1]
        result[c] = [terms[j] for j in ranked[:top_n] if scores[i, j] > 0]
    return result


def _ctfidf(counts: np.ndarray) -> np.ndarray:
    """Compute the class-based TF-IDF matrix from per-class term counts.

    ``tf`` is each class row L1-normalized by its token total, then square-root
    dampened (BERTopic's ``reduce_frequent_words``, softening residual
    stopwords that survive the list); ``idf`` is ``log(1 + A / f_x)`` where
    ``A`` is the average tokens per class and ``f_x`` the term's total
    frequency across classes (BERTopic's c-TF-IDF).
    """
    tokens_per_class = counts.sum(axis=1, keepdims=True)
    tf = counts / np.where(tokens_per_class == 0, 1, tokens_per_class)
    tf = np.sqrt(tf)
    avg_tokens = tokens_per_class.mean()
    term_freq = counts.sum(axis=0)
    idf = np.log(1 + avg_tokens / np.where(term_freq == 0, 1, term_freq))
    return tf * idf
