"""PDF-to-images operation block — format + DPI selectors."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space


class PdfToImagesRefs(NamedTuple):
    get_fmt: Callable[[], str]
    get_dpi: Callable[[], int]


def build_pdf_to_images_block(page: ft.Page) -> tuple[ft.Column, PdfToImagesRefs]:
    """Build the pdf-to-images operation block."""
    _fmt_get: list[Callable] = []
    fmt_grid, _get_fmt, _ = segmented_selector(
        ["jpg", "png"],
        "jpg",
        page,
        labels={"jpg": "JPG", "png": "PNG"},
        columns=2,
    )
    _fmt_get.append(_get_fmt)

    _dpi_get: list[Callable] = []
    dpi_grid, _get_dpi, _ = segmented_selector(
        ["72", "96", "150", "300"],
        "150",
        page,
        labels={"72": "72 dpi", "96": "96 dpi", "150": "150 dpi", "300": "300 dpi"},
        columns=2,
    )
    _dpi_get.append(_get_dpi)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            section_label("Formato"),
            fmt_grid,
            ft.Row(
                [
                    section_label("Resolução (DPI)"),
                    ft.Container(expand=True),
                    help_icon_for("document.dpi", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            dpi_grid,
        ],
    )
    return block, PdfToImagesRefs(
        get_fmt=lambda: _fmt_get[0](),
        get_dpi=lambda: int(_dpi_get[0]()),
    )
