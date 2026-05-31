"""Fábricas de botões e seleção segmentada."""
from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.theme.tokens import Color, Motion, Radius, Space


def primary_button(
    text: str,
    icon: str | None = None,
    on_click: Callable | None = None,
    loading: bool = False,
) -> ft.FilledButton:
    """Ação primária — herda primary (dourado) do tema automaticamente."""
    return ft.FilledButton(
        text="Executando..." if loading else text,
        icon=ft.Icons.HOURGLASS_EMPTY if loading else icon,
        disabled=loading,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=Radius.md),
            animation_duration=Motion.fast,
        ),
    )


def secondary_button(
    text: str,
    icon: str | None = None,
    on_click: Callable | None = None,
) -> ft.OutlinedButton:
    """Ação secundária — contorno sem preenchimento."""
    return ft.OutlinedButton(
        text=text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=Radius.md),
        ),
    )


def danger_button(
    text: str,
    icon: str | None = None,
    on_click: Callable | None = None,
) -> ft.TextButton:
    """Ação destrutiva — ghost vermelho (nunca usa o dourado primário)."""
    err = Color.log.error
    return ft.TextButton(
        text=text,
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: err,
                ft.ControlState.HOVERED: err,
                ft.ControlState.PRESSED: err,
            },
            overlay_color=ft.Colors.with_opacity(0.1, err),
        ),
    )


def segmented_selector(
    options: list[str],
    value: str,
    page: ft.Page,
    on_change: Callable[[str], None] | None = None,
    columns: int = 3,
    labels: dict[str, str] | None = None,
) -> tuple[ft.Column, Callable[[], str], Callable[[bool], None]]:
    """Grade N×columns de chips clicáveis com cores do DS.

    Returns:
        (control, get_value, set_disabled)
    """
    _selected: list[str] = [value]
    _disabled: list[bool] = [False]
    _ctrs: dict[str, ft.Container] = {}
    _texts: dict[str, ft.Text] = {}

    def _palette():
        return Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light

    def _border(active: bool) -> ft.Border:
        c = _palette()
        color = c.primary if active else c.outline
        width = 1.5 if active else 1.0
        s = ft.BorderSide(width, color)
        return ft.Border(left=s, right=s, top=s, bottom=s)

    def _bgcolor(active: bool) -> str:
        c = _palette()
        return ft.Colors.with_opacity(0.14, c.primary) if active else ft.Colors.TRANSPARENT

    def _text_color(active: bool) -> str:
        c = _palette()
        return c.primary if active else c.text_secondary

    def _on_click(_e, opt: str) -> None:
        if _disabled[0] or opt == _selected[0]:
            return
        prev = _selected[0]
        _selected[0] = opt
        _ctrs[prev].border = _border(False)
        _ctrs[prev].bgcolor = _bgcolor(False)
        _texts[prev].color = _text_color(False)
        _ctrs[opt].border = _border(True)
        _ctrs[opt].bgcolor = _bgcolor(True)
        _texts[opt].color = _text_color(True)
        if on_change:
            on_change(opt)
        page.update()

    def _make_chip(opt: str) -> ft.Container:
        active = opt == _selected[0]
        display = labels[opt] if labels else opt
        t = ft.Text(display, size=14, text_align=ft.TextAlign.CENTER, color=_text_color(active))
        c = ft.Container(
            content=t,
            border=_border(active),
            bgcolor=_bgcolor(active),
            border_radius=Radius.sm,
            padding=ft.Padding(left=2, right=2, top=7, bottom=7),
            expand=True,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, _o=opt: _on_click(e, _o),
            animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
            ink=True,
        )
        _ctrs[opt] = c
        _texts[opt] = t
        return c

    chips = [_make_chip(o) for o in options]
    rows = [ft.Row(controls=chips[i:i + columns], spacing=Space.sm) for i in range(0, len(chips), columns)]
    grid = ft.Column(controls=rows, spacing=Space.sm)

    def _get_value() -> str:
        return _selected[0]

    def _set_disabled(disabled: bool) -> None:
        _disabled[0] = disabled
        grid.opacity = 0.4 if disabled else 1.0

    return grid, _get_value, _set_disabled
