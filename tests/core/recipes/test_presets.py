"""Unit tests for built-in presets — none may be type-incoherent."""

import pytest


@pytest.mark.unit
def test_presets_are_not_empty():
    from src.core.recipes.presets import PRESETS

    assert PRESETS


@pytest.mark.unit
def test_every_preset_is_valid_for_each_accepted_initial_kind():
    """A preset must validate for every kind its first step accepts."""
    from src.core.recipes.presets import PRESETS
    from src.core.recipes.registry import STEP_REGISTRY
    from src.core.recipes.validate import validate_recipe

    for preset in PRESETS:
        assert preset.steps, f"{preset.name} has no steps"
        first = STEP_REGISTRY[preset.steps[0].op]
        for kind in first.accepts:
            errors = validate_recipe(preset, kind)
            assert errors == [], f"{preset.name} invalid for {kind}: {errors}"


@pytest.mark.unit
def test_preset_names_are_unique():
    from src.core.recipes.presets import PRESETS

    names = [p.name for p in PRESETS]
    assert len(names) == len(set(names))


@pytest.mark.unit
def test_preset_by_name():
    from src.core.recipes.presets import PRESETS, preset_by_name

    assert preset_by_name(PRESETS[0].name) is PRESETS[0]
    assert preset_by_name("não existe") is None
