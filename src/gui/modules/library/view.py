"""Library module — full-screen browser over output/ with a filterable grid."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from typing import TYPE_CHECKING

import flet as ft

from src.core.library.scanner import filter_items, scan_library, sort_items
from src.core.library.thumbnails import thumbnail_for
from src.core.library.types import (
    KIND_AUDIO,
    KIND_DOCUMENT,
    KIND_IMAGE,
    KIND_VIDEO,
    LibraryItem,
)
from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.base import Module
from src.gui.modules.library.cards import (
    ItemCard,
    build_item_card,
    build_item_row,
    build_list_header,
)
from src.gui.theme.components import (
    Cursor,
    hairline,
    help_icon_for,
    secondary_button,
    segmented_selector,
)
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

# Category filter: source files vs derived/processed outputs. "processed"
# groups every non-source category (processed + text/analysis/digest).
_CATEGORY_OPTIONS = [
    ("all", "Todas"),
    ("source", "Origem"),
    ("processed", "Processado"),
]
_PROCESSED_CATEGORIES = {"processed", "text", "analysis", "digest"}

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

# Cap how many cards render at once; "Carregar mais" reveals the next batch.
# Guards against the GridView page.update() slowdown with thousands of items
# (Flet issue #6270) — a personal library rarely needs more than one page.
_PAGE_SIZE = 120

# Bridge targets per kind: (module_id, tooltip, icon). Sending a file back to
# its own module means "reprocess it"; audio/video also reach Transcription.
_BRIDGES: dict[str, list[tuple[str, str, str]]] = {
    KIND_AUDIO: [
        ("transcription", "Transcrever", ft.Icons.SUBTITLES_OUTLINED),
        ("audio", "Reprocessar no Áudio", ft.Icons.GRAPHIC_EQ_OUTLINED),
    ],
    KIND_VIDEO: [
        ("transcription", "Transcrever", ft.Icons.SUBTITLES_OUTLINED),
        ("audio", "Extrair áudio", ft.Icons.GRAPHIC_EQ_OUTLINED),
    ],
    KIND_IMAGE: [
        ("image", "Reprocessar nas Imagens", ft.Icons.IMAGE_OUTLINED),
    ],
    KIND_DOCUMENT: [
        ("document", "Reprocessar nos Documentos", ft.Icons.DESCRIPTION_OUTLINED),
    ],
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
    cfg = settings.load()

    # Cached scan result; filtering/sorting/searching operate on this in memory
    # so keystrokes never hit the filesystem. A re-scan only happens on mount.
    _all_items: list[LibraryItem] = []
    _query: list[str] = [""]
    _search_gen: list[int] = [0]

    # Display mode: "grid" (cards + thumbnails) or "list" (compact table rows).
    _view_mode: list[str] = [cfg.get("last_library_view", "grid")]

    # Thumbnails are generated off the UI thread; the generation counter drops
    # stale results from a previous scan/apply (same trick as the audio player).
    # Cache keyed by (path, mtime) so edits invalidate automatically.
    _thumb_gen: list[int] = [0]
    _thumb_cache: dict[tuple[str, float], bytes] = {}

    # How many items are currently revealed (paging cap).
    _shown: list[int] = [_PAGE_SIZE]

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

    # List/table view — a fixed column header above a lazily rendered ListView.
    list_header = build_list_header()
    list_body = ft.ListView(
        expand=True,
        spacing=0,
        cache_extent=600,
        padding=ft.Padding(left=0, right=Space.xs, top=0, bottom=Space.md),
    )
    list_container = ft.Column(
        controls=[list_header, list_body],
        expand=True,
        spacing=0,
        visible=False,
    )

    grid_area = ft.Stack([grid, list_container, empty_state], expand=True)

    # "Load more" — on_click wired after _on_load_more is defined.
    load_more_btn = secondary_button("Carregar mais", icon=ft.Icons.EXPAND_MORE)
    load_more_btn.visible = False
    load_more_row = ft.Row(
        controls=[load_more_btn],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    # ------------------------------------------------------------------
    # Filter / search / sort state readers
    # ------------------------------------------------------------------

    def _active_kinds() -> set[str] | None:
        value = get_filter()
        return None if value == "all" else {value}

    def _active_since() -> float | None:
        delta = _SINCE_DELTAS.get(date_dd.value)
        return None if delta is None else time.time() - delta

    def _active_categories() -> set[str] | None:
        value = cat_dd.value
        if value == "source":
            return {"source"}
        if value == "processed":
            return _PROCESSED_CATEGORIES
        return None

    # ------------------------------------------------------------------
    # Item actions: open file, open folder, bridges to other modules
    # ------------------------------------------------------------------

    def _toast(message: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.ERROR)
        page.snack_bar.open = True
        page.update()

    def _open_file(item: LibraryItem) -> None:
        try:
            os.startfile(str(item.path))  # Windows shell open
        except Exception as exc:
            logging.debug("[d] startfile failed for %s: %s", item.path, exc)
            _toast(f"Não foi possível abrir {item.path.name}")

    def _open_folder(item: LibraryItem) -> None:
        try:
            subprocess.run(["explorer", "/select,", str(item.path)], check=False)
        except Exception as exc:
            logging.debug("[d] explorer select failed for %s: %s", item.path, exc)

    def _bridge_targets(item: LibraryItem) -> list[tuple[str, str, str]]:
        # A document that isn't a PDF (e.g. extracted .txt) can't be reprocessed
        # by the Documents module.
        if item.kind == KIND_DOCUMENT and item.suffix != ".pdf":
            return []
        return _BRIDGES.get(item.kind, [])

    def _icon_action(icon: str, tooltip: str, handler) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            icon_size=18,
            tooltip=tooltip,
            on_click=handler,
            style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
        )

    def _build_actions(item: LibraryItem) -> list[ft.Control]:
        actions: list[ft.Control] = [
            _icon_action(
                ft.Icons.FOLDER_OPEN_OUTLINED,
                "Abrir pasta",
                lambda _e, _it=item: _open_folder(_it),
            )
        ]
        for module_id, tip, icon in _bridge_targets(item):
            actions.append(
                _icon_action(
                    icon,
                    tip,
                    lambda _e, _m=module_id, _p=str(item.path): (
                        nav[0](_m, {"file": _p}) if nav else None
                    ),
                )
            )
        return actions

    # ------------------------------------------------------------------
    # Apply (in-memory) + rescan (filesystem)
    # ------------------------------------------------------------------

    def _apply() -> None:
        """Filter/sort the cached scan and rebuild the visible page (no page.update)."""
        by = sort_dd.value or "modified"
        items = sort_items(
            filter_items(
                _all_items,
                kinds=_active_kinds(),
                categories=_active_categories(),
                query=_query[0] or None,
                since=_active_since(),
            ),
            by=by,
            desc=(by != "name"),
        )
        visible = items[: _shown[0]]
        count_label.value = (
            f"{len(items)} arquivo" if len(items) == 1 else f"{len(items)} arquivos"
        )
        remaining = len(items) - len(visible)
        load_more_btn.visible = remaining > 0
        load_more_btn.text = f"Carregar mais ({remaining})"
        empty_state.visible = not items

        if _view_mode[0] == "list":
            # Bump the thumbnail generation so any in-flight grid work is dropped
            # (list rows use plain type icons — no thumbnails to generate).
            _thumb_gen[0] += 1
            list_body.controls = [
                build_item_row(
                    it, page=page, on_open=_open_file, build_actions=_build_actions
                )
                for it in visible
            ]
            list_container.visible = bool(visible)
            grid.visible = False
            return

        cards = [
            build_item_card(
                it, page=page, on_open=_open_file, build_actions=_build_actions
            )
            for it in visible
        ]
        grid.controls = [c.control for c in cards]
        list_container.visible = False
        grid.visible = bool(visible)
        _spawn_thumbnail_thread(list(zip(visible, cards)))

    def _spawn_thumbnail_thread(pairs: list[tuple[LibraryItem, ItemCard]]) -> None:
        """Generate thumbnails in one daemon thread, updating each card in place.

        Single-threaded on purpose: pymupdf raster and ffmpeg frame grabs are
        CPU-bound and parallelizing them would only add GPU/CPU contention.
        """
        _thumb_gen[0] += 1
        gen = _thumb_gen[0]
        if not pairs:
            return

        def _worker() -> None:
            # Small head start so the freshly rebuilt grid is mounted before the
            # first scoped update (set_thumbnail also guards with try/except).
            time.sleep(0.05)
            for item, card in pairs:
                if gen != _thumb_gen[0]:
                    return  # superseded by a newer scan/apply
                key = (str(item.path), item.modified)
                data = _thumb_cache.get(key)
                if data is None:
                    data = thumbnail_for(item)
                    if data:
                        _thumb_cache[key] = data
                if data and gen == _thumb_gen[0]:
                    card.set_thumbnail(data)  # scoped update, never page.update

        threading.Thread(target=_worker, daemon=True).start()

    def _render_from_top() -> None:
        """Reset paging to the first page and rebuild (no page.update)."""
        _shown[0] = _PAGE_SIZE
        _apply()

    def _render_from_top_and_update() -> None:
        _render_from_top()
        try:
            page.update()
        except Exception:
            pass

    def _on_load_more(_e) -> None:
        _shown[0] += _PAGE_SIZE
        _apply()
        try:
            page.update()
        except Exception:
            pass

    load_more_btn.on_click = _on_load_more

    def _rescan() -> None:
        nonlocal _all_items
        _all_items = scan_library()
        _render_from_top()

    # ------------------------------------------------------------------
    # Kind filter (segmented selector)
    # ------------------------------------------------------------------

    def _on_filter_change(value: str) -> None:
        settings.set("last_library_filter", value)
        # segmented_selector flushes page.update() after this returns
        _render_from_top()

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
            _render_from_top_and_update()

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
        _render_from_top_and_update()

    # Flet 0.85 Dropdown uses on_select for selection changes (not on_change,
    # which the 0.85.2 constructor rejects — verified against the installed API).
    sort_dd = ft.Dropdown(
        label="Ordenar",
        value=cfg.get("last_library_sort", "modified"),
        options=[ft.dropdown.Option(k, lbl) for k, lbl in _SORT_OPTIONS],
        width=180,
        on_select=_on_sort_change,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    date_dd = ft.Dropdown(
        label="Período",
        value="all",
        options=[ft.dropdown.Option(k, lbl) for k, lbl in _DATE_OPTIONS],
        width=170,
        on_select=lambda _e: _render_from_top_and_update(),
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    def _on_category_change(e: ft.ControlEvent) -> None:
        settings.set("last_library_category", e.control.value)
        _render_from_top_and_update()

    cat_dd = ft.Dropdown(
        label="Categoria",
        value=cfg.get("last_library_category", "all"),
        options=[ft.dropdown.Option(k, lbl) for k, lbl in _CATEGORY_OPTIONS],
        width=160,
        on_select=_on_category_change,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )

    toolbar = ft.Row(
        controls=[search_field, cat_dd, sort_dd, date_dd],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ------------------------------------------------------------------
    # View-mode toggle (grid | list)
    # ------------------------------------------------------------------

    grid_btn = ft.IconButton(
        icon=ft.Icons.GRID_VIEW_OUTLINED,
        icon_size=18,
        tooltip="Grade",
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )
    list_btn = ft.IconButton(
        icon=ft.Icons.VIEW_LIST_OUTLINED,
        icon_size=18,
        tooltip="Lista",
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _sync_view_buttons() -> None:
        active = _view_mode[0]
        grid_btn.icon = (
            ft.Icons.GRID_VIEW if active == "grid" else ft.Icons.GRID_VIEW_OUTLINED
        )
        grid_btn.icon_color = (
            ft.Colors.PRIMARY if active == "grid" else ft.Colors.ON_SURFACE_VARIANT
        )
        list_btn.icon = (
            ft.Icons.VIEW_LIST if active == "list" else ft.Icons.VIEW_LIST_OUTLINED
        )
        list_btn.icon_color = (
            ft.Colors.PRIMARY if active == "list" else ft.Colors.ON_SURFACE_VARIANT
        )

    def _set_view(mode: str) -> None:
        if mode == _view_mode[0]:
            return
        _view_mode[0] = mode
        settings.set("last_library_view", mode)
        _sync_view_buttons()
        _render_from_top_and_update()

    grid_btn.on_click = lambda _e: _set_view("grid")
    list_btn.on_click = lambda _e: _set_view("list")
    _sync_view_buttons()

    view_toggle = ft.Row(controls=[grid_btn, list_btn], spacing=0)

    # ------------------------------------------------------------------
    # Header + layout
    # ------------------------------------------------------------------

    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED, color=ft.Colors.PRIMARY),
        ft.Text(
            "Biblioteca",
            size=Type.title.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("library", page)
    if _help is not None:
        header_controls.append(_help)
    header_controls.extend([ft.Container(expand=True), view_toggle, count_label])

    header = ft.Row(
        controls=header_controls,
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
            load_more_row,
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
    # Lifecycle + auto-refresh
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        # Re-scan every time the tab is opened so fresh outputs (and external
        # deletions) show up.
        _rescan()

    def _on_pipeline_event(event) -> None:
        # If a pipeline finishes while the Library is the visible module, refresh
        # live. (Navigation is blocked during a running pipeline, so this is a
        # safety net / future-proofing rather than a common path today.)
        if not isinstance(event, PipelineEvent):
            return
        if event.type == "task_done" and control.visible:
            _rescan()
            try:
                page.update()
            except Exception:
                pass

    page.pubsub.subscribe(_on_pipeline_event)

    return Module(
        id=_MODULE_ID,
        label="Biblioteca",
        icon=ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
        selected_icon=ft.Icons.COLLECTIONS_BOOKMARK,
        control=control,
        on_mount=_on_mount,
    )
