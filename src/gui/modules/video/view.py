"""Módulo Vídeo — placeholder para PR3/PR4."""

from __future__ import annotations

import flet as ft

from src.gui.modules.base import Module


def build_video_placeholder() -> Module:
    """Retorna placeholder do módulo Vídeo (implementação no PR4)."""
    control = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(ft.Icons.VIDEO_FILE_OUTLINED, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(
                    "Módulo Vídeo",
                    size=20,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Em breve — download, conversão e extração de áudio de vídeo.",
                    size=13,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        ),
        alignment=ft.Alignment(0, 0),
        expand=True,
    )
    return Module(
        id="video",
        label="Vídeo",
        icon=ft.Icons.VIDEO_FILE_OUTLINED,
        selected_icon=ft.Icons.VIDEO_FILE,
        control=control,
    )
