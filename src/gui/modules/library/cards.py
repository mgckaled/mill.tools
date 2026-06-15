"""Item card factory for the Library grid (module-local, not in the DS).

Each card shows a media area (a type icon, swapped for a thumbnail later via
`set_thumbnail`), the file name, a category badge and size·date. The card body
is clickable when `on_open` is given; an optional actions row hosts the bridge
buttons. Accent color per kind reuses the Home palette.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.core.library.types import (
    KIND_AUDIO,
    KIND_DOCUMENT,
    KIND_IMAGE,
    KIND_TRANSCRIPTION,
    KIND_VIDEO,
    LibraryItem,
)
from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Color, Radius, Space, Type

# Accent per kind — same mapping the Home cards use.
KIND_ACCENT: dict[str, str] = {
    KIND_AUDIO: Color.log.ok,
    KIND_VIDEO: Color.log.info,
    KIND_IMAGE: Color.log.step,
    KIND_TRANSCRIPTION: Color.log.work,
    KIND_DOCUMENT: Color.log.error,
}

KIND_ICON: dict[str, str] = {
    KIND_AUDIO: ft.Icons.AUDIO_FILE_OUTLINED,
    KIND_VIDEO: ft.Icons.VIDEO_FILE_OUTLINED,
    KIND_IMAGE: ft.Icons.IMAGE_OUTLINED,
    KIND_TRANSCRIPTION: ft.Icons.SUBTITLES_OUTLINED,
    KIND_DOCUMENT: ft.Icons.DESCRIPTION_OUTLINED,
}

# Category → short PT-BR badge shown on the card (visible label = Portuguese).
CATEGORY_LABEL: dict[str, str] = {
    "source": "Origem",
    "processed": "Processado",
    "text": "Texto",
    "analysis": "Análise",
    "digest": "Resumo",
}

_MEDIA_H = 120

# 1×1 px transparent PNG — ft.Image requires a src in Flet 0.85; this is the
# placeholder until the thumbnail thread swaps in a real preview.
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fmt_size(num_bytes: int) -> str:
    """Human-readable file size (B / KB / MB / GB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            if unit == "B":
                return f"{int(size)} B"
            if size < 1024:
                return f"{size:.1f} {unit}"
        if unit != "MB":
            size /= 1024
    return f"{size / 1024:.1f} GB"


def _fmt_date(mtime: float) -> str:
    """Absolute date as dd/mm/yyyy HH:MM (local time)."""
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(mtime))


@dataclass
class ItemCard:
    """Handle to a built card.

    Attributes:
        control: The Flet control to place in the grid.
        set_thumbnail: Swap the type icon for a preview image (PR6.3 thread).
    """

    control: ft.Control
    set_thumbnail: Callable[[bytes], None]


def build_item_card(
    item: LibraryItem,
    *,
    page: ft.Page,
    on_open: Callable[[LibraryItem], None] | None = None,
    build_actions: Callable[[LibraryItem], list[ft.Control]] | None = None,
) -> ItemCard:
    """Build one grid card for a Library item.

    Args:
        item: The item to render.
        page: Flet page (needed for scoped updates).
        on_open: Optional callback when the card body is clicked.
        build_actions: Optional factory returning action controls (bridges).
    """
    accent = KIND_ACCENT.get(item.kind, ft.Colors.PRIMARY)
    icon_name = KIND_ICON.get(item.kind, ft.Icons.INSERT_DRIVE_FILE_OUTLINED)

    type_icon = ft.Icon(icon_name, size=44, color=accent)
    # gapless_playback avoids a flicker when the icon is replaced by a thumb.
    thumb_img = ft.Image(
        _BLANK_PNG,
        fit=ft.BoxFit.COVER,
        expand=True,
        gapless_playback=True,
        visible=False,
    )

    media = ft.Container(
        content=ft.Stack(
            [
                ft.Container(
                    content=type_icon, alignment=ft.Alignment.CENTER, expand=True
                ),
                ft.Container(content=thumb_img, expand=True),
            ],
            expand=True,
        ),
        height=_MEDIA_H,
        bgcolor=ft.Colors.with_opacity(0.06, accent),
        border_radius=Radius.sm,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        alignment=ft.Alignment.CENTER,
    )

    name_text = ft.Text(
        item.path.name,
        size=Type.input.size,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.ON_SURFACE,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        tooltip=item.path.name,
    )

    badge = ft.Container(
        content=ft.Text(
            CATEGORY_LABEL.get(item.category, item.category),
            size=Type.small.size,
            color=accent,
            weight=ft.FontWeight.W_600,
        ),
        bgcolor=ft.Colors.with_opacity(0.12, accent),
        border_radius=Radius.pill,
        padding=ft.Padding(left=Space.xs, right=Space.xs, top=1, bottom=1),
    )

    meta_text = ft.Text(
        f"{_fmt_size(item.size_bytes)} · {_fmt_date(item.modified)}",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    # Only the media area opens the file — this keeps the action buttons'
    # own taps intact (no whole-card GestureDetector swallowing them).
    media_control: ft.Control = media
    if on_open is not None:
        media_control = ft.GestureDetector(
            mouse_cursor=Cursor.interactive,
            content=media,
            on_tap=lambda _e, _it=item: on_open(_it),
        )

    body_controls: list[ft.Control] = [
        media_control,
        name_text,
        ft.Row(
            controls=[badge, ft.Container(expand=True)],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        meta_text,
    ]

    if build_actions is not None:
        actions = build_actions(item)
        if actions:
            body_controls.append(ft.Row(controls=actions, spacing=Space.xxs, wrap=True))

    card_inner = ft.Container(
        content=ft.Column(controls=body_controls, spacing=Space.xs),
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.sm, bottom=Space.sm
        ),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=Radius.md,
        bgcolor=Color.dark.surface_variant,
    )

    def _set_thumbnail(data: bytes) -> None:
        """Swap the type icon for a preview image (called from the thumb thread)."""
        thumb_img.src = data
        thumb_img.visible = True
        type_icon.visible = False
        try:
            thumb_img.update()
            type_icon.update()
        except RuntimeError:
            pass

    return ItemCard(control=card_inner, set_thumbnail=_set_thumbnail)
