"""Append-only cross-module failure log — the Observatório's "Logs" tab data.

Every ``task_error`` emitted by the GUI's ``EventBus`` (any module) is written
here at the broadcast point itself (``gui/events.py::EventBus.emit()``), not by
each worker — the pubsub broadcast is already page-wide, so a single hook
catches every module's failures without touching any ``worker.py``. User
cancellations are filtered out before they reach here (they are not failures).
Persisted to ``~/.mill-tools/ml_logs.json``, capped at the last
``_MAX_ENTRIES`` — same convention as ``activity.py``/``model_timing.py``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Explicit cap requested for this log — smaller than activity.py's 200 since
# failures are rarer and each entry is only useful for near-term debugging.
_MAX_ENTRIES = 100


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


def load_logs(path: Path | None = None) -> list[LogEntry]:
    """Load the log in append order (oldest first). ``[]`` on absence or
    corruption.

    Individual malformed entries are skipped (logged) rather than aborting the
    whole load — same convention as ``core.observatory.activity.load_activity``.
    """
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read ML failure log %s: %s", path, exc)
        return []

    entries: list[LogEntry] = []
    for raw in data:
        try:
            entries.append(
                LogEntry(
                    module=raw["module"],
                    stage=raw["stage"],
                    message=raw["message"],
                    timestamp=float(raw["timestamp"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed ML failure entry: %r", raw)
    return entries


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
    entries.append(entry)
    entries = entries[-_MAX_ENTRIES:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(e) for e in entries]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.debug("[d] Could not write ML failure log: %s", exc)


def recent(entries: list[LogEntry], *, limit: int = 50) -> list[LogEntry]:
    """The most recent ``limit`` entries, newest first (the feed's default view)."""
    return list(reversed(entries))[:limit]
