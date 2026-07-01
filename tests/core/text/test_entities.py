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


@pytest.mark.unit
def test_load_glossary_patterns_absent_file_returns_empty(mocker, tmp_path):
    mocker.patch(
        "src.core.text.entities._glossary_path",
        return_value=tmp_path / "nope.json",
    )
    assert entities._load_glossary_patterns() == []


@pytest.mark.unit
def test_load_glossary_patterns_malformed_json_returns_empty(mocker, tmp_path):
    bad = tmp_path / "entity_glossary.json"
    bad.write_text("not json", encoding="utf-8")
    mocker.patch("src.core.text.entities._glossary_path", return_value=bad)
    assert entities._load_glossary_patterns() == []


@pytest.mark.unit
def test_load_glossary_patterns_non_list_returns_empty(mocker, tmp_path):
    bad = tmp_path / "entity_glossary.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    mocker.patch("src.core.text.entities._glossary_path", return_value=bad)
    assert entities._load_glossary_patterns() == []


@pytest.mark.unit
def test_load_glossary_patterns_reads_valid_list(mocker, tmp_path):
    good = tmp_path / "entity_glossary.json"
    good.write_text('[{"label": "MISC", "pattern": "Muad\'Dib"}]', encoding="utf-8")
    mocker.patch("src.core.text.entities._glossary_path", return_value=good)
    assert entities._load_glossary_patterns() == [
        {"label": "MISC", "pattern": "Muad'Dib"}
    ]


@pytest.mark.unit
@_MODEL
def test_glossary_pattern_adds_entities_the_model_would_miss(mocker, tmp_path):
    # Made-up term the statistical model has no way of recognizing on its own.
    glossary = tmp_path / "entity_glossary.json"
    glossary.write_text(
        '[{"label": "PROD", "pattern": "Zyloquark9000"}]', encoding="utf-8"
    )
    mocker.patch("src.core.text.entities._glossary_path", return_value=glossary)
    entities._NLP_CACHE.clear()  # force a fresh load so the glossary is read
    try:
        out = entities.entities("O produto Zyloquark9000 foi lançado ontem.")
        assert ("Zyloquark9000", "PROD") in out
    finally:
        entities._NLP_CACHE.clear()  # don't leak the ruler into other tests
