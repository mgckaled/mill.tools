"""Resize operation block for the image module."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Layout, Space, Type


def _parse_int(tf: ft.TextField, default: int) -> int:
    try:
        v = int((tf.value or "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


class ResizeRefs(NamedTuple):
    get_mode: Callable[[], str]
    get_width: Callable[[], int | None]
    get_height: Callable[[], int | None]
    get_scale_pct: Callable[[], float]


def build_resize_block(page: ft.Page) -> tuple[ft.Column, ResizeRefs]:
    """Build the resize operation block.

    Returns the Column widget and a ResizeRefs for value collection.
    """
    _mode_get: list[Callable] = []

    w_tf = ft.TextField(
        hint_text="Largura px (opcional)",
        keyboard_type=ft.KeyboardType.NUMBER,
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    h_tf = ft.TextField(
        hint_text="Altura px (opcional)",
        keyboard_type=ft.KeyboardType.NUMBER,
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    wh_row = ft.Row([w_tf, h_tf], spacing=8)

    scale_col, scale_slider = labeled_slider(
        label="Escala",
        value=100.0,
        min=1.0,
        max=400.0,
        divisions=399,
        fmt=lambda v: f"{int(v)}%",
    )
    scale_col.visible = False

    def _on_mode_change(mode: str) -> None:
        wh_row.visible = mode in ("contain", "exact")
        scale_col.visible = mode == "scale_pct"
        try:
            if wh_row.page:
                wh_row.page.update()
        except RuntimeError:
            pass

    mode_grid, _mget, _mset = segmented_selector(
        ["contain", "exact", "scale_pct"],
        "contain",
        page,
        on_change=_on_mode_change,
        labels={"contain": "Caber", "exact": "Exato", "scale_pct": "Escala %"},
        columns=3,
    )
    _mode_get.append(_mget)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Redimensionar"),
                    ft.Container(expand=True),
                    help_icon_for("image.resize", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Modo"),
            mode_grid,
            ft.Row([section_label("Dimensões")]),
            wh_row,
            scale_col,
        ],
    )

    refs = ResizeRefs(
        get_mode=lambda: _mode_get[0](),
        get_width=lambda: _parse_int(w_tf, 0) or None,
        get_height=lambda: _parse_int(h_tf, 0) or None,
        get_scale_pct=lambda: float(scale_slider.value),
    )
    return block, refs
