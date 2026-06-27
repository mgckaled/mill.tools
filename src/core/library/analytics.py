"""Pure aggregations over the Library catalog — the dashboard's number-crunching.

Receives the ``LibraryItem`` list that ``scan_library`` already produces and
answers a few actionable questions: how much of each kind do I produce, what is
filling the disk, how has the archive grown over time. Everything here is pure
Python (``collections.Counter`` + simple sums) so the panel shows numbers
*without* the optional ``[analysis]``/``[data-plot]`` extras; only the chart
(Plano 1) needs them. Chartable tables are returned as ``QueryResult`` so the
same contract that feeds the Data module's charts feeds these panels — no
DataFrame ever crosses into the GUI.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from src.core.data.types import QueryResult
from src.core.library.types import LibraryItem


@dataclass(frozen=True, slots=True)
class LibrarySummary:
    """Headline metrics for the whole archive."""

    total_count: int
    total_bytes: int
    count_by_kind: dict[str, int]  # kind -> file count, descending by count
    bytes_by_kind: dict[str, int]  # kind -> total bytes, descending by bytes
    count_by_category: dict[str, int]  # category -> file count
    oldest: float | None  # min mtime, None when the archive is empty
    newest: float | None  # max mtime, None when the archive is empty


def summary(items: list[LibraryItem]) -> LibrarySummary:
    """Compute headline counts/sizes and the archive's time span. Pure."""
    if not items:
        return LibrarySummary(0, 0, {}, {}, {}, None, None)

    count_by_kind = Counter(it.kind for it in items)
    bytes_by_kind: Counter[str] = Counter()
    count_by_category = Counter(it.category for it in items)
    total_bytes = 0
    for it in items:
        bytes_by_kind[it.kind] += it.size_bytes
        total_bytes += it.size_bytes

    mtimes = [it.modified for it in items]
    return LibrarySummary(
        total_count=len(items),
        total_bytes=total_bytes,
        count_by_kind=dict(count_by_kind.most_common()),
        bytes_by_kind=dict(bytes_by_kind.most_common()),
        count_by_category=dict(count_by_category.most_common()),
        oldest=min(mtimes),
        newest=max(mtimes),
    )


def largest(items: list[LibraryItem], n: int = 10) -> list[LibraryItem]:
    """Return the ``n`` biggest files (disk-cleanup question), largest first."""
    return sorted(items, key=lambda it: it.size_bytes, reverse=True)[:n]


def size_by_kind(items: list[LibraryItem]) -> QueryResult:
    """Total bytes per kind as a chartable table ('what fills the disk?', bars)."""
    bytes_by_kind: Counter[str] = Counter()
    files_by_kind: Counter[str] = Counter()
    for it in items:
        bytes_by_kind[it.kind] += it.size_bytes
        files_by_kind[it.kind] += 1

    rows = [
        (kind, files_by_kind[kind], total)
        for kind, total in bytes_by_kind.most_common()
    ]
    return QueryResult(
        columns=["tipo", "arquivos", "bytes"],
        rows=rows,
        elapsed=0.0,
        n_rows=len(rows),
    )


def growth_by_period(items: list[LibraryItem], period: str = "month") -> QueryResult:
    """Files and bytes produced per calendar period (growth question, line chart).

    ``period`` is ``"month"`` (``YYYY-MM``) or ``"day"`` (``YYYY-MM-DD``). Rows are
    ordered chronologically by the period label (ISO format sorts naturally).
    """
    fmt = "%Y-%m" if period != "day" else "%Y-%m-%d"
    counts: Counter[str] = Counter()
    sizes: dict[str, int] = defaultdict(int)
    for it in items:
        label = time.strftime(fmt, time.localtime(it.modified))
        counts[label] += 1
        sizes[label] += it.size_bytes

    rows = [(label, counts[label], sizes[label]) for label in sorted(counts)]
    return QueryResult(
        columns=["período", "arquivos", "bytes"],
        rows=rows,
        elapsed=0.0,
        n_rows=len(rows),
    )
