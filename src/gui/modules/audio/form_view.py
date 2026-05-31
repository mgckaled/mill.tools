"""Formulário de entrada do módulo Áudio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from src.gui import settings
from src.gui.components.input_source import InputItem, build_input_source

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


# ─── helpers visuais (mesma linguagem do form_view.py da Transcrição) ─────────

def _section_label(text: str) -> ft.Text:
    return ft.Text(text, size=13, weight=ft.FontWeight.W_600, color=ft.Colors.ON_SURFACE_VARIANT)


def _divider() -> ft.Divider:
    return ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT)


# ─── grade de chips clicáveis ─────────────────────────────────────────────────

def _chip_grid(
    options: list[str],
    initial: str,
    page: ft.Page,
    on_change: Callable[[str], None] | None = None,
    cols: int = 3,
    labels: dict[str, str] | None = None,
) -> tuple[ft.Column, Callable[[], str], Callable[[bool], None]]:
    """Grade NxCOLS de chips clicáveis sem wrapper externo.

    Returns:
        (control, get_value, set_disabled)
    """
    _selected: list[str] = [initial]
    _disabled: list[bool] = [False]
    _ctrs: dict[str, ft.Container] = {}
    _texts: dict[str, ft.Text] = {}

    def _border(active: bool) -> ft.Border:
        color = ft.Colors.BLUE_400 if active else ft.Colors.OUTLINE_VARIANT
        width = 2 if active else 1
        s = ft.BorderSide(width, color)
        return ft.Border(left=s, right=s, top=s, bottom=s)

    def _bgcolor(active: bool):
        return ft.Colors.with_opacity(0.12, ft.Colors.BLUE_400) if active else ft.Colors.TRANSPARENT

    def _text_color(active: bool) -> str:
        return ft.Colors.BLUE_300 if active else ft.Colors.ON_SURFACE_VARIANT

    def _on_click(_e, opt: str) -> None:
        if _disabled[0] or opt == _selected[0]:
            return
        prev = _selected[0]
        _selected[0] = opt
        _ctrs[prev].border = _border(False)
        _ctrs[prev].bgcolor = _bgcolor(False)
        _texts[prev].color = _text_color(False)
        _ctrs[opt].border = _border(True)
        _ctrs[opt].bgcolor = _bgcolor(True)
        _texts[opt].color = _text_color(True)
        if on_change:
            on_change(opt)
        page.update()

    def _make_chip(opt: str) -> ft.Container:
        active = opt == _selected[0]
        display = labels[opt] if labels else opt
        t = ft.Text(display, size=14, text_align=ft.TextAlign.CENTER, color=_text_color(active))
        c = ft.Container(
            content=t,
            border=_border(active),
            bgcolor=_bgcolor(active),
            border_radius=6,
            padding=ft.Padding(left=2, right=2, top=7, bottom=7),
            expand=True,
            alignment=ft.Alignment.CENTER,
            on_click=lambda e, _o=opt: _on_click(e, _o),
            animate=ft.Animation(120, ft.AnimationCurve.EASE_IN_OUT),
            ink=True,
        )
        _ctrs[opt] = c
        _texts[opt] = t
        return c

    chips = [_make_chip(o) for o in options]
    rows: list[ft.Row] = []
    for i in range(0, len(chips), cols):
        rows.append(ft.Row(controls=chips[i : i + cols], spacing=8))

    grid = ft.Column(controls=rows, spacing=8)

    def _get_value() -> str:
        return _selected[0]

    def _set_disabled(disabled: bool) -> None:
        _disabled[0] = disabled
        grid.opacity = 0.4 if disabled else 1.0

    return grid, _get_value, _set_disabled


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

    fmt_grid, _get_fmt, _set_fmt_disabled = _chip_grid(
        _FMT_OPTIONS,
        cfg.get("last_audio_fmt", "mp3"),
        page,
        on_change=_on_fmt_change,
    )

    # ── Bitrate — grade 2×3 ───────────────────────────────────────────────────

    quality_grid, _get_quality, _set_quality_disabled = _chip_grid(
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
        label_text_style=ft.TextStyle(size=13),
        active_color=ft.Colors.BLUE_400,
    )

    embed_row = ft.Container(
        content=embed_switch,
        visible=False,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
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
            "last_audio_fmt": _get_fmt(),
            "last_audio_quality": _get_quality(),
            "last_audio_embed_meta": embed_switch.value,
        })
        on_start(AudioArgs(
            items=items,
            fmt=_get_fmt(),
            quality=_get_quality(),
            embed_meta=bool(embed_switch.value) and _has_url_items[0],
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
        page.update()

    # ── fill_from_path (bridge on_mount) ─────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── layout — mesma estrutura que o form_view.py da Transcrição ────────────
    #   Container(padding=20) → Column(spacing=16)
    #   _section_label → controles → _divider()

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
                        _section_label("Entrada"),
                        input_source.control,

                        _divider(),

                        # ── Formato de saída ──────────────────────────────
                        _section_label("Formato de saída"),
                        fmt_grid,

                        _divider(),

                        # ── Bitrate ───────────────────────────────────────
                        _section_label("Bitrate (kbps)"),
                        quality_grid,
                        embed_row,

                        _divider(),

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
