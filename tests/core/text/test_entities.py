"""Unit tests for src/core/text/entities.py — spaCy NER (CNN, torch-free)."""

from __future__ import annotations

import pytest

pytest.importorskip("spacy")

from src.core.text import entities  # noqa: E402

# Some tests need the actual model download; skip them cleanly when it is absent
# (mirrors the Tesseract-gated OCR tests).
_MODEL = pytest.mark.skipif(
    not entities.is_available("pt"),
    reason="pt_core_news_sm model not installed",
)


@pytest.mark.unit
@_MODEL
def test_extracts_person_org_location():
    out = entities.entities(
        "Maria Silva trabalha na Petrobras no Rio de Janeiro desde 2020."
    )
    texts = [t for t, _ in out]
    labels = {label for _, label in out}
    assert "Maria Silva" in texts
    assert "Petrobras" in texts
    assert labels & {"PER", "ORG", "LOC"}  # at least one core entity type


@pytest.mark.unit
@_MODEL
def test_deduplicates_repeated_entities():
    out = entities.entities("A Petrobras cresceu. A Petrobras investiu mais.")
    pairs = [p for p in out if p[0] == "Petrobras"]
    assert len(pairs) == 1  # collapsed to a single (text, label)


@pytest.mark.unit
@_MODEL
def test_blank_text_returns_empty():
    assert entities.entities("   ") == []


@pytest.mark.unit
def test_is_available_false_without_spacy(mocker):
    # Simulate spaCy importable but the model missing.
    mocker.patch("spacy.util.is_package", return_value=False)
    assert entities.is_available("pt") is False


@pytest.mark.unit
def test_gate_raises_when_model_missing(mocker):
    mocker.patch("src.core.text.entities.is_available", return_value=False)
    with pytest.raises(RuntimeError, match="spacy download"):
        entities.entities("Maria foi ao Rio.")


@pytest.mark.unit
def test_model_for_falls_back_to_pt():
    assert entities._model_for("xx") == "pt_core_news_sm"
    assert entities._model_for("en") == "en_core_web_sm"
