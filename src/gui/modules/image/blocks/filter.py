"""Filter operation block for the image module."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space


class FilterRefs(NamedTuple):
    get_type: Callable[[], str]


def build_filter_block(page: ft.Page) -> tuple[ft.Column, FilterRefs]:
    """Build the filter operation block.

    Returns the Column widget and a FilterRefs for value collection.
    """
    _type_get: list[Callable] = []
    grid, _get, _set_disabled = segmented_selector(
        ["blur", "sharpen", "autocontrast", "equalize", "grayscale"],
        "blur",
        page,
        labels={
            "blur": "Blur",
            "sharpen": "Nitidez",
            "autocontrast": "Autocontraste",
            "equalize": "Equalizar",
            "grayscale": "Cinza",
        },
        columns=3,
    )
    _type_get.append(_get)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Filtros"), ft.Container(expand=True), help_icon_for("image.filter", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Tipo de filtro"),
            grid,
        ],
    )

    refs = FilterRefs(get_type=lambda: _type_get[0]())
    return block, refs
