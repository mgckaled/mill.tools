"""Unit tests for src/core/text/summarize.py — in-house TextRank."""

from __future__ import annotations

import pytest

from src.core.text import summarize


@pytest.mark.unit
def test_split_sentences_basic():
    out = summarize.split_sentences("Primeira frase. Segunda frase! Terceira?")
    assert out == ["Primeira frase.", "Segunda frase!", "Terceira?"]


@pytest.mark.unit
def test_central_sentence_kept_and_order_preserved():
    # The "whisper/transcrição" theme is central (repeated); the off-topic
    # sentences about cooking are peripheral and should be dropped first.
    text = (
        "O Whisper transcreve áudio em texto usando GPU. "
        "Hoje choveu bastante na cidade pela manhã. "
        "A transcrição com Whisper acelera muito o fluxo de trabalho. "
        "Gosto de bolo de chocolate no café da tarde. "
        "O modelo Whisper roda transcrição local sem enviar dados para a nuvem."
    )
    out = summarize.extractive_summary(text, sentences=2)
    assert len(out) == 2
    joined = " ".join(out).lower()
    assert "whisper" in joined
    # Original order preserved: each kept sentence keeps its relative position.
    sents = summarize.split_sentences(text)
    positions = [sents.index(s) for s in out]
    assert positions == sorted(positions)


@pytest.mark.unit
def test_returns_all_when_fewer_than_requested():
    text = "Só uma frase aqui."
    assert summarize.extractive_summary(text, sentences=5) == ["Só uma frase aqui."]


@pytest.mark.unit
def test_blank_text_returns_empty():
    assert summarize.extractive_summary("   ", sentences=3) == []


@pytest.mark.unit
def test_respects_sentence_count():
    text = " ".join(
        f"Esta é a frase número {i} do documento de teste." for i in range(20)
    )
    out = summarize.extractive_summary(text, sentences=4)
    assert len(out) == 4


@pytest.mark.unit
def test_gate_raises_when_sklearn_missing(mocker):
    mocker.patch("src.core.text.summarize.is_available", return_value=False)
    with pytest.raises(RuntimeError, match="ml"):
        summarize.extractive_summary(
            "uma frase. outra frase. mais uma frase.", sentences=1
        )
