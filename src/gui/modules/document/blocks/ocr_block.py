"""OCR operation block — language + DPI selectors, gated on Tesseract availability."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.core.document.ocr import is_available as _ocr_ok
from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Space, Type


class OcrRefs(NamedTuple):
    get_lang: Callable[[], str]
    get_dpi: Callable[[], int]
    available: bool


def build_ocr_block(page: ft.Page) -> tuple[ft.Column, OcrRefs]:
    """Build the OCR operation block.

    Disables the controls and shows a warning when Tesseract isn't installed.
    """
    available = _ocr_ok()

    warning = ft.Text(
        "⚠ Tesseract não encontrado.\n"
        "Instale o binário (PATH ou C:\\Program Files\\Tesseract-OCR) "
        "e rode: uv sync --extra ocr",
        color=ft.Colors.ERROR,
        size=Type.small.size,
        visible=not available,
    )

    _lang_get: list[Callable] = []
    lang_grid, _get_lang, _set_lang_disabled = segmented_selector(
        ["por", "eng", "por+eng", "spa"],
        "por",
        page,
        labels={
            "por": "Português",
            "eng": "English",
            "por+eng": "PT+EN",
            "spa": "Español",
        },
        columns=2,
    )
    _lang_get.append(_get_lang)
    _set_lang_disabled(not available)

    _dpi_get: list[Callable] = []
    dpi_grid, _get_dpi, _set_dpi_disabled = segmented_selector(
        ["150", "300"],
        "300",
        page,
        labels={"150": "150 dpi", "300": "300 dpi"},
        columns=2,
    )
    _dpi_get.append(_get_dpi)
    _set_dpi_disabled(not available)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            warning,
            ft.Row(
                [
                    section_label("Idioma"),
                    ft.Container(expand=True),
                    help_icon_for("document.ocr", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            lang_grid,
            section_label("Resolução (DPI)"),
            dpi_grid,
            ft.Text(
                "Texto nativo é usado quando existe; OCR só nas páginas escaneadas.\n"
                "Saída: .txt em output/document/processed/",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )
    return block, OcrRefs(
        get_lang=lambda: _lang_get[0](),
        get_dpi=lambda: int(_dpi_get[0]()),
        available=available,
    )
