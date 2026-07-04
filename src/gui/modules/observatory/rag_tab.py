"""Observatório — aba Índice/RAG: 3 sub-abas (Índice · Painel · Uso de disco).

Nested manual tabs — Flet 0.85 has no ``ft.Tabs``, so "aba" here is just the
same ``Row(TextButton) + Stack(visible=)`` pattern used by the outer
Observatório tab bar, repeated one level deeper (there is no special nesting
support needed, or missing, in the framework for this).

Migrated from the AI hub (PR7.2/Plano 2): Índice and Painel used to live
beside Conversa there. Grouping them here keeps the AI hub to its one job
(chat) and puts RAG-index inspection beside the rest of the app's
ML-transparency surface. The "Reindexar" action inside Índice can't run a
pipeline itself — Observatório stays read-only, like the Library hub — so it
bridges to the AI hub's Conversa tab via ``nav`` and triggers the reindex
there.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import flet as ft

from src.gui import settings
from src.gui.modules.observatory.disk_usage_tab import build_disk_usage_tab
from src.gui.modules.observatory.index_tab import build_index_tab
from src.gui.modules.observatory.rag_analytics_tab import build_analytics_tab
from src.gui.theme.components import Cursor, hairline
from src.gui.theme.tokens import Space

_DEFAULT_SUBTAB = "indice"


def build_rag_tab(page: ft.Page, nav: list) -> tuple[ft.Control, Callable[[], None]]:
    """Build the nested Índice/RAG tab. ``nav`` bridges "Reindexar" to the AI hub."""

    def _on_reindex() -> None:
        nav[0]("ai", {"trigger_reindex": True})

    index_tab = build_index_tab(page, on_reindex=_on_reindex)
    index_view = index_tab.control

    analytics_tab = build_analytics_tab(page)
    analytics_view = analytics_tab.control
    analytics_view.visible = False

    disk_view, apply_disk = build_disk_usage_tab(page)
    disk_view.visible = False

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_indice = ft.TextButton(
        "Índice", icon=ft.Icons.INVENTORY_2_OUTLINED, style=_tab_style(True)
    )
    tab_painel = ft.TextButton(
        "Painel", icon=ft.Icons.INSIGHTS_OUTLINED, style=_tab_style(False)
    )
    tab_disco = ft.TextButton(
        "Uso de disco", icon=ft.Icons.STORAGE_OUTLINED, style=_tab_style(False)
    )

    def _show_subtab(name: str) -> None:
        index_view.visible = name == "indice"
        analytics_view.visible = name == "painel"
        disk_view.visible = name == "disco"
        tab_indice.style = _tab_style(name == "indice")
        tab_painel.style = _tab_style(name == "painel")
        tab_disco.style = _tab_style(name == "disco")
        settings.set("last_observatory_rag_subtab", name)
        if name == "disco":
            apply_disk()
        page.update()

    tab_indice.on_click = lambda _e: _show_subtab("indice")
    tab_painel.on_click = lambda _e: _show_subtab("painel")
    tab_disco.on_click = lambda _e: _show_subtab("disco")

    body_stack = ft.Stack([index_view, analytics_view, disk_view], expand=True)

    control = ft.Column(
        controls=[
            ft.Row([tab_indice, tab_painel, tab_disco], spacing=Space.xs),
            hairline(),
            ft.Container(content=body_stack, expand=True),
        ],
        expand=True,
        spacing=Space.sm,
    )

    def _refresh_rag_status() -> None:
        def _worker() -> None:
            from src.core.rag.indexer import index_dir
            from src.core.rag.stats import index_stats

            try:
                stats = index_stats(index_dir())
            except Exception as exc:  # pure read, but stay defensive
                logging.debug("[d] RAG index status read failed: %s", exc)
                return
            index_tab.apply(stats)
            analytics_tab.apply(stats)

        threading.Thread(target=_worker, daemon=True).start()

    def apply() -> None:
        """Refresh the sub-tabs — called by the outer Observatório view."""
        _refresh_rag_status()
        if disk_view.visible:
            apply_disk()

    # Restore the saved sub-tab's visibility directly (no page.update() — the
    # control isn't mounted yet at build time); the outer view's own apply()
    # call during on_mount is what actually refreshes the data.
    saved = settings.load().get("last_observatory_rag_subtab", _DEFAULT_SUBTAB)
    index_view.visible = saved == "indice"
    analytics_view.visible = saved == "painel"
    disk_view.visible = saved == "disco"
    tab_indice.style = _tab_style(saved == "indice")
    tab_painel.style = _tab_style(saved == "painel")
    tab_disco.style = _tab_style(saved == "disco")

    return control, apply
