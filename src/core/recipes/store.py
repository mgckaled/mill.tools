"""Persist user recipes to ~/.mill-tools/recipes.json (same dir as config.json)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from src.core.recipes.types import Recipe, RecipeStep

logger = logging.getLogger(__name__)


def _store_path() -> Path:
    """Canonical on-disk location for user recipes."""
    return Path.home() / ".mill-tools" / "recipes.json"


def load_recipes(path: Path | None = None) -> list[Recipe]:
    """Load user-saved recipes. Returns [] if the file is missing or unreadable.

    Malformed individual entries are skipped (logged) rather than aborting the
    whole load, so one bad hand-edit never hides every other saved recipe.
    """
    path = path or _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[!] Could not read recipes file %s: %s", path, exc)
        return []

    recipes: list[Recipe] = []
    for entry in data:
        try:
            steps = [
                RecipeStep(op=s["op"], params=dict(s.get("params", {})))
                for s in entry["steps"]
            ]
            recipes.append(
                Recipe(
                    name=entry["name"],
                    steps=steps,
                    description=entry.get("description", ""),
                )
            )
        except (KeyError, TypeError):
            logger.warning("[!] Skipping malformed recipe entry: %r", entry)
    return recipes


def save_recipe(recipe: Recipe, path: Path | None = None) -> None:
    """Add or replace a recipe by name, then persist the full list."""
    path = path or _store_path()
    others = [r for r in load_recipes(path) if r.name != recipe.name]
    others.append(recipe)
    _write(others, path)


def delete_recipe(name: str, path: Path | None = None) -> bool:
    """Remove a recipe by name. Returns True when something was removed."""
    path = path or _store_path()
    recipes = load_recipes(path)
    kept = [r for r in recipes if r.name != name]
    if len(kept) == len(recipes):
        return False
    _write(kept, path)
    return True


def _write(recipes: list[Recipe], path: Path) -> None:
    """Serialize recipes to JSON (slots dataclasses → dataclasses.asdict)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(r) for r in recipes]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
