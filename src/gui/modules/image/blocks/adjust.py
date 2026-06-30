"""Adjust operation block for the image module."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Space


class AdjustRefs(NamedTuple):
    get_brightness: Callable[[], float]
    get_contrast: Callable[[], float]
    get_color: Callable[[], float]
    get_sharpness: Callable[[], float]


def build_adjust_block(page: ft.Page) -> tuple[ft.Column, AdjustRefs]:
    """Build the adjust operation block.

    Returns the Column widget and an AdjustRefs for value collection.
    """
    bright_col, bright_slider = labeled_slider(
        label="Brilho",
        value=1.0,
        min=0.1,
        max=2.0,
        divisions=19,
        fmt=lambda v: f"{v:.1f}",
    )
    contrast_col, contrast_slider = labeled_slider(
        label="Contraste",
        value=1.0,
        min=0.1,
        max=2.0,
        divisions=19,
        fmt=lambda v: f"{v:.1f}",
    )
    color_col, color_slider = labeled_slider(
        label="Saturação",
        value=1.0,
        min=0.1,
        max=2.0,
        divisions=19,
        fmt=lambda v: f"{v:.1f}",
    )
    sharpness_col, sharpness_slider = labeled_slider(
        label="Nitidez",
        value=1.0,
        min=0.1,
        max=2.0,
        divisions=19,
        fmt=lambda v: f"{v:.1f}",
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Ajustes"),
                    ft.Container(expand=True),
                    help_icon_for("image.adjust", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bright_col,
            contrast_col,
            color_col,
            sharpness_col,
        ],
    )

    refs = AdjustRefs(
        get_brightness=lambda: float(bright_slider.value or 1.0),
        get_contrast=lambda: float(contrast_slider.value or 1.0),
        get_color=lambda: float(color_slider.value or 1.0),
        get_sharpness=lambda: float(sharpness_slider.value or 1.0),
    )
    return block, refs
