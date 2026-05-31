"""Fábricas de layout — scaffold de módulo, seção e divisores."""
from __future__ import annotations

import flet as ft

from src.gui.theme.tokens import Layout, Space, Type


def section_label(text: str) -> ft.Text:
    """Rótulo de seção (13px W600 ON_SURFACE_VARIANT) — uso standalone no layout."""
    return ft.Text(
        text,
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def module_scaffold(form: ft.Control, panel: ft.Control) -> ft.Row:
    """Layout padrão dos módulos: form fixo (380px) | divisor | painel expand."""
    return ft.Row(
        controls=[
            ft.Container(content=form, width=Layout.form_width),
            ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=panel,
                expand=True,
                padding=ft.Padding(
                    left=Space.md, right=Space.md,
                    top=Space.sm, bottom=Space.sm,
                ),
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def section(label: str, *controls: ft.Control) -> ft.Column:
    """Grupo de seção com rótulo label no topo."""
    return ft.Column(
        controls=[
            ft.Text(
                label,
                size=Type.label.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            *controls,
        ],
        spacing=Space.sm,
    )


def hairline(vertical: bool = False) -> ft.Control:
    """Divisor fino de 1px usando outline_variant do tema."""
    if vertical:
        return ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT)
    return ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT)
