"""Unit tests for src/core/rag/feedback.py — the retrieval-feedback log.

Reuses ``observatory/_jsonlog`` (append/cap/load), so these focus on the
feedback entry's own fields, the cap, and corruption tolerance.
"""

from __future__ import annotations

import json

import pytest


def _log(path, **overrides):
    from src.core.rag.feedback import log_feedback

    payload = dict(
        query="o que eu disse sobre X?",
        search_query="o que eu disse sobre X no vídeo Y?",
        sources=["C:/out/a.txt", "C:/out/b.txt"],
        cited_sources=["C:/out/a.txt"],
        pool_max_score=0.81,
        low_confidence=False,
        verdict="up",
        model="gemma3-4b-custom",
        embed_space_id="nomic-embed-custom:768:scheme-x",
        path=path,
    )
    payload.update(overrides)
    log_feedback(**payload)


@pytest.mark.unit
def test_log_and_load_round_trip(tmp_path):
    from src.core.rag.feedback import load_feedback

    path = tmp_path / "retrieval_feedback.json"
    _log(path, now=1000.0)
    entries = load_feedback(path)

    assert len(entries) == 1
    e = entries[0]
    assert e.query == "o que eu disse sobre X?"
    assert e.search_query == "o que eu disse sobre X no vídeo Y?"
    assert e.sources == ("C:/out/a.txt", "C:/out/b.txt")
    assert e.cited_sources == ("C:/out/a.txt",)  # cited subset recorded (Fase 1.4)
    assert e.pool_max_score == pytest.approx(0.81)
    assert e.low_confidence is False
    assert e.verdict == "up"
    assert e.model == "gemma3-4b-custom"
    assert e.embed_space_id == "nomic-embed-custom:768:scheme-x"
    assert e.timestamp == 1000.0


@pytest.mark.unit
def test_verdict_constants():
    from src.core.rag.feedback import VERDICT_DOWN, VERDICT_UP

    assert (VERDICT_UP, VERDICT_DOWN) == ("up", "down")


@pytest.mark.unit
def test_cap_keeps_last_entries(tmp_path, monkeypatch):
    import src.core.rag.feedback as feedback

    monkeypatch.setattr(feedback, "_MAX_ENTRIES", 3)
    path = tmp_path / "retrieval_feedback.json"
    for i in range(5):
        _log(path, query=f"q{i}", now=float(i))

    entries = feedback.load_feedback(path)
    assert [e.query for e in entries] == ["q2", "q3", "q4"]  # oldest dropped


@pytest.mark.unit
def test_load_absent_and_corrupt_are_empty(tmp_path):
    from src.core.rag.feedback import load_feedback

    path = tmp_path / "retrieval_feedback.json"
    assert load_feedback(path) == []  # absent

    path.write_text("not json at all", encoding="utf-8")
    assert load_feedback(path) == []  # corrupt → empty, never raises


@pytest.mark.unit
def test_load_skips_malformed_entry(tmp_path):
    from src.core.rag.feedback import load_feedback

    path = tmp_path / "retrieval_feedback.json"
    path.write_text(
        json.dumps(
            [
                {
                    "query": "ok",
                    "search_query": "ok",
                    "sources": [],
                    "pool_max_score": 0.5,
                    "low_confidence": True,
                    "verdict": "down",
                    "model": "m",
                    "embed_space_id": "s",
                    "timestamp": 1.0,
                },
                {"missing": "fields"},
            ]
        ),
        encoding="utf-8",
    )
    entries = load_feedback(path)
    assert len(entries) == 1
    assert entries[0].verdict == "down"


@pytest.mark.unit
def test_load_legacy_entry_without_cited_sources_defaults_empty(tmp_path):
    """A feedback log written before the cited/consulted split has no
    ``cited_sources`` key — it must load as an empty tuple, never raise."""
    from src.core.rag.feedback import load_feedback

    path = tmp_path / "retrieval_feedback.json"
    path.write_text(
        json.dumps(
            [
                {
                    "query": "q",
                    "search_query": "q",
                    "sources": ["a.txt"],
                    "pool_max_score": 0.7,
                    "low_confidence": False,
                    "verdict": "up",
                    "model": "m",
                    "embed_space_id": "s",
                    "timestamp": 1.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    entries = load_feedback(path)
    assert len(entries) == 1
    assert entries[0].sources == ("a.txt",)
    assert entries[0].cited_sources == ()


@pytest.mark.unit
def test_recent_is_newest_first(tmp_path):
    from src.core.rag.feedback import load_feedback, recent

    path = tmp_path / "retrieval_feedback.json"
    for i in range(3):
        _log(path, query=f"q{i}", now=float(i))
    newest = recent(load_feedback(path), limit=2)
    assert [e.query for e in newest] == ["q2", "q1"]
