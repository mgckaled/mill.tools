"""AI operation blocks (remove_bg and describe) for the image module."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.core.image.background import is_available as _rembg_ok
from src.gui.theme.components import labeled_field, help_icon_for
from src.gui.theme.tokens import Layout, Space, Type


class AIRefs(NamedTuple):
    rembg_block: ft.Column
    describe_block: ft.Column
    set_rembg_disabled: Callable[[bool], None]
    set_desc_disabled: Callable[[bool], None]
    get_rembg_model: Callable[[], str]
    get_desc_model: Callable[[], str]
    get_desc_prompt: Callable[[], str]


def build_ai_blocks(page: ft.Page) -> AIRefs:
    """Build the remove_bg and describe blocks.

    Both blocks are returned via AIRefs since they share availability state.
    """
    rembg_available = _rembg_ok()

    # ── remove_bg ─────────────────────────────────────────────────────────────

    rembg_warning = ft.Text(
        "⚠ Extra não instalado.\nExecute: uv sync --extra ai-image",
        color=ft.Colors.ERROR,
        size=Type.small.size,
        visible=not rembg_available,
    )
    rembg_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option("u2net",             "u2net — geral (padrão)"),
            ft.dropdown.Option("u2netp",            "u2netp — rápido e leve"),
            ft.dropdown.Option("silueta",           "silueta — compacto"),
            ft.dropdown.Option("isnet-general-use", "isnet — recortes precisos"),
            ft.dropdown.Option("u2net_human_seg",   "humano — otimizado para pessoas"),
        ],
        value="u2net",
        disabled=not rembg_available,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    rembg_block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            rembg_warning,
            labeled_field("Modelo", rembg_dd, help_key="image.rembg_model", page=page),
            ft.Text(
                "Saída: sempre PNG com transparência",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )

    # ── describe ──────────────────────────────────────────────────────────────

    desc_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option("moondream-custom", "moondream-custom"),
            ft.dropdown.Option("llava:7b",         "llava:7b"),
            ft.dropdown.Option("minicpm-v",        "minicpm-v"),
        ],
        value="moondream-custom",
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )
    desc_prompt_tf = ft.TextField(
        hint_text="Prompt customizado (vazio = padrão PT-BR)",
        text_size=Type.caption.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )

    describe_block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            labeled_field("Modelo vision", desc_dd, help_key="image.describe_model", page=page),
            labeled_field("Prompt", desc_prompt_tf, help_key="image.describe_prompt", page=page),
            ft.Text(
                "Saída: .txt salvo em output/image/processed/",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )

    return AIRefs(
        rembg_block=rembg_block,
        describe_block=describe_block,
        set_rembg_disabled=lambda d: setattr(rembg_dd, "disabled", d),
        set_desc_disabled=lambda d: setattr(desc_dd, "disabled", d),
        get_rembg_model=lambda: rembg_dd.value or "u2net",
        get_desc_model=lambda: desc_dd.value or "moondream-custom",
        get_desc_prompt=lambda: (desc_prompt_tf.value or "").strip(),
    )
