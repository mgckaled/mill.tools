"""Entry point da GUI desktop do yt-transcriber (Flet)."""

import flet as ft

from src.gui.app import build_app


def main(page: ft.Page) -> None:
    """Configura a página raiz e monta o app."""
    page.title = "yt-transcriber"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 900
    page.window.height = 700
    page.window.min_width = 700
    page.window.min_height = 500
    build_app(page)


if __name__ == "__main__":
    ft.run(main)
