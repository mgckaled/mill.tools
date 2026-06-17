"""Unit tests for src/gui/modules/ai/pipeline_log.py — builders and resolver."""

from __future__ import annotations

import pytest


def _event(type: str, payload: dict | None = None):
    from src.gui.events import PipelineEvent

    return PipelineEvent(type=type, stage="ai", payload=payload or {}, module_id="ai")


@pytest.mark.unit
def test_fmt_index_builders():
    from src.gui.modules.ai import pipeline_log

    assert "3" in pipeline_log.fmt_index_start(3)
    assert "2/5" in pipeline_log.fmt_index_progress(2, 5)
    done = pipeline_log.fmt_index_done(4, 40, 10)
    assert "4" in done and "40" in done and "+10" in done


@pytest.mark.unit
def test_fmt_index_done_negative_added_has_no_plus():
    from src.gui.modules.ai import pipeline_log

    assert "+" not in pipeline_log.fmt_index_done(2, 5, -3)


@pytest.mark.unit
def test_fmt_answer_builders():
    from src.gui.modules.ai import pipeline_log

    assert "qwen7b-custom" in pipeline_log.fmt_answer_start("qwen7b-custom")
    assert "2" in pipeline_log.fmt_answer_done(2)


@pytest.mark.unit
@pytest.mark.parametrize(
    "type,payload,expected_substr",
    [
        ("progress_start", {}, "Iniciando"),
        ("index_start", {}, "Indexando"),
        ("progress_update", {"current": 2, "total": 6}, "2/6"),
        ("answer_start", {}, "Consultando"),
        ("index_done", {}, "atualizado"),
        ("answer_done", {}, "gerada"),
        ("task_done", {}, "Concluído"),
        ("task_error", {}, "Erro"),
    ],
)
def test_resolve_status_known_events(type, payload, expected_substr):
    from src.gui.modules.ai.pipeline_log import resolve_status

    label = resolve_status(_event(type, payload))
    assert label is not None and expected_substr in label


@pytest.mark.unit
def test_resolve_status_progress_update_without_total_is_none():
    from src.gui.modules.ai.pipeline_log import resolve_status

    assert resolve_status(_event("progress_update", {"current": 1})) is None


@pytest.mark.unit
def test_resolve_status_unknown_event_is_none():
    from src.gui.modules.ai.pipeline_log import resolve_status

    assert resolve_status(_event("log", {"message": "x"})) is None
