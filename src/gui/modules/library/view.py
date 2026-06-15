"""Library module — full-screen browser over output/ with a filterable grid."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import flet as ft

from src.core.library.scanner import filter_items, scan_library, sort_items
from src.gui.modules.base import Module
from src.gui.modules.library.cards import build_item_card
from src.gui.theme.components import hairline, segmented_selector
from src.gui.theme.tokens import Layout, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "library"

# Filter chips: value → PT-BR label (visible). "all" clears the kind filter.
_FILTER_OPTIONS = ["all", "audio", "video", "image", "transcription", "document"]
_FILTER_LABELS = {
    "all": "Todos",
    "audio": "Áudio",
    "video": "Vídeo",
    "image": "Imagens",
    "transcription": "Transcrição",
    "document": "Documentos",
}


def build_library_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Library module — a read-only grid of every output/ file.

    Args:
        page: Flet page.
        bus: Shared application EventBus (used for auto-refresh in PR6.5).
        cancel_event: threading.Event (kept for signature symmetry; no pipeline).
        pipeline_running: Shared [bool] with app.py (signature symmetry).
        nav: List holding [navigate_to] — used by the bridge actions (PR6.4).
    """

    # ------------------------------------------------------------------
    # Grid + count
    # ------------------------------------------------------------------

    grid = ft.GridView(
        expand=True,
        max_extent=220,
        child_aspect_ratio=0.8,
        spacing=Space.md,
        run_spacing=Space.md,
        cache_extent=400,
        padding=ft.Padding(left=0, right=Space.xs, top=0, bottom=Space.md),
    )

    count_label = ft.Text(
        "",
        size=Type.caption.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    empty_state = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.INBOX_OUTLINED,
                    size=48,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Nada por aqui ainda",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Gere saídas nos outros módulos e elas aparecerão aqui.",
                    size=Type.input.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=Space.sm,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        visible=False,
    )

    grid_area = ft.Stack([grid, empty_state], expand=True)

    # ------------------------------------------------------------------
    # Rescan + render
    # ------------------------------------------------------------------

    def _active_kinds() -> set[str] | None:
        value = get_filter()
        return None if value == "all" else {value}

    def _rescan_and_render() -> None:
        items = sort_items(
            filter_items(scan_library(), kinds=_active_kinds()),
            by="modified",
            desc=True,
        )
        grid.controls = [build_item_card(it, page=page).control for it in items]
        count_label.value = (
            f"{len(items)} arquivo" if len(items) == 1 else f"{len(items)} arquivos"
        )
        empty_state.visible = not items
        grid.visible = bool(items)

    # ------------------------------------------------------------------
    # Filter selector (kind)
    # ------------------------------------------------------------------

    filter_grid, get_filter, _ = segmented_selector(
        options=_FILTER_OPTIONS,
        value="all",
        page=page,
        on_change=lambda _v: _rescan_and_render(),
        columns=6,
        labels=_FILTER_LABELS,
    )

    # ------------------------------------------------------------------
    # Header + layout
    # ------------------------------------------------------------------

    header = ft.Row(
        controls=[
            ft.Icon(ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED, color=ft.Colors.PRIMARY),
            ft.Text(
                "Biblioteca",
                size=Type.title.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE,
            ),
            ft.Container(expand=True),
            count_label,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=Space.sm,
    )

    content_col = ft.Column(
        controls=[
            header,
            filter_grid,
            hairline(),
            grid_area,
        ],
        expand=True,
        spacing=Space.md,
    )

    control = ft.Container(
        content=content_col,
        expand=True,
        padding=ft.Padding(
            left=Layout.content_lateral,
            right=Layout.content_lateral,
            top=Space.md,
            bottom=Space.md,
        ),
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        # Re-scan every time the tab is opened so fresh outputs show up.
        _rescan_and_render()

    return Module(
        id=_MODULE_ID,
        label="Biblioteca",
        icon=ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
        selected_icon=ft.Icons.COLLECTIONS_BOOKMARK,
        control=control,
        on_mount=_on_mount,
    )
