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
@_MODEL
def test_handles_text_longer_than_a_single_spacy_chunk():
    # A full book/long transcription can exceed spaCy's own 1,000,000-char
    # nlp.max_length guard (E088) if passed in one call. Repeating a short
    # paragraph past _MAX_CHARS proves entities() chunks instead of crashing,
    # and still finds + dedupes an entity that repeats across chunks.
    paragraph = "Maria Silva trabalha na Petrobras. "
    text = paragraph * 4000
    assert len(text) > entities._MAX_CHARS

    out = entities.entities(text)
    names = {t for t, _ in out}
    assert "Maria Silva" in names
    assert "Petrobras" in names


@pytest.mark.unit
def test_is_available_false_without_spacy(mocker):
    # Simulate spaCy importable but the model missing.
    mocker.patch("spacy.util.is_package", return_value=False)
    assert entities.is_available("pt") is False


@pytest.mark.unit
def test_gate_raises_when_model_missing(mocker):
    # entities() skips the is_available() check on a _NLP_CACHE hit — force a
    # miss so this test exercises the gate regardless of test execution order
    # (an earlier @_MODEL test may have already cached "pt").
    entities._NLP_CACHE.pop("pt", None)
    mocker.patch("src.core.text.entities.is_available", return_value=False)
    with pytest.raises(RuntimeError, match="spacy download"):
        entities.entities("Maria foi ao Rio.")


@pytest.mark.unit
def test_cache_hit_skips_is_available_recheck(mocker):
    # Once a language's pipeline is cached, entities() must not re-run the
    # spacy.util.is_package() metadata scan on every call.
    fake_doc = mocker.Mock(ents=[])
    fake_nlp = mocker.MagicMock()
    fake_nlp.pipe_names = ["tok2vec", "ner"]
    fake_nlp.pipe.return_value = [fake_doc]

    entities._NLP_CACHE["pt"] = fake_nlp
    spy = mocker.patch("src.core.text.entities.is_available")
    try:
        assert entities.entities("qualquer texto") == []
        spy.assert_not_called()
    finally:
        entities._NLP_CACHE.pop("pt", None)


@pytest.mark.unit
def test_model_for_falls_back_to_pt():
    assert entities._model_for("xx") == "pt_core_news_sm"
    assert entities._model_for("en") == "en_core_web_sm"


@pytest.mark.unit
def test_model_for_logs_on_unrecognized_language(caplog):
    import logging

    caplog.set_level(logging.DEBUG, logger=None)
    entities._model_for("xx")
    assert any("xx" in r.message for r in caplog.records)


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
