"""Border operation block for the image module."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Layout, Space, Type


class BorderRefs(NamedTuple):
    get_padding: Callable[[], int]
    get_color: Callable[[], str]
    get_fill_alpha: Callable[[], bool]


def build_border_block(page: ft.Page) -> tuple[ft.Column, BorderRefs]:
    """Build the border operation block.

    Returns the Column widget and a BorderRefs for value collection.
    """
    pad_col, pad_slider = labeled_slider(
        label="Espessura",
        value=20.0,
        min=1.0,
        max=200.0,
        divisions=199,
        fmt=lambda v: f"{int(v)}px",
    )

    color_tf = ft.TextField(
        value="#000000",
        label="Cor da borda (hex)",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )
    fill_alpha_sw = ft.Switch(
        label="Preencher alpha pela cor da borda",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Borda"),
                    ft.Container(expand=True),
                    help_icon_for("image.border", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            pad_col,
            color_tf,
            fill_alpha_sw,
        ],
    )

    refs = BorderRefs(
        get_padding=lambda: int(pad_slider.value),
        get_color=lambda: (color_tf.value or "#000000").strip(),
        get_fill_alpha=lambda: bool(fill_alpha_sw.value),
    )
    return block, refs
