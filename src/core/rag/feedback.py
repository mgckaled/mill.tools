"""Append-only retrieval-feedback log (PLANO_RAG_EVAL, Fase 2).

Every 👍/👎 on a Conversa answer is recorded here — the raw dataset that a
future plan can use to recalibrate the out-of-scope threshold against real
usage or seed a reranker. This plan only *collects*; no automatic use of the
feedback (no threshold recalibration, no training) happens yet.

Owned by ``core/rag/`` — not ``core/observatory/`` (whose package stays
read-only): only the generic append/cap/load skeleton is reused from
``observatory/_jsonlog.py`` (the same one behind ``ml_activity.json``). Each
entry carries the ``embed_space_id`` it was produced under, so a later reindex
under a new model/scheme never makes old feedback silently incomparable — the
regular rule for every persisted RAG entry.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from src.core.observatory import _jsonlog

# Same magnitude as ml_activity.json's cap — generous for personal use without
# the file growing unbounded.
_MAX_ENTRIES = 200

_LABEL = "retrieval feedback"

# Machine-readable verdict values (the GUI maps 👍/👎 onto these).
VERDICT_UP = "up"
VERDICT_DOWN = "down"


@dataclass(frozen=True, slots=True)
class FeedbackEntry:
    """One 👍/👎 on a Conversa answer, with the retrieval context behind it."""

    query: str  # the original user question
    search_query: str  # what was actually retrieved (condensed; == query if not)
    sources: tuple[str, ...]  # the cited source document paths
    pool_max_score: float  # best dense cosine over the scope-respecting pool
    low_confidence: bool  # whether the out-of-scope warning fired
    verdict: str  # VERDICT_UP | VERDICT_DOWN
    model: str  # the answer model
    embed_space_id: str  # the index's embedding space at feedback time
    timestamp: float  # epoch seconds


def _store_path() -> Path:
    """Canonical on-disk location for the retrieval-feedback log."""
    return Path.home() / ".mill-tools" / "retrieval_feedback.json"


def _parse_entry(raw: dict) -> FeedbackEntry:
    return FeedbackEntry(
        query=raw["query"],
        search_query=raw["search_query"],
        sources=tuple(raw.get("sources", [])),
        pool_max_score=float(raw["pool_max_score"]),
        low_confidence=bool(raw["low_confidence"]),
        verdict=raw["verdict"],
        model=raw["model"],
        embed_space_id=raw.get("embed_space_id", "?"),
        timestamp=float(raw["timestamp"]),
    )


def load_feedback(path: Path | None = None) -> list[FeedbackEntry]:
    """Load the feedback log in append order (oldest first). ``[]`` on absence
    or corruption; a malformed entry is skipped rather than aborting the load.
    """
    return _jsonlog.load_entries(path or _store_path(), _parse_entry, label=_LABEL)


def log_feedback(
    *,
    query: str,
    search_query: str,
    sources: Sequence[str],
    pool_max_score: float,
    low_confidence: bool,
    verdict: str,
    model: str,
    embed_space_id: str,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Append one feedback entry, capped at the last ``_MAX_ENTRIES``.

    ``now`` is injectable (epoch seconds) for deterministic tests; defaults to
    the wall clock.
    """
    path = path or _store_path()
    entry = FeedbackEntry(
        query=query,
        search_query=search_query,
        sources=tuple(sources),
        pool_max_score=float(pool_max_score),
        low_confidence=bool(low_confidence),
        verdict=verdict,
        model=model,
        embed_space_id=embed_space_id,
        timestamp=now if now is not None else time.time(),
    )
    entries = load_feedback(path)
    _jsonlog.append_capped(
        path,
        entries,
        entry,
        asdict,
        keep=lambda es: es[-_MAX_ENTRIES:],
        label=_LABEL,
    )


def recent(entries: list[FeedbackEntry], *, limit: int = 15) -> list[FeedbackEntry]:
    """The most recent ``limit`` entries, newest first."""
    return _jsonlog.recent(entries, limit=limit)
