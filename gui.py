"""Entry point da GUI desktop do mill.tools (Flet)."""

import flet as ft

from src.gui.app import build_app
from src.gui.assets import WINDOW_ICON
from src.gui.splash import show_splash


def main(page: ft.Page) -> None:
    """Configura a página raiz e monta o app."""
    page.title = "mill.tools"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 1000
    page.window.min_height = 600
    page.window.icon = WINDOW_ICON  # Windows-only; caminho absoluto (issue #3438)
    show_splash(page, on_complete=lambda: build_app(page))


if __name__ == "__main__":
    ft.run(main)
