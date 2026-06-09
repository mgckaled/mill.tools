"""Formulário de entrada do módulo Áudio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from src.gui import settings
from src.core.audio.args import AudioArgs
from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import Cursor, hairline, help_icon_for, section, segmented_selector, switch_row
from src.gui.theme.tokens import Space, Type

_ALLOWED_EXTS = [
    "mp3", "wav", "flac", "ogg", "opus", "aac", "m4a",
    "mp4", "mkv", "webm", "avi", "mov",
]

_FMT_OPTIONS = ["best", "mp3", "m4a", "wav", "ogg", "opus"]
_QUALITY_OPTIONS = ["best", "320", "256", "128", "96", "64"]
_QUALITY_LABELS = {
    "best": "best",
    "320": "320 kb/s",
    "256": "256 kb/s",
    "128": "128 kb/s",
    "96": "96 kb/s",
    "64": "64 kb/s",
}
_NO_BITRATE_FMTS = {"wav", "best"}


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

    # ── Formato de saída — grade 2×3 ─────────────────────────────────────────

    def _on_fmt_change(fmt: str) -> None:
        _set_quality_disabled(fmt in _NO_BITRATE_FMTS)

    fmt_grid, _get_fmt, _set_fmt_disabled = segmented_selector(
        _FMT_OPTIONS,
        cfg.get("last_audio_fmt", "mp3"),
        page,
        on_change=_on_fmt_change,
    )

    # ── Bitrate — grade 2×3 ───────────────────────────────────────────────────

    quality_grid, _get_quality, _set_quality_disabled = segmented_selector(
        _QUALITY_OPTIONS,
        cfg.get("last_audio_quality", "best"),
        page,
        labels=_QUALITY_LABELS,
    )
    # estado inicial antes do mount (sem update)
    _set_quality_disabled(cfg.get("last_audio_fmt", "mp3") in _NO_BITRATE_FMTS)

    # ── Embutir capa e metadados (visível apenas com URLs) ────────────────────

    embed_switch = ft.Switch(
        label="Embutir capa e metadados",
        value=cfg.get("last_audio_embed_meta", True),
        label_text_style=ft.TextStyle(size=Type.input.size),
        active_color=ft.Colors.PRIMARY,
    )

    _embed_icon = help_icon_for("audio.embed_meta", page)
    embed_row = ft.Container(
        content=ft.Row(
            [embed_switch] + ([_embed_icon] if _embed_icon else []),
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        visible=False,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    # ── Pós-processamento — denoise + normalize ───────────────────────────────

    denoise_switch = switch_row(
        "Reduzir ruído (spectral gating)",
        cfg.get("last_audio_denoise", False),
    )
    normalize_switch = switch_row(
        "Normalizar volume (loudnorm)",
        cfg.get("last_audio_normalize", False),
    )

    lufs_values: list[float] = [cfg.get("last_audio_lufs", -14.0)]

    _lufs_value_text = ft.Text(
        f"{lufs_values[0]:.0f} LUFS",
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.PRIMARY,
    )

    _lufs_ctl = ft.Slider(
        value=lufs_values[0],
        min=-23.0,
        max=-6.0,
        divisions=17,
        active_color=ft.Colors.PRIMARY,
        label="{value:.0f} LUFS",
        expand=True,
    )

    def _on_lufs_change(e) -> None:
        lufs_values[0] = e.control.value
        _lufs_value_text.value = f"{lufs_values[0]:.0f} LUFS"
        if _lufs_value_text.page:
            _lufs_value_text.update()

    _lufs_ctl.on_change = _on_lufs_change

    def _set_lufs_disabled(disabled: bool) -> None:
        _lufs_ctl.disabled = disabled

    _lufs_icon = help_icon_for("audio.normalize_lufs", page)
    _lufs_col = ft.Column(
        controls=[
            ft.Row(
                [
                    ft.Text(
                        "Alvo (LUFS)",
                        size=Type.label.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ]
                + ([_lufs_icon] if _lufs_icon else [])
                + [ft.Container(expand=True), _lufs_value_text],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            _lufs_ctl,
        ],
        spacing=Space.xs,
    )

    lufs_block = ft.Container(
        content=_lufs_col,
        visible=bool(normalize_switch.value),
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_normalize_change(e) -> None:
        lufs_block.visible = bool(e.control.value)
        if lufs_block.page:
            lufs_block.update()

    normalize_switch.on_change = _on_normalize_change

    _denoise_icon   = help_icon_for("audio.denoise",    page)
    _normalize_icon = help_icon_for("audio.normalize",  page)

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
        settings.save({
            "last_audio_fmt":       _get_fmt(),
            "last_audio_quality":   _get_quality(),
            "last_audio_embed_meta": embed_switch.value,
            "last_audio_denoise":   denoise_switch.value,
            "last_audio_normalize": normalize_switch.value,
            "last_audio_lufs":      lufs_values[0],
        })
        on_start(AudioArgs(
            items=items,
            fmt=_get_fmt(),
            quality=_get_quality(),
            embed_meta=bool(embed_switch.value) and _has_url_items[0],
            denoise=bool(denoise_switch.value),
            normalize=bool(normalize_switch.value),
            normalize_target_lufs=lufs_values[0],
        ))

    # ── set_running ───────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        input_source.set_enabled(not running)
        _set_fmt_disabled(running)
        _set_quality_disabled(running or _get_fmt() in _NO_BITRATE_FMTS)
        embed_switch.disabled = running
        denoise_switch.disabled   = running
        normalize_switch.disabled = running
        _set_lufs_disabled(running)
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
                        # ── Entrada ───────────────────────────────────────
                        section("Entrada", input_source.control,
                                help_key="audio.input", page=page),

                        hairline(),

                        # ── Formato de saída ──────────────────────────────
                        section("Formato de saída", fmt_grid,
                                help_key="audio.format", page=page),

                        hairline(),

                        # ── Bitrate ───────────────────────────────────────
                        section("Bitrate (kbps)", quality_grid, embed_row,
                                help_key="audio.bitrate", page=page),

                        hairline(),

                        # ── Pós-processamento ─────────────────────────────
                        section(
                            "Pós-processamento",
                            ft.Row(
                                [denoise_switch]
                                + ([_denoise_icon] if _denoise_icon else []),
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [normalize_switch]
                                + ([_normalize_icon] if _normalize_icon else []),
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            lufs_block,
                        ),

                        hairline(),

                        # ── Iniciar ───────────────────────────────────────
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
