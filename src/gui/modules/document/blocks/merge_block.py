"""Merge operation block — no extra parameters."""

from __future__ import annotations

import flet as ft

from src.gui.theme.tokens import Space, Type


def build_merge_block() -> ft.Column:
    """Build the merge block (info-only, no inputs)."""
    return ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Text(
                "Selecione dois ou mais PDFs para unir em um único arquivo.",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ),
        ],
    )
