"""Unit tests for the Recipes module pipeline_log — fmt_* + resolve_status."""

import pytest


@pytest.mark.unit
def test_fmt_builders():
    from src.gui.modules.recipes import pipeline_log as pl

    assert "Receita: R (3 passo(s))" in pl.fmt_recipe_start("R", 3)
    assert "Passo 2/4: Transcrever" in pl.fmt_step_start(2, 4, "Transcrever")
    assert "x.mp3" in pl.fmt_step_output("x.mp3")
    assert "2 arquivo" in pl.fmt_recipe_done(2)


@pytest.mark.unit
@pytest.mark.parametrize(
    "etype,payload,expected",
    [
        ("recipe_start", {}, "Iniciando…"),
        (
            "step_start",
            {"idx": 2, "total": 4, "label": "Transcrever"},
            "Passo 2/4 — Transcrever",
        ),
        ("task_done", {}, "Concluído."),
        ("task_error", {}, "Erro."),
    ],
)
def test_resolve_status(etype, payload, expected):
    from src.gui.events import PipelineEvent
    from src.gui.modules.recipes import pipeline_log as pl

    event = PipelineEvent(etype, "recipes", payload, "recipes")
    assert pl.resolve_status(event) == expected


@pytest.mark.unit
def test_resolve_status_unknown_returns_none():
    from src.gui.events import PipelineEvent
    from src.gui.modules.recipes import pipeline_log as pl

    event = PipelineEvent("progress_update", "recipes", {}, "recipes")
    assert pl.resolve_status(event) is None
