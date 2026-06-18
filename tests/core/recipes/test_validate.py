"""Unit tests for validate_recipe — accepts/produces coherence and unknown ops."""

import pytest


def _recipe(*ops):
    from src.core.recipes.types import Recipe, RecipeStep

    return Recipe(name="r", steps=[RecipeStep(o) for o in ops])


@pytest.mark.unit
def test_coherent_chain_is_valid():
    from src.core.recipes.validate import validate_recipe

    recipe = _recipe(
        "audio.download", "transcription.transcribe", "transcription.analyze"
    )
    assert validate_recipe(recipe, "url") == []


@pytest.mark.unit
def test_kind_mismatch_is_reported():
    from src.core.recipes.validate import validate_recipe

    # image.resize produces 'image'; transcribe accepts audio/video only.
    recipe = _recipe("image.resize", "transcription.transcribe")
    errors = validate_recipe(recipe, "image")
    assert len(errors) == 1
    assert "Transcrever" in errors[0]
    assert "não aceita" in errors[0]


@pytest.mark.unit
def test_unknown_op_is_reported():
    from src.core.recipes.validate import validate_recipe

    errors = validate_recipe(_recipe("audio.nope"), "url")
    assert errors
    assert "desconhecida" in errors[0]


@pytest.mark.unit
def test_first_step_incompatible_with_initial_kind():
    from src.core.recipes.validate import validate_recipe

    # analyze accepts text/markdown, not url.
    errors = validate_recipe(_recipe("transcription.analyze"), "url")
    assert errors
    assert "não aceita" in errors[0]


@pytest.mark.unit
def test_empty_recipe_is_reported():
    from src.core.recipes.types import Recipe
    from src.core.recipes.validate import validate_recipe

    errors = validate_recipe(Recipe(name="r", steps=[]), "url")
    assert errors


@pytest.mark.unit
def test_video_subtitle_chain_is_valid_from_video():
    from src.core.recipes.validate import validate_recipe

    # video → transcribe (text) → video.subtitle (accepts text) is coherent.
    recipe = _recipe("transcription.transcribe", "video.subtitle")
    assert validate_recipe(recipe, "video") == []
