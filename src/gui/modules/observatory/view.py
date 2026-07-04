"""Observatório module — cross-module ML activity + status, read-only.

A hub (reached from the AppBar, not the rail), auto-contido like IA/Receitas.
No worker/pipeline — pure reads over ``core/observatory/`` on each mount, same
"read-only" spirit as the Library hub. Five manual tabs
(Índice/RAG | Status | Atividade | Logs | Tempo de resposta) — Flet 0.85 has
no ``ft.Tabs``. Índice/RAG is first/default: it groups the RAG-index
inspector + analytics + disk usage (migrated from the AI hub, which now only
shows Conversa) — the leftmost tab is the hub's landing tab, same convention
as when Status held that spot before this tab existed.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.modules.base import Module
from src.gui.modules.observatory.activity_tab import build_activity_tab
from src.gui.modules.observatory.logs_tab import build_logs_tab
from src.gui.modules.observatory.rag_tab import build_rag_tab
from src.gui.modules.observatory.status_tab import build_status_tab
from src.gui.modules.observatory.timing_tab import build_timing_tab
from src.gui.theme.components import Cursor, hairline
from src.gui.theme.tokens import Space

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "observatory"


def build_observatory_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Observatório module — read-only cross-module ML visibility.

    Args:
        page: Flet page.
        bus: Shared application EventBus (kept for signature symmetry with the
            other hubs; this module has no pipeline of its own).
        cancel_event: threading.Event (signature symmetry; unused).
        pipeline_running: Shared [bool] with app.py (signature symmetry).
        nav: List holding [navigate_to] — used by the Índice/RAG tab to bridge
            "Reindexar" over to the AI hub (this hub stays read-only).
    """
    rag_view, apply_rag = build_rag_tab(page, nav)
    status_view, apply_status = build_status_tab(page)
    activity_view, apply_activity = build_activity_tab(page)
    logs_view, apply_logs = build_logs_tab(page)
    timing_view, apply_timing = build_timing_tab(page)
    status_view.visible = False
    activity_view.visible = False
    logs_view.visible = False
    timing_view.visible = False

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_rag = ft.TextButton(
        "Índice/RAG", icon=ft.Icons.INVENTORY_2_OUTLINED, style=_tab_style(True)
    )
    tab_status = ft.TextButton(
        "Status", icon=ft.Icons.MONITOR_HEART_OUTLINED, style=_tab_style(False)
    )
    tab_activity = ft.TextButton(
        "Atividade", icon=ft.Icons.HISTORY_OUTLINED, style=_tab_style(False)
    )
    tab_logs = ft.TextButton(
        "Logs", icon=ft.Icons.ERROR_OUTLINE, style=_tab_style(False)
    )
    tab_timing = ft.TextButton(
        "Tempo de resposta", icon=ft.Icons.SPEED_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str) -> None:
        rag_view.visible = name == "rag"
        status_view.visible = name == "status"
        activity_view.visible = name == "atividade"
        logs_view.visible = name == "logs"
        timing_view.visible = name == "timing"
        tab_rag.style = _tab_style(name == "rag")
        tab_status.style = _tab_style(name == "status")
        tab_activity.style = _tab_style(name == "atividade")
        tab_logs.style = _tab_style(name == "logs")
        tab_timing.style = _tab_style(name == "timing")
        settings.set("last_observatory_tab", name)
        if name == "rag":
            apply_rag()
        elif name == "status":
            apply_status()
        elif name == "atividade":
            apply_activity()
        elif name == "logs":
            apply_logs()
        else:
            apply_timing()
        page.update()

    tab_rag.on_click = lambda _e: _show_tab("rag")
    tab_status.on_click = lambda _e: _show_tab("status")
    tab_activity.on_click = lambda _e: _show_tab("atividade")
    tab_logs.on_click = lambda _e: _show_tab("logs")
    tab_timing.on_click = lambda _e: _show_tab("timing")

    body_stack = ft.Stack(
        [rag_view, status_view, activity_view, logs_view, timing_view], expand=True
    )

    control = ft.Column(
        controls=[
            ft.Row(
                [tab_rag, tab_status, tab_activity, tab_logs, tab_timing],
                spacing=Space.xs,
            ),
            hairline(),
            ft.Container(content=body_stack, expand=True, padding=Space.md),
        ],
        expand=True,
        spacing=Space.sm,
    )

    def _on_mount(_payload: dict) -> None:
        # Mark every current entry as "seen" (the AppBar badge is cleared by
        # navigate_to right after this runs) and re-scan the saved tab.
        from src.core.observatory.activity import load_activity

        entries = load_activity()
        if entries:
            settings.set("last_ml_activity_seen", entries[-1].timestamp)
        saved = settings.load().get("last_observatory_tab", "rag")
        _show_tab(saved)

    return Module(
        id=_MODULE_ID,
        label="Observatório",
        icon=ft.Icons.QUERY_STATS_OUTLINED,
        selected_icon=ft.Icons.QUERY_STATS,
        control=control,
        on_mount=_on_mount,
    )
