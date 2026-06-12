"""Split operation block — page range input."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, labeled_field, section_label
from src.gui.theme.tokens import Layout, Space


class SplitRefs(NamedTuple):
    get_pages: Callable[[], str]


def build_split_block(page: ft.Page) -> tuple[ft.Column, SplitRefs]:
    """Build the split operation block."""
    pages_field = ft.TextField(
        hint_text='ex.: "1-3,5,8-"',
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )
    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Páginas"), ft.Container(expand=True),
                 help_icon_for("document.pages", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            labeled_field("Intervalo de páginas", pages_field),
        ],
    )
    return block, SplitRefs(get_pages=lambda: pages_field.value or "")
