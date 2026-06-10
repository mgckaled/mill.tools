"""QR code operation block — data input, size slider, format selector."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, labeled_field, section_label, segmented_selector, slider_row
from src.gui.theme.tokens import Layout, Space


class QrRefs(NamedTuple):
    get_data: Callable[[], str]
    get_size: Callable[[], int]
    get_fmt: Callable[[], str]


def build_qr_block(page: ft.Page) -> tuple[ft.Column, QrRefs]:
    """Build the QR code operation block."""
    data_field = ft.TextField(
        hint_text="URL ou texto para codificar",
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    _size: list[int] = [300]

    def _on_size(v: float) -> None:
        _size[0] = int(v)

    size_col = slider_row(
        "Tamanho (px)",
        300, 100, 600,
        divisions=10,
        on_change=_on_size,
        help_key="document.qr_size",
        page=page,
    )

    _fmt_get: list[Callable] = []
    fmt_grid, _get_fmt, _ = segmented_selector(
        ["png", "jpg"], "png", page,
        labels={"png": "PNG", "jpg": "JPG"},
        columns=2,
    )
    _fmt_get.append(_get_fmt)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            labeled_field("Conteúdo / URL", data_field),
            size_col,
            section_label("Formato"),
            fmt_grid,
        ],
    )
    return block, QrRefs(
        get_data=lambda: data_field.value or "",
        get_size=lambda: _size[0],
        get_fmt=lambda: _fmt_get[0](),
    )
