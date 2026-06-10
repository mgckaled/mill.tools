"""Stamp operation block — preset selector + custom text."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import labeled_field, section_label, segmented_selector
from src.gui.theme.tokens import Layout, Space, Type

_PRESETS = ["PAGO", "RASCUNHO", "CONFIDENCIAL", "Personalizado"]


class StampRefs(NamedTuple):
    get_text: Callable[[], str]


def build_stamp_block(page: ft.Page) -> tuple[ft.Column, StampRefs]:
    """Build the stamp operation block."""
    _preset_get: list[Callable] = []
    preset_grid, _get_preset, _ = segmented_selector(
        _PRESETS, "RASCUNHO", page, columns=2,
    )
    _preset_get.append(_get_preset)

    custom_field = ft.TextField(
        hint_text="Texto personalizado",
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        visible=False,
    )

    def _on_preset_change(v: str) -> None:
        custom_field.visible = v == "Personalizado"
        try:
            custom_field.update()
        except RuntimeError:
            pass

    # Patch: wrap grid to intercept selection changes
    _orig_get = _get_preset

    def _patched_get() -> str:
        val = _orig_get()
        _on_preset_change(val)
        return val

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            section_label("Carimbo"),
            preset_grid,
            custom_field,
        ],
    )

    def _get_text() -> str:
        preset = _preset_get[0]()
        if preset == "Personalizado":
            return custom_field.value or "PERSONALIZADO"
        return preset

    return block, StampRefs(get_text=_get_text)
