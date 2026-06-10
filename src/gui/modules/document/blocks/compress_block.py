"""Compress operation block — image quality slider."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, slider_row
from src.gui.theme.tokens import Space


class CompressRefs(NamedTuple):
    get_image_quality: Callable[[], int]


def build_compress_block(page: ft.Page) -> tuple[ft.Column, CompressRefs]:
    """Build the compress operation block."""
    _quality: list[int] = [75]

    def _on_change(e) -> None:
        _quality[0] = int(e.control.value)

    quality_col = slider_row(
        "Qualidade da imagem",
        75, 50, 95,
        divisions=9,
        on_change=_on_change,
        help_key="document.image_quality",
        page=page,
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[quality_col],
    )
    return block, CompressRefs(get_image_quality=lambda: _quality[0])
