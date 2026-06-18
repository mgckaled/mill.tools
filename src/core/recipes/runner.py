"""Sequential recipe executor: pipes each step's output into the next.

Mirrors the event anatomy of ``run_queue_pipeline`` (``progress_start`` /
``task_done`` / ``task_error`` / cancel checks) but iterates *heterogeneous*
steps, chaining ``outputs[N] → inputs[N+1]``. Adapters write to their module's
canonical output dir (no shared out_dir), so PR6's Library classifies each
artifact by kind.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.recipes.registry import STEP_REGISTRY
from src.core.recipes.types import Recipe, StepContext
from src.core.recipes.validate import validate_recipe

logger = logging.getLogger(__name__)


def _fail(emit, emit_terminal: bool, message: str) -> None:
    """Report a terminal failure: task_error when standalone, log line in a batch."""
    if emit_terminal:
        emit("task_error", {"message": message})
    else:
        emit("log", {"message": f"[!] {message}"})


def execute_recipe(
    recipe: Recipe,
    initial_inputs: list,
    *,
    initial_kind: str,
    emit,
    cancel_is_set,
    emit_terminal: bool = True,
) -> list[Path]:
    """Run every step in order, feeding outputs forward. Returns final outputs.

    A history of every step's outputs is kept in ``outputs_by_op`` so multi-input
    steps (e.g. ``video.subtitle``) can reach the original video + the .srt the
    linear ``current`` already discarded.

    Args:
        recipe: The recipe to run.
        initial_inputs: ``[url]`` or ``[Path, ...]`` to feed the first step.
        initial_kind: Logical kind of ``initial_inputs`` (url/audio/video/pdf/...).
        emit: ``emit(type, payload)`` — forwards to an EventBus/CLIEventBus.
        cancel_is_set: ``() -> bool`` — checked between steps.
        emit_terminal: When True (standalone run) emit progress_start/task_done/
            task_error. When False (one entry of a batch) skip those — the batch
            wrapper owns the lifecycle — and report failures as a log line so a
            per-item failure does not look like the whole batch aborting.

    Returns:
        The final step's output paths, or ``[]`` on invalid/failed/cancelled runs.
    """
    # Validate before spending any CPU. Indexing STEP_REGISTRY blindly would raise
    # KeyError on a stale user recipe naming a renamed/removed op; validate_recipe
    # turns that (and kind mismatches) into a clean "recipe invalid" message.
    errors = validate_recipe(recipe, initial_kind)
    if errors:
        _fail(emit, emit_terminal, "Receita inválida: " + "; ".join(errors))
        return []

    total = len(recipe.steps)
    emit("recipe_start", {"name": recipe.name, "total_steps": total})
    if emit_terminal:
        emit("progress_start", {})

    current: list = list(initial_inputs)
    outputs_by_op: dict[str, list[Path]] = {}

    for idx, step in enumerate(recipe.steps, 1):
        if cancel_is_set():
            _fail(emit, emit_terminal, "Cancelado pelo usuário.")
            return []

        spec = STEP_REGISTRY[step.op]  # safe: validate_recipe ran above
        emit(
            "step_start",
            {"op": step.op, "label": spec.label, "idx": idx, "total": total},
        )
        ctx = StepContext(
            emit=emit,
            cancel_is_set=cancel_is_set,
            initial_inputs=list(initial_inputs),
            outputs_by_op=outputs_by_op,
        )
        try:
            current = spec.adapter(current, step.params, ctx)
        except Exception as exc:  # noqa: BLE001 — any core failure aborts the chain
            logger.warning("[!] Step '%s' failed: %s", step.op, exc)
            emit("step_error", {"op": step.op, "idx": idx, "message": str(exc)})
            _fail(emit, emit_terminal, f"Falha no passo '{spec.label}': {exc}")
            return []

        outputs_by_op[step.op] = [Path(p) for p in current]
        emit(
            "step_done",
            {
                "op": step.op,
                "idx": idx,
                "total": total,
                "outputs": [str(p) for p in current],
            },
        )

    final = [Path(p) for p in current]
    if emit_terminal:
        emit("task_done", {"output_paths": [str(p) for p in final]})
    return final


def execute_recipe_batch(
    recipe: Recipe,
    runs: list,
    *,
    emit,
    cancel_is_set,
) -> list[Path]:
    """Run ``recipe`` once per entry in ``runs``, aggregating the final outputs.

    Mirrors ``run_queue_pipeline``: emits a single ``progress_start`` up front,
    a ``queue_progress`` per entry, and one terminal ``task_done`` at the end.
    Each per-entry run is ``emit_terminal=False`` so an individual failure logs a
    line and is counted, without aborting the whole batch.

    Args:
        recipe: The recipe to apply to every entry.
        runs: List of ``(initial_inputs, initial_kind, label)`` tuples.
        emit: ``emit(type, payload)`` forwarder.
        cancel_is_set: ``() -> bool`` — checked between entries.

    Returns:
        Every final output path across all successful entries.
    """
    total = len(runs)
    emit("progress_start", {})
    all_outputs: list[Path] = []
    failed = 0

    for idx, (inputs, kind, label) in enumerate(runs, 1):
        if cancel_is_set():
            emit("task_error", {"message": "Cancelado pelo usuário."})
            return all_outputs
        emit(
            "queue_progress",
            {"current_item": idx, "total_items": total, "item_name": label},
        )
        outputs = execute_recipe(
            recipe,
            inputs,
            initial_kind=kind,
            emit=emit,
            cancel_is_set=cancel_is_set,
            emit_terminal=False,
        )
        if outputs:
            all_outputs.extend(outputs)
        else:
            failed += 1

    emit(
        "task_done",
        {"output_paths": [str(p) for p in all_outputs], "failed_count": failed},
    )
    return all_outputs
