"""Append-only, per-(domain, model) latency log — the Observatório's timing data.

Every call to ``make_llm()`` (LLM/VLM) and to the embedder (embed) writes one
``TimingEntry`` here at its natural completion point, mirroring
``activity.py``'s convention. Persisted to ``~/.mill-tools/model_timings.json``,
capped at the last ``_MAX_PER_BUCKET`` entries *per (domain, model) pair* — not
a flat cut on the whole file, because "llm" is called far more often than
"vlm"/"embed" and a flat cut would silently evict their history.

Load/append mechanics are shared with ``activity.py``/``logs.py`` via
``_jsonlog.py``; the per-bucket cap strategy (``_trim_per_bucket``) is kept
here since it is specific to this module's shape.

The embedding hot path (``embedder.embed_texts``, called once per document
during indexing) sums the elapsed time of every sub-batch and records a
*single* entry per call instead of one per sub-batch — otherwise a large
corpus reindex would trigger dozens of full log rewrites per document. See
``embedder.py``.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.core.observatory import _jsonlog

# Same magnitude as core.recipes.history's _MAX_RUNS — generous enough to span
# months of personal use without the file growing unbounded.
_MAX_PER_BUCKET = 500

_LABEL = "model timing"


@dataclass(frozen=True, slots=True)
class TimingEntry:
    """One model call's latency, tagged by domain."""

    model: str
    domain: str  # "llm" | "vlm" | "embed"
    elapsed: float  # seconds
    timestamp: float  # epoch seconds


def _store_path() -> Path:
    """Canonical on-disk location for the model timing log."""
    return Path.home() / ".mill-tools" / "model_timings.json"


def _parse_entry(raw: dict) -> TimingEntry:
    return TimingEntry(
        model=raw["model"],
        domain=raw["domain"],
        elapsed=float(raw["elapsed"]),
        timestamp=float(raw["timestamp"]),
    )


def load_timings(path: Path | None = None) -> list[TimingEntry]:
    """Load the log in append order (oldest first). ``[]`` on absence or
    corruption.

    Individual malformed entries are skipped (logged) rather than aborting the
    whole load.
    """
    return _jsonlog.load_entries(path or _store_path(), _parse_entry, label=_LABEL)


def _trim_per_bucket(
    entries: list[TimingEntry], *, cap: int | None = None
) -> list[TimingEntry]:
    """Keep only the last ``cap`` entries per (domain, model), then re-sort by
    timestamp.

    A flat ``entries[-cap:]`` would let a chatty domain (e.g. "llm", called far
    more often than "vlm"/"embed") silently evict the other domains' history —
    so the cut is per bucket instead. ``cap`` defaults to ``_MAX_PER_BUCKET``
    read at call time (not bound as a parameter default) so tests can
    monkeypatch the module attribute.
    """
    if cap is None:
        cap = _MAX_PER_BUCKET
    buckets: dict[tuple[str, str], list[TimingEntry]] = {}
    for e in entries:
        buckets.setdefault((e.domain, e.model), []).append(e)
    trimmed = [e for group in buckets.values() for e in group[-cap:]]
    trimmed.sort(key=lambda e: e.timestamp)
    return trimmed


def record_timing(
    model: str,
    domain: str,
    elapsed: float,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Append one sample, capped at ``_MAX_PER_BUCKET`` per (domain, model).

    Non-positive ``elapsed`` is dropped silently — a zero/negative duration
    means the call errored or was never actually timed, not a valid sample.
    ``now`` is injectable (epoch seconds) so callers get deterministic tests;
    defaults to the wall clock.
    """
    if elapsed <= 0:
        return
    path = path or _store_path()
    entry = TimingEntry(
        model=model,
        domain=domain,
        elapsed=float(elapsed),
        timestamp=now if now is not None else time.time(),
    )
    entries = load_timings(path)
    _jsonlog.append_capped(
        path,
        entries,
        entry,
        asdict,
        keep=_trim_per_bucket,
        label=_LABEL,
    )


def timings_by_domain(
    entries: list[TimingEntry], domain: str
) -> dict[str, list[float]]:
    """Filter + group into the ``{model: [durations]}`` shape
    ``core.rag.analytics.model_timings`` expects."""
    out: dict[str, list[float]] = {}
    for e in entries:
        if e.domain == domain:
            out.setdefault(e.model, []).append(e.elapsed)
    return out
