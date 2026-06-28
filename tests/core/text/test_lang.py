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
