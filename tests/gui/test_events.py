"""Unit tests for src/gui/events.py — EventBus + the Observatório Logs hook."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.events import EventBus


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    import src.core.observatory.logs as logs_mod

    monkeypatch.setattr(logs_mod, "_store_path", lambda: tmp_path / "ml_logs.json")
    return tmp_path


@pytest.mark.unit
def test_emit_always_broadcasts_via_pubsub():
    page = MagicMock()
    bus = EventBus(page)
    bus.emit("progress_start", "download", module_id="audio")
    page.pubsub.send_all.assert_called_once()


@pytest.mark.unit
def test_task_error_is_logged_to_the_failure_log(isolate):
    from src.core.observatory.logs import load_logs

    page = MagicMock()
    bus = EventBus(page)
    bus.emit(
        "task_error", "convert", {"message": "ffmpeg not found"}, module_id="audio"
    )

    entries = load_logs(isolate / "ml_logs.json")
    assert len(entries) == 1
    assert entries[0].module == "audio"
    assert entries[0].stage == "convert"
    assert entries[0].message == "ffmpeg not found"


@pytest.mark.parametrize(
    "message",
    ["Cancelado.", "Cancelado pelo usuário.", "Indexação cancelada."],
)
@pytest.mark.unit
def test_user_cancellations_are_not_logged(isolate, message):
    from src.core.observatory.logs import load_logs

    page = MagicMock()
    bus = EventBus(page)
    bus.emit("task_error", "convert", {"message": message}, module_id="image")

    assert load_logs(isolate / "ml_logs.json") == []


@pytest.mark.unit
def test_non_error_events_are_not_logged(isolate):
    from src.core.observatory.logs import load_logs

    page = MagicMock()
    bus = EventBus(page)
    bus.emit("task_done", "convert", {"output_path": "/x"}, module_id="audio")
    bus.emit("progress_start", "convert", module_id="audio")
    bus.emit("log", "system", {"message": "erro simulado"}, module_id="audio")

    assert load_logs(isolate / "ml_logs.json") == []


@pytest.mark.unit
def test_a_broken_log_write_does_not_break_emit(isolate, mocker):
    mocker.patch(
        "src.core.observatory.logs.log_error", side_effect=RuntimeError("boom")
    )
    page = MagicMock()
    bus = EventBus(page)
    bus.emit("task_error", "convert", {"message": "real failure"}, module_id="audio")
    page.pubsub.send_all.assert_called_once()  # broadcast still happened
