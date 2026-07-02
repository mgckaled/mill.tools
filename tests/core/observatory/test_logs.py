"""Unit tests for src/core/observatory/logs.py — failure log round-trip."""

from __future__ import annotations

import pytest

from src.core.observatory.logs import load_logs, log_error, recent


@pytest.fixture
def logs_path(tmp_path):
    return tmp_path / ".mill-tools" / "ml_logs.json"


@pytest.mark.unit
def test_load_missing_returns_empty(logs_path):
    assert load_logs(logs_path) == []


@pytest.mark.unit
def test_log_and_load_round_trip(logs_path):
    log_error("audio", "convert", "ffmpeg not found", path=logs_path)
    log_error("image", "resize", "invalid dimensions", path=logs_path)

    entries = load_logs(logs_path)
    assert [e.module for e in entries] == ["audio", "image"]
    assert entries[0].stage == "convert"
    assert entries[1].message == "invalid dimensions"


@pytest.mark.unit
def test_log_error_uses_injected_clock(logs_path):
    log_error("data", "query", "boom", path=logs_path, now=42.0)
    assert load_logs(logs_path)[0].timestamp == 42.0


@pytest.mark.unit
def test_log_caps_at_max_entries(logs_path, monkeypatch):
    import src.core.observatory.logs as mod

    monkeypatch.setattr(mod, "_MAX_ENTRIES", 3)
    for i in range(5):
        log_error("rag", "answer", str(i), path=logs_path, now=float(i))

    entries = load_logs(logs_path)
    assert len(entries) == 3
    assert [e.message for e in entries] == ["2", "3", "4"]  # oldest fell off the front


@pytest.mark.unit
def test_load_malformed_json_returns_empty(logs_path, caplog):
    logs_path.parent.mkdir(parents=True, exist_ok=True)
    logs_path.write_text("not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert load_logs(logs_path) == []


@pytest.mark.unit
def test_load_skips_malformed_entries(logs_path, caplog):
    import json

    logs_path.parent.mkdir(parents=True, exist_ok=True)
    logs_path.write_text(
        json.dumps(
            [
                {
                    "module": "audio",
                    "stage": "convert",
                    "message": "ok",
                    "timestamp": 1.0,
                },
                {"module": "audio"},  # missing required keys
            ]
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        entries = load_logs(logs_path)
    assert len(entries) == 1
    assert "Skipping malformed" in caplog.text


@pytest.mark.unit
def test_recent_returns_newest_first_and_respects_limit(logs_path):
    for i in range(5):
        log_error("rag", "answer", str(i), path=logs_path, now=float(i))
    entries = load_logs(logs_path)

    top2 = recent(entries, limit=2)
    assert [e.message for e in top2] == ["4", "3"]
