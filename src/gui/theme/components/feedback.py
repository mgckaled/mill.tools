"""Fábricas de feedback visual: log, títulos, cards de resumo, spinner."""

from __future__ import annotations

import math
from typing import Callable

import flet as ft

from src.gui.theme.tokens import Color, Motion, Radius, Space, Type

_PREFIX_COLORS: dict[str, str] = {
    "[i]": Color.log.info,
    "[*]": Color.log.step,
    "[~]": Color.log.work,
    "[✓]": Color.log.ok,
    "[!]": Color.log.error,
    "[»]": Color.log.muted,
    "[d]": Color.log.muted,
}


def log_line(text: str) -> ft.Text:
    """Linha de log monoespaçada com cor semântica por prefixo.

    Linhas com prefixo [x] usam no_wrap=True (linhas de status curtas).
    Texto sem prefixo (ex: segmentos de transcrição) quebra normalmente.
    """
    color = Color.log.text
    is_prefixed = False
    for prefix, c in _PREFIX_COLORS.items():
        if text.startswith(prefix):
            color = c
            is_prefixed = True
            break
    return ft.Text(
        text,
        font_family=Type.FONT_MONO,
        size=Type.mono.size,
        color=color,
        selectable=True,
        no_wrap=is_prefixed,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def section_title(text: str) -> ft.Text:
    """Título de seção de resultados (22px bold)."""
    return ft.Text(text, size=Type.title.size, weight=ft.FontWeight.W_600)


def helper_text(text: str) -> ft.Text:
    """Texto de apoio caption em cor secundária."""
    return ft.Text(text, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT)


def spinner() -> tuple[ft.Image, Callable[[], None], Callable[[], None]]:
    """Cata-vento animado do mill.tools.

    Returns:
        (control, start, stop) — gira continuamente enquanto start() estiver ativo;
        stop() interrompe sem resetar o ângulo.
    """
    from src.gui.assets import b64

    _spinning: list[bool] = [False]
    img = ft.Image(
        src=b64("mill-symbol.png"),
        width=22,
        height=22,
        rotate=ft.Rotate(angle=0, alignment=ft.Alignment.CENTER),
        animate_rotation=ft.Animation(Motion.spin, ft.AnimationCurve.LINEAR),
    )

    def _step(_=None) -> None:
        if _spinning[0]:
            img.rotate.angle += 2 * math.pi
            img.update()

    img.on_animation_end = _step

    def start() -> None:
        if not _spinning[0]:
            _spinning[0] = True
            _step()

    def stop() -> None:
        _spinning[0] = False

    return img, start, stop


def summary_card(content: ft.Control) -> ft.Container:
    """Card de resumo com fundo surface_variant, borda e raio lg."""
    return ft.Container(
        content=content,
        bgcolor=Color.dark.surface_variant,
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE),
            right=ft.BorderSide(1, ft.Colors.OUTLINE),
            top=ft.BorderSide(1, ft.Colors.OUTLINE),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE),
        ),
        border_radius=Radius.lg,
        padding=ft.Padding(
            left=Space.lg,
            right=Space.lg,
            top=Space.md,
            bottom=Space.md,
        ),
    )
