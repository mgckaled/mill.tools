"""Fábricas de cards de resultado."""

from __future__ import annotations

import subprocess
from pathlib import Path

import flet as ft

from src.gui.theme.tokens import Color, Radius, Space, Type


def output_card(
    path: Path,
    accent: str | None = None,
    icon: str = ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
    extra_actions: list[ft.Control] | None = None,
) -> ft.Container:
    """Card de arquivo de saída: borda colorida, nome, pasta e botão abrir.

    Args:
        path: Caminho do arquivo gerado.
        accent: Cor de destaque (borda, ícone). Default: Color.log.info.
        icon: Ícone do tipo de arquivo.
        extra_actions: Botões adicionais inseridos após "Abrir pasta".
    """
    from src.gui.theme.components.buttons import action_button

    c = accent or Color.log.info

    def _open(_e) -> None:
        subprocess.run(["explorer", "/select,", str(path)], check=False)

    open_btn = action_button(
        "Abrir pasta",
        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
        on_click=_open,
        accent=c,
    )

    return ft.Container(
        margin=ft.Margin(top=6, bottom=2, left=0, right=0),
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        border=ft.Border(
            left=ft.BorderSide(1, c),
            right=ft.BorderSide(1, c),
            top=ft.BorderSide(1, c),
            bottom=ft.BorderSide(1, c),
        ),
        border_radius=Radius.sm,
        bgcolor=ft.Colors.with_opacity(0.05, c),
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(icon, size=16, color=c),
                        ft.Text(
                            path.name,
                            size=Type.mono.size,
                            color=ft.Colors.ON_SURFACE,
                            font_family=Type.FONT_MONO,
                            expand=True,
                            selectable=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            no_wrap=True,
                        ),
                    ],
                    spacing=Space.sm,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(
                    str(path.parent),
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    font_family=Type.FONT_MONO,
                    selectable=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    no_wrap=True,
                ),
                ft.Row(
                    controls=[open_btn, *(extra_actions or [])],
                    spacing=Space.xs,
                ),
            ],
            spacing=Space.xs,
        ),
    )
