"""Unit tests for the recipe store — JSON round-trip, replace, delete, resilience."""

import pytest


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / ".mill-tools" / "recipes.json"


def _recipe(name="Minha receita"):
    from src.core.recipes.types import Recipe, RecipeStep

    return Recipe(
        name=name,
        steps=[
            RecipeStep("audio.download"),
            RecipeStep("audio.normalize", {"target_lufs": -16.0}),
        ],
        description="descrição",
    )


@pytest.mark.unit
def test_load_missing_file_returns_empty(store_path):
    from src.core.recipes.store import load_recipes

    assert load_recipes(store_path) == []


@pytest.mark.unit
def test_save_and_load_round_trip(store_path):
    from src.core.recipes.store import load_recipes, save_recipe

    save_recipe(_recipe(), store_path)
    loaded = load_recipes(store_path)

    assert len(loaded) == 1
    assert loaded[0].name == "Minha receita"
    assert loaded[0].description == "descrição"
    assert loaded[0].steps[1].op == "audio.normalize"
    assert loaded[0].steps[1].params == {"target_lufs": -16.0}


@pytest.mark.unit
def test_save_replaces_existing_by_name(store_path):
    from src.core.recipes.store import load_recipes, save_recipe
    from src.core.recipes.types import Recipe, RecipeStep

    save_recipe(_recipe("R"), store_path)
    save_recipe(Recipe("R", [RecipeStep("document.ocr")], "nova"), store_path)

    loaded = load_recipes(store_path)
    assert len(loaded) == 1
    assert loaded[0].description == "nova"
    assert loaded[0].steps[0].op == "document.ocr"


@pytest.mark.unit
def test_delete_recipe(store_path):
    from src.core.recipes.store import delete_recipe, load_recipes, save_recipe

    save_recipe(_recipe("A"), store_path)
    save_recipe(_recipe("B"), store_path)

    assert delete_recipe("A", store_path) is True
    remaining = load_recipes(store_path)
    assert [r.name for r in remaining] == ["B"]
    assert delete_recipe("missing", store_path) is False


@pytest.mark.unit
def test_load_skips_malformed_entries(store_path):
    from src.core.recipes.store import load_recipes

    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        '[{"name":"ok","steps":[{"op":"audio.download"}]},{"missing":"steps"}]',
        encoding="utf-8",
    )

    loaded = load_recipes(store_path)
    assert len(loaded) == 1
    assert loaded[0].name == "ok"
    assert loaded[0].steps[0].params == {}  # default applied


@pytest.mark.unit
def test_load_invalid_json_returns_empty(store_path):
    from src.core.recipes.store import load_recipes

    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("{not valid json", encoding="utf-8")

    assert load_recipes(store_path) == []
