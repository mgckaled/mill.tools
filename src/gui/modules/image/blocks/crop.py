"""Crop operation block for the image module."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Layout, Space, Type


def _parse_int(tf: ft.TextField, default: int) -> int:
    try:
        v = int((tf.value or "").strip())
        return v if v >= 0 else default
    except ValueError:
        return default


class CropRefs(NamedTuple):
    get_mode: Callable[[], str]
    get_left: Callable[[], int]
    get_top: Callable[[], int]
    get_width: Callable[[], int]
    get_height: Callable[[], int]
    get_ratio: Callable[[], str]
    get_trim_color: Callable[[], str]


def build_crop_block(page: ft.Page) -> tuple[ft.Column, CropRefs]:
    """Build the crop operation block.

    Returns the Column widget and a CropRefs for value collection.
    """
    _mode_get: list[Callable] = []

    left_tf = ft.TextField(
        hint_text="Esquerda px", value="0", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=Type.input.size, height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    top_tf = ft.TextField(
        hint_text="Topo px", value="0", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=Type.input.size, height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    w_tf = ft.TextField(
        hint_text="Largura px (0=até borda)", value="0",
        keyboard_type=ft.KeyboardType.NUMBER, text_size=Type.input.size, height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    h_tf = ft.TextField(
        hint_text="Altura px (0=até borda)", value="0",
        keyboard_type=ft.KeyboardType.NUMBER, text_size=Type.input.size, height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    trim_color_tf = ft.TextField(
        value="#ffffff", text_size=Type.input.size, height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
    )

    manual_col = ft.Column([
        ft.Row([left_tf, top_tf], spacing=8),
        ft.Row([w_tf, h_tf], spacing=8),
    ], spacing=Space.sm)

    _ratio_get: list[Callable] = []
    ratio_grid, _rget, _rset = segmented_selector(
        ["1:1", "4:3", "16:9", "3:2"], "1:1", page, columns=4,
    )
    _ratio_get.append(_rget)
    ratio_col = ft.Column([section_label("Proporção"), ratio_grid], spacing=Space.sm)

    autotrim_col = ft.Column([
        section_label("Cor de fundo a remover"),
        trim_color_tf,
    ], spacing=Space.sm)

    def _on_mode_change(mode: str) -> None:
        manual_col.visible = mode == "manual"
        ratio_col.visible = mode == "ratio"
        autotrim_col.visible = mode == "autotrim"
        try:
            if manual_col.page:
                manual_col.page.update()
        except RuntimeError:
            pass

    mode_grid, _mget, _mset = segmented_selector(
        ["manual", "ratio", "autotrim"],
        "manual",
        page,
        on_change=_on_mode_change,
        labels={"manual": "Manual", "ratio": "Proporção", "autotrim": "Auto-trim"},
        columns=3,
    )
    _mode_get.append(_mget)
    ratio_col.visible = False
    autotrim_col.visible = False

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [section_label("Cortar"), ft.Container(expand=True), help_icon_for("image.crop", page)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Modo"),
            mode_grid,
            manual_col,
            ratio_col,
            autotrim_col,
        ],
    )

    refs = CropRefs(
        get_mode=lambda: _mode_get[0](),
        get_left=lambda: _parse_int(left_tf, 0),
        get_top=lambda: _parse_int(top_tf, 0),
        get_width=lambda: _parse_int(w_tf, 0),
        get_height=lambda: _parse_int(h_tf, 0),
        get_ratio=lambda: _ratio_get[0](),
        get_trim_color=lambda: (trim_color_tf.value or "#ffffff").strip(),
    )
    return block, refs
