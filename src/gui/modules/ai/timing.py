"""Pure helpers for the AI answer-time estimate.

A RAG answer is a single blocking ``invoke()`` whose output length is unknown
ahead of time, so a true countdown is impossible. Instead we show a live
elapsed clock plus a *typical* time learned from a rolling per-model average of
recent answers. These helpers are pure (no Flet, no I/O) and unit-tested; the
view persists the samples and runs the live ticker.
"""

from __future__ import annotations

# Rolling window of recent answer durations kept per model. Small so the
# estimate tracks the current machine/model state instead of stale history.
KEEP = 5


def record_duration(
    times: list[float], duration: float, *, keep: int = KEEP
) -> list[float]:
    """Append ``duration`` (s) and keep only the last ``keep`` positive samples."""
    base = [t for t in times if t > 0]
    if duration > 0:
        base.append(float(duration))
    return base[-keep:]


def average(times: list[float]) -> float | None:
    """Mean of the positive samples, or None when there is no history."""
    vals = [t for t in times if t > 0]
    return sum(vals) / len(vals) if vals else None


def format_clock(seconds: float) -> str:
    """Format a duration as ``M:SS`` (e.g. 74 → '1:14')."""
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def format_typical(avg: float | None, model: str) -> str | None:
    """Render '~28s (típico do <model>)', or None when there is no history."""
    if not avg or avg <= 0:
        return None
    return f"~{int(round(avg))}s (típico do {model})"


def compose_status(elapsed: float, typical: str | None) -> str:
    """Compose the live status line shown while the answer is being generated."""
    line = f"Gerando resposta… {format_clock(elapsed)}"
    if typical:
        line += f" · {typical}"
    return line
