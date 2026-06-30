"""Formulário de entrada do módulo Áudio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.gui import settings
from src.core.audio.args import AudioArgs
from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.modules.audio.blocks.denoise import build_denoise_block
from src.gui.modules.audio.blocks.normalize import build_normalize_block
from src.gui.modules.audio.blocks.output import build_output_block
from src.gui.theme.components import (
    Cursor,
    hairline,
    section,
)

_ALLOWED_EXTS = [
    "mp3",
    "wav",
    "flac",
    "ogg",
    "opus",
    "aac",
    "m4a",
    "mp4",
    "mkv",
    "webm",
    "avi",
    "mov",
]


@dataclass
class AudioFormPanel:
    """Painel do formulário de áudio com métodos de controle."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


# ─── build_audio_form ─────────────────────────────────────────────────────────


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
        output_refs.set_embed_visible(has_url)
        start_btn.disabled = len(items) == 0
        if start_btn.page:
            start_btn.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
    )

    # ── Blocos ────────────────────────────────────────────────────────────────

    output_block, output_refs = build_output_block(page, cfg)
    denoise_block, denoise_refs = build_denoise_block(page, cfg)
    normalize_block, normalize_refs = build_normalize_block(page, cfg)

    # ── Botão Iniciar ─────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _on_start_click() -> None:
        items = input_source.get_items()
        if not items:
            return
        settings.save(
            {
                "last_audio_fmt": output_refs.get_fmt(),
                "last_audio_quality": output_refs.get_quality(),
                "last_audio_embed_meta": output_refs.get_embed_meta(),
                "last_audio_denoise": denoise_refs.get_denoise(),
                "last_audio_normalize": normalize_refs.get_normalize(),
                "last_audio_lufs": normalize_refs.get_target_lufs(),
            }
        )
        on_start(
            AudioArgs(
                items=items,
                fmt=output_refs.get_fmt(),
                quality=output_refs.get_quality(),
                embed_meta=output_refs.get_embed_meta() and _has_url_items[0],
                denoise=denoise_refs.get_denoise(),
                normalize=normalize_refs.get_normalize(),
                normalize_target_lufs=normalize_refs.get_target_lufs(),
            )
        )

    # ── set_running ───────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = (
            ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        )
        input_source.set_enabled(not running)
        output_refs.set_disabled(running)
        denoise_refs.set_disabled(running)
        normalize_refs.set_disabled(running)
        page.update()

    # ── fill_from_path (bridge on_mount) ─────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── layout ────────────────────────────────────────────────────────────────

    control = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        expand=True,
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        section(
                            "Entrada",
                            input_source.control,
                            help_key="audio.input",
                            page=page,
                        ),
                        hairline(),
                        output_block,
                        hairline(),
                        section(
                            "Pós-processamento",
                            denoise_block,
                            normalize_block,
                        ),
                        hairline(),
                        ft.Row(
                            controls=[start_btn],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                ),
            ),
        ],
    )

    return AudioFormPanel(
        control=control,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
