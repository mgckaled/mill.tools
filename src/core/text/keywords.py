"""Keyphrase extraction via YAKE — unsupervised, statistical, torch-free.

YAKE scores candidate n-grams from local text statistics (term frequency,
position, dispersion) with no neural model, training corpus or dictionary, so it
is small and offline. A **lower** score means a **more** relevant phrase, so the
returned list is sorted ascending. The dependency is optional (``[nlp]`` extra)
and lazily imported; ``is_available()`` gates the GUI/CLI the way the Tesseract
and embedder gates do.
"""

from __future__ import annotations

SETUP_HINT = "Instale o extra de NLP: uv sync --extra nlp"


def is_available() -> bool:
    """True if the ``yake`` package is importable (the ``[nlp]`` extra)."""
    try:
        import yake  # noqa: F401  (presence probe only)

        return True
    except ImportError:
        return False


def keyphrases(
    text: str, *, lang: str = "pt", top_n: int = 10, ngram: int = 3
) -> list[tuple[str, float]]:
    """Return up to ``top_n`` keyphrases as ``(phrase, score)``, best (lowest) first.

    Args:
        text: The full document text.
        lang: YAKE language code (``"pt"``/``"en"``) for its stopword list.
        top_n: Maximum number of phrases to return.
        ngram: Maximum words per phrase (1–3 is typical).

    Returns:
        ``(phrase, score)`` pairs sorted by ascending score (lower = more
        relevant); an empty list for blank text.

    Raises:
        RuntimeError: if the ``[nlp]`` extra (yake) is not installed.
    """
    if not is_available():
        raise RuntimeError(SETUP_HINT)
    if not text.strip():
        return []

    import yake

    extractor = yake.KeywordExtractor(lan=lang, n=ngram, top=top_n)
    # YAKE returns (phrase, score) already sorted ascending; cast numpy floats.
    return [
        (phrase, float(score)) for phrase, score in extractor.extract_keywords(text)
    ]
