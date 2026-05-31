"""Ícone de ajuda (ⓘ): tooltip no hover, modal opcional no clique."""
from __future__ import annotations

import flet as ft

from src.gui.help_content import help_for, help_long_for
from src.gui.theme.tokens import Radius, Space, Type


def help_icon(
    short: str,
    long: str | None = None,
    page: ft.Page | None = None,
    size: int = 16,
) -> ft.Tooltip:
    """ⓘ com tooltip estilizado (short). Se `long` e `page`, clique abre modal."""
    icon = ft.Icon(ft.Icons.INFO_OUTLINED, size=size, color=ft.Colors.ON_SURFACE_VARIANT)

    inner = ft.Container(
        content=icon,
        border_radius=Radius.pill,
        padding=Space.xs,
        ink=long is not None,
    )

    def _hover(e: ft.HoverEvent) -> None:
        icon.color = ft.Colors.PRIMARY if e.data == "true" else ft.Colors.ON_SURFACE_VARIANT
        icon.update()

    inner.on_hover = _hover

    if long is not None and page is not None:
        def _open(_e) -> None:
            dlg = ft.AlertDialog(
                title=ft.Text(short[:60], size=15, weight=ft.FontWeight.W_600),
                content=ft.Container(
                    content=ft.Text(long, selectable=True),
                    width=420,
                ),
                actions=[
                    ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog()),
                ],
            )
            page.show_dialog(dlg)

        inner.on_click = _open

    return ft.Tooltip(
        message=short,
        wait_duration=300,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        border_radius=Radius.md,
        padding=ft.Padding(left=Space.lg, right=Space.lg, top=Space.sm, bottom=Space.sm),
        text_style=ft.TextStyle(
            color=ft.Colors.ON_SURFACE,
            size=Type.body.size,
        ),
        content=inner,
    )


def help_icon_for(key: str, page: ft.Page | None = None) -> ft.Tooltip | None:
    """Monta a ⓘ a partir do registro. None se a chave não tiver texto curto."""
    short = help_for(key)
    if not short:
        return None
    return help_icon(short, help_long_for(key), page)
