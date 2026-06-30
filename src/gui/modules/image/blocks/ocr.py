"""OCR operation block for the image module (Tesseract → .txt)."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.core.image.ocr import is_available as _ocr_ok
from src.gui.theme.components import labeled_field
from src.gui.theme.tokens import Space, Type


class OCRRefs(NamedTuple):
    block: ft.Column
    set_disabled: Callable[[bool], None]
    get_lang: Callable[[], str]


def build_ocr_block(page: ft.Page) -> OCRRefs:
    """Build the OCR block (language picker). Card is disabled if Tesseract is absent."""
    available = _ocr_ok()

    warning = ft.Text(
        "⚠ Tesseract não encontrado. Instale o extra [ocr] e o binário.",
        color=ft.Colors.ERROR,
        size=Type.small.size,
        visible=not available,
    )
    lang_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option("por", "Português"),
            ft.dropdown.Option("eng", "Inglês"),
            ft.dropdown.Option("por+eng", "Português + Inglês"),
            ft.dropdown.Option("spa", "Espanhol"),
        ],
        value="por",
        disabled=not available,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            warning,
            labeled_field("Idioma", lang_dd, help_key="image.ocr", page=page),
            ft.Text(
                "Saída: .txt em output/image/processed/ (indexável no RAG)",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )

    return OCRRefs(
        block=block,
        set_disabled=lambda d: setattr(lang_dd, "disabled", d),
        get_lang=lambda: lang_dd.value or "por",
    )
