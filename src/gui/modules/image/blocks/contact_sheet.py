"""Contact sheet operation block for the image module."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Layout, Space, Type


class ContactSheetRefs(NamedTuple):
    get_cols: Callable[[], int]
    get_thumb_size: Callable[[], int]
    get_gap: Callable[[], int]
    get_bg_color: Callable[[], str]


def build_contact_sheet_block(page: ft.Page) -> tuple[ft.Column, ContactSheetRefs]:
    """Build the contact sheet operation block.

    Returns the Column widget and a ContactSheetRefs for value collection.
    """
    cols_col, cols_slider = labeled_slider(
        label="Colunas", value=4.0, min=1.0, max=10.0, divisions=9,
        fmt=lambda v: f"{int(v)}",
    )
    thumb_col, thumb_slider = labeled_slider(
        label="Tamanho das miniaturas (px)", value=200.0, min=50.0, max=500.0, divisions=45,
        fmt=lambda v: f"{int(v)}",
    )
    gap_col, gap_slider = labeled_slider(
        label="Espaçamento (px)", value=10.0, min=0.0, max=50.0, divisions=50,
        fmt=lambda v: f"{int(v)}",
    )

    bg_color_tf = ft.TextField(
        value="#ffffff",
        label="Cor de fundo (hex)",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Colagem"), ft.Container(expand=True), help_icon_for("image.contact_sheet", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            cols_col,
            thumb_col,
            gap_col,
            bg_color_tf,
        ],
    )

    refs = ContactSheetRefs(
        get_cols=lambda: max(1, int(cols_slider.value or 4)),
        get_thumb_size=lambda: max(10, int(thumb_slider.value or 200)),
        get_gap=lambda: max(0, int(gap_slider.value or 10)),
        get_bg_color=lambda: (bg_color_tf.value or "#ffffff").strip(),
    )
    return block, refs
