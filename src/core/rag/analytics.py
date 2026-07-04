"""Pure analytics over the persisted RAG index and the per-model answer history.

Two actionable questions, no Ollama and no network:

* **Which documents dominate my searches?** ``index_health`` ranks the index by
  chunks and flags sources changed since the last build (stale → reindex).
* **Which model answers fastest on this machine?** ``model_timings`` turns the
  ``ai_answer_times`` map (``{model: [durations]}``) into count/mean/median/p90
  per model, fastest first — the most personally useful metric.

Reuses the already-computed ``IndexStats``/``DocStat`` from ``stats.py`` instead
of re-reading the store, and the percentile math is the stdlib ``statistics``
module so the panel needs no extra. Chartable tables come back as ``QueryResult``.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.core.data.types import QueryResult
from src.core.rag.stats import DocStat, IndexStats


@dataclass(frozen=True, slots=True)
class IndexHealth:
    """Health snapshot of the persisted index."""

    n_docs: int
    n_chunks: int
    top_docs: tuple[DocStat, ...]  # heaviest by n_chunks (already sorted)
    stale_docs: tuple[DocStat, ...]  # source mtime newer than the index build


@dataclass(frozen=True, slots=True)
class ModelTiming:
    """Answer-time stats for one model, in seconds."""

    model: str
    count: int
    mean: float
    median: float
    p90: float


def _current_mtime(source_path: str) -> float | None:
    """Read a source file's current on-disk mtime; ``None`` if it cannot be
    stat'd (deleted/moved). A missing file is not "stale" in the sense this
    function cares about — content-changed-since-index — reconciling a
    removed source is the indexer's job (``build_index``), not this check's.
    """
    try:
        return Path(source_path).stat().st_mtime
    except OSError:
        return None


def index_health(
    stats: IndexStats,
    *,
    top_n: int = 10,
    current_mtime: Callable[[str], float | None] = _current_mtime,
) -> IndexHealth:
    """Rank documents by weight and flag stale sources.

    A document is *stale* when its source's **current** on-disk mtime is newer
    than the mtime recorded at index time (``DocStat.mtime``) — the file
    changed after it was last embedded, so it needs reindexing. Comparing
    against the index's ``updated_at`` (the old approach) never fired: that
    timestamp is the ``vectors.npz`` write time, which by construction always
    comes *after* every chunk's recorded mtime was captured. When the index
    was never built (``updated_at is None``) nothing is flagged stale.

    ``current_mtime`` is injectable (defaults to a real ``Path.stat()``) so
    this stays unit-testable without touching the filesystem.
    """
    per_doc = stats.per_doc  # already ordered by n_chunks desc, then filename
    top_docs = per_doc[:top_n]

    stale: tuple[DocStat, ...] = ()
    if stats.updated_at is not None:
        stale = tuple(
            d
            for d in per_doc
            if (cur := current_mtime(d.source_path)) is not None and cur > d.mtime
        )
    return IndexHealth(
        n_docs=stats.n_docs,
        n_chunks=stats.n_chunks,
        top_docs=top_docs,
        stale_docs=stale,
    )


def _p90(values: list[float]) -> float:
    """90th percentile via stdlib quantiles; degrades for tiny samples.

    ``statistics.quantiles`` needs at least two points, so a single sample
    returns itself. ``method="inclusive"`` keeps the result within [min, max].
    """
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=10, method="inclusive")[-1]


def model_timings(times_map: dict[str, list[float]]) -> tuple[ModelTiming, ...]:
    """Aggregate per-model answer durations, fastest (lowest mean) first.

    Non-positive samples are dropped; a model with no positive samples is
    omitted entirely. Ties on the mean break on the model name for stability.
    """
    timings: list[ModelTiming] = []
    for model, raw in times_map.items():
        values = sorted(float(t) for t in raw if t and t > 0)
        if not values:
            continue
        timings.append(
            ModelTiming(
                model=model,
                count=len(values),
                mean=statistics.fmean(values),
                median=statistics.median(values),
                p90=_p90(values),
            )
        )
    timings.sort(key=lambda t: (t.mean, t.model))
    return tuple(timings)


def top_docs_result(health: IndexHealth) -> QueryResult:
    """Heaviest documents as a chartable table (bars: documento × chunks)."""
    rows = [(Path(d.source_path).name, d.n_chunks) for d in health.top_docs]
    return QueryResult(
        columns=["documento", "chunks"], rows=rows, elapsed=0.0, n_rows=len(rows)
    )


def model_timings_result(timings: tuple[ModelTiming, ...]) -> QueryResult:
    """Per-model timing as a chartable table (bars: modelo × média/p90)."""
    rows = [(t.model, t.count, round(t.mean, 1), round(t.p90, 1)) for t in timings]
    return QueryResult(
        columns=["modelo", "respostas", "média_s", "p90_s"],
        rows=rows,
        elapsed=0.0,
        n_rows=len(rows),
    )
