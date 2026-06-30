"""Rotate operation block — angle selector + page range."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import labeled_field, section_label, segmented_selector
from src.gui.theme.tokens import Layout, Space


class RotateRefs(NamedTuple):
    get_angle: Callable[[], int]
    get_pages: Callable[[], str]


def build_rotate_block(page: ft.Page) -> tuple[ft.Column, RotateRefs]:
    """Build the rotate operation block."""
    _angle_get: list[Callable] = []
    angle_grid, _get, _ = segmented_selector(
        ["90", "180", "270"],
        "90",
        page,
        labels={"90": "90°", "180": "180°", "270": "270°"},
        columns=3,
    )
    _angle_get.append(_get)

    pages_field = ft.TextField(
        hint_text='ex.: "all", "1,3,5"',
        value="all",
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            section_label("Ângulo"),
            angle_grid,
            labeled_field("Páginas (all = todas)", pages_field),
        ],
    )
    return block, RotateRefs(
        get_angle=lambda: int(_angle_get[0]()),
        get_pages=lambda: pages_field.value or "all",
    )
