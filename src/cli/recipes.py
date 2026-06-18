"""CLI subcommand `recipe` — run reusable cross-module recipes.

    uv run main.py recipe list                                  # presets + saved
    uv run main.py recipe run "Limpar áudio do YouTube" <URL>    # run by name
    uv run main.py recipe run "YouTube → transcrição completa" <URL> --model medium

Unlike `library`/`ai`, this subcommand has a real runner (``execute_recipe``), so
it follows the normal runner pattern: a ``CLIEventBus`` renders progress and the
same core powers the GUI — cheap parity.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from src.cli.transcription import resolve_input

logger = logging.getLogger(__name__)


def add_recipe_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the `recipe` subcommand (sub-subparsers: list / run)."""
    p = subparsers.add_parser("recipe", help="Run reusable cross-module recipes")
    sub = p.add_subparsers(dest="recipe_op", required=True)

    lst = sub.add_parser("list", help="List built-in and saved recipes")
    lst.add_argument("--verbose", action="store_true", help="Enable debug logging")

    run = sub.add_parser("run", help="Run a recipe by name on a URL or local file")
    run.add_argument("name", help="Recipe name (see 'recipe list')")
    run.add_argument("input", help="URL or local file path to feed the first step")
    run.add_argument(
        "--model",
        default=None,
        help="Override the Whisper model of any transcribe step (e.g. medium)",
    )
    run.add_argument("--verbose", action="store_true", help="Enable debug logging")

    p.set_defaults(func=run_recipe_cli)


def _all_recipes() -> list:
    """Built-in presets first, then user-saved recipes."""
    from src.core.recipes import store
    from src.core.recipes.presets import PRESETS

    return [*PRESETS, *store.load_recipes()]


def _find_recipe(name: str):
    """Return the first recipe matching ``name`` (presets take precedence)."""
    return next((r for r in _all_recipes() if r.name == name), None)


def _step_label(op: str) -> str:
    from src.core.recipes.registry import STEP_REGISTRY

    spec = STEP_REGISTRY.get(op)
    return spec.label if spec else op


def _list_recipes() -> None:
    """Print built-in and saved recipes with their step chains."""
    from src.core.recipes import store
    from src.core.recipes.presets import PRESETS

    def _print(recipe) -> None:
        chain = " → ".join(_step_label(s.op) for s in recipe.steps)
        print(f"  • {recipe.name}")
        if recipe.description:
            print(f"      {recipe.description}")
        print(f"      {chain}")

    print("Receitas embutidas:")
    for recipe in PRESETS:
        _print(recipe)

    saved = store.load_recipes()
    if saved:
        print("\nReceitas salvas:")
        for recipe in saved:
            _print(recipe)


def _with_model_override(recipe, model: str | None):
    """Return a copy of ``recipe`` with the Whisper model of transcribe steps set."""
    if not model:
        return recipe
    from src.core.recipes.types import Recipe, RecipeStep

    steps = [
        RecipeStep(s.op, {**s.params, "model": model})
        if s.op == "transcription.transcribe"
        else s
        for s in recipe.steps
    ]
    return Recipe(recipe.name, steps, recipe.description)


def _make_emit(bus):
    """Adapt the runner's ``emit(type, payload)`` to the CLIEventBus.

    Recipe-specific events (recipe_start / step_*) are rendered as log lines; the
    generic ones (progress_*, task_done/error) are forwarded so the bar/summary
    work exactly like any other CLI pipeline.
    """

    def emit(type: str, payload: dict) -> None:
        if type == "recipe_start":
            bus.emit(
                "log",
                "recipe",
                {
                    "message": f"[*] Receita: {payload['name']} ({payload['total_steps']} passo(s))"
                },
            )
        elif type == "step_start":
            bus.emit(
                "log",
                "recipe",
                {
                    "message": f"[→] Passo {payload['idx']}/{payload['total']}: {payload['label']}"
                },
            )
        elif type == "step_done":
            for out in payload.get("outputs", []):
                bus.emit("log", "recipe", {"message": f"    ✓ {out}"})
        elif type == "step_error":
            pass  # task_error reports the failure to the user
        else:
            bus.emit(type, "recipe", payload, "recipes")

    return emit


def run_recipe_cli(ns: argparse.Namespace) -> None:
    """Dispatch the `recipe` subcommand: list, or run a recipe by name."""
    # Output filenames may contain non-cp1252 characters (e.g. fullwidth ｜).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if ns.recipe_op == "list":
        _list_recipes()
        return

    recipe = _find_recipe(ns.name)
    if recipe is None:
        logger.error("Receita não encontrada: %r. Veja 'recipe list'.", ns.name)
        sys.exit(1)

    from src.core.recipes.inputs import kind_for

    kind, value = resolve_input(ns.input)
    try:
        initial_kind = kind_for(kind, value)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    recipe = _with_model_override(recipe, ns.model)

    from src.cli.bus import CLIEventBus
    from src.core.recipes.runner import execute_recipe

    bus = CLIEventBus()
    cancel = threading.Event()
    final = execute_recipe(
        recipe,
        [value],
        initial_kind=initial_kind,
        emit=_make_emit(bus),
        cancel_is_set=cancel.is_set,
    )
    if not final:
        sys.exit(1)
