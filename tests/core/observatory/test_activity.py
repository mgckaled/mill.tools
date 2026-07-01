"""Unit tests for src/core/observatory/activity.py — activity log round-trip."""

from __future__ import annotations

import pytest

from src.core.observatory.activity import load_activity, log_activity, recent


@pytest.fixture
def activity_path(tmp_path):
    return tmp_path / ".mill-tools" / "ml_activity.json"


@pytest.mark.unit
def test_load_missing_returns_empty(activity_path):
    assert load_activity(activity_path) == []


@pytest.mark.unit
def test_log_and_load_round_trip(activity_path):
    log_activity("data", "outliers_detected", "12 linhas atípicas", path=activity_path)
    log_activity("library", "image_dedup", "3 grupos", path=activity_path)

    entries = load_activity(activity_path)
    assert [e.module for e in entries] == ["data", "library"]
    assert entries[0].event == "outliers_detected"
    assert entries[1].detail == "3 grupos"


@pytest.mark.unit
def test_log_activity_uses_injected_clock(activity_path):
    log_activity("rag", "answered", "resposta gerada", path=activity_path, now=42.0)
    assert load_activity(activity_path)[0].timestamp == 42.0


@pytest.mark.unit
def test_log_caps_at_max_entries(activity_path, monkeypatch):
    import src.core.observatory.activity as mod

    monkeypatch.setattr(mod, "_MAX_ENTRIES", 3)
    for i in range(5):
        log_activity("rag", "e", str(i), path=activity_path, now=float(i))

    entries = load_activity(activity_path)
    assert len(entries) == 3
    assert [e.detail for e in entries] == ["2", "3", "4"]  # oldest fell off the front


@pytest.mark.unit
def test_load_malformed_json_returns_empty(activity_path, caplog):
    activity_path.parent.mkdir(parents=True, exist_ok=True)
    activity_path.write_text("not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert load_activity(activity_path) == []


@pytest.mark.unit
def test_load_skips_malformed_entries(activity_path, caplog):
    import json

    activity_path.parent.mkdir(parents=True, exist_ok=True)
    activity_path.write_text(
        json.dumps(
            [
                {"module": "rag", "event": "e", "detail": "ok", "timestamp": 1.0},
                {"module": "rag"},  # missing required keys
            ]
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        entries = load_activity(activity_path)
    assert len(entries) == 1
    assert "Skipping malformed" in caplog.text


@pytest.mark.unit
def test_recent_returns_newest_first_and_respects_limit(activity_path):
    for i in range(5):
        log_activity("rag", "e", str(i), path=activity_path, now=float(i))
    entries = load_activity(activity_path)

    top2 = recent(entries, limit=2)
    assert [e.detail for e in top2] == ["4", "3"]
