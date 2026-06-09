"""Slider factory with live value label."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.theme.tokens import Space, Type


def labeled_slider(
    *,
    label: str,
    value: float,
    min: float,
    max: float,
    divisions: int | None = None,
    fmt: Callable[[float], str] = lambda v: f"{v:.0f}",
    on_commit: Callable[[float], None] | None = None,
) -> tuple[ft.Column, ft.Slider]:
    """Slider with live label update on on_change and commit on on_change_end.

    Returns (column, slider) — read slider.value to get the current value.
    The label text updates on every drag tick; on_commit fires only when the
    user releases the thumb (on_change_end, which exists in Flet 0.85).

    Never calls page.update() — only updates the label Text widget directly.
    """
    value_text = ft.Text(
        fmt(value),
        size=Type.input.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.PRIMARY,
    )
    slider = ft.Slider(
        value=value,
        min=min,
        max=max,
        divisions=divisions,
        active_color=ft.Colors.PRIMARY,
        expand=True,
    )

    def _on_change(e: ft.ControlEvent) -> None:
        value_text.value = fmt(slider.value)
        try:
            if value_text.page:
                value_text.update()
        except RuntimeError:
            pass

    def _on_end(e: ft.ControlEvent) -> None:
        if on_commit:
            on_commit(slider.value)

    slider.on_change = _on_change
    slider.on_change_end = _on_end

    col = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Text(
                        label,
                        size=Type.label.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(expand=True),
                    value_text,
                ],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row([slider], spacing=0),
        ],
        spacing=Space.xs,
    )
    return col, slider
