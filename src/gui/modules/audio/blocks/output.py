"""Output block for the audio module — format, bitrate and metadata embed."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import (
    hairline,
    help_icon_for,
    section,
    segmented_selector,
)
from src.gui.theme.tokens import Type

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


class OutputRefs(NamedTuple):
    get_fmt: Callable[[], str]
    get_quality: Callable[[], str]
    get_embed_meta: Callable[[], bool]
    set_embed_visible: Callable[[bool], None]
    set_disabled: Callable[[bool], None]


def build_output_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, OutputRefs]:
    """Build the format + bitrate + embed block.

    Returns the wrapped control (two sections) and an OutputRefs for value
    collection. The format→bitrate disable interplay is owned internally.
    """

    def _on_fmt_change(fmt: str) -> None:
        _set_quality_disabled(fmt in _NO_BITRATE_FMTS)

    fmt_grid, _get_fmt, _set_fmt_disabled = segmented_selector(
        _FMT_OPTIONS,
        cfg.get("last_audio_fmt", "mp3"),
        page,
        on_change=_on_fmt_change,
    )

    quality_grid, _get_quality, _set_quality_disabled = segmented_selector(
        _QUALITY_OPTIONS,
        cfg.get("last_audio_quality", "best"),
        page,
        labels=_QUALITY_LABELS,
    )
    # Initial state before mount (no update).
    _set_quality_disabled(cfg.get("last_audio_fmt", "mp3") in _NO_BITRATE_FMTS)

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

    def _set_embed_visible(visible: bool) -> None:
        embed_row.visible = visible
        if embed_row.page:
            embed_row.update()

    def _set_disabled(running: bool) -> None:
        _set_fmt_disabled(running)
        _set_quality_disabled(running or _get_fmt() in _NO_BITRATE_FMTS)
        embed_switch.disabled = running

    control = ft.Column(
        spacing=16,
        controls=[
            section(
                "Formato de saída",
                fmt_grid,
                help_key="audio.format",
                page=page,
            ),
            hairline(),
            section(
                "Bitrate (kbps)",
                quality_grid,
                embed_row,
                help_key="audio.bitrate",
                page=page,
            ),
        ],
    )

    refs = OutputRefs(
        get_fmt=lambda: _get_fmt(),
        get_quality=lambda: _get_quality(),
        get_embed_meta=lambda: bool(embed_switch.value),
        set_embed_visible=_set_embed_visible,
        set_disabled=_set_disabled,
    )
    return control, refs
