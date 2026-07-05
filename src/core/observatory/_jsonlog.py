"""Shared skeleton for the Observatório's append-only JSON logs.

``activity.py``, ``logs.py`` and ``model_timing.py`` were ~90% identical:
load tolerant-per-entry (skip and warn on a malformed row, never abort the
whole file) + append + cap + ``recent()``. This module extracts that
skeleton; each caller supplies its own dataclass (via ``parse``/``to_dict``)
and its own cap strategy (via ``keep`` — a flat ``entries[-cap:]`` for
``activity``/``logs``, a per-``(domain, model)`` bucket cut for
``model_timing``, so a chatty domain cannot evict a quieter one's history).

The on-disk shape (a single JSON array, pretty-printed) is unchanged from
before this refactor — only the write itself is now atomic (temp file +
``os.replace`` via :mod:`src.core.io_atomic`), so a crash or a concurrent
reader never observes a half-written log.

**Accepted gap — no inter-process lock.** ``append_capped`` is a
read-modify-write: the caller loads the current entries, then this module
writes the merged, capped list back. Atomicity only covers the write itself;
if the GUI and a CLI run concurrently and both log around the same instant,
one's read can miss the other's not-yet-written entry — a lost update, not a
corrupted file. Accepted rather than fixed: these logs are best-effort
observability (activity/failure feeds, latency samples), not a system of
record, and neither process is long-running enough for the race to matter in
practice. Real cross-process locking is out of scope (see
``docs/plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md``, "Fora do escopo").
"""

from __future__ import annotations

import json
import logging
from typing import Callable, TypeVar

from pathlib import Path

from src.core.io_atomic import atomic_write_text

logger = logging.getLogger(__name__)

T = TypeVar("T")


def load_entries(
    path: Path,
    parse: Callable[[dict], T],
    *,
    label: str,
) -> list[T]:
    """Load entries in append order (oldest first). ``[]`` on absence or
    corruption; an individual malformed entry is skipped (logged) rather
    than aborting the whole load.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read %s log %s: %s", label, path, exc)
        return []

    entries: list[T] = []
    for raw in data:
        try:
            entries.append(parse(raw))
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed %s entry: %r", label, raw)
    return entries


def append_capped(
    path: Path,
    entries: list[T],
    new_entry: T,
    to_dict: Callable[[T], dict],
    *,
    keep: Callable[[list[T]], list[T]],
    label: str,
) -> None:
    """Append ``new_entry`` and rewrite the log capped by ``keep``.

    ``entries`` is the log state already loaded by the caller (via
    :func:`load_entries`) — this function does not re-read the file, so
    callers that already paid for a load do not pay twice.
    """
    capped = keep([*entries, new_entry])
    try:
        payload = json.dumps([to_dict(e) for e in capped], ensure_ascii=False, indent=2)
        atomic_write_text(path, payload)
    except OSError as exc:
        logger.debug("[d] Could not write %s log: %s", label, exc)


def recent(entries: list[T], *, limit: int) -> list[T]:
    """The most recent ``limit`` entries, newest first."""
    return list(reversed(entries))[:limit]
