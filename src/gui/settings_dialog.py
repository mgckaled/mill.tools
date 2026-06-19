"""Global settings dialog (opened from the AppBar gear).

Currently hosts the YouTube cookies setting used to pass the anti-bot gate. The cookie
resolution itself lives in src/core/ytdlp_cookies.py (pure, reused by every yt-dlp call
site); this dialog only persists the user's choice via gui.settings.
"""

from __future__ import annotations

import flet as ft

from src.core import ytdlp_cookies
from src.gui import settings
from src.gui.theme.components import Cursor, section
from src.gui.theme.tokens import Space, Type

_BROWSER_LABELS = {
    "auto": "Automático (detecta o Zen)",
    "none": "Desativado",
    "zen": "Zen",
    "firefox": "Firefox",
    "chrome": "Chrome",
    "edge": "Edge",
    "brave": "Brave",
    "chromium": "Chromium",
    "opera": "Opera",
    "vivaldi": "Vivaldi",
    "safari": "Safari",
}


def open_settings_dialog(page: ft.Page) -> None:
    """Open the global settings modal (YouTube cookies)."""
    cfg = settings.load()

    status = ft.Text(
        ytdlp_cookies.detected_summary(),
        size=Type.caption.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    profile_field = ft.TextField(
        label="Perfil (avançado, opcional)",
        value=cfg.get("yt_cookies_profile", ""),
        hint_text="Caminho do perfil (vazio = detectar automaticamente)",
        dense=True,
        text_size=Type.input.size,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _refresh_status(_e=None) -> None:
        status.value = ytdlp_cookies.detected_summary(
            browser_dd.value, profile_field.value
        )
        if status.page:
            status.update()

    browser_dd = ft.Dropdown(
        label="Navegador dos cookies",
        value=cfg.get("yt_cookies_browser", "none"),
        options=[
            ft.dropdown.Option(key=b, text=_BROWSER_LABELS.get(b, b))
            for b in ytdlp_cookies.BROWSERS
        ],
        on_select=_refresh_status,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    profile_field.on_blur = _refresh_status

    def _save(_e=None) -> None:
        settings.set("yt_cookies_browser", browser_dd.value or "none")
        settings.set("yt_cookies_profile", (profile_field.value or "").strip())
        page.pop_dialog()
        page.open(ft.SnackBar(content=ft.Text("Configurações salvas."), duration=2000))

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.SETTINGS_OUTLINED, color=ft.Colors.PRIMARY, size=20),
                ft.Text(
                    "Configurações",
                    size=Type.body.size,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(
            width=520,
            content=ft.Column(
                controls=[
                    section(
                        "Cookies do YouTube",
                        browser_dd,
                        status,
                        profile_field,
                    ),
                    ft.Text(
                        "Os cookies do navegador logado ajudam a passar a verificação "
                        "anti-bot do YouTube ao baixar (Áudio, Vídeo e Transcrição). São "
                        "lidos localmente; nada é enviado além das requisições normais de "
                        "download.",
                        size=Type.caption.size,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=Space.md,
            ),
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
            ft.FilledButton(
                "Salvar",
                icon=ft.Icons.SAVE_OUTLINED,
                on_click=_save,
                style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
            ),
        ],
    )
    page.show_dialog(dlg)
