"""Speed block for the audio module — playback speed toggle + factor slider."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, labeled_slider, switch_row
from src.gui.theme.tokens import Space


class SpeedRefs(NamedTuple):
    get_factor: Callable[[], float]
    set_disabled: Callable[[bool], None]


def build_speed_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, SpeedRefs]:
    """Build the speed toggle + factor slider block.

    When the toggle is off, ``get_factor`` returns 1.0 (disabled).
    """
    factor_col, factor_slider = labeled_slider(
        label="Velocidade",
        value=cfg.get("last_audio_speed", 1.25),
        min=0.5,
        max=3.0,
        divisions=25,
        fmt=lambda v: f"{v:.2f}×",
    )

    slider_block = ft.Container(
        content=factor_col,
        visible=cfg.get("last_audio_speed_on", False),
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_change(e) -> None:
        slider_block.visible = bool(e.control.value)
        if slider_block.page:
            slider_block.update()

    speed_switch = switch_row(
        "Mudar velocidade (sem alterar tom)",
        cfg.get("last_audio_speed_on", False),
        on_change=_on_change,
    )
    _icon = help_icon_for("audio.speed", page)

    control = ft.Column(
        spacing=Space.sm,
        controls=[
            ft.Row(
                [speed_switch] + ([_icon] if _icon else []),
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            slider_block,
        ],
    )

    def _set_disabled(running: bool) -> None:
        speed_switch.disabled = running
        factor_slider.disabled = running

    refs = SpeedRefs(
        get_factor=lambda: float(factor_slider.value) if speed_switch.value else 1.0,
        set_disabled=_set_disabled,
    )
    return control, refs
