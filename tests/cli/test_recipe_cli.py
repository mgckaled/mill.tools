"""Unit tests for the `recipe` CLI — parser + run_recipe_cli dispatch.

execute_recipe is the runner here (recipes have a real pipeline, unlike
library/ai), so it is mocked at its source to validate the Namespace → run wiring.
"""

import argparse
from pathlib import Path

import pytest

_YT_PRESET = "YouTube → transcrição completa"


def _parse(*argv: str) -> argparse.Namespace:
    from src.cli.recipes import add_recipe_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_recipe_parser(sub)
    return parser.parse_args(["recipe", *argv])


@pytest.mark.unit
def test_list_parser():
    ns = _parse("list")
    assert ns.recipe_op == "list"
    assert callable(ns.func)


@pytest.mark.unit
def test_stats_parser():
    ns = _parse("stats")
    assert ns.recipe_op == "stats"
    assert callable(ns.func)


@pytest.mark.unit
def test_stats_runner_no_history(mocker, capsys):
    mocker.patch("src.core.recipes.history.load_runs", return_value=[])
    ns = _parse("stats")
    ns.func(ns)
    assert "Sem histórico" in capsys.readouterr().out


@pytest.mark.unit
def test_stats_runner_prints_aggregate(mocker, capsys):
    from src.core.recipes.history import RunRecord

    runs = [
        RunRecord("Limpar áudio", 0.0, 10.0, 10.0, "ok", 2),
        RunRecord(
            "Limpar áudio", 0.0, 20.0, 20.0, "error", 2, failed_op="audio.normalize"
        ),
    ]
    mocker.patch("src.core.recipes.history.load_runs", return_value=runs)
    ns = _parse("stats")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "Histórico de receitas" in out
    assert "Limpar áudio" in out
    assert "audio.normalize" in out


@pytest.mark.unit
def test_run_parser_defaults():
    ns = _parse("run", "My Recipe", "https://youtu.be/x")
    assert ns.recipe_op == "run"
    assert ns.name == "My Recipe"
    assert ns.input == "https://youtu.be/x"
    assert ns.model is None
    assert callable(ns.func)


@pytest.mark.unit
def test_run_parser_model_flag():
    ns = _parse("run", "R", "f.mp3", "--model", "medium")
    assert ns.model == "medium"


@pytest.mark.unit
def test_find_recipe_returns_preset():
    from src.cli.recipes import _find_recipe

    assert _find_recipe(_YT_PRESET) is not None


@pytest.mark.unit
def test_find_recipe_missing(mocker):
    from src.cli import recipes

    mocker.patch("src.core.recipes.store.load_recipes", return_value=[])
    assert recipes._find_recipe("não existe") is None


@pytest.mark.unit
def test_list_runner_prints_presets(mocker, capsys):
    mocker.patch("src.core.recipes.store.load_recipes", return_value=[])
    ns = _parse("list")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "Receitas embutidas" in out
    assert "YouTube" in out


@pytest.mark.unit
def test_run_dispatches_to_execute_recipe(mocker):
    mock_exec = mocker.patch(
        "src.core.recipes.runner.execute_recipe", return_value=[Path("o.md")]
    )
    ns = _parse("run", _YT_PRESET, "https://youtu.be/x")
    ns.func(ns)

    assert mock_exec.called
    args = mock_exec.call_args.args
    kwargs = mock_exec.call_args.kwargs
    assert args[1] == ["https://youtu.be/x"]  # initial_inputs
    assert kwargs["initial_kind"] == "url"
    assert callable(kwargs["emit"])
    assert callable(kwargs["cancel_is_set"])


@pytest.mark.unit
def test_run_applies_model_override_to_transcribe(mocker):
    mock_exec = mocker.patch(
        "src.core.recipes.runner.execute_recipe", return_value=[Path("o")]
    )
    ns = _parse("run", _YT_PRESET, "https://youtu.be/x", "--model", "medium")
    ns.func(ns)

    recipe = mock_exec.call_args.args[0]
    transcribe = next(s for s in recipe.steps if s.op == "transcription.transcribe")
    assert transcribe.params["model"] == "medium"


@pytest.mark.unit
def test_run_missing_recipe_exits(mocker):
    mocker.patch("src.core.recipes.store.load_recipes", return_value=[])
    ns = _parse("run", "Inexistente", "https://x")
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_run_failed_recipe_exits(mocker):
    mocker.patch("src.core.recipes.runner.execute_recipe", return_value=[])
    ns = _parse("run", _YT_PRESET, "https://x")
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_run_unsupported_input_exits(mocker, tmp_path):
    # A real file with an unsupported extension → kind_for raises → exit 1.
    bad = tmp_path / "data.zip"
    bad.write_bytes(b"x")
    mocker.patch("src.core.recipes.runner.execute_recipe", return_value=[Path("o")])
    ns = _parse("run", _YT_PRESET, str(bad))
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_step_label_falls_back_to_op():
    from src.cli.recipes import _step_label

    assert _step_label("audio.download") == "Baixar áudio"
    assert _step_label("unknown.op") == "unknown.op"


@pytest.mark.unit
def test_list_runner_includes_saved(mocker, capsys):
    from src.core.recipes.types import Recipe, RecipeStep

    mocker.patch(
        "src.core.recipes.store.load_recipes",
        return_value=[Recipe("Custom", [RecipeStep("audio.download")], "minha")],
    )
    ns = _parse("list")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "Receitas salvas" in out
    assert "Custom" in out


@pytest.mark.unit
def test_make_emit_translates_recipe_events():
    from src.cli.recipes import _make_emit

    calls = []

    class _Bus:
        def emit(self, type, stage="", payload=None, module_id=""):
            calls.append((type, payload))

    emit = _make_emit(_Bus())
    emit("recipe_start", {"name": "R", "total_steps": 3})
    emit("step_start", {"idx": 1, "total": 3, "label": "Baixar"})
    emit("step_done", {"outputs": ["a.mp3", "b.txt"]})
    emit("step_error", {"op": "x"})  # silent — task_error reports
    emit("task_done", {"output_paths": ["z"]})

    messages = [p.get("message", "") for t, p in calls if t == "log"]
    assert any("Receita: R (3 passo(s))" in m for m in messages)
    assert any("Passo 1/3: Baixar" in m for m in messages)
    assert sum(1 for m in messages if "a.mp3" in m) == 1
    assert sum(1 for m in messages if "b.txt" in m) == 1
    # generic events are forwarded verbatim
    assert ("task_done", {"output_paths": ["z"]}) in calls
