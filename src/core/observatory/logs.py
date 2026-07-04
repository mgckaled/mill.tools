"""Append-only cross-module failure log — the Observatório's "Logs" tab data.

Every ``task_error`` emitted by the GUI's ``EventBus`` (any module) is written
here at the broadcast point itself (``gui/events.py::EventBus.emit()``), not by
each worker — the pubsub broadcast is already page-wide, so a single hook
catches every module's failures without touching any ``worker.py``. User
cancellations are filtered out before they reach here (they are not failures).
Persisted to ``~/.mill-tools/ml_logs.json``, capped at the last
``_MAX_ENTRIES`` — same convention as ``activity.py``/``model_timing.py``.

Load/append/cap mechanics are shared with those two modules via
``_jsonlog.py`` — this module only supplies the dataclass and the cap
strategy (flat: keep the last ``_MAX_ENTRIES``, regardless of ``module``).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.core.observatory import _jsonlog

# Explicit cap requested for this log — smaller than activity.py's 200 since
# failures are rarer and each entry is only useful for near-term debugging.
_MAX_ENTRIES = 100

_LABEL = "ML failure"


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One task_error, logged at the EventBus broadcast point."""

    module: str  # PipelineEvent.module_id, e.g. "transcription" | "audio" | "image"
    stage: str  # PipelineEvent.stage
    message: str  # payload["message"]
    timestamp: float  # epoch seconds


def _store_path() -> Path:
    """Canonical on-disk location for the failure log."""
    return Path.home() / ".mill-tools" / "ml_logs.json"


def _parse_entry(raw: dict) -> LogEntry:
    return LogEntry(
        module=raw["module"],
        stage=raw["stage"],
        message=raw["message"],
        timestamp=float(raw["timestamp"]),
    )


def load_logs(path: Path | None = None) -> list[LogEntry]:
    """Load the log in append order (oldest first). ``[]`` on absence or
    corruption.

    Individual malformed entries are skipped (logged) rather than aborting the
    whole load.
    """
    return _jsonlog.load_entries(path or _store_path(), _parse_entry, label=_LABEL)


def log_error(
    module: str,
    stage: str,
    message: str,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Append one entry to the log, capped at the last ``_MAX_ENTRIES``.

    ``now`` is injectable (epoch seconds) so callers get deterministic tests;
    defaults to the wall clock.
    """
    path = path or _store_path()
    entry = LogEntry(
        module=module,
        stage=stage,
        message=message,
        timestamp=now if now is not None else time.time(),
    )
    entries = load_logs(path)
    _jsonlog.append_capped(
        path,
        entries,
        entry,
        asdict,
        keep=lambda es: es[-_MAX_ENTRIES:],
        label=_LABEL,
    )


def recent(entries: list[LogEntry], *, limit: int = 50) -> list[LogEntry]:
    """The most recent ``limit`` entries, newest first (the feed's default view)."""
    return _jsonlog.recent(entries, limit=limit)
