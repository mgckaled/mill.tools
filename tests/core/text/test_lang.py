"""Unit tests for src/core/text/lang.py — PT/EN heuristic."""

from __future__ import annotations

import pytest

from src.core.text.lang import detect_lang


@pytest.mark.unit
def test_detects_portuguese():
    assert (
        detect_lang("O modelo de linguagem que não para de aprender com os dados.")
        == "pt"
    )


@pytest.mark.unit
def test_detects_english():
    assert (
        detect_lang("The model that keeps learning from the data and the world.")
        == "en"
    )


@pytest.mark.unit
def test_empty_defaults_to_pt():
    assert detect_lang("") == "pt"
    assert detect_lang("123 456 !!!") == "pt"


@pytest.mark.unit
def test_ambiguous_english_words_do_not_bias_toward_portuguese():
    # "do" and "as" are common English words that used to sit in _PT_MARKERS
    # too (they double as PT function words) — a real English sentence built
    # mostly around them used to tip "pt" purely from that overlap.
    assert detect_lang("As long as I do this, it works.") == "en"
