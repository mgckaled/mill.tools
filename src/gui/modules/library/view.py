"""Library module — full-screen browser over output/ with a filterable grid."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

import flet as ft

from src.core.library.scanner import filter_items, scan_library, sort_items
from src.core.library.types import LibraryItem
from src.gui import settings
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

# Sort key → visible PT-BR label (the key is what gets persisted).
_SORT_OPTIONS = [
    ("modified", "Data (recente)"),
    ("name", "Nome (A→Z)"),
    ("size", "Tamanho (maior)"),
]

# Date-range key → seconds back from now (None = any date).
_SINCE_DELTAS: dict[str, int | None] = {
    "all": None,
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}
_DATE_OPTIONS = [
    ("all", "Qualquer data"),
    ("24h", "Últimas 24h"),
    ("7d", "Últimos 7 dias"),
    ("30d", "Últimos 30 dias"),
]

_SEARCH_DEBOUNCE_S = 0.25


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
    cfg = settings.load()

    # Cached scan result; filtering/sorting/searching operate on this in memory
    # so keystrokes never hit the filesystem. A re-scan only happens on mount.
    _all_items: list[LibraryItem] = []
    _query: list[str] = [""]
    _search_gen: list[int] = [0]

    # ------------------------------------------------------------------
    # Grid + count + empty state
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
                    ft.Icons.INBOX_OUTLINED, size=48, color=ft.Colors.OUTLINE_VARIANT
                ),
                ft.Text(
                    "Nada por aqui",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Ajuste os filtros ou gere saídas nos outros módulos.",
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
    # Filter / search / sort state readers
    # ------------------------------------------------------------------

    def _active_kinds() -> set[str] | None:
        value = get_filter()
        return None if value == "all" else {value}

    def _active_since() -> float | None:
        delta = _SINCE_DELTAS.get(date_dd.value)
        return None if delta is None else time.time() - delta

    # ------------------------------------------------------------------
    # Apply (in-memory) + rescan (filesystem)
    # ------------------------------------------------------------------

    def _apply() -> None:
        """Filter/sort the cached scan and rebuild the grid (no page.update)."""
        by = sort_dd.value or "modified"
        items = sort_items(
            filter_items(
                _all_items,
                kinds=_active_kinds(),
                query=_query[0] or None,
                since=_active_since(),
            ),
            by=by,
            desc=(by != "name"),
        )
        grid.controls = [build_item_card(it, page=page).control for it in items]
        count_label.value = (
            f"{len(items)} arquivo" if len(items) == 1 else f"{len(items)} arquivos"
        )
        empty_state.visible = not items
        grid.visible = bool(items)

    def _apply_and_update() -> None:
        _apply()
        try:
            page.update()
        except Exception:
            pass

    def _rescan() -> None:
        nonlocal _all_items
        _all_items = scan_library()
        _apply()

    # ------------------------------------------------------------------
    # Kind filter (segmented selector)
    # ------------------------------------------------------------------

    def _on_filter_change(value: str) -> None:
        settings.set("last_library_filter", value)
        _apply()  # segmented_selector flushes page.update() after this returns

    filter_grid, get_filter, _ = segmented_selector(
        options=_FILTER_OPTIONS,
        value=cfg.get("last_library_filter", "all"),
        page=page,
        on_change=_on_filter_change,
        columns=6,
        labels=_FILTER_LABELS,
    )

    # ------------------------------------------------------------------
    # Search field (debounced) + sort + date dropdowns
    # ------------------------------------------------------------------

    def _on_search(e: ft.ControlEvent) -> None:
        _query[0] = e.control.value or ""
        _search_gen[0] += 1
        gen = _search_gen[0]

        async def _later() -> None:
            await asyncio.sleep(_SEARCH_DEBOUNCE_S)
            if gen != _search_gen[0]:
                return  # superseded by a newer keystroke
            _apply_and_update()

        page.run_task(_later)

    search_field = ft.TextField(
        hint_text="Buscar por nome…",
        prefix_icon=ft.Icons.SEARCH,
        on_change=_on_search,
        dense=True,
        expand=True,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _on_sort_change(e: ft.ControlEvent) -> None:
        settings.set("last_library_sort", e.control.value)
        _apply_and_update()

    sort_dd = ft.Dropdown(
        label="Ordenar",
        value=cfg.get("last_library_sort", "modified"),
        options=[ft.dropdown.Option(k, lbl) for k, lbl in _SORT_OPTIONS],
        width=180,
        on_change=_on_sort_change,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    date_dd = ft.Dropdown(
        label="Período",
        value="all",
        options=[ft.dropdown.Option(k, lbl) for k, lbl in _DATE_OPTIONS],
        width=170,
        on_change=lambda _e: _apply_and_update(),
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    toolbar = ft.Row(
        controls=[search_field, sort_dd, date_dd],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
            toolbar,
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
        _rescan()

    return Module(
        id=_MODULE_ID,
        label="Biblioteca",
        icon=ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
        selected_icon=ft.Icons.COLLECTIONS_BOOKMARK,
        control=control,
        on_mount=_on_mount,
    )
