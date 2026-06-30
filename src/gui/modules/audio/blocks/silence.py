"""Silence-trim block for the audio module — toggle + threshold/duration."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, labeled_slider, switch_row
from src.gui.theme.tokens import Space


class SilenceRefs(NamedTuple):
    get_trim: Callable[[], bool]
    get_threshold_db: Callable[[], float]
    get_min_s: Callable[[], float]
    set_trim: Callable[[bool], None]
    set_disabled: Callable[[bool], None]


def build_silence_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, SilenceRefs]:
    """Build the silence-removal toggle + threshold/min-duration sliders.

    Sliders are revealed only when the toggle is on.
    """
    th_col, th_slider = labeled_slider(
        label="Limiar (dB)",
        value=cfg.get("last_audio_silence_threshold", -40.0),
        min=-60.0,
        max=-20.0,
        divisions=40,
        fmt=lambda v: f"{v:.0f} dB",
    )
    min_col, min_slider = labeled_slider(
        label="Silêncio mínimo (s)",
        value=cfg.get("last_audio_silence_min", 0.5),
        min=0.2,
        max=3.0,
        divisions=28,
        fmt=lambda v: f"{v:.1f} s",
    )

    sliders_block = ft.Container(
        content=ft.Column([th_col, min_col], spacing=Space.sm),
        visible=cfg.get("last_audio_trim_silence", False),
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_change(e) -> None:
        sliders_block.visible = bool(e.control.value)
        if sliders_block.page:
            sliders_block.update()

    trim_switch = switch_row(
        "Remover silêncio",
        cfg.get("last_audio_trim_silence", False),
        on_change=_on_change,
    )
    _icon = help_icon_for("audio.trim_silence", page)

    control = ft.Column(
        spacing=Space.sm,
        controls=[
            ft.Row(
                [trim_switch] + ([_icon] if _icon else []),
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            sliders_block,
        ],
    )

    def _set_trim(value: bool) -> None:
        trim_switch.value = value
        sliders_block.visible = value
        if trim_switch.page:
            trim_switch.update()
        if sliders_block.page:
            sliders_block.update()

    def _set_disabled(running: bool) -> None:
        trim_switch.disabled = running
        th_slider.disabled = running
        min_slider.disabled = running

    refs = SilenceRefs(
        get_trim=lambda: bool(trim_switch.value),
        get_threshold_db=lambda: float(th_slider.value),
        get_min_s=lambda: float(min_slider.value),
        set_trim=_set_trim,
        set_disabled=_set_disabled,
    )
    return control, refs
