"""Fábricas de layout — scaffold de módulo, seção e divisores."""
from __future__ import annotations

import flet as ft

from src.gui.theme.tokens import Layout, Space, Type


def _label_row(text: str, help_key: str | None, page: ft.Page | None) -> ft.Control:
    from src.gui.theme.components.help import help_icon_for
    label = ft.Text(
        text,
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    icon = help_icon_for(help_key, page) if help_key else None
    if icon:
        return ft.Row(
            [label, icon],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return label


def section_label(text: str) -> ft.Text:
    """Rótulo de seção simples (13px W600 ON_SURFACE_VARIANT), sem ⓘ."""
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


def section(
    label: str,
    *controls: ft.Control,
    help_key: str | None = None,
    page: ft.Page | None = None,
) -> ft.Column:
    """Grupo de seção com rótulo + ⓘ opcional no topo."""
    header = _label_row(label, help_key, page)
    return ft.Column(controls=[header, *controls], spacing=Space.sm)


def hairline(vertical: bool = False) -> ft.Control:
    """Divisor fino de 1px usando outline_variant do tema."""
    if vertical:
        return ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT)
    return ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT)
