"""Unit tests for run_recipe_pipeline — forwards runner events to a fake bus.

execute_recipe is mocked (the runner core is tested separately); here we only
verify the worker forwards events under module_id="recipes" and adds the
human-readable log lines for the step boundaries.
"""

import threading

import pytest


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, type, stage="", payload=None, module_id=""):
        self.events.append((type, payload or {}, module_id))


def _recipe():
    from src.core.recipes.types import Recipe, RecipeStep

    return Recipe("R", [RecipeStep("audio.download")])


def _fake_execute(recipe, initial_inputs, *, initial_kind, emit, cancel_is_set):
    emit("recipe_start", {"name": "R", "total_steps": 2})
    emit("step_start", {"op": "a", "label": "Baixar", "idx": 1, "total": 2})
    emit("step_done", {"op": "a", "idx": 1, "total": 2, "outputs": ["x.mp3"]})
    emit("task_done", {"output_paths": ["y.md"]})
    from pathlib import Path

    return [Path("y.md")]


@pytest.mark.unit
def test_run_recipe_pipeline_forwards_events_and_logs(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", side_effect=_fake_execute)
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        initial_inputs=["https://x"],
        initial_kind="url",
        install_log_handler=False,
    )

    assert ok is True
    types = [t for t, _, _ in bus.events]
    assert "recipe_start" in types
    assert "step_start" in types
    assert "task_done" in types
    assert all(mid == "recipes" for _, _, mid in bus.events)

    logs = [p["message"] for t, p, _ in bus.events if t == "log"]
    assert any("Receita: R" in m for m in logs)
    assert any("Passo 1/2: Baixar" in m for m in logs)
    assert any("x.mp3" in m for m in logs)


@pytest.mark.unit
def test_run_recipe_pipeline_returns_false_when_no_output(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", return_value=[])
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        initial_inputs=["https://x"],
        initial_kind="url",
        install_log_handler=False,
    )

    assert ok is False


@pytest.mark.unit
def test_run_recipe_pipeline_handles_unexpected_exception(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch(
        "src.core.recipes.runner.execute_recipe", side_effect=RuntimeError("boom")
    )
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        initial_inputs=["https://x"],
        initial_kind="url",
        install_log_handler=False,
    )

    assert ok is False
    assert any(t == "task_error" for t, _, _ in bus.events)
