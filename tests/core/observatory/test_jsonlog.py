"""Unit tests for src/core/observatory/_jsonlog.py — shared log skeleton."""

from __future__ import annotations

import pytest

from src.core.observatory import _jsonlog


def _parse(raw: dict) -> dict:
    return {"n": raw["n"]}


def _to_dict(entry: dict) -> dict:
    return entry


@pytest.mark.unit
def test_load_entries_missing_file_returns_empty(tmp_path):
    path = tmp_path / "log.json"
    assert _jsonlog.load_entries(path, _parse, label="test") == []


@pytest.mark.unit
def test_load_entries_malformed_json_returns_empty(tmp_path, caplog):
    path = tmp_path / "log.json"
    path.write_text("not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert _jsonlog.load_entries(path, _parse, label="test") == []
    assert "Could not read test log" in caplog.text


@pytest.mark.unit
def test_load_entries_skips_malformed_rows(tmp_path, caplog):
    import json

    path = tmp_path / "log.json"
    path.write_text(json.dumps([{"n": 1}, {"missing": True}]), encoding="utf-8")
    with caplog.at_level("WARNING"):
        entries = _jsonlog.load_entries(path, _parse, label="test")
    assert entries == [{"n": 1}]
    assert "Skipping malformed test entry" in caplog.text


@pytest.mark.unit
def test_append_capped_writes_and_round_trips(tmp_path):
    path = tmp_path / "log.json"
    _jsonlog.append_capped(
        path, [], {"n": 1}, _to_dict, keep=lambda es: es, label="test"
    )
    entries = _jsonlog.load_entries(path, _parse, label="test")
    assert entries == [{"n": 1}]


@pytest.mark.unit
def test_append_capped_applies_keep_strategy(tmp_path):
    path = tmp_path / "log.json"
    existing = [{"n": 1}, {"n": 2}]
    _jsonlog.append_capped(
        path,
        existing,
        {"n": 3},
        _to_dict,
        keep=lambda es: es[-2:],
        label="test",
    )
    entries = _jsonlog.load_entries(path, _parse, label="test")
    assert entries == [{"n": 2}, {"n": 3}]


@pytest.mark.unit
def test_append_capped_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "log.json"
    _jsonlog.append_capped(
        path, [], {"n": 1}, _to_dict, keep=lambda es: es, label="test"
    )
    assert path.exists()


@pytest.mark.unit
def test_append_capped_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "log.json"
    _jsonlog.append_capped(
        path, [], {"n": 1}, _to_dict, keep=lambda es: es, label="test"
    )
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.unit
def test_append_capped_swallows_oserror(tmp_path, mocker, caplog):
    path = tmp_path / "log.json"
    mocker.patch(
        "src.core.observatory._jsonlog.atomic_write_text",
        side_effect=OSError("disk full"),
    )
    with caplog.at_level("DEBUG"):
        _jsonlog.append_capped(
            path, [], {"n": 1}, _to_dict, keep=lambda es: es, label="test"
        )
    assert "Could not write test log" in caplog.text


@pytest.mark.unit
def test_recent_returns_newest_first_and_respects_limit():
    entries = [{"n": i} for i in range(5)]
    top2 = _jsonlog.recent(entries, limit=2)
    assert top2 == [{"n": 4}, {"n": 3}]
