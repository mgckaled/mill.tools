"""Global settings dialog (opened from the AppBar gear).

Hosts the YouTube cookies setting (anti-bot gate) and cloud API keys
(Google Gemini, Zhipu GLM). The cookie resolution itself lives in
src/core/ytdlp_cookies.py (pure, reused by every yt-dlp call site); the API
key read/write lives in src/gui/views/form_env.py (pure file I/O against the
project's .env, no Flet) — moved here from the Transcrição form, which was
never the right owner since every module that calls a cloud model (Analyzer,
Prompter, RAG chat, Dados' assess/nl2sql, descrição de imagem) needs the same
keys, not just Transcrição. Credenciais is deliberately the LAST section in
this dialog. Everything else here only persists the user's choice via
gui.settings; API keys are the one exception (they go straight to .env, same
as before the move — see the security note on write_api_key/write_glm_api_key
call sites below).
"""

from __future__ import annotations

import flet as ft

from src.core import ytdlp_cookies
from src.gui import settings
from src.gui.theme.components import Cursor, section
from src.gui.theme.tokens import Space, Type
from src.gui.views.form_env import (
    read_api_key,
    read_glm_api_key,
    write_api_key,
    write_glm_api_key,
)

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
        page.show_dialog(
            ft.SnackBar(content=ft.Text("Configurações salvas."), duration=2000)
        )

    # Cloud API keys (Google Gemini, Zhipu GLM). Unlike the cookies fields
    # above, these save on blur (not on the dialog's "Salvar" button) — same
    # behavior as before the move from the Transcrição form, kept as-is.
    # Security note: read/write only ever touch the local .env file via
    # form_env.py; the value never crosses into gui.settings/config.json or
    # any network call made by this dialog.
    api_key_field = ft.TextField(
        label="Google API Key",
        hint_text="AIza...",
        value=read_api_key(),
        password=True,
        can_reveal_password=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _on_api_key_blur(_e: ft.ControlEvent) -> None:
        write_api_key(api_key_field.value or "")

    api_key_field.on_blur = _on_api_key_blur

    glm_api_key_field = ft.TextField(
        label="GLM API Key",
        hint_text="...",
        value=read_glm_api_key(),
        password=True,
        can_reveal_password=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _on_glm_api_key_blur(_e: ft.ControlEvent) -> None:
        write_glm_api_key(glm_api_key_field.value or "")

    glm_api_key_field.on_blur = _on_glm_api_key_blur

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
                    # Credenciais fica sempre por último, deliberadamente.
                    section(
                        "Credenciais",
                        api_key_field,
                        glm_api_key_field,
                    ),
                    ft.Text(
                        "Necessárias apenas para modelos Gemini/GLM. Salvas localmente "
                        "no .env do projeto ao sair do campo — nunca saem desta máquina "
                        "nem são enviadas a nenhum serviço além do provedor escolhido "
                        "quando você de fato usa um modelo daquela nuvem.",
                        size=Type.caption.size,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=Space.md,
                scroll=ft.ScrollMode.AUTO,
                height=460,
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
