"""Keyphrase extraction via YAKE — unsupervised, statistical, torch-free.

YAKE scores candidate n-grams from local text statistics (term frequency,
position, dispersion) with no neural model, training corpus or dictionary, so it
is small and offline. A **lower** score means a **more** relevant phrase, so the
returned list is sorted ascending. The dependency is optional (``[nlp]`` extra)
and lazily imported; ``is_available()`` gates the GUI/CLI the way the Tesseract
and embedder gates do.

Deduplication is tuned down from YAKE's defaults: the installed
``KeywordExtractor`` takes ``dedup_lim``/``dedup_func``/``window_size``
(snake_case — its own README uses a stale camelCase spelling that the
constructor's ``**kwargs`` silently swallows instead of rejecting, so this was
verified against the actual installed signature, not just the docs). Lowering
``dedup_lim`` from the 0.9 default trims near-duplicate phrase variants from
the top-N; a wider ``window_size`` fits Portuguese's freer word order better.
"""

from __future__ import annotations

from src.core.text import clean

SETUP_HINT = "Instale o extra de NLP: uv sync --extra nlp"

# Tuned down from YAKE's defaults (0.9 dedup_lim, "seqm" dedup_func already
# default, 1 window_size) to cut near-duplicate phrase variants from the top-N.
_DEDUP_LIM = 0.75
_DEDUP_FUNC = "seqm"
_WINDOW_SIZE = 2

# Structural artifacts that survive clean.clean_document_text (a loose month
# name, a stray figure/table/page label) and would otherwise pollute the
# top-N as if they were real content — PLANO_INSIGHTS_QUALIDADE.md, Fase 5.1.
# Small and hand-curated, not meant to be exhaustive.
_EXTRA_STOPWORDS = frozenset(
    {
        "página",
        "pagina",
        "figura",
        "tabela",
        "anexo",
        "page",
        "figure",
        "table",
        "appendix",
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


def is_available() -> bool:
    """True if the ``yake`` package is importable (the ``[nlp]`` extra)."""
    try:
        import yake  # noqa: F401  (presence probe only)

        return True
    except ImportError:
        return False


def _stopwords_for(lang: str) -> set[str]:
    """Return YAKE's own default stopword set for *lang*, unioned with our
    small set of structural artifacts (loose months, page/figure labels).

    Passing ``stopwords=`` to the real ``KeywordExtractor`` *replaces* its
    default list entirely rather than extending it (verified against the
    installed ``yake==0.7.1`` source, ``_load_stopwords``) — passing only our
    extras would silently disable all of YAKE's normal function-word
    filtering. A throwaway extractor is built first just to read its default
    set, then merged with ours for the real extractor in :func:`keyphrases`.
    """
    import yake

    defaults = yake.KeywordExtractor(lan=lang).stopword_set
    return defaults | _EXTRA_STOPWORDS


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

    cleaned = clean.clean_document_text(text)
    if not cleaned.strip():
        return []

    extractor = yake.KeywordExtractor(
        lan=lang,
        n=ngram,
        top=top_n,
        dedup_lim=_DEDUP_LIM,
        dedup_func=_DEDUP_FUNC,
        stopwords=_stopwords_for(lang),
        window_size=_WINDOW_SIZE,
    )
    # YAKE returns (phrase, score) already sorted ascending; cast numpy floats.
    return [
        (phrase, float(score)) for phrase, score in extractor.extract_keywords(cleaned)
    ]
