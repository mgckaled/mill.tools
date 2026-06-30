"""Denoise block for the audio module — spectral gating toggle + noise mode."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import (
    help_icon_for,
    section_label,
    segmented_selector,
    switch_row,
)
from src.gui.theme.tokens import Space

_MODE_LABELS = {"stationary": "Constante", "adaptive": "Variável"}


class DenoiseRefs(NamedTuple):
    get_denoise: Callable[[], bool]
    get_stationary: Callable[[], bool]
    set_stationary: Callable[[bool], None]
    set_denoise: Callable[[bool], None]
    set_disabled: Callable[[bool], None]


def build_denoise_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, DenoiseRefs]:
    """Build the denoise toggle + noise-mode (stationary/adaptive) block.

    The mode selector is revealed only when denoise is on.
    """
    initial_mode = (
        "stationary" if cfg.get("last_audio_stationary", True) else "adaptive"
    )

    mode_grid, _get_mode, _set_mode_disabled, _set_mode = segmented_selector(
        ["stationary", "adaptive"],
        initial_mode,
        page,
        labels=_MODE_LABELS,
        columns=2,
        with_setter=True,
    )

    mode_block = ft.Container(
        content=ft.Column(
            [section_label("Tipo de ruído"), mode_grid],
            spacing=Space.xs,
        ),
        visible=cfg.get("last_audio_denoise", False),
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_denoise_change(e) -> None:
        mode_block.visible = bool(e.control.value)
        if mode_block.page:
            mode_block.update()

    denoise_switch = switch_row(
        "Reduzir ruído (spectral gating)",
        cfg.get("last_audio_denoise", False),
        on_change=_on_denoise_change,
    )
    _icon = help_icon_for("audio.denoise", page)

    control = ft.Column(
        spacing=Space.sm,
        controls=[
            ft.Row(
                [denoise_switch] + ([_icon] if _icon else []),
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            mode_block,
        ],
    )

    def _set_denoise(value: bool) -> None:
        denoise_switch.value = value
        mode_block.visible = value
        if denoise_switch.page:
            denoise_switch.update()
        if mode_block.page:
            mode_block.update()

    def _set_disabled(running: bool) -> None:
        denoise_switch.disabled = running
        _set_mode_disabled(running)

    refs = DenoiseRefs(
        get_denoise=lambda: bool(denoise_switch.value),
        get_stationary=lambda: _get_mode() == "stationary",
        set_stationary=lambda v: _set_mode("stationary" if v else "adaptive"),
        set_denoise=_set_denoise,
        set_disabled=_set_disabled,
    )
    return control, refs
