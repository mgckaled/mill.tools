"""Form panel for the Recipes module: pick a recipe, choose input, run.

Pure UI construction — no threading here. The view wires ``on_run`` and reads the
getters. ``refresh()`` re-lists recipes so the PR8.3 builder can show a freshly
saved recipe without rebuilding the module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.recipes.presets import PRESETS
from src.core.recipes.registry import STEP_REGISTRY
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    primary_button,
    section_label,
)
from src.gui.theme.tokens import Color, Radius, Space, Type

if TYPE_CHECKING:
    from src.core.io_types import InputItem
    from src.core.recipes.types import Recipe

# Every file kind a recipe can take as its initial input.
_ALLOWED_EXTS = [
    "mp3",
    "wav",
    "flac",
    "ogg",
    "opus",
    "aac",
    "m4a",
    "mp4",
    "mkv",
    "webm",
    "avi",
    "mov",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "avif",
    "tiff",
    "bmp",
    "gif",
    "pdf",
    "txt",
    "md",
]

_KIND_LABELS = {
    "url": "URL",
    "audio": "Áudio",
    "video": "Vídeo",
    "image": "Imagem",
    "pdf": "PDF",
    "text": "Texto",
}


@dataclass
class RecipesForm:
    """Handles exposed by the form so the view can drive it."""

    control: ft.Control
    get_recipe: Callable[[], "Recipe | None"]
    get_inputs: Callable[[], "list[InputItem]"]
    set_running: Callable[[bool], None]
    refresh: Callable[[], None]


def _border(width: float, color: str) -> ft.Border:
    side = ft.BorderSide(width, color)
    return ft.Border(left=side, right=side, top=side, bottom=side)


def _expected_input_label(recipe: "Recipe") -> str:
    """PT-BR list of the input kinds the recipe's first step accepts."""
    spec = STEP_REGISTRY.get(recipe.steps[0].op) if recipe.steps else None
    if spec is None:
        return "?"
    return " ou ".join(_KIND_LABELS.get(k, k) for k in sorted(spec.accepts))


def build_recipes_form(
    page: ft.Page,
    *,
    on_run: Callable[[], None],
    load_saved: Callable[[], "list[Recipe]"],
) -> RecipesForm:
    """Build the left form panel and return its handles.

    Args:
        page: Flet page (FilePicker registration).
        on_run: Called when the user presses "Rodar receita".
        load_saved: Returns the user-saved recipes to list under the presets.
    """
    selected: list[Recipe | None] = [None]
    cards_by_recipe: list[tuple[Recipe, ft.Container]] = []

    # ── header ────────────────────────────────────────────────────────────
    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.ACCOUNT_TREE_OUTLINED, color=ft.Colors.PRIMARY),
        ft.Text(
            "Receitas",
            size=Type.title.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("recipes", page)
    if _help is not None:
        header_controls.extend([ft.Container(expand=True), _help])
    header = ft.Row(
        header_controls,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=Space.sm,
    )

    # ── input + expected-kind hint ──────────────────────────────────────────
    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        url_hint="URL ou selecione um arquivo de entrada",
    )

    expected_hint = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
        no_wrap=False,
    )

    run_btn = primary_button(
        "Rodar receita",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        on_click=lambda _e: on_run(),
    )
    run_btn.disabled = True

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    def _refresh_run_enabled() -> None:
        run_btn.disabled = selected[0] is None
        _safe_update(run_btn)

    # ── recipe cards ────────────────────────────────────────────────────────
    def _select(recipe: "Recipe") -> None:
        selected[0] = recipe
        for r, card in cards_by_recipe:
            is_sel = r is recipe
            card.border = _border(
                1.5,
                ft.Colors.PRIMARY if is_sel else ft.Colors.OUTLINE_VARIANT,
            )
            card.bgcolor = (
                ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)
                if is_sel
                else Color.dark.surface_variant
            )
            _safe_update(card)
        expected_hint.value = f"Entrada esperada: {_expected_input_label(recipe)}"
        _safe_update(expected_hint)
        _refresh_run_enabled()

    def _make_card(recipe: "Recipe") -> ft.Control:
        chain = " → ".join(
            STEP_REGISTRY[s.op].label if s.op in STEP_REGISTRY else s.op
            for s in recipe.steps
        )
        card = ft.Container(
            border_radius=Radius.md,
            border=_border(1.5, ft.Colors.OUTLINE_VARIANT),
            bgcolor=Color.dark.surface_variant,
            padding=ft.Padding(
                left=Space.sm, right=Space.sm, top=Space.sm, bottom=Space.sm
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        recipe.name,
                        size=Type.body_strong.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE,
                        no_wrap=False,
                    ),
                    ft.Text(
                        recipe.description,
                        size=Type.small.size,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        no_wrap=False,
                    ),
                    ft.Text(
                        chain,
                        size=Type.small.size,
                        color=ft.Colors.PRIMARY,
                        no_wrap=False,
                    ),
                ],
                spacing=Space.xxs,
            ),
        )
        cards_by_recipe.append((recipe, card))
        return ft.GestureDetector(
            content=card,
            on_tap=lambda _e, _r=recipe: _select(_r),
            mouse_cursor=Cursor.interactive,
        )

    recipe_list = ft.Column(spacing=Space.xs, scroll=ft.ScrollMode.AUTO)

    def refresh() -> None:
        selected[0] = None
        cards_by_recipe.clear()
        recipe_list.controls.clear()
        recipe_list.controls.append(section_label("Embutidas"))
        recipe_list.controls.extend(_make_card(r) for r in PRESETS)
        saved = load_saved()
        if saved:
            recipe_list.controls.append(section_label("Salvas"))
            recipe_list.controls.extend(_make_card(r) for r in saved)
        expected_hint.value = ""
        _safe_update(recipe_list, expected_hint)
        _refresh_run_enabled()

    refresh()

    def set_running(running: bool) -> None:
        run_btn.disabled = running or selected[0] is None
        input_source.set_enabled(not running)
        _safe_update(run_btn)

    # ── assemble ──────────────────────────────────────────────────────────
    body = ft.Column(
        controls=[
            header,
            section_label("Receita"),
            recipe_list,
            section_label("Entrada"),
            input_source.control,
            expected_hint,
            run_btn,
        ],
        spacing=Space.md,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    control = ft.Container(
        content=body,
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
        ),
        expand=True,
    )

    return RecipesForm(
        control=control,
        get_recipe=lambda: selected[0],
        get_inputs=input_source.get_items,
        set_running=set_running,
        refresh=refresh,
    )
