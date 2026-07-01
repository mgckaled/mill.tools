"""Append-only cross-module ML activity log — the Observatório's raw data.

Every module that runs an ML operation (RAG, Biblioteca, Transcrição, Dados,
Receitas) writes one ``ActivityEntry`` here at its natural completion point —
the orchestration layer's job (worker/CLI), same convention as
``core/recipes/history.py``'s ``RunRecord``: the pure operations themselves
never persist anything. Persisted to ``~/.mill-tools/ml_activity.json``,
capped at the last ``_MAX_ENTRIES``.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Keep the log bounded so the file never grows without limit (same idea as
# core.recipes.history's _MAX_RUNS).
_MAX_ENTRIES = 200


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    """One ML-touching event, logged by whichever module produced it."""

    module: str  # "rag" | "library" | "transcription" | "data" | "recipes"
    event: str  # short machine-readable event name, e.g. "outliers_detected"
    detail: str  # human-readable one-liner (Portuguese), shown as-is in the feed
    timestamp: float  # epoch seconds


def _store_path() -> Path:
    """Canonical on-disk location for the ML activity log."""
    return Path.home() / ".mill-tools" / "ml_activity.json"


def load_activity(path: Path | None = None) -> list[ActivityEntry]:
    """Load the activity log in append order (oldest first). ``[]`` on absence
    or corruption.

    Individual malformed entries are skipped (logged) rather than aborting the
    whole load — same convention as ``core.recipes.history.load_runs``.
    """
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read ML activity log %s: %s", path, exc)
        return []

    entries: list[ActivityEntry] = []
    for raw in data:
        try:
            entries.append(
                ActivityEntry(
                    module=raw["module"],
                    event=raw["event"],
                    detail=raw["detail"],
                    timestamp=float(raw["timestamp"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed ML activity entry: %r", raw)
    return entries


def log_activity(
    module: str,
    event: str,
    detail: str,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> None:
    """Append one entry to the log, capped at the last ``_MAX_ENTRIES``.

    ``now`` is injectable (epoch seconds) so callers get deterministic tests;
    defaults to the wall clock.
    """
    path = path or _store_path()
    entry = ActivityEntry(
        module=module,
        event=event,
        detail=detail,
        timestamp=now if now is not None else time.time(),
    )
    entries = load_activity(path)
    entries.append(entry)
    entries = entries[-_MAX_ENTRIES:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(e) for e in entries]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.debug("[d] Could not write ML activity log: %s", exc)


def recent(entries: list[ActivityEntry], *, limit: int = 15) -> list[ActivityEntry]:
    """The most recent ``limit`` entries, newest first (the feed's default view)."""
    return list(reversed(entries))[:limit]
