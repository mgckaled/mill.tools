"""Unit tests for src/core/rag/analytics.py — index health + model timings."""

from __future__ import annotations

import pytest

from src.core.rag.analytics import (
    index_health,
    model_timings,
    model_timings_result,
    top_docs_result,
)
from src.core.rag.stats import DocStat, IndexStats


def _doc(source, n_chunks, *, kind="document", mtime=0.0, chars=100):
    return DocStat(
        source_path=source,
        kind=kind,
        n_chunks=n_chunks,
        mtime=mtime,
        char_total=chars,
    )


def _stats(per_doc, *, updated_at=100.0):
    return IndexStats(
        n_docs=len(per_doc),
        n_chunks=sum(d.n_chunks for d in per_doc),
        dim=768,
        embed_model="nomic-embed-custom",
        disk_bytes=1234,
        updated_at=updated_at,
        per_doc=tuple(per_doc),
    )


# ---------------------------------------------------------------------------
# model_timings
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_model_timings_empty_map():
    assert model_timings({}) == ()


@pytest.mark.unit
def test_model_timings_stats_and_fastest_first():
    timings = model_timings({"slow": [10.0, 20.0, 30.0], "fast": [1.0, 3.0]})

    assert [t.model for t in timings] == ["fast", "slow"]  # lowest mean first
    fast, slow = timings
    assert fast.count == 2
    assert fast.mean == 2.0
    assert fast.median == 2.0
    assert fast.p90 == pytest.approx(2.8)
    assert slow.mean == 20.0
    assert slow.median == 20.0
    assert slow.p90 == pytest.approx(28.0)


@pytest.mark.unit
def test_model_timings_drops_non_positive_and_empty_models():
    timings = model_timings({"m": [0.0, -5.0, 4.0], "empty": [0.0, -1.0]})
    assert len(timings) == 1
    assert timings[0].model == "m"
    assert timings[0].count == 1
    assert timings[0].mean == 4.0


@pytest.mark.unit
def test_model_timings_single_sample_p90_is_itself():
    timings = model_timings({"m": [5.0]})
    assert timings[0].count == 1
    assert timings[0].p90 == 5.0
    assert timings[0].median == 5.0


# ---------------------------------------------------------------------------
# index_health
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_index_health_top_docs_limited():
    per_doc = [_doc(f"d{i}.txt", n_chunks=10 - i) for i in range(5)]
    health = index_health(_stats(per_doc), top_n=3)
    assert health.n_docs == 5
    assert [d.source_path for d in health.top_docs] == ["d0.txt", "d1.txt", "d2.txt"]


@pytest.mark.unit
def test_index_health_flags_stale_when_current_mtime_newer_than_recorded():
    # Both were embedded at mtime=100.0; only "changed.txt" was touched again
    # afterwards (its current on-disk mtime moved on to 200.0).
    per_doc = [
        _doc("fresh.txt", 3, mtime=100.0),
        _doc("changed.txt", 2, mtime=100.0),
    ]
    current = {"fresh.txt": 100.0, "changed.txt": 200.0}
    health = index_health(
        _stats(per_doc, updated_at=500.0),
        current_mtime=lambda p: current[p],
    )
    assert [d.source_path for d in health.stale_docs] == ["changed.txt"]


@pytest.mark.unit
def test_index_health_treats_unreadable_source_as_not_stale():
    # A deleted/moved source can't be stat'd — that's the indexer's
    # reconciliation job, not staleness detection.
    per_doc = [_doc("deleted.txt", 1, mtime=100.0)]
    health = index_health(
        _stats(per_doc, updated_at=500.0), current_mtime=lambda _p: None
    )
    assert health.stale_docs == ()


@pytest.mark.unit
def test_index_health_never_built_flags_nothing_stale():
    per_doc = [_doc("a.txt", 3, mtime=999.0)]
    health = index_health(_stats(per_doc, updated_at=None))
    assert health.stale_docs == ()


@pytest.mark.unit
def test_index_health_default_current_mtime_reads_real_file(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("hello", encoding="utf-8")
    recorded_mtime = path.stat().st_mtime - 1000  # recorded well before "now"
    per_doc = [_doc(str(path), 1, mtime=recorded_mtime)]

    health = index_health(_stats(per_doc, updated_at=recorded_mtime + 500))
    assert [d.source_path for d in health.stale_docs] == [str(path)]


# ---------------------------------------------------------------------------
# QueryResult builders
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_top_docs_result_uses_basename():
    per_doc = [_doc("/abs/path/to/notes.txt", 7)]
    result = top_docs_result(index_health(_stats(per_doc)))
    assert result.columns == ["documento", "chunks"]
    assert result.rows == [("notes.txt", 7)]


@pytest.mark.unit
def test_model_timings_result_shape():
    timings = model_timings({"fast": [1.0, 3.0]})
    result = model_timings_result(timings)
    assert result.columns == ["modelo", "respostas", "média_s", "p90_s"]
    assert result.rows[0][0] == "fast"
    assert result.rows[0][1] == 2  # count
    assert result.elapsed == 0.0
