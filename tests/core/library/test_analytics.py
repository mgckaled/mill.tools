"""Unit tests for src/core/library/analytics.py — pure archive aggregations."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.core.library.analytics import (
    growth_by_period,
    largest,
    size_by_kind,
    summary,
)
from src.core.library.types import LibraryItem


def _item(name, kind, *, size=1024, category="processed", mtime=0.0):
    p = Path(name)
    return LibraryItem(
        path=p,
        kind=kind,
        category=category,
        size_bytes=size,
        modified=mtime,
        stem=p.stem,
        suffix=p.suffix.lower(),
    )


def _epoch(year, month, day=15):
    """Local epoch seconds for a date — keeps month labels deterministic."""
    return time.mktime((year, month, day, 12, 0, 0, 0, 0, -1))


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_summary_empty():
    s = summary([])
    assert s.total_count == 0
    assert s.total_bytes == 0
    assert s.count_by_kind == {}
    assert s.bytes_by_kind == {}
    assert s.oldest is None
    assert s.newest is None


@pytest.mark.unit
def test_summary_counts_sizes_and_span():
    items = [
        _item("a.mp3", "audio", size=100, mtime=10.0),
        _item("b.mp3", "audio", size=300, mtime=30.0),
        _item("c.mp4", "video", size=1000, category="source", mtime=20.0),
    ]
    s = summary(items)

    assert s.total_count == 3
    assert s.total_bytes == 1400
    assert s.count_by_kind == {"audio": 2, "video": 1}
    # bytes_by_kind ordered by total bytes descending: video (1000) > audio (400)
    assert list(s.bytes_by_kind.items()) == [("video", 1000), ("audio", 400)]
    assert s.count_by_category == {"processed": 2, "source": 1}
    assert s.oldest == 10.0
    assert s.newest == 30.0


# ---------------------------------------------------------------------------
# largest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_largest_orders_by_size_desc_and_limits():
    items = [
        _item("small.txt", "transcription", size=10),
        _item("big.mp4", "video", size=9000),
        _item("mid.mp3", "audio", size=500),
    ]
    top2 = largest(items, 2)
    assert [it.path.name for it in top2] == ["big.mp4", "mid.mp3"]


@pytest.mark.unit
def test_largest_empty():
    assert largest([], 5) == []


# ---------------------------------------------------------------------------
# size_by_kind
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_size_by_kind_result_shape_and_order():
    items = [
        _item("a.mp3", "audio", size=100),
        _item("b.mp3", "audio", size=100),
        _item("c.mp4", "video", size=1000),
    ]
    result = size_by_kind(items)
    assert result.columns == ["tipo", "arquivos", "bytes"]
    assert result.elapsed == 0.0
    # video first (more bytes), then audio (2 files, 200 bytes)
    assert result.rows == [("video", 1, 1000), ("audio", 2, 200)]
    assert result.n_rows == 2


# ---------------------------------------------------------------------------
# growth_by_period
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_growth_by_month_is_chronological():
    items = [
        _item("a.mp3", "audio", size=100, mtime=_epoch(2026, 3)),
        _item("b.mp3", "audio", size=200, mtime=_epoch(2026, 1)),
        _item("c.mp3", "audio", size=50, mtime=_epoch(2026, 1)),
    ]
    result = growth_by_period(items, "month")
    assert result.columns == ["período", "arquivos", "bytes"]
    assert result.rows == [
        ("2026-01", 2, 250),
        ("2026-03", 1, 100),
    ]


@pytest.mark.unit
def test_growth_by_day_label_format():
    items = [_item("a.mp3", "audio", mtime=_epoch(2026, 6, 27))]
    result = growth_by_period(items, "day")
    assert result.rows[0][0] == "2026-06-27"


@pytest.mark.unit
def test_growth_empty():
    result = growth_by_period([], "month")
    assert result.rows == []
    assert result.n_rows == 0
