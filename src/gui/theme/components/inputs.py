"""Fábricas de inputs e controles de formulário."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.theme.tokens import Space, Type


def labeled_field(
    label: str,
    control: ft.Control,
    helper: str | None = None,
    help_key: str | None = None,
    page: ft.Page | None = None,
) -> ft.Column:
    """Rótulo acima do controle com helper opcional abaixo e ⓘ opcional."""
    from src.gui.theme.components.help import help_icon_for
    icon = help_icon_for(help_key, page) if help_key else None
    label_text = ft.Text(
        label,
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    label_row: ft.Control = (
        ft.Row(
            [label_text, icon],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if icon else label_text
    )
    items: list[ft.Control] = [label_row, control]
    if helper:
        items.append(
            ft.Text(helper, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT)
        )
    return ft.Column(controls=items, spacing=Space.sm)


def switch_row(
    label: str,
    value: bool,
    on_change: Callable | None = None,
    label_size: float | None = None,
) -> ft.Switch:
    """Switch com rótulo inline e cor ativa do tema (primary = dourado)."""
    return ft.Switch(
        label=label,
        value=value,
        on_change=on_change,
        label_text_style=ft.TextStyle(size=label_size or Type.body.size),
        active_color=ft.Colors.PRIMARY,
    )


def slider_row(
    label: str,
    value: float,
    min_val: float = 1.0,
    max_val: float = 10.0,
    divisions: int | None = None,
    on_change: Callable | None = None,
    help_key: str | None = None,
    page: ft.Page | None = None,
) -> ft.Column:
    """Rótulo + slider com cor ativa do tema (primary = dourado) e ⓘ opcional."""
    from src.gui.theme.components.help import help_icon_for
    icon = help_icon_for(help_key, page) if help_key else None
    label_text = ft.Text(
        label,
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    label_row: ft.Control = (
        ft.Row(
            [label_text, icon],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        if icon else label_text
    )
    slider = ft.Slider(
        value=value,
        min=min_val,
        max=max_val,
        divisions=divisions,
        active_color=ft.Colors.PRIMARY,
        on_change=on_change,
        expand=True,
    )
    return ft.Column(controls=[label_row, slider], spacing=Space.xs)
