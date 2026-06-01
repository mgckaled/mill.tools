"""Ícone de ajuda (ⓘ): tooltip no hover, modal opcional no clique.

Ponto único de replicação para todos os módulos da GUI:
  - help_icon(short, long, page)  → constrói o ⓘ diretamente
  - help_icon_for(key, page)      → lê de help_content.py pelo registro

Importar sempre via: from src.gui.theme.components import help_icon_for
"""
from __future__ import annotations

import flet as ft

from src.gui.help_content import help_for, help_long_for
from src.gui.theme.tokens import Color, Radius, Space, Type

_TOOLTIP_MAX_WIDTH = 280
_HINT_CLICK = "\n\n↗ Clique para mais detalhes"


def _make_tooltip(message: str, has_long: bool = False) -> ft.Tooltip:
    """Tooltip estilizado. Se has_long, anexa hint de clique na mensagem."""
    text = message + _HINT_CLICK if has_long else message
    return ft.Tooltip(
        message=text,
        wait_duration=300,
        decoration=ft.BoxDecoration(
            bgcolor=Color.dark.surface_variant,
            border_radius=Radius.md,
            border=ft.Border(
                left=ft.BorderSide(1, Color.dark.outline_variant),
                right=ft.BorderSide(1, Color.dark.outline_variant),
                top=ft.BorderSide(1, Color.dark.outline_variant),
                bottom=ft.BorderSide(1, Color.dark.outline_variant),
            ),
            shadows=[ft.BoxShadow(
                blur_radius=10,
                spread_radius=0,
                offset=ft.Offset(0, 4),
                color=ft.Colors.with_opacity(0.35, ft.Colors.BLACK),
            )],
        ),
        size_constraints=ft.BoxConstraints(max_width=_TOOLTIP_MAX_WIDTH),
        padding=ft.Padding(
            left=Space.lg, right=Space.lg,
            top=Space.sm, bottom=Space.sm,
        ),
        text_style=ft.TextStyle(
            color=ft.Colors.ON_SURFACE,
            size=Type.caption.size,
        ),
        text_align=ft.TextAlign.LEFT,
        prefer_below=True,
    )


def help_icon(
    short: str,
    long: str | None = None,
    page: ft.Page | None = None,
    size: int = 16,
) -> ft.Container:
    """ⓘ com tooltip (short) no hover. Se `long` e `page`, clique abre modal detalhado."""
    has_long = long is not None and page is not None
    icon = ft.Icon(ft.Icons.INFO_OUTLINED, size=size, color=ft.Colors.ON_SURFACE_VARIANT)
    box = ft.Container(
        content=icon,
        tooltip=_make_tooltip(short, has_long=has_long),
        border_radius=Radius.pill,
        padding=Space.xs,
        ink=has_long,
    )

    def _hover(e: ft.HoverEvent) -> None:
        icon.color = ft.Colors.PRIMARY if e.data == "true" else ft.Colors.ON_SURFACE_VARIANT
        icon.update()

    box.on_hover = _hover

    if has_long:
        def _open(_e) -> None:
            dlg = ft.AlertDialog(
                title=ft.Text(short[:60], size=Type.body.size, weight=ft.FontWeight.W_600),
                content=ft.Container(
                    content=ft.Text(long, selectable=True),
                    width=420,
                ),
                actions=[
                    ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog()),
                ],
            )
            page.show_dialog(dlg)

        box.on_click = _open

    return box


def help_icon_for(key: str, page: ft.Page | None = None) -> ft.Container | None:
    """Monta o ⓘ a partir do registro central (help_content.py).

    Retorna None se a chave não tiver texto curto — o chamador pode ignorar
    ou omitir o ícone sem precisar de lógica extra.
    """
    short = help_for(key)
    if not short:
        return None
    return help_icon(short, help_long_for(key), page)
