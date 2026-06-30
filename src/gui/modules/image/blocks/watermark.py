"""Watermark operation block for the image module."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import (
    Cursor,
    help_icon_for,
    section_label,
    segmented_selector,
)
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Layout, Space, Type


class WatermarkRefs(NamedTuple):
    get_mode: Callable[[], str]
    get_text: Callable[[], str]
    get_text_color: Callable[[], str]
    get_text_size: Callable[[], int]
    get_path: Callable[[], Path | None]
    get_position: Callable[[], str]
    get_opacity: Callable[[], float]
    get_rotation: Callable[[], int]


def build_watermark_block(page: ft.Page) -> tuple[ft.Column, WatermarkRefs]:
    """Build the watermark operation block.

    Returns the Column widget and a WatermarkRefs for value collection.
    """
    _mode_get: list[Callable] = []
    _wm_path: list[Path | None] = [None]

    path_text = ft.Text(
        "Nenhum arquivo selecionado",
        size=12,
        color=ft.Colors.ON_SURFACE_VARIANT,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )

    picker = ft.FilePicker()
    page.services.append(picker)

    async def _pick_image(_e) -> None:
        files = await picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.IMAGE,
        )
        if files and files[0].path:
            _wm_path[0] = Path(files[0].path)
            path_text.value = Path(files[0].path).name
            try:
                if path_text.page:
                    path_text.update()
            except RuntimeError:
                pass

    text_tf = ft.TextField(
        hint_text="Texto da marca d'água",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    text_color_tf = ft.TextField(
        value="#ffffff",
        label="Cor (hex)",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    size_col, size_slider = labeled_slider(
        label="Tamanho",
        value=40.0,
        min=8.0,
        max=120.0,
        divisions=112,
        fmt=lambda v: f"{int(v)}",
    )
    opacity_col, opacity_slider = labeled_slider(
        label="Opacidade",
        value=0.5,
        min=0.0,
        max=1.0,
        divisions=20,
        fmt=lambda v: f"{int(v * 100)}%",
    )
    rotation_col, rotation_slider = labeled_slider(
        label="Rotação",
        value=0.0,
        min=0.0,
        max=360.0,
        divisions=72,
        fmt=lambda v: f"{int(v)}°",
    )

    qr_data_tf = ft.TextField(
        hint_text="URL ou texto do QR Code",
        text_size=Type.input.size,
        height=Layout.field_height,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    qr_col = ft.Column(
        [section_label("Conteúdo do QR"), qr_data_tf],
        spacing=Space.sm,
        visible=False,
    )

    _pos_get: list[Callable] = []
    pos_grid, _pget, _pset = segmented_selector(
        [
            "top-left",
            "top-center",
            "top-right",
            "middle-left",
            "center",
            "middle-right",
            "bottom-left",
            "bottom-center",
            "bottom-right",
            "tile",
        ],
        "bottom-right",
        page,
        labels={
            "top-left": "↖",
            "top-center": "↑",
            "top-right": "↗",
            "middle-left": "←",
            "center": "⬤",
            "middle-right": "→",
            "bottom-left": "↙",
            "bottom-center": "↓",
            "bottom-right": "↘",
            "tile": "▦",
        },
        columns=3,
    )
    _pos_get.append(_pget)

    text_col = ft.Column(
        [
            section_label("Texto"),
            text_tf,
            ft.Row(
                [section_label("Cor"), text_color_tf],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            size_col,
        ],
        spacing=Space.sm,
    )

    image_col = ft.Column(
        [
            section_label("Arquivo de imagem"),
            ft.Row(
                [
                    path_text,
                    ft.OutlinedButton(
                        "Selecionar",
                        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                        on_click=_pick_image,
                        style=ft.ButtonStyle(
                            padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                            mouse_cursor=Cursor.interactive,
                        ),
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=Space.sm,
        visible=False,
    )

    def _on_mode_change(mode: str) -> None:
        text_col.visible = mode == "text"
        image_col.visible = mode == "image"
        qr_col.visible = mode == "qr"
        try:
            if text_col.page:
                text_col.page.update()
        except RuntimeError:
            pass

    mode_grid, _mget, _mset = segmented_selector(
        ["text", "image", "qr"],
        "text",
        page,
        on_change=_on_mode_change,
        labels={"text": "Texto", "image": "Imagem", "qr": "QR Code"},
        columns=3,
    )
    _mode_get.append(_mget)

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Marca d'água"),
                    ft.Container(expand=True),
                    help_icon_for("image.watermark", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Modo"),
            mode_grid,
            text_col,
            image_col,
            qr_col,
            section_label("Posição"),
            pos_grid,
            opacity_col,
            rotation_col,
        ],
    )

    def _get_text() -> str:
        # The core's `text` param doubles as the QR payload in qr mode.
        if _mode_get[0]() == "qr":
            return (qr_data_tf.value or "").strip()
        return (text_tf.value or "").strip()

    refs = WatermarkRefs(
        get_mode=lambda: _mode_get[0](),
        get_text=_get_text,
        get_text_color=lambda: (text_color_tf.value or "#ffffff").strip(),
        get_text_size=lambda: int(size_slider.value),
        get_path=lambda: _wm_path[0],
        get_position=lambda: _pos_get[0](),
        get_opacity=lambda: float(opacity_slider.value),
        get_rotation=lambda: int(rotation_slider.value),
    )
    return block, refs
