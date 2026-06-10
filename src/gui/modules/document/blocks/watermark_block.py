"""Watermark operation block — text, opacity, position."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import labeled_field, section_label, segmented_selector, slider_row
from src.gui.theme.tokens import Layout, Space


class WatermarkRefs(NamedTuple):
    get_text: Callable[[], str]
    get_opacity: Callable[[], float]
    get_position: Callable[[], str]


def build_watermark_block(page: ft.Page) -> tuple[ft.Column, WatermarkRefs]:
    """Build the watermark operation block."""
    text_field = ft.TextField(
        hint_text="Texto da marca d'água",
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    _opacity: list[float] = [0.3]

    def _on_opacity(v: float) -> None:
        _opacity[0] = round(v, 2)

    opacity_col = slider_row(
        "Opacidade",
        0.3, 0.1, 0.9,
        divisions=8,
        on_change=_on_opacity,
    )

    _pos_get: list[Callable] = []
    pos_grid, _get_pos, _ = segmented_selector(
        ["center", "top", "bottom"],
        "center",
        page,
        labels={"center": "Centro", "top": "Topo", "bottom": "Base"},
        columns=3,
    )
    _pos_get.append(_get_pos)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            labeled_field("Texto da marca d'água", text_field),
            opacity_col,
            section_label("Posição"),
            pos_grid,
        ],
    )
    return block, WatermarkRefs(
        get_text=lambda: text_field.value or "",
        get_opacity=lambda: _opacity[0],
        get_position=lambda: _pos_get[0](),
    )
