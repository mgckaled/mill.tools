"""Encrypt operation block — password field."""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import help_icon_for, labeled_field, section_label
from src.gui.theme.tokens import Layout, Space


class EncryptRefs(NamedTuple):
    get_password: Callable[[], str]


def build_encrypt_block(page: ft.Page) -> tuple[ft.Column, EncryptRefs]:
    """Build the encrypt operation block."""
    password_field = ft.TextField(
        hint_text="Senha para proteger o documento",
        password=True,
        can_reveal_password=True,
        height=Layout.field_height,
        text_size=13,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )

    block = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            ft.Row(
                [
                    section_label("Criptografar"),
                    ft.Container(expand=True),
                    help_icon_for("document.password", page),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            labeled_field("Senha (AES-256)", password_field),
        ],
    )
    return block, EncryptRefs(get_password=lambda: password_field.value or "")
