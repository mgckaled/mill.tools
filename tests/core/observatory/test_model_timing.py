"""Unit tests for src/core/observatory/model_timing.py — per-domain timing log."""

from __future__ import annotations

import pytest

from src.core.observatory.model_timing import (
    load_timings,
    record_timing,
    timings_by_domain,
)


@pytest.fixture
def timings_path(tmp_path):
    return tmp_path / ".mill-tools" / "model_timings.json"


@pytest.mark.unit
def test_load_missing_returns_empty(timings_path):
    assert load_timings(timings_path) == []


@pytest.mark.unit
def test_record_and_load_round_trip(timings_path):
    record_timing("gemini-2.5-flash", "llm", 4.2, path=timings_path)
    record_timing("moondream-custom", "vlm", 2.1, path=timings_path)

    entries = load_timings(timings_path)
    assert [(e.model, e.domain) for e in entries] == [
        ("gemini-2.5-flash", "llm"),
        ("moondream-custom", "vlm"),
    ]
    assert entries[0].elapsed == 4.2


@pytest.mark.unit
def test_record_timing_uses_injected_clock(timings_path):
    record_timing("nomic-embed-custom", "embed", 0.3, path=timings_path, now=42.0)
    assert load_timings(timings_path)[0].timestamp == 42.0


@pytest.mark.unit
@pytest.mark.parametrize("elapsed", [0.0, -1.0])
def test_record_timing_drops_non_positive_elapsed(timings_path, elapsed):
    record_timing("gemini-2.5-flash", "llm", elapsed, path=timings_path)
    assert load_timings(timings_path) == []


@pytest.mark.unit
def test_cap_is_per_domain_model_bucket_not_flat(timings_path, monkeypatch):
    """A chatty 'llm' domain must not evict 'vlm'/'embed' history."""
    import src.core.observatory.model_timing as mod

    monkeypatch.setattr(mod, "_MAX_PER_BUCKET", 3)

    record_timing("moondream-custom", "vlm", 1.0, path=timings_path, now=0.0)
    record_timing("nomic-embed-custom", "embed", 0.5, path=timings_path, now=1.0)
    for i in range(10):
        record_timing(
            "gemini-2.5-flash", "llm", 1.0, path=timings_path, now=float(2 + i)
        )

    entries = load_timings(timings_path)
    by_domain = {}
    for e in entries:
        by_domain.setdefault(e.domain, []).append(e)

    assert len(by_domain["vlm"]) == 1
    assert len(by_domain["embed"]) == 1
    assert len(by_domain["llm"]) == 3  # capped, but did not push the others out


@pytest.mark.unit
def test_cap_keeps_most_recent_within_a_bucket(timings_path, monkeypatch):
    import src.core.observatory.model_timing as mod

    monkeypatch.setattr(mod, "_MAX_PER_BUCKET", 3)
    for i in range(5):
        record_timing(
            "gemini-2.5-flash", "llm", float(i), path=timings_path, now=float(i)
        )

    entries = load_timings(timings_path)
    assert [e.elapsed for e in entries] == [2.0, 3.0, 4.0]  # oldest 2 fell off


@pytest.mark.unit
def test_load_malformed_json_returns_empty(timings_path, caplog):
    timings_path.parent.mkdir(parents=True, exist_ok=True)
    timings_path.write_text("not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert load_timings(timings_path) == []


@pytest.mark.unit
def test_load_skips_malformed_entries(timings_path, caplog):
    import json

    timings_path.parent.mkdir(parents=True, exist_ok=True)
    timings_path.write_text(
        json.dumps(
            [
                {"model": "m", "domain": "llm", "elapsed": 1.0, "timestamp": 1.0},
                {"model": "m"},  # missing required keys
            ]
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        entries = load_timings(timings_path)
    assert len(entries) == 1
    assert "Skipping malformed" in caplog.text


@pytest.mark.unit
def test_timings_by_domain_filters_and_groups(timings_path):
    record_timing("gemini-2.5-flash", "llm", 4.0, path=timings_path)
    record_timing("gemini-2.5-flash", "llm", 6.0, path=timings_path)
    record_timing("moondream-custom", "vlm", 2.0, path=timings_path)

    entries = load_timings(timings_path)
    llm_map = timings_by_domain(entries, "llm")
    vlm_map = timings_by_domain(entries, "vlm")

    assert llm_map == {"gemini-2.5-flash": [4.0, 6.0]}
    assert vlm_map == {"moondream-custom": [2.0]}
    assert timings_by_domain(entries, "embed") == {}
