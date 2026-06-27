"""Unit tests for run_recipe_pipeline — single run, batch, and clean-intermediates.

execute_recipe / execute_recipe_batch are mocked (the runner core is tested
separately); here we verify the worker forwards events under module_id="recipes",
adds step log lines, and cleans intermediate files when asked.
"""

import threading

import pytest


@pytest.fixture(autouse=True)
def _history(mocker):
    """Never touch the real run-history file; expose the spy to the tests."""
    return mocker.patch("src.core.recipes.history.append_run")


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, type, stage="", payload=None, module_id=""):
        self.events.append((type, payload or {}, module_id))


def _recipe():
    from src.core.recipes.types import Recipe, RecipeStep

    return Recipe("R", [RecipeStep("audio.download")])


def _fake_execute(
    recipe, initial_inputs, *, initial_kind, emit, cancel_is_set, emit_terminal=True
):
    emit("recipe_start", {"name": "R", "total_steps": 2})
    emit("step_start", {"op": "a", "label": "Baixar", "idx": 1, "total": 2})
    emit("step_done", {"op": "a", "idx": 1, "total": 2, "outputs": ["x.mp3"]})
    if emit_terminal:
        emit("task_done", {"output_paths": ["y.md"]})
    from pathlib import Path

    return [Path("y.md")]


@pytest.mark.unit
def test_single_run_forwards_events_and_logs(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", side_effect=_fake_execute)
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    assert ok is True
    types = [t for t, _, _ in bus.events]
    assert "recipe_start" in types and "step_start" in types and "task_done" in types
    assert all(mid == "recipes" for _, _, mid in bus.events)
    logs = [p["message"] for t, p, _ in bus.events if t == "log"]
    assert any("Receita: R" in m for m in logs)
    assert any("Passo 1/2: Baixar" in m for m in logs)
    assert any("x.mp3" in m for m in logs)


@pytest.mark.unit
def test_batch_uses_execute_recipe_batch(mocker):
    from src.gui.modules.recipes import worker

    called = {}

    def _fake_batch(recipe, runs, *, emit, cancel_is_set):
        called["n"] = len(runs)
        emit("task_done", {"output_paths": ["a.md", "b.md"]})
        from pathlib import Path

        return [Path("a.md"), Path("b.md")]

    mocker.patch(
        "src.core.recipes.runner.execute_recipe_batch", side_effect=_fake_batch
    )
    bus = _Bus()

    ok = worker.run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        runs=[(["a.mp3"], "audio", "a"), (["b.mp3"], "audio", "b")],
        install_log_handler=False,
    )

    assert ok is True
    assert called["n"] == 2


@pytest.mark.unit
def test_clean_intermediates_removes_non_final(mocker, tmp_path):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    inter = tmp_path / "inter.mp3"
    inter.write_bytes(b"x")
    final = tmp_path / "final.md"
    final.write_text("ok", encoding="utf-8")

    def _exec(
        recipe, initial_inputs, *, initial_kind, emit, cancel_is_set, emit_terminal=True
    ):
        emit("step_done", {"op": "a", "idx": 1, "total": 2, "outputs": [str(inter)]})
        emit("step_done", {"op": "b", "idx": 2, "total": 2, "outputs": [str(final)]})
        emit("task_done", {"output_paths": [str(final)]})
        return [final]

    mocker.patch("src.core.recipes.runner.execute_recipe", side_effect=_exec)

    run_recipe_pipeline(
        bus=_Bus(),
        cancel_event=threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        clean_intermediates=True,
        install_log_handler=False,
    )

    assert not inter.exists()  # intermediate removed
    assert final.exists()  # final kept


@pytest.mark.unit
def test_returns_false_when_no_output(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", return_value=[])
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    assert ok is False


@pytest.mark.unit
def test_records_ok_run(mocker, _history):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", side_effect=_fake_execute)
    run_recipe_pipeline(
        _Bus(),
        threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    _history.assert_called_once()
    record = _history.call_args.args[0]
    assert record.status == "ok"
    assert record.recipe_name == "R"
    assert record.n_steps == 1  # len(recipe.steps)
    assert record.batch_size is None
    assert record.duration >= 0


@pytest.mark.unit
def test_records_error_with_failed_op(mocker, _history):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    def _exec(recipe, inputs, *, initial_kind, emit, cancel_is_set, emit_terminal=True):
        emit("step_error", {"op": "audio.normalize", "idx": 1, "message": "boom"})
        emit("task_error", {"message": "Falha"})
        return []

    mocker.patch("src.core.recipes.runner.execute_recipe", side_effect=_exec)
    run_recipe_pipeline(
        _Bus(),
        threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    record = _history.call_args.args[0]
    assert record.status == "error"
    assert record.failed_op == "audio.normalize"


@pytest.mark.unit
def test_records_cancelled_run(mocker, _history):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch("src.core.recipes.runner.execute_recipe", return_value=[])
    cancel = threading.Event()
    cancel.set()  # user cancelled
    run_recipe_pipeline(
        _Bus(),
        cancel,
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    assert _history.call_args.args[0].status == "cancelled"


@pytest.mark.unit
def test_records_batch_size(mocker, _history):
    from src.gui.modules.recipes import worker

    def _fake_batch(recipe, runs, *, emit, cancel_is_set):
        emit("task_done", {"output_paths": ["a.md"]})
        from pathlib import Path

        return [Path("a.md")]

    mocker.patch(
        "src.core.recipes.runner.execute_recipe_batch", side_effect=_fake_batch
    )
    worker.run_recipe_pipeline(
        _Bus(),
        threading.Event(),
        recipe=_recipe(),
        runs=[(["a.mp3"], "audio", "a"), (["b.mp3"], "audio", "b")],
        install_log_handler=False,
    )

    assert _history.call_args.args[0].batch_size == 2


@pytest.mark.unit
def test_handles_unexpected_exception(mocker):
    from src.gui.modules.recipes.worker import run_recipe_pipeline

    mocker.patch(
        "src.core.recipes.runner.execute_recipe", side_effect=RuntimeError("boom")
    )
    bus = _Bus()

    ok = run_recipe_pipeline(
        bus,
        threading.Event(),
        recipe=_recipe(),
        runs=[(["https://x"], "url", "x")],
        install_log_handler=False,
    )

    assert ok is False
    assert any(t == "task_error" for t, _, _ in bus.events)
