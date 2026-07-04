"""Observatório — sub-aba Uso de disco: tamanho de cada entrada em ~/.mill-tools/.

Nested under the Índice/RAG tab, beside Índice and Painel. Cheap (only
``os.stat`` calls, no imports of optional-extra packages, no network) — unlike
the Status tab, this never needs a background thread.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.core.observatory.disk_usage import disk_usage, total_bytes
from src.core.rag.stats import fmt_disk_size
from src.gui.theme.components import help_icon_for, section_label
from src.gui.theme.tokens import IconSize, Space, Type


def _entry_row(entry) -> ft.Row:
    icon = (
        ft.Icons.FOLDER_OUTLINED
        if entry.is_dir
        else ft.Icons.INSERT_DRIVE_FILE_OUTLINED
    )
    return ft.Row(
        controls=[
            ft.Icon(icon, size=Type.body.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(
                entry.name,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE,
                expand=True,
            ),
            ft.Text(
                fmt_disk_size(entry.size_bytes),
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                font_family=Type.FONT_MONO,
            ),
        ],
        spacing=Space.sm,
    )


def build_disk_usage_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the disk usage sub-tab control plus an ``apply()`` refresher."""
    entries_col = ft.Column(spacing=Space.xs)
    total_text = ft.Text(
        "—",
        size=Type.body_strong.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE,
        font_family=Type.FONT_MONO,
    )

    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.STORAGE_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY),
        ft.Text(
            "Uso de disco",
            size=Type.heading.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
        ft.Container(expand=True),
        ft.Text("Total:", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT),
        total_text,
    ]
    _help = help_icon_for("observatory.disk_usage", page)
    if _help is not None:
        header_controls.insert(2, _help)

    control = ft.Column(
        controls=[
            ft.Row(
                header_controls,
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("~/.mill-tools/"),
            entries_col,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def apply() -> None:
        entries = disk_usage()
        if not entries:
            entries_col.controls = [
                ft.Text(
                    "Nenhum arquivo em ~/.mill-tools/ ainda.",
                    italic=True,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    size=Type.input.size,
                )
            ]
        else:
            entries_col.controls = [_entry_row(e) for e in entries]
        total_text.value = fmt_disk_size(total_bytes(entries))
        try:
            control.update()
        except Exception:
            pass

    return control, apply
