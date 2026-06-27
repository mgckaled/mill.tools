"""Append-only execution history for recipes — the panel's (and Plano 7's) raw data.

The recipe ``runner`` stays pure: it never persists anything. Instead the
orchestration layer (GUI worker / CLI) records one ``RunRecord`` per run when it
sees the terminal event, append-only to ``~/.mill-tools/recipe_runs.json``
(capped at the last ``_MAX_RUNS``, mirroring the ``data_assessments.json``
convention). ``aggregate`` then answers the panel's questions: which recipes are
reliable, which are slow, and what breaks most.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from src.core.data.types import QueryResult

logger = logging.getLogger(__name__)

# Keep the history bounded so the file never grows without limit (same idea as
# the assessment cache). Old runs fall off the front.
_MAX_RUNS = 500

# Run outcomes.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RunRecord:
    """One recipe execution, recorded at its terminal event."""

    recipe_name: str
    started_at: float  # epoch seconds
    finished_at: float  # epoch seconds
    duration: float  # finished_at - started_at, in seconds
    status: str  # STATUS_OK | STATUS_ERROR | STATUS_CANCELLED
    n_steps: int
    failed_op: str | None = None  # the "module.op" that failed (errors only)
    batch_size: int | None = None  # number of inputs in a batch run, else None


@dataclass(frozen=True, slots=True)
class RecipeAgg:
    """Aggregated reliability/speed metrics for one recipe name."""

    recipe_name: str
    n_runs: int
    n_ok: int
    success_rate: float  # n_ok / n_runs, in [0, 1]
    avg_duration: float  # mean duration over all runs, seconds
    most_failing_op: str | None  # most common failed_op among error runs


def _store_path() -> Path:
    """Canonical on-disk location for the recipe run history."""
    return Path.home() / ".mill-tools" / "recipe_runs.json"


def load_runs(path: Path | None = None) -> list[RunRecord]:
    """Load the run history. Returns [] when missing, unreadable or malformed.

    Individual malformed entries are skipped (logged) rather than aborting the
    whole load, so one bad hand-edit never hides the rest of the history.
    """
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read recipe history %s: %s", path, exc)
        return []

    runs: list[RunRecord] = []
    for entry in data:
        try:
            runs.append(
                RunRecord(
                    recipe_name=entry["recipe_name"],
                    started_at=float(entry["started_at"]),
                    finished_at=float(entry["finished_at"]),
                    duration=float(entry["duration"]),
                    status=entry["status"],
                    n_steps=int(entry["n_steps"]),
                    failed_op=entry.get("failed_op"),
                    batch_size=entry.get("batch_size"),
                )
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("[!] Skipping malformed run entry: %r", entry)
    return runs


def append_run(record: RunRecord, *, path: Path | None = None) -> None:
    """Append one run to the history, capped at the last ``_MAX_RUNS``."""
    path = path or _store_path()
    runs = load_runs(path)
    runs.append(record)
    runs = runs[-_MAX_RUNS:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in runs]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logger.debug("[d] Could not write recipe history: %s", exc)


def aggregate(runs: list[RunRecord]) -> tuple[RecipeAgg, ...]:
    """Group runs by recipe and compute reliability/speed, busiest first.

    Recipes are ordered by run count (descending), ties broken by name.
    """
    by_recipe: dict[str, list[RunRecord]] = defaultdict(list)
    for run in runs:
        by_recipe[run.recipe_name].append(run)

    aggs: list[RecipeAgg] = []
    for name, group in by_recipe.items():
        n_runs = len(group)
        n_ok = sum(1 for r in group if r.status == STATUS_OK)
        total_duration = sum(r.duration for r in group)
        failed_ops = Counter(
            r.failed_op for r in group if r.status == STATUS_ERROR and r.failed_op
        )
        top_fail = failed_ops.most_common(1)
        aggs.append(
            RecipeAgg(
                recipe_name=name,
                n_runs=n_runs,
                n_ok=n_ok,
                success_rate=n_ok / n_runs,
                avg_duration=total_duration / n_runs,
                most_failing_op=top_fail[0][0] if top_fail else None,
            )
        )
    aggs.sort(key=lambda a: (-a.n_runs, a.recipe_name))
    return tuple(aggs)


def aggregate_result(aggs: tuple[RecipeAgg, ...]) -> QueryResult:
    """Per-recipe metrics as a chartable table (bars: receita × duração média)."""
    rows = [
        (
            a.recipe_name,
            a.n_runs,
            round(a.success_rate * 100, 1),
            round(a.avg_duration, 1),
        )
        for a in aggs
    ]
    return QueryResult(
        columns=["receita", "execuções", "sucesso_%", "duração_média_s"],
        rows=rows,
        elapsed=0.0,
        n_rows=len(rows),
    )
