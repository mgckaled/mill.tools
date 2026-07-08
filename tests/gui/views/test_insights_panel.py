"""Unit tests for src/gui/views/insights_panel.py::_compute — pure I/O + engine
glue, no Flet dependency, so it's tested directly like profile_section's
_classify_path (mock the engines at their source module, per the codebase's
usual lazy-import patching convention)."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_compute_feeds_all_three_engines_the_same_cleaned_text(tmp_path, mocker):
    """PLANO_INSIGHTS_QUALIDADE.md, Fase 5.2: one cleaning call, three engines
    — page markers/front matter must be gone before keywords/summarize/
    entities/detect_lang ever see the text."""
    import src.core.text.entities as ner
    import src.core.text.keywords as keywords
    import src.core.text.summarize as summarize
    from src.core.text.clean import page_marker
    from src.gui.views.insights_panel import _compute

    path = tmp_path / "doc.txt"
    path.write_text(
        f"Claude's Constitution\n\n{page_marker(1)}\n\nReal content sentence here.",
        encoding="utf-8",
    )

    keywords_mock = mocker.patch.object(keywords, "keyphrases", return_value=[])
    mocker.patch.object(keywords, "is_available", return_value=True)
    summary_mock = mocker.patch.object(summarize, "extractive_summary", return_value=[])
    mocker.patch.object(summarize, "is_available", return_value=True)
    entities_mock = mocker.patch.object(ner, "entities", return_value=[])
    mocker.patch.object(ner, "availability", return_value=None)

    _compute(str(path))

    seen_texts = {
        keywords_mock.call_args.args[0],
        summary_mock.call_args.args[0],
        entities_mock.call_args.args[0],
    }
    assert len(seen_texts) == 1  # same cleaned string fed to all three
    cleaned = seen_texts.pop()
    assert "Página" not in cleaned
    assert "Claude's Constitution" not in cleaned
    assert "Real content sentence here." in cleaned


@pytest.mark.unit
def test_compute_detect_lang_runs_on_cleaned_text(tmp_path, mocker):
    import src.core.text.entities as ner
    import src.core.text.keywords as keywords
    import src.core.text.lang as lang_mod
    import src.core.text.summarize as summarize
    from src.gui.views.insights_panel import _compute

    path = tmp_path / "doc.txt"
    path.write_text(
        "January 2024\n\nConteúdo real em português aqui.", encoding="utf-8"
    )

    mocker.patch.object(keywords, "is_available", return_value=False)
    mocker.patch.object(summarize, "is_available", return_value=False)
    mocker.patch.object(ner, "availability", return_value="algum hint")
    lang_spy = mocker.patch.object(lang_mod, "detect_lang", return_value="pt")

    _compute(str(path))

    lang_spy.assert_called_once()
    (cleaned_arg,) = lang_spy.call_args.args
    assert "January 2024" not in cleaned_arg


@pytest.mark.unit
def test_compute_sets_entities_hint_when_model_unavailable(tmp_path, mocker):
    import src.core.text.entities as ner
    import src.core.text.keywords as keywords
    import src.core.text.summarize as summarize
    from src.gui.views.insights_panel import _compute

    path = tmp_path / "doc.txt"
    path.write_text("Some real English sentence here.", encoding="utf-8")

    mocker.patch.object(keywords, "is_available", return_value=False)
    mocker.patch.object(summarize, "is_available", return_value=False)
    entities_mock = mocker.patch.object(ner, "entities")
    mocker.patch.object(
        ner,
        "availability",
        return_value="Modelo de inglês ausente: uv run python -m spacy download en_core_web_sm",
    )

    data = _compute(str(path))

    assert data.entities is None
    assert data.entities_hint == (
        "Modelo de inglês ausente: uv run python -m spacy download en_core_web_sm"
    )
    entities_mock.assert_not_called()


@pytest.mark.unit
def test_compute_runs_entities_when_available(tmp_path, mocker):
    import src.core.text.entities as ner
    import src.core.text.keywords as keywords
    import src.core.text.summarize as summarize
    from src.gui.views.insights_panel import _compute

    path = tmp_path / "doc.txt"
    path.write_text("Maria trabalha na Petrobras.", encoding="utf-8")

    mocker.patch.object(keywords, "is_available", return_value=False)
    mocker.patch.object(summarize, "is_available", return_value=False)
    mocker.patch.object(ner, "availability", return_value=None)
    entities_mock = mocker.patch.object(
        ner, "entities", return_value=[("Maria", "PER")]
    )

    data = _compute(str(path))

    assert data.entities == [("Maria", "PER")]
    assert data.entities_hint is None
    entities_mock.assert_called_once()
