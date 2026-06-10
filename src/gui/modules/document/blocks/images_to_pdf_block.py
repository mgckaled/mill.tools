"""Images-to-PDF operation block — output name field."""
from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import labeled_field
from src.gui.theme.tokens import Layout, Space


class ImagesToPdfRefs(NamedTuple):
    get_output_name: Callable[[], str]


def build_images_to_pdf_block() -> tuple[ft.Column, ImagesToPdfRefs]:
    """Build the images-to-pdf operation block."""
    name_field = ft.TextField(
        hint_text="Nome do arquivo de saída (opcional)",
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            labeled_field("Nome do arquivo de saída", name_field),
        ],
    )
    return block, ImagesToPdfRefs(get_output_name=lambda: name_field.value or "")
