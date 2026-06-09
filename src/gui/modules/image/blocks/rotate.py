"""Rotate operation block for the image module."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space, Type


class RotateRefs(NamedTuple):
    get_angle: Callable[[], int]
    get_flip_h: Callable[[], bool]
    get_flip_v: Callable[[], bool]
    get_exif_auto: Callable[[], bool]


def build_rotate_block(page: ft.Page) -> tuple[ft.Column, RotateRefs]:
    """Build the rotate operation block.

    Returns the Column widget and a RotateRefs for value collection.
    """
    _angle_get: list[Callable] = []
    angle_grid, _get, _set_disabled = segmented_selector(
        ["0", "90", "180", "270"],
        "0",
        page,
        labels={"0": "0°", "90": "90°", "180": "180°", "270": "270°"},
        columns=4,
    )
    _angle_get.append(_get)

    flip_h_sw = ft.Switch(
        label="Espelhar horizontal",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )
    flip_v_sw = ft.Switch(
        label="Espelhar vertical",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )
    exif_sw = ft.Switch(
        label="Corrigir orientação EXIF",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Girar"), ft.Container(expand=True), help_icon_for("image.rotate", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Ângulo (sentido horário)"),
            angle_grid,
            flip_h_sw,
            flip_v_sw,
            exif_sw,
        ],
    )

    refs = RotateRefs(
        get_angle=lambda: int(_angle_get[0]()),
        get_flip_h=lambda: bool(flip_h_sw.value),
        get_flip_v=lambda: bool(flip_v_sw.value),
        get_exif_auto=lambda: bool(exif_sw.value),
    )
    return block, refs
