"""Observatório module — cross-module ML activity + status, read-only.

A hub (reached from the AppBar, not the rail), auto-contido like IA/Receitas.
No worker/pipeline — pure reads over ``core/observatory/`` on each mount, same
"read-only" spirit as the Library hub. Three manual tabs
(Atividade | Status | Tempo de resposta) — Flet 0.85 has no ``ft.Tabs``.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.modules.base import Module
from src.gui.modules.observatory.activity_tab import build_activity_tab
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
        nav: List holding [navigate_to] (signature symmetry).
    """
    activity_view, apply_activity = build_activity_tab(page)
    status_view, apply_status = build_status_tab(page)
    timing_view, apply_timing = build_timing_tab(page)
    status_view.visible = False
    timing_view.visible = False

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_activity = ft.TextButton(
        "Atividade", icon=ft.Icons.HISTORY_OUTLINED, style=_tab_style(True)
    )
    tab_status = ft.TextButton(
        "Status", icon=ft.Icons.MONITOR_HEART_OUTLINED, style=_tab_style(False)
    )
    tab_timing = ft.TextButton(
        "Tempo de resposta", icon=ft.Icons.SPEED_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str) -> None:
        activity_view.visible = name == "atividade"
        status_view.visible = name == "status"
        timing_view.visible = name == "timing"
        tab_activity.style = _tab_style(name == "atividade")
        tab_status.style = _tab_style(name == "status")
        tab_timing.style = _tab_style(name == "timing")
        settings.set("last_observatory_tab", name)
        if name == "atividade":
            apply_activity()
        elif name == "status":
            apply_status()
        else:
            apply_timing()
        page.update()

    tab_activity.on_click = lambda _e: _show_tab("atividade")
    tab_status.on_click = lambda _e: _show_tab("status")
    tab_timing.on_click = lambda _e: _show_tab("timing")

    body_stack = ft.Stack([activity_view, status_view, timing_view], expand=True)

    control = ft.Column(
        controls=[
            ft.Row([tab_activity, tab_status, tab_timing], spacing=Space.xs),
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
        saved = settings.load().get("last_observatory_tab", "atividade")
        _show_tab(saved)

    return Module(
        id=_MODULE_ID,
        label="Observatório",
        icon=ft.Icons.QUERY_STATS_OUTLINED,
        selected_icon=ft.Icons.QUERY_STATS,
        control=control,
        on_mount=_on_mount,
    )
