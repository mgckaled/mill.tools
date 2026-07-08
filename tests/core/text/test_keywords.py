"""Unit tests for src/core/text/keywords.py — YAKE keyphrases."""

from __future__ import annotations

import pytest

pytest.importorskip("yake")

from src.core.text import keywords  # noqa: E402


@pytest.mark.unit
def test_obvious_terms_appear_in_top_phrases():
    text = (
        "O Banco Central do Brasil elevou a taxa de juros para conter a inflação. "
        "A inflação preocupa o Banco Central, que monitora a taxa de juros de perto. "
        "Analistas avaliam a decisão do Banco Central sobre os juros."
    )
    out = keywords.keyphrases(text, lang="pt", top_n=10, ngram=2)
    phrases = " ".join(p for p, _ in out).lower()
    assert "banco central" in phrases
    # Scores are floats and sorted ascending (lower = more relevant).
    scores = [s for _, s in out]
    assert all(isinstance(s, float) for s in scores)
    assert scores == sorted(scores)


@pytest.mark.unit
def test_respects_top_n():
    text = " ".join(f"termo{i} relevante importante" for i in range(40))
    out = keywords.keyphrases(text, top_n=5)
    assert len(out) <= 5


@pytest.mark.unit
def test_blank_text_returns_empty():
    assert keywords.keyphrases("   ") == []


@pytest.mark.unit
def test_is_available_true_when_installed():
    assert keywords.is_available() is True


@pytest.mark.unit
def test_gate_raises_when_unavailable(mocker):
    mocker.patch("src.core.text.keywords.is_available", return_value=False)
    with pytest.raises(RuntimeError, match="nlp"):
        keywords.keyphrases("qualquer texto")


@pytest.mark.unit
def test_stopwords_for_merges_yake_defaults_with_extras():
    # Must keep YAKE's own function-word filtering (e.g. "de") *and* add our
    # structural artifacts -- passing only the extras would silently replace
    # (not extend) YAKE's default list (verified against yake==0.7.1's
    # _load_stopwords source).
    merged = keywords._stopwords_for("pt")
    assert "de" in merged  # a real YAKE PT stopword
    assert "página" in merged  # our extra


@pytest.mark.unit
def test_keyphrases_of_messy_pdf_excludes_structural_artifacts(messy_pdf_text):
    """PLANO_INSIGHTS_QUALIDADE.md, Fase 5.1: page markers are already gone at
    the source (clean_document_text); loose front-matter words that survive
    tokenization must not surface as keyphrases either."""
    out = keywords.keyphrases(messy_pdf_text, lang="en", top_n=10)
    phrases = " ".join(p for p, _ in out).lower()
    assert "página" not in phrases
    assert "anthropic" not in phrases
    assert "january" not in phrases


@pytest.mark.unit
def test_keyphrases_blank_after_cleaning_returns_empty():
    # A "document" that is nothing but a page marker: non-blank before
    # cleaning, blank after -- must degrade to [], not crash inside YAKE.
    from src.core.text.clean import page_marker

    text = f"\n\n{page_marker(1)}\n\n"
    assert keywords.keyphrases(text) == []


@pytest.mark.unit
def test_extractor_receives_the_tuned_dedup_params(mocker):
    # yake.KeywordExtractor.__init__ has a **kwargs catch-all that silently
    # swallows unknown keyword names instead of raising -- these must be the
    # real (snake_case) parameter names, not a typo that gets no-op'd away.
    import yake

    spy = mocker.patch("yake.KeywordExtractor", wraps=yake.KeywordExtractor)
    keywords.keyphrases("Texto qualquer para extrair frases-chave.", lang="pt")

    _, kwargs = spy.call_args
    assert kwargs["dedup_lim"] == keywords._DEDUP_LIM
    assert kwargs["dedup_func"] == keywords._DEDUP_FUNC
    assert kwargs["window_size"] == keywords._WINDOW_SIZE
