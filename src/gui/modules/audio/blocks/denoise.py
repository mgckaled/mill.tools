"""Denoise block for the audio module — spectral gating toggle."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, switch_row


class DenoiseRefs(NamedTuple):
    get_denoise: Callable[[], bool]
    set_disabled: Callable[[bool], None]


def build_denoise_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, DenoiseRefs]:
    """Build the denoise toggle block."""
    denoise_switch = switch_row(
        "Reduzir ruído (spectral gating)",
        cfg.get("last_audio_denoise", False),
    )
    _icon = help_icon_for("audio.denoise", page)

    control = ft.Row(
        [denoise_switch] + ([_icon] if _icon else []),
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _set_disabled(running: bool) -> None:
        denoise_switch.disabled = running

    refs = DenoiseRefs(
        get_denoise=lambda: bool(denoise_switch.value),
        set_disabled=_set_disabled,
    )
    return control, refs
