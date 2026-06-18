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


def _clean_intermediates(paths: set[str], emit_bus) -> None:
    """Delete intermediate files (produced but not final). Never the user input."""
    removed = 0
    for raw in paths:
        try:
            fp = Path(raw)
            if fp.exists():
                fp.unlink()
                removed += 1
        except OSError as exc:
            logging.getLogger(__name__).debug("[d] could not remove %s: %s", raw, exc)
    if removed:
        emit_bus(
            "log", payload={"message": f"[i] {removed} intermediário(s) removido(s)."}
        )


def run_recipe_pipeline(
    bus: EventBus,
    cancel_event: threading.Event,
    *,
    recipe: Recipe,
    runs: list,
    clean_intermediates: bool = False,
    install_log_handler: bool = True,
) -> bool:
    """Run ``recipe`` over one or many inputs via the recipe runner.

    ``runs`` is a list of ``(initial_inputs, initial_kind, label)``: a single
    entry runs once (execute_recipe); multiple entries run as a batch
    (execute_recipe_batch — one independent run per entry, with queue_progress).

    The worker forwards every runner event to the bus and adds ``log`` lines for
    the step boundaries; the core's own ``logging.info`` is surfaced via
    ``_LogScope``. When ``clean_intermediates`` is set, files produced by
    non-final steps are deleted at the end (final outputs and user inputs kept).

    Returns True when at least one final output was produced.
    """
    from src.core.recipes.runner import execute_recipe, execute_recipe_batch

    emit_bus = make_emitter(bus, _MODULE_ID, "recipes")
    produced: set[str] = set()
    finals: set[str] = set()

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
                produced.add(out)
                emit_bus(
                    "log",
                    payload={"message": pipeline_log.fmt_step_output(Path(out).name)},
                )
        elif type == "task_done":
            finals.update(payload.get("output_paths", []))

    scope: contextlib.AbstractContextManager = (
        _LogScope(bus, _MODULE_ID) if install_log_handler else contextlib.nullcontext()
    )
    with scope:
        try:
            if len(runs) == 1:
                inputs, kind, _label = runs[0]
                final = execute_recipe(
                    recipe,
                    inputs,
                    initial_kind=kind,
                    emit=_emit,
                    cancel_is_set=cancel_event.is_set,
                )
            else:
                final = execute_recipe_batch(
                    recipe, runs, emit=_emit, cancel_is_set=cancel_event.is_set
                )
            if clean_intermediates:
                _clean_intermediates(produced - finals, emit_bus)
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
    runs: list,
    clean_intermediates: bool = False,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_recipe_pipeline in a daemon thread; call on_finish() when done."""

    def _run() -> None:
        run_recipe_pipeline(
            bus,
            cancel_event,
            recipe=recipe,
            runs=runs,
            clean_intermediates=clean_intermediates,
        )
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
