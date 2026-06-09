"""Tests for CLIEventBus event dispatch."""

import pytest
from io import StringIO
from unittest.mock import patch
from src.cli.bus import CLIEventBus


def _make_bus() -> CLIEventBus:
    return CLIEventBus()


# ── progress_start / progress_update / task_done ─────────────────────────────

@pytest.mark.unit
def test_progress_start_creates_bar():
    bus = _make_bus()
    bus.emit("progress_start")
    assert bus._bar is not None
    bus._bar.close()


@pytest.mark.unit
def test_progress_update_advances_bar():
    bus = _make_bus()
    bus.emit("progress_start")
    bus.emit("progress_update", payload={"current": 0.5})
    assert bus._bar.n == 50
    bus._bar.close()


@pytest.mark.unit
def test_task_done_closes_bar(capsys):
    bus = _make_bus()
    bus.emit("progress_start")
    bus.emit("task_done", payload={"output_paths": ["/tmp/out.mp3"]})
    assert bus._bar is None
    captured = capsys.readouterr()
    assert "/tmp/out.mp3" in captured.out


@pytest.mark.unit
def test_task_error_closes_bar_and_logs(capsys, caplog):
    import logging
    bus = _make_bus()
    bus.emit("progress_start")
    with caplog.at_level(logging.ERROR, logger="src.cli.bus"):
        bus.emit("task_error", payload={"message": "Something went wrong"})
    assert bus._bar is None
    assert "Something went wrong" in caplog.text


# ── queue_progress ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_queue_progress_writes_label(capsys):
    bus = _make_bus()
    bus.emit("queue_progress", payload={
        "current_item": 2,
        "total_items": 5,
        "item_name": "video.mp4",
    })
    out = capsys.readouterr().out
    assert "2/5" in out
    assert "video.mp4" in out


# ── log ───────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_log_non_mutable_writes_line(capsys):
    bus = _make_bus()
    bus.emit("log", payload={"message": "Hello test", "mutable": False})
    assert "Hello test" in capsys.readouterr().out


@pytest.mark.unit
def test_log_mutable_overwrites_line(capsys):
    bus = _make_bus()
    bus.emit("log", payload={"message": "  42%", "mutable": True})
    out = capsys.readouterr().out
    assert "42%" in out
    # Mutable lines start with \r (carriage return)
    assert "\r" in out


@pytest.mark.unit
def test_mutable_followed_by_non_mutable_adds_newline(capsys):
    bus = _make_bus()
    bus.emit("log", payload={"message": "progress", "mutable": True})
    bus.emit("log", payload={"message": "done", "mutable": False})
    out = capsys.readouterr().out
    assert "\n" in out


# ── op_start / op_done ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_audio_op_start_writes_operation(capsys):
    bus = _make_bus()
    bus.emit("audio_op_start", payload={
        "operation": "convert",
        "item_name": "audio.wav",
        "item_idx": 1,
        "total": 3,
    })
    out = capsys.readouterr().out
    assert "convert" in out
    assert "audio.wav" in out


@pytest.mark.unit
def test_audio_op_done_writes_elapsed(capsys):
    bus = _make_bus()
    bus.emit("audio_op_done", payload={
        "output_path": "/out/audio.mp3",
        "elapsed": "2.4s",
        "item_idx": 1,
        "total": 1,
        "src_size_bytes": 1024 * 100,
        "out_size_bytes": 1024 * 90,
    })
    out = capsys.readouterr().out
    assert "2.4s" in out


# ── ANSI stripping ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_log_strips_ansi_codes(capsys):
    bus = _make_bus()
    bus.emit("log", payload={"message": "\x1b[32m  42.0%\x1b[0m"})
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "42.0%" in out
