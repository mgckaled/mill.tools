"""Layout raiz e navegação entre views do yt-transcriber GUI."""

import flet as ft


def build_app(page: ft.Page) -> None:
    """Monta o app na página Flet — substituído na implementação completa."""
    page.add(
        ft.Column(
            controls=[
                ft.Text("yt-transcriber", size=28, weight=ft.FontWeight.BOLD),
                ft.Text("Interface gráfica em construção...", size=14, color=ft.Colors.GREY_400),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )
    )
    page.update()
