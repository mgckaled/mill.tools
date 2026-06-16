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


# ── List (table) view ─────────────────────────────────────────────────────

# Column widths shared by the header and every row so the cells line up. The
# name column flexes (expand=True); the rest are fixed so values stay aligned.
_LIST_ICON_W = 30
_LIST_CAT_W = 116
_LIST_SIZE_W = 84
_LIST_DATE_W = 140
_LIST_ACTIONS_W = 128


def _hcell(
    label: str, *, width: int | None = None, expand: bool = False
) -> ft.Container:
    """One header cell (column title), aligned with the row cells below it."""
    return ft.Container(
        content=ft.Text(
            label,
            size=Type.small.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        width=width,
        expand=expand,
    )


def build_list_header() -> ft.Control:
    """Column-title row for the Library list/table view (mirrors build_item_row)."""
    cells = [
        ft.Container(width=_LIST_ICON_W),  # leading icon column (no title)
        _hcell("Nome", expand=True),
        _hcell("Categoria", width=_LIST_CAT_W),
        _hcell("Tamanho", width=_LIST_SIZE_W),
        _hcell("Data", width=_LIST_DATE_W),
        _hcell("Ações", width=_LIST_ACTIONS_W),
    ]
    return ft.Container(
        content=ft.Row(
            cells, spacing=Space.sm, vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )


def build_item_row(
    item: LibraryItem,
    *,
    page: ft.Page,
    on_open: Callable[[LibraryItem], None] | None = None,
    build_actions: Callable[[LibraryItem], list[ft.Control]] | None = None,
) -> ft.Control:
    """Build one table row for a Library item (list view).

    The layout mirrors `build_list_header` so the columns line up. The cells
    (icon, name, category, size, date) open the file on click; the trailing
    actions stay independently tappable (they sit outside the click area).
    Truncated text exposes its full value through a tooltip.

    Args:
        item: The item to render.
        page: Flet page (kept for signature symmetry with build_item_card).
        on_open: Optional callback when the row body is clicked.
        build_actions: Optional factory returning action controls (bridges).
    """
    accent = KIND_ACCENT.get(item.kind, ft.Colors.PRIMARY)
    icon_name = KIND_ICON.get(item.kind, ft.Icons.INSERT_DRIVE_FILE_OUTLINED)

    leading = ft.Container(
        content=ft.Icon(icon_name, size=18, color=accent),
        width=_LIST_ICON_W,
        alignment=ft.Alignment.CENTER,
    )
    name_cell = ft.Text(
        item.path.name,
        size=Type.input.size,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.ON_SURFACE,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        tooltip=item.path.name,
        expand=True,
    )
    cat_label = CATEGORY_LABEL.get(item.category, item.category)
    cat_cell = ft.Container(
        content=ft.Container(
            content=ft.Text(
                cat_label,
                size=Type.small.size,
                color=accent,
                weight=ft.FontWeight.W_600,
                no_wrap=True,
            ),
            bgcolor=ft.Colors.with_opacity(0.12, accent),
            border_radius=Radius.pill,
            padding=ft.Padding(left=Space.xs, right=Space.xs, top=1, bottom=1),
        ),
        width=_LIST_CAT_W,
        alignment=ft.Alignment.CENTER_LEFT,
    )
    size_str = _fmt_size(item.size_bytes)
    size_cell = ft.Container(
        content=ft.Text(
            size_str,
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            tooltip=size_str,
        ),
        width=_LIST_SIZE_W,
        alignment=ft.Alignment.CENTER_LEFT,
    )
    date_str = _fmt_date(item.modified)
    date_cell = ft.Container(
        content=ft.Text(
            date_str,
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            tooltip=date_str,
        ),
        width=_LIST_DATE_W,
        alignment=ft.Alignment.CENTER_LEFT,
    )

    cells = ft.Container(
        content=ft.Row(
            controls=[leading, name_cell, cat_cell, size_cell, date_cell],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    # Only the cells open the file; the actions stay tappable because they are
    # siblings of the click area, never descendants of its GestureDetector.
    clickable: ft.Control
    if on_open is not None:
        clickable = ft.GestureDetector(
            mouse_cursor=Cursor.interactive,
            content=cells,
            on_tap=lambda _e, _it=item: on_open(_it),
            expand=True,
        )
    else:
        cells.expand = True
        clickable = cells

    actions = build_actions(item) if build_actions is not None else []
    actions_cell = ft.Container(
        content=ft.Row(
            controls=actions,
            spacing=Space.xxs,
            alignment=ft.MainAxisAlignment.END,
        ),
        width=_LIST_ACTIONS_W,
        alignment=ft.Alignment.CENTER_RIGHT,
    )

    row_container = ft.Container(
        content=ft.Row(
            controls=[clickable, actions_cell],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
        ),
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        border_radius=Radius.sm,
    )

    def _on_hover(e: ft.HoverEvent) -> None:
        row_container.bgcolor = Color.dark.surface_hover if e.data == "true" else None
        try:
            row_container.update()
        except RuntimeError:
            pass

    row_container.on_hover = _on_hover
    return row_container
