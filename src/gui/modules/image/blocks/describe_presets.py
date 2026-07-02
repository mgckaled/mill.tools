"""Describe-prompt preset selector (icon cards, 2x3 grid) for the image module.

Six fixed presets for the "Descrição IA" tab's prompt field. Mirrors the card
style of ``src/gui/components/profile_selector.py`` (icon + label, tooltip
carries the longer description) but is self-contained, since these presets
aren't part of the ``src.analysis`` profile system.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Color, IconSize, Motion, Radius, Space, Type


class _PresetMeta(NamedTuple):
    id: str
    icon: str
    label: str
    description: str


_PRESETS: tuple[_PresetMeta, ...] = (
    _PresetMeta(
        "detailed",
        "ARTICLE_OUTLINED",
        "Detalhada",
        "Descrição completa: objetos, contexto, cores e texto visível.",
    ),
    _PresetMeta(
        "short",
        "SHORT_TEXT",
        "Objetiva",
        "Uma frase curta, como legenda — boa para alt-text.",
    ),
    _PresetMeta(
        "technical",
        "PALETTE_OUTLINED",
        "Técnica",
        "Composição, enquadramento, luz e estilo — olhar de fotógrafo/artista.",
    ),
    _PresetMeta(
        "text",
        "TEXT_FIELDS_OUTLINED",
        "Extração de texto",
        "Transcreve literalmente todo o texto visível na imagem.",
    ),
    _PresetMeta(
        "objects",
        "FORMAT_LIST_BULLETED_OUTLINED",
        "Lista de objetos",
        "Enumera em tópicos os objetos e elementos identificáveis.",
    ),
    _PresetMeta(
        "narrative",
        "AUTO_STORIES_OUTLINED",
        "Narrativa",
        "Descrição criativa: atmosfera, emoção e a história da imagem.",
    ),
)

_PRESET_IDS = {p.id for p in _PRESETS}
_COLUMNS = 3


def build_describe_preset_selector(
    page: ft.Page,
    value: str = "detailed",
    on_select: Callable[[str], None] | None = None,
) -> tuple[ft.Column, Callable[[], str]]:
    """Build the 2x3 preset card grid.

    Args:
        page: Flet page (used for theme palette + updates).
        value: Initially selected preset id.
        on_select: Optional callback receiving the new preset id on selection
            (fires even when re-tapping the already-selected card).

    Returns:
        ``(control, get_value)``.
    """
    _selected: list[str] = [value if value in _PRESET_IDS else "detailed"]
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
        prev = _selected[0]
        if pid != prev:
            _selected[0] = pid
            _restyle(prev, False)
            _restyle(pid, True)
        # Always fire on_select, even re-tapping the active card: it lets the
        # caller reapply the preset's prompt text after the user has edited it.
        if on_select:
            on_select(pid)
        page.update()

    def _make_card(meta: _PresetMeta) -> ft.GestureDetector:
        active = meta.id == _selected[0]
        icon = ft.Icon(
            getattr(ft.Icons, meta.icon, ft.Icons.ARTICLE_OUTLINED),
            size=IconSize.xl,
            color=_accent(active),
        )
        text = ft.Text(
            meta.label,
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
            tooltip=meta.description,
            animate=ft.Animation(Motion.fast, ft.AnimationCurve.EASE_IN_OUT),
        )
        _ctrs[meta.id] = container
        _icons[meta.id] = icon
        _texts[meta.id] = text
        return ft.GestureDetector(
            mouse_cursor=Cursor.interactive,
            on_tap=lambda _e, _p=meta.id: _on_tap(_p),
            content=container,
            expand=True,
        )

    cards = [_make_card(m) for m in _PRESETS]
    rows = [
        ft.Row(controls=cards[i : i + _COLUMNS], spacing=Space.sm)
        for i in range(0, len(cards), _COLUMNS)
    ]
    grid = ft.Column(controls=rows, spacing=Space.sm)

    def _get_value() -> str:
        return _selected[0]

    return grid, _get_value
