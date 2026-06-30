"""Extract-text operation block — no extra parameters."""

from __future__ import annotations

import flet as ft

from src.gui.theme.tokens import Space, Type


def build_extract_text_block() -> ft.Column:
    """Build the extract-text block (info-only, no inputs)."""
    return ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Text(
                "Extrai todo o texto embutido do PDF e salva em .txt. "
                "PDFs escaneados (sem texto) retornarão arquivo vazio.",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
                no_wrap=False,
            ),
        ],
    )
