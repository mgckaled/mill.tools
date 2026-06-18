"""Type-coherence validation for recipes (accepts/produces chain)."""

from __future__ import annotations

from src.core.recipes.registry import STEP_REGISTRY
from src.core.recipes.types import Recipe


def validate_recipe(recipe: Recipe, initial_kind: str) -> list[str]:
    """Return a list of human-readable errors (empty list = valid).

    Walks the chain checking that each step's ``accepts`` includes the kind
    produced by the previous step (or ``initial_kind`` for the first step), and
    that every op exists in the registry. Used both live by the GUI builder
    (disable "Run" + show the error) and by the runner before executing.

    Args:
        recipe: The recipe to validate.
        initial_kind: Logical kind of the recipe's initial input (url/audio/...).

    Returns:
        List of PT-BR error strings; empty when the recipe is coherent.
    """
    errors: list[str] = []
    if not recipe.steps:
        errors.append("A receita não tem passos.")
        return errors

    produced = initial_kind
    for i, step in enumerate(recipe.steps, 1):
        spec = STEP_REGISTRY.get(step.op)
        if spec is None:
            errors.append(f"Passo {i}: operação desconhecida '{step.op}'")
            break
        if produced not in spec.accepts:
            errors.append(
                f"Passo {i} ({spec.label}): não aceita '{produced}' "
                f"(aceita: {', '.join(sorted(spec.accepts))})"
            )
            break
        produced = spec.produces
    return errors
