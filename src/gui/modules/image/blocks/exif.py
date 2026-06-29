"""EXIF metadata block for the image module.

A standing section (not an operation card) applied to any image→image op.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, section_label, segmented_selector
from src.gui.theme.tokens import Layout, Space, Type

_MODES = ["preserve", "strip_gps", "strip", "inject"]
_LABELS = {
    "preserve": "Preservar",
    "strip_gps": "Remover GPS",
    "strip": "Remover tudo",
    "inject": "Injetar",
}


class ExifRefs(NamedTuple):
    get_mode: Callable[[], str]
    get_artist: Callable[[], str]
    get_copyright: Callable[[], str]
    get_description: Callable[[], str]
    set_disabled: Callable[[bool], None]


def _field(label: str) -> ft.TextField:
    return ft.TextField(
        label=label,
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )


def build_exif_block(page: ft.Page) -> tuple[ft.Column, ExifRefs]:
    """Build the EXIF metadata section and return its Column + ExifRefs."""
    artist_tf = _field("Artista")
    copyright_tf = _field("Copyright")
    desc_tf = _field("Descrição")

    inject_col = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[artist_tf, copyright_tf, desc_tf],
    )

    def _on_mode(value: str) -> None:
        inject_col.visible = value == "inject"
        if inject_col.page:
            inject_col.update()

    seg_col, get_mode, set_seg_disabled = segmented_selector(
        _MODES,
        "preserve",
        page,
        on_change=_on_mode,
        columns=2,
        labels=_LABELS,
    )

    def _set_disabled(disabled: bool) -> None:
        set_seg_disabled(disabled)
        for tf in (artist_tf, copyright_tf, desc_tf):
            tf.disabled = disabled

    block = ft.Column(
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Metadados (EXIF)"),
                    ft.Container(expand=True),
                    help_icon_for("image.exif", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            seg_col,
            inject_col,
        ],
    )

    refs = ExifRefs(
        get_mode=get_mode,
        get_artist=lambda: (artist_tf.value or "").strip(),
        get_copyright=lambda: (copyright_tf.value or "").strip(),
        get_description=lambda: (desc_tf.value or "").strip(),
        set_disabled=_set_disabled,
    )
    return block, refs
