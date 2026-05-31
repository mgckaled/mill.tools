"""Formulário de entrada do módulo Áudio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from src.gui import settings
from src.gui.components.input_source import InputItem, build_input_source

# Extensões aceitas no seletor de arquivos
_ALLOWED_EXTS = [
    "mp3", "wav", "flac", "ogg", "opus", "aac", "m4a",
    "mp4", "mkv", "webm", "avi", "mov",
]

_FMT_OPTIONS = ["best", "mp3", "m4a", "wav", "ogg", "opus"]
_QUALITY_OPTIONS = ["best", "320", "256", "128", "96", "64"]

# Formatos sem bitrate configurável (lossless ou "best")
_NO_BITRATE_FMTS = {"wav", "best"}


@dataclass
class AudioArgs:
    """Parâmetros do pipeline de áudio recebidos do formulário."""

    items: list[InputItem] = field(default_factory=list)
    fmt: str = "mp3"
    quality: str = "best"
    embed_meta: bool = True


@dataclass
class AudioFormPanel:
    """Painel do formulário de áudio com métodos de controle."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


def build_audio_form(
    page: ft.Page,
    on_start: Callable[[AudioArgs], None],
) -> AudioFormPanel:
    """Constrói o formulário do módulo Áudio.

    Args:
        page: Página Flet.
        on_start: Chamado com AudioArgs ao clicar Iniciar.
    """
    cfg = settings.load()

    # ── InputSource ───────────────────────────────────────────────────────────

    _has_url_items: list[bool] = [False]

    def _on_items_change(items: list[InputItem]) -> None:
        has_url = any(i.kind == "url" for i in items)
        _has_url_items[0] = has_url
        embed_row.visible = has_url
        start_btn.disabled = len(items) == 0
        if embed_row.page:
            embed_row.update()
        if start_btn.page:
            start_btn.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
    )

    # ── Formato de saída ──────────────────────────────────────────────────────

    def _on_fmt_select(_e) -> None:
        quality_dropdown.disabled = fmt_dropdown.value in _NO_BITRATE_FMTS
        quality_dropdown.update()

    fmt_dropdown = ft.Dropdown(
        label="Formato de saída",
        options=[ft.dropdown.Option(f) for f in _FMT_OPTIONS],
        value=cfg.get("last_audio_fmt", "mp3"),
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.BLUE_400,
        on_select=_on_fmt_select,
    )

    quality_dropdown = ft.Dropdown(
        label="Bitrate",
        options=[ft.dropdown.Option(q) for q in _QUALITY_OPTIONS],
        value=cfg.get("last_audio_quality", "best"),
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.BLUE_400,
        disabled=cfg.get("last_audio_fmt", "mp3") in _NO_BITRATE_FMTS,
    )

    # ── Embutir capa e metadados (só para URLs) ───────────────────────────────

    embed_switch = ft.Switch(
        label="Embutir capa e metadados",
        value=cfg.get("last_audio_embed_meta", True),
        label_text_style=ft.TextStyle(size=13),
        active_color=ft.Colors.BLUE_400,
    )

    embed_row = ft.Container(
        content=embed_switch,
        visible=False,  # exibido apenas quando há itens de URL
    )

    # ── Botão Iniciar ─────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
    )

    def _on_start_click() -> None:
        items = input_source.get_items()
        if not items:
            return
        settings.save({
            "last_audio_fmt": fmt_dropdown.value,
            "last_audio_quality": quality_dropdown.value,
            "last_audio_embed_meta": embed_switch.value,
        })
        on_start(AudioArgs(
            items=items,
            fmt=fmt_dropdown.value or "mp3",
            quality=quality_dropdown.value or "best",
            embed_meta=bool(embed_switch.value) and _has_url_items[0],
        ))

    # ── set_running ───────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        input_source.set_enabled(not running)
        fmt_dropdown.disabled = running
        quality_dropdown.disabled = running or fmt_dropdown.value in _NO_BITRATE_FMTS
        embed_switch.disabled = running
        page.update()

    # ── fill_from_path (bridge on_mount) ─────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── layout ────────────────────────────────────────────────────────────────

    control = ft.Column(
        controls=[
            ft.Text(
                "Entrada",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
                weight=ft.FontWeight.W_500,
            ),
            input_source.control,
            ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
            ft.Text(
                "Configurações",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
                weight=ft.FontWeight.W_500,
            ),
            fmt_dropdown,
            quality_dropdown,
            embed_row,
            ft.Container(expand=True),
            ft.Row(
                controls=[start_btn],
                alignment=ft.MainAxisAlignment.END,
            ),
        ],
        expand=True,
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
    )

    return AudioFormPanel(
        control=control,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
