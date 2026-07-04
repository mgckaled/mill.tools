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


@pytest.mark.unit
def test_lead_bias_favors_earlier_sentence_with_equal_content():
    # Two sentences are literally identical (same content/vocabulary); only
    # their position in the document differs. Plain TextRank would give them
    # near-identical scores, but the lead-position prior should still favor
    # the earlier one.
    sentences = [
        "O modelo Whisper transcreve áudio local sem enviar dados à nuvem.",
        "Frase neutra e isolada que não compartilha vocabulário com as outras.",
        "O modelo Whisper transcreve áudio local sem enviar dados à nuvem.",
    ]
    sim = summarize._sentence_similarity(sentences)
    scores = summarize._textrank_scores(sim)
    assert scores[0] > scores[2]


@pytest.mark.unit
def test_sentence_similarity_handles_empty_vocabulary():
    # Punctuation-only "sentences" leave TfidfVectorizer with no tokens at all
    # (raises ValueError internally) — must degrade to "no similarity signal"
    # instead of propagating the error.
    sim = summarize._sentence_similarity(["...", "??", "!!!"])
    assert sim.shape == (3, 3)
    assert (sim == 0).all()


@pytest.mark.unit
def test_sample_indices_returns_all_when_under_cap():
    assert summarize._sample_indices(5, 400) == [0, 1, 2, 3, 4]


@pytest.mark.unit
def test_sample_indices_covers_full_range_not_just_head():
    # Regression for the old head-truncation bug: a plain `sents[:cap]` slice
    # never reaches the tail of a document longer than `cap`. The stratified
    # sample must keep both ends reachable and stay roughly evenly spaced.
    idx = summarize._sample_indices(1000, 400)
    assert len(idx) <= 400
    assert idx[0] == 0
    assert idx[-1] == 999
    assert max(b - a for a, b in zip(idx, idx[1:])) <= 4


@pytest.mark.unit
def test_diversifies_near_duplicate_sentences():
    # Two of the three sentences are identical (fully redundant); the third is
    # distinct. Plain top-k by PageRank alone risks picking both duplicates
    # (they reinforce each other); MMR should keep only one copy and use the
    # second slot for the distinct sentence instead.
    text = (
        "O Whisper transcreve áudio em texto usando GPU local. "
        "O Whisper transcreve áudio em texto usando GPU local. "
        "A ferramenta também gera legendas em SRT e VTT automaticamente."
    )
    out = summarize.extractive_summary(text, sentences=2)
    assert len(out) == 2
    assert len(set(out)) == 2  # not two copies of the same duplicate sentence
