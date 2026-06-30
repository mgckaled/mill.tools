"""Filter operation block — a clickable grid of live filter previews."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import Cursor, help_icon_for, section_label
from src.gui.theme.tokens import Radius, Space, Type

_FILTERS: list[tuple[str, str]] = [
    ("blur", "Blur"),
    ("sharpen", "Nitidez"),
    ("autocontrast", "Autocontraste"),
    ("equalize", "Equalizar"),
    ("grayscale", "Cinza"),
]
_NAMES = [n for n, _ in _FILTERS]

# 1×1 px transparent PNG placeholder (Flet 0.85 requires src in the constructor).
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FilterRefs(NamedTuple):
    get_type: Callable[[], str]
    render_previews: Callable[[str], None]


def build_filter_block(page: ft.Page) -> tuple[ft.Column, FilterRefs]:
    """Build the filter grid block; render_previews(path) fills the thumbnails."""
    _selected = ["blur"]
    _imgs: dict[str, ft.Image] = {}
    _cells: dict[str, ft.Container] = {}

    def _refresh_selection() -> None:
        for name, cell in _cells.items():
            active = name == _selected[0]
            side = ft.BorderSide(
                2 if active else 1,
                ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT,
            )
            cell.border = ft.Border(left=side, right=side, top=side, bottom=side)

    def _select(name: str) -> None:
        _selected[0] = name
        _refresh_selection()
        try:
            page.update()
        except Exception:
            pass

    cells_row = ft.Row(wrap=True, spacing=6, run_spacing=6)
    for name, label in _FILTERS:
        img = ft.Image(
            _BLANK_PNG,
            width=96,
            height=96,
            fit=ft.BoxFit.COVER,
            border_radius=Radius.sm,
        )
        _imgs[name] = img
        cell = ft.Container(
            content=ft.Column(
                [
                    img,
                    ft.Text(label, size=Type.tiny.size, text_align=ft.TextAlign.CENTER),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            padding=4,
            border_radius=Radius.sm,
        )
        _cells[name] = cell
        cells_row.controls.append(
            ft.GestureDetector(
                mouse_cursor=Cursor.interactive,
                content=cell,
                on_tap=lambda _e, n=name: _select(n),
            )
        )
    _refresh_selection()

    hint = ft.Text(
        "Selecione uma imagem para pré-visualizar os filtros.",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    def _render_previews(path: str) -> None:
        async def _run() -> None:
            from src.core.image.filter_previews import generate_filter_previews

            previews = await asyncio.to_thread(
                generate_filter_previews, Path(path), _NAMES
            )
            for name, data in previews.items():
                if name in _imgs:
                    _imgs[name].src = data
            hint.visible = False
            try:
                cells_row.update()
                hint.update()
            except Exception:
                pass

        try:
            page.run_task(_run)
        except Exception:
            pass

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Filtros"),
                    ft.Container(expand=True),
                    help_icon_for("image.filter", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            hint,
            cells_row,
        ],
    )

    refs = FilterRefs(
        get_type=lambda: _selected[0],
        render_previews=_render_previews,
    )
    return block, refs
