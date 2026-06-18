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


def execute_recipe(
    recipe: Recipe,
    initial_inputs: list,
    *,
    initial_kind: str,
    emit,
    cancel_is_set,
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

    Returns:
        The final step's output paths, or ``[]`` on invalid/failed/cancelled runs.
    """
    # Validate before spending any CPU. Indexing STEP_REGISTRY blindly would raise
    # KeyError on a stale user recipe naming a renamed/removed op; validate_recipe
    # turns that (and kind mismatches) into a clean "recipe invalid" message.
    errors = validate_recipe(recipe, initial_kind)
    if errors:
        emit("task_error", {"message": "Receita inválida: " + "; ".join(errors)})
        return []

    total = len(recipe.steps)
    emit("recipe_start", {"name": recipe.name, "total_steps": total})
    emit("progress_start", {})

    current: list = list(initial_inputs)
    outputs_by_op: dict[str, list[Path]] = {}

    for idx, step in enumerate(recipe.steps, 1):
        if cancel_is_set():
            emit("task_error", {"message": "Cancelado pelo usuário."})
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
            emit("task_error", {"message": f"Falha no passo '{spec.label}': {exc}"})
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
    emit("task_done", {"output_paths": [str(p) for p in final]})
    return final
