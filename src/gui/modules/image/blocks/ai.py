"""AI operation blocks (remove_bg and describe) for the image module."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.core.image.background import is_available as _rembg_ok
from src.gui.theme.components import labeled_field, section_label, segmented_selector
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import IconSize, Layout, Radius, Space, Type
from src.llm_factory import is_cloud_model


class AIRefs(NamedTuple):
    rembg_block: ft.Column
    describe_block: ft.Column
    set_rembg_disabled: Callable[[bool], None]
    set_desc_disabled: Callable[[bool], None]
    get_rembg_model: Callable[[], str]
    get_rembg_bg_mode: Callable[[], str]
    get_rembg_bg_color: Callable[[], str]
    get_rembg_bg_blur: Callable[[], int]
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
            ft.dropdown.Option("u2net", "u2net — geral (padrão)"),
            ft.dropdown.Option("u2netp", "u2netp — rápido e leve"),
            ft.dropdown.Option("silueta", "silueta — compacto"),
            ft.dropdown.Option("isnet-general-use", "isnet — recortes precisos"),
            ft.dropdown.Option("u2net_human_seg", "humano — otimizado para pessoas"),
        ],
        value="u2net",
        disabled=not rembg_available,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    # Background replacement: keep transparent, or composite over color/blur.
    bg_color_tf = ft.TextField(
        value="#ffffff",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )
    bg_color_col = ft.Column(
        [section_label("Cor de fundo"), bg_color_tf], spacing=Space.xs, visible=False
    )
    blur_col, blur_slider = labeled_slider(
        label="Intensidade do desfoque",
        value=15.0,
        min=1.0,
        max=40.0,
        divisions=39,
        fmt=lambda v: f"{int(v)}",
    )
    blur_col.visible = False

    def _on_bg_mode(mode: str) -> None:
        bg_color_col.visible = mode == "color"
        blur_col.visible = mode == "blur"
        try:
            if bg_color_col.page:
                bg_color_col.page.update()
        except RuntimeError:
            pass

    bg_mode_grid, _bg_get, _bg_set = segmented_selector(
        ["transparent", "color", "blur"],
        "transparent",
        page,
        on_change=_on_bg_mode,
        labels={"transparent": "Transparente", "color": "Cor", "blur": "Desfoque"},
        columns=3,
    )

    rembg_block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            rembg_warning,
            labeled_field("Modelo", rembg_dd, help_key="image.rembg_model", page=page),
            section_label("Fundo"),
            bg_mode_grid,
            bg_color_col,
            blur_col,
            ft.Text(
                "Saída: PNG (transparente preserva o alpha)",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )

    # ── describe ──────────────────────────────────────────────────────────────

    desc_cloud_warning = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        border_radius=Radius.sm,
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CLOUD_OUTLINED, size=IconSize.md, color=ft.Colors.PRIMARY
                ),
                ft.Text(
                    "Com modelos em nuvem (Gemini/GLM), a imagem é enviada a um "
                    "provedor externo para ser descrita.",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    no_wrap=False,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    def _on_desc_model_select(e: ft.ControlEvent) -> None:
        desc_cloud_warning.visible = is_cloud_model(e.control.value or "")
        try:
            if desc_cloud_warning.page:
                desc_cloud_warning.update()
        except RuntimeError:
            pass

    desc_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option("moondream-custom", "moondream-custom — rápido"),
            ft.dropdown.Option(
                "gemma3-4b-custom", "gemma3-4b-custom — melhor qualidade (mais lento)"
            ),
            ft.dropdown.Option("llava:7b", "llava:7b"),
            ft.dropdown.Option("minicpm-v", "minicpm-v"),
            ft.dropdown.Option("glm-4.6v-flash", "glm-4.6v-flash (nuvem)"),
            ft.dropdown.Option("gemini-2.5-flash", "gemini-2.5-flash (nuvem)"),
        ],
        value="moondream-custom",
        on_select=_on_desc_model_select,
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
            labeled_field(
                "Modelo vision", desc_dd, help_key="image.describe_model", page=page
            ),
            desc_cloud_warning,
            labeled_field(
                "Prompt", desc_prompt_tf, help_key="image.describe_prompt", page=page
            ),
            ft.Text(
                "Saída: .txt salvo em output/image/processed/",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )

    def _set_rembg_disabled(d: bool) -> None:
        rembg_dd.disabled = d
        bg_color_tf.disabled = d
        _bg_set(d)

    return AIRefs(
        rembg_block=rembg_block,
        describe_block=describe_block,
        set_rembg_disabled=_set_rembg_disabled,
        set_desc_disabled=lambda d: setattr(desc_dd, "disabled", d),
        get_rembg_model=lambda: rembg_dd.value or "u2net",
        get_rembg_bg_mode=lambda: _bg_get(),
        get_rembg_bg_color=lambda: (bg_color_tf.value or "#ffffff").strip(),
        get_rembg_bg_blur=lambda: int(blur_slider.value),
        get_desc_model=lambda: desc_dd.value or "moondream-custom",
        get_desc_prompt=lambda: (desc_prompt_tf.value or "").strip(),
    )
