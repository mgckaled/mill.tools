"""Worker for the Recipes module: run a recipe in a background daemon thread.

No Flet dependency — drives everything through the EventBus (module_id="recipes")
so it is unit-testable with a fake bus. The runner (execute_recipe) is the same
core the CLI uses; this worker only adapts its ``emit(type, payload)`` shape to
the bus and adds human-readable log lines for the step boundaries.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src.gui.modules._pipeline_runner import _LogScope, make_emitter
from src.gui.modules.recipes import pipeline_log

if TYPE_CHECKING:
    from src.core.recipes.types import Recipe
    from src.gui.events import EventBus

_MODULE_ID = "recipes"


def run_recipe_pipeline(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    recipe: Recipe,
    initial_inputs: list,
    initial_kind: str,
    install_log_handler: bool = True,
) -> bool:
    """Run ``recipe`` over ``initial_inputs`` via execute_recipe.

    The runner emits recipe_start / step_start / step_done / task_done|error and
    the adapters emit progress_update; this worker forwards them all to the bus
    and emits extra ``log`` lines so the panel reads as a step-by-step narrative.
    The core functions' own ``logging.info`` is surfaced via ``_LogScope``.

    Returns True when the recipe produced at least one final output.
    """
    from src.core.recipes.runner import execute_recipe

    emit_bus = make_emitter(bus, _MODULE_ID, "recipes")

    def _emit(type: str, payload: dict) -> None:
        emit_bus(type, payload=payload)  # raw event — the view/bar consume it
        if type == "recipe_start":
            emit_bus(
                "log",
                payload={
                    "message": pipeline_log.fmt_recipe_start(
                        payload["name"], payload["total_steps"]
                    )
                },
            )
        elif type == "step_start":
            emit_bus(
                "log",
                payload={
                    "message": pipeline_log.fmt_step_start(
                        payload["idx"], payload["total"], payload["label"]
                    )
                },
            )
        elif type == "step_done":
            for out in payload.get("outputs", []):
                emit_bus(
                    "log",
                    payload={"message": pipeline_log.fmt_step_output(Path(out).name)},
                )

    scope: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope:
        try:
            final = execute_recipe(
                recipe,
                initial_inputs,
                initial_kind=initial_kind,
                emit=_emit,
                cancel_is_set=cancel_event.is_set,
            )
            return bool(final)
        except Exception as exc:  # safety net — execute_recipe already emits task_error
            logging.getLogger(__name__).warning("[!] Recipe error: %s", exc)
            emit_bus("task_error", payload={"message": str(exc)})
            return False


def start_recipe_pipeline(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    recipe: Recipe,
    initial_inputs: list,
    initial_kind: str,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_recipe_pipeline in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_recipe_pipeline(
            bus,
            cancel_event,
            recipe=recipe,
            initial_inputs=initial_inputs,
            initial_kind=initial_kind,
        )
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
