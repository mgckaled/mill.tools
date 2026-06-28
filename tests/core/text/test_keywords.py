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
