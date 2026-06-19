"""Grouped analysis-profile selector (icon cards) for the GUI forms.

Renders the ``src.analysis`` profiles as labelled groups of icon+label cards.
One profile is selected at a time; selecting a card calls ``on_change`` with the
profile id. Reused by the Transcription form and the Documents analyze block.

Design system: each card is a single ``ft.GestureDetector`` (no ``ink=True``)
over an animated ``ft.Container``; the selected card uses the golden accent.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.analysis import GROUPS, PROFILES
from src.gui.theme.components import Cursor, section_label
from src.gui.theme.tokens import Color, IconSize, Motion, Radius, Space, Type

_COLUMNS = 3


def build_profile_selector(
    page: ft.Page,
    value: str,
    on_change: Callable[[str], None] | None = None,
) -> tuple[ft.Column, Callable[[], str], Callable[[str], None]]:
    """Build a grouped profile selector.

    Args:
        page: Flet page (used for theme palette + updates).
        value: Initially selected profile id.
        on_change: Optional callback receiving the new profile id on selection.

    Returns:
        ``(control, get_value, set_value)``.
    """
    _selected: list[str] = [value if value in PROFILES else "default"]
    _ctrs: dict[str, ft.Container] = {}
    _icons: dict[str, ft.Icon] = {}
    _texts: dict[str, ft.Text] = {}

    def _palette():
        return Color.dark if page.theme_mode != ft.ThemeMode.LIGHT else Color.light

    def _border(active: bool) -> ft.Border:
        c = _palette()
        side = ft.BorderSide(
            1.5 if active else 1.0, c.primary if active else c.outline_variant
        )
        return ft.Border(left=side, right=side, top=side, bottom=side)

    def _bgcolor(active: bool) -> str:
        c = _palette()
        return (
            ft.Colors.with_opacity(0.14, c.primary) if active else ft.Colors.TRANSPARENT
        )

    def _accent(active: bool) -> str:
        c = _palette()
        return c.primary if active else c.text_secondary

    def _restyle(pid: str, active: bool) -> None:
        _ctrs[pid].border = _border(active)
        _ctrs[pid].bgcolor = _bgcolor(active)
        _icons[pid].color = _accent(active)
        _texts[pid].color = _accent(active)

    def _on_tap(pid: str) -> None:
        if pid == _selected[0]:
            return
        prev = _selected[0]
        _selected[0] = pid
        _restyle(prev, False)
        _restyle(pid, True)
        if on_change:
            on_change(pid)
        page.update()

    def _make_card(pid: str) -> ft.GestureDetector:
        profile = PROFILES[pid]
        active = pid == _selected[0]
        icon = ft.Icon(
            getattr(ft.Icons, profile.icon, ft.Icons.ARTICLE_OUTLINED),
            size=IconSize.xl,
            color=_accent(active),
        )
        text = ft.Text(
            profile.label,
            size=Type.small.size,
            text_align=ft.TextAlign.CENTER,
            color=_accent(active),
            max_lines=1,
        )
        container = ft.Container(
            content=ft.Column(
                controls=[icon, text],
                spacing=Space.xxs,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            border=_border(active),
            bgcolor=_bgcolor(active),
            border_radius=Radius.sm,
            padding=ft.Padding(left=4, right=4, top=10, bottom=10),
            expand=True,
            alignment=ft.Alignment.CENTER,
            tooltip=profile.persona,
            animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
        )
        _ctrs[pid] = container
        _icons[pid] = icon
        _texts[pid] = text
        return ft.GestureDetector(
            mouse_cursor=Cursor.interactive,
            on_tap=lambda _e, _p=pid: _on_tap(_p),
            content=container,
            expand=True,
        )

    sections: list[ft.Control] = []
    for group in GROUPS:
        sections.append(section_label(group.label))
        cards = [_make_card(pid) for pid in group.profile_ids if pid in PROFILES]
        rows = [
            ft.Row(controls=cards[i : i + _COLUMNS], spacing=Space.sm)
            for i in range(0, len(cards), _COLUMNS)
        ]
        sections.extend(rows)

    grid = ft.Column(controls=sections, spacing=Space.sm)

    def _get_value() -> str:
        return _selected[0]

    def _set_value(pid: str) -> None:
        if pid not in PROFILES or pid == _selected[0]:
            return
        prev = _selected[0]
        _selected[0] = pid
        _restyle(prev, False)
        _restyle(pid, True)

    return grid, _get_value, _set_value
