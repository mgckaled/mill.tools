"""Tests for the saved-queries store (queries.json)."""

import pytest


@pytest.mark.unit
def test_round_trip_save_and_load(tmp_path):
    from src.core.data.store import SavedQuery, load_queries, save_query

    path = tmp_path / "queries.json"
    q = SavedQuery(name="resumo", sql="SELECT 1", question="quanto?", description="d")
    save_query(q, path)

    loaded = load_queries(path)
    assert loaded == [q]


@pytest.mark.unit
def test_save_replaces_by_name(tmp_path):
    from src.core.data.store import SavedQuery, load_queries, save_query

    path = tmp_path / "queries.json"
    save_query(SavedQuery(name="x", sql="SELECT 1"), path)
    save_query(SavedQuery(name="x", sql="SELECT 2"), path)

    loaded = load_queries(path)
    assert len(loaded) == 1
    assert loaded[0].sql == "SELECT 2"


@pytest.mark.unit
def test_delete_query(tmp_path):
    from src.core.data.store import SavedQuery, delete_query, load_queries, save_query

    path = tmp_path / "queries.json"
    save_query(SavedQuery(name="x", sql="SELECT 1"), path)
    assert delete_query("x", path) is True
    assert delete_query("x", path) is False
    assert load_queries(path) == []


@pytest.mark.unit
def test_load_missing_file_returns_empty(tmp_path):
    from src.core.data.store import load_queries

    assert load_queries(tmp_path / "nope.json") == []


@pytest.mark.unit
def test_malformed_entries_are_skipped(tmp_path):
    from src.core.data.store import load_queries

    path = tmp_path / "queries.json"
    path.write_text(
        '[{"name": "ok", "sql": "SELECT 1"}, {"name": "bad"}]', encoding="utf-8"
    )
    loaded = load_queries(path)
    assert [q.name for q in loaded] == ["ok"]


@pytest.mark.unit
def test_invalid_json_returns_empty(tmp_path):
    from src.core.data.store import load_queries

    path = tmp_path / "queries.json"
    path.write_text("{ not json", encoding="utf-8")
    assert load_queries(path) == []
