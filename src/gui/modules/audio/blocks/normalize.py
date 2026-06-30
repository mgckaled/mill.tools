"""Normalize block for the audio module — loudnorm toggle + LUFS target."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, switch_row
from src.gui.theme.tokens import Space, Type


class NormalizeRefs(NamedTuple):
    get_normalize: Callable[[], bool]
    get_target_lufs: Callable[[], float]
    set_normalize: Callable[[bool], None]
    set_target_lufs: Callable[[float], None]
    set_disabled: Callable[[bool], None]


def build_normalize_block(page: ft.Page, cfg: dict) -> tuple[ft.Control, NormalizeRefs]:
    """Build the normalize toggle + LUFS target slider block.

    The LUFS slider is revealed only when the switch is on (container visible=
    + animate_opacity), matching the original form behaviour.
    """
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

    _normalize_icon = help_icon_for("audio.normalize", page)

    control = ft.Column(
        spacing=Space.sm,
        controls=[
            ft.Row(
                [normalize_switch] + ([_normalize_icon] if _normalize_icon else []),
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            lufs_block,
        ],
    )

    def _set_normalize(value: bool) -> None:
        normalize_switch.value = value
        lufs_block.visible = value
        if normalize_switch.page:
            normalize_switch.update()
        if lufs_block.page:
            lufs_block.update()

    def _set_target_lufs(value: float) -> None:
        lufs_values[0] = value
        _lufs_ctl.value = value
        _lufs_value_text.value = f"{value:.0f} LUFS"
        if _lufs_ctl.page:
            _lufs_ctl.update()
        if _lufs_value_text.page:
            _lufs_value_text.update()

    def _set_disabled(running: bool) -> None:
        normalize_switch.disabled = running
        _lufs_ctl.disabled = running

    refs = NormalizeRefs(
        get_normalize=lambda: bool(normalize_switch.value),
        get_target_lufs=lambda: lufs_values[0],
        set_normalize=_set_normalize,
        set_target_lufs=_set_target_lufs,
        set_disabled=_set_disabled,
    )
    return control, refs
