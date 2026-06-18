"""Form panel for the Recipes module: pick & run a recipe, or build a new one.

Pure UI construction — no threading here. The view wires ``on_run`` and reads the
getters. A mode toggle switches between "Rodar" (run a preset/saved recipe) and
"Construir" (assemble a new chain and save it). ``refresh()`` re-lists recipes so
a freshly saved recipe shows up immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.recipes import store
from src.core.recipes.presets import PRESETS
from src.core.recipes.registry import STEP_REGISTRY
from src.core.recipes.types import Recipe, RecipeStep
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    primary_button,
    secondary_button,
    section_label,
)
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type

if TYPE_CHECKING:
    from src.core.io_types import InputItem

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


def _expected_input_label(recipe: Recipe) -> str:
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
    on_notify: Callable[[str], None] | None = None,
) -> RecipesForm:
    """Build the left form panel and return its handles.

    Args:
        page: Flet page (FilePicker registration).
        on_run: Called when the user presses "Rodar receita".
        load_saved: Returns the user-saved recipes to list under the presets.
        on_notify: Optional toast callback for builder feedback (save/errors).
    """
    selected: list[Recipe | None] = [None]
    cards_by_recipe: list[tuple[Recipe, ft.Container]] = []

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    def _notify(msg: str) -> None:
        if on_notify:
            on_notify(msg)

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

    # ── mode toggle (Rodar | Construir) — manual tabs (no ft.Tabs in 0.85) ──
    def _btn_style(active: bool) -> ft.ButtonStyle:
        c = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
        return ft.ButtonStyle(
            mouse_cursor=Cursor.interactive,
            color={
                ft.ControlState.DEFAULT: c,
                ft.ControlState.HOVERED: ft.Colors.PRIMARY,
            },
        )

    run_tab = ft.TextButton("Rodar", icon=ft.Icons.PLAY_ARROW_ROUNDED)
    build_tab = ft.TextButton("Construir", icon=ft.Icons.BUILD_OUTLINED)

    def _set_mode(building: bool) -> None:
        build_section.visible = building
        run_section.visible = not building
        run_tab.style = _btn_style(not building)
        build_tab.style = _btn_style(building)
        _safe_update(build_section, run_section, run_tab, build_tab)

    run_tab.on_click = lambda _e: _set_mode(False)
    build_tab.on_click = lambda _e: _set_mode(True)
    mode_toggle = ft.Row([run_tab, build_tab], spacing=Space.xs)

    # ─────────────────────────────────────────────────────────────────────
    # RUN section
    # ─────────────────────────────────────────────────────────────────────
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
        "Rodar receita", icon=ft.Icons.PLAY_ARROW_ROUNDED, on_click=lambda _e: on_run()
    )
    run_btn.disabled = True

    def _refresh_run_enabled() -> None:
        run_btn.disabled = selected[0] is None
        _safe_update(run_btn)

    def _select(recipe: Recipe) -> None:
        selected[0] = recipe
        for r, card in cards_by_recipe:
            is_sel = r is recipe
            card.border = _border(
                1.5, ft.Colors.PRIMARY if is_sel else ft.Colors.OUTLINE_VARIANT
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

    def _make_card(recipe: Recipe) -> ft.Control:
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

    recipe_list = ft.Column(spacing=Space.xs)

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

    run_section = ft.Column(
        controls=[
            section_label("Receita"),
            recipe_list,
            section_label("Entrada"),
            input_source.control,
            expected_hint,
            run_btn,
        ],
        spacing=Space.md,
    )

    # ─────────────────────────────────────────────────────────────────────
    # BUILD section — assemble a new chain and save it
    # ─────────────────────────────────────────────────────────────────────
    built_steps: list[RecipeStep] = []

    name_field = ft.TextField(
        label="Nome da receita",
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
    )

    builder_error = ft.Text(
        "", size=Type.small.size, color=ft.Colors.ERROR, no_wrap=False
    )

    save_btn = secondary_button("Salvar receita", icon=ft.Icons.SAVE_OUTLINED)

    # Reordering uses ↑/↓ buttons, not ft.ReorderableListView. That control exists
    # in this Flet build but is a bounded scrollable (no `shrink_wrap`; needs a
    # fixed height) — nesting it inside the scrolling form Column is fragile and
    # can't be render-verified headless. The ↑/↓ fallback is deterministic, has no
    # nested-scroll pitfalls, and reorders the chain just as well.
    steps_list = ft.Column(spacing=Space.xxs)

    add_dd = ft.Dropdown(
        label="Adicionar passo",
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _produced_kind() -> str | None:
        """Output kind currently at the tail of the built chain (None if empty)."""
        if not built_steps:
            return None
        return STEP_REGISTRY[built_steps[-1].op].produces

    def _candidate_options() -> list[ft.dropdown.Option]:
        """Ops whose accepts matches the current tail kind (all ops for step 1)."""
        produced = _produced_kind()
        candidates = [
            (op, spec.label)
            for op, spec in STEP_REGISTRY.items()
            if produced is None or produced in spec.accepts
        ]
        candidates.sort(key=lambda t: t[1])
        return [ft.dropdown.Option(key=op, text=label) for op, label in candidates]

    def _chain_errors() -> list[str]:
        """Validate the built chain's accepts/produces coherence (after reorder)."""
        produced: str | None = None
        for i, step in enumerate(built_steps, 1):
            spec = STEP_REGISTRY[step.op]
            if produced is not None and produced not in spec.accepts:
                return [f"Passo {i} ({spec.label}) não aceita '{produced}'."]
            produced = spec.produces
        return []

    def _move(idx: int, delta: int) -> None:
        new = idx + delta
        if 0 <= new < len(built_steps):
            built_steps[idx], built_steps[new] = built_steps[new], built_steps[idx]
            _rebuild_builder()

    def _step_row(idx: int, step: RecipeStep) -> ft.Control:
        spec = STEP_REGISTRY[step.op]

        def _remove(_e=None) -> None:
            built_steps.pop(idx)
            _rebuild_builder()

        return ft.Container(
            border_radius=Radius.sm,
            bgcolor=Color.dark.surface_variant,
            padding=ft.Padding(
                left=Space.sm, right=Space.xs, top=Space.xxs, bottom=Space.xxs
            ),
            content=ft.Row(
                controls=[
                    ft.Text(
                        f"{idx + 1}. {spec.label}",
                        size=Type.input.size,
                        color=ft.Colors.ON_SURFACE,
                        expand=True,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.KEYBOARD_ARROW_UP,
                        icon_size=IconSize.sm,
                        tooltip="Subir",
                        disabled=idx == 0,
                        on_click=lambda _e, _i=idx: _move(_i, -1),
                        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.KEYBOARD_ARROW_DOWN,
                        icon_size=IconSize.sm,
                        tooltip="Descer",
                        disabled=idx == len(built_steps) - 1,
                        on_click=lambda _e, _i=idx: _move(_i, 1),
                        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=IconSize.sm,
                        tooltip="Remover passo",
                        on_click=_remove,
                        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
                    ),
                ],
                spacing=Space.xxs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _refresh_save_enabled() -> None:
        errors = _chain_errors()
        builder_error.value = errors[0] if errors else ""
        save_btn.disabled = (
            bool(errors) or not built_steps or not (name_field.value or "").strip()
        )
        _safe_update(builder_error, save_btn)

    def _rebuild_builder() -> None:
        steps_list.controls[:] = [_step_row(i, s) for i, s in enumerate(built_steps)]
        add_dd.options = _candidate_options()
        add_dd.value = None
        _refresh_save_enabled()
        _safe_update(steps_list, add_dd)

    def _on_add(e: ft.ControlEvent) -> None:
        op = e.control.value
        if op and op in STEP_REGISTRY:
            built_steps.append(RecipeStep(op))
            _rebuild_builder()

    add_dd.on_select = _on_add
    name_field.on_change = lambda _e: _refresh_save_enabled()

    def _on_save(_e=None) -> None:
        name = (name_field.value or "").strip()
        if not name or not built_steps:
            return
        if _chain_errors():
            return
        store.save_recipe(
            Recipe(name=name, steps=list(built_steps), description="Receita do usuário")
        )
        _notify(f'Receita "{name}" salva.')
        # Reset the builder and re-list so the new recipe shows under "Salvas".
        built_steps.clear()
        name_field.value = ""
        _rebuild_builder()
        _safe_update(name_field)
        refresh()

    save_btn.on_click = _on_save

    build_section = ft.Column(
        controls=[
            ft.Text(
                "Monte uma cadeia: cada passo só oferece operações compatíveis com "
                "a saída do anterior.",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=False,
            ),
            name_field,
            section_label("Passos"),
            steps_list,
            add_dd,
            builder_error,
            save_btn,
        ],
        spacing=Space.md,
        visible=False,
    )

    # ── initial state ───────────────────────────────────────────────────────
    refresh()
    _rebuild_builder()
    _set_mode(False)

    def set_running(running: bool) -> None:
        run_btn.disabled = running or selected[0] is None
        input_source.set_enabled(not running)
        _safe_update(run_btn)

    # ── assemble ──────────────────────────────────────────────────────────
    body = ft.Column(
        controls=[header, mode_toggle, run_section, build_section],
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
