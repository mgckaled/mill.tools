"""Módulo Áudio — placeholder para PR3."""

from __future__ import annotations

import flet as ft

from src.gui.modules.base import Module


def build_audio_placeholder() -> Module:
    """Retorna placeholder do módulo Áudio (implementação no PR3)."""
    control = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(ft.Icons.MUSIC_NOTE_OUTLINED, size=48, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(
                    "Módulo Áudio",
                    size=20,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Em breve — download, conversão e extração de áudio.",
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
        id="audio",
        label="Áudio",
        icon=ft.Icons.MUSIC_NOTE_OUTLINED,
        selected_icon=ft.Icons.MUSIC_NOTE,
        control=control,
    )
