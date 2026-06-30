"""Favicon operation block for the image module."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.tokens import Space, Type


_ALL_SIZES = [16, 32, 48, 64, 128, 256]


class FaviconRefs(NamedTuple):
    get_sizes: Callable[[], list[int]]


def build_favicon_block(page: ft.Page) -> tuple[ft.Column, FaviconRefs]:
    """Build the favicon operation block.

    Returns the Column widget and a FaviconRefs for value collection.
    """
    checks: dict[int, ft.Checkbox] = {
        s: ft.Checkbox(
            label=f"{s}px",
            value=True,
            active_color=ft.Colors.PRIMARY,
            label_style=ft.TextStyle(size=Type.body.size),
        )
        for s in _ALL_SIZES
    }

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Favicon"),
                    ft.Container(expand=True),
                    help_icon_for("image.favicon", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Tamanhos (.ico multires)"),
            ft.Row(
                [checks[s] for s in _ALL_SIZES],
                wrap=True,
                spacing=8,
                run_spacing=4,
            ),
        ],
    )

    def _get_sizes() -> list[int]:
        sizes = [s for s, chk in checks.items() if chk.value]
        return sizes or [32]

    refs = FaviconRefs(get_sizes=_get_sizes)
    return block, refs
