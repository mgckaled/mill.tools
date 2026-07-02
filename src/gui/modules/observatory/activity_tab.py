"""Observatório — aba Atividade: feed cronológico cross-módulo de eventos de ML.

Mirrors library/analytics_panel.py's shape: `build_activity_tab(page) ->
(control, apply)`. Reads core/observatory/activity.py's persisted log — never
writes to it (writing is the orchestration layer's job, at each operation's
own completion point).
"""

from __future__ import annotations

import time
from typing import Callable

import flet as ft

from src.core.observatory.activity import ActivityEntry, load_activity, recent
from src.gui.theme.tokens import Space, Type

_MODULE_LABELS = {
    "rag": "IA",
    "library": "Biblioteca",
    "transcription": "Transcrição",
    "data": "Dados",
    "recipes": "Receitas",
}

_FEED_LIMIT = 15


def _fmt_time(ts: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(ts))


def _entry_row(entry: ActivityEntry) -> ft.Row:
    module_label = _MODULE_LABELS.get(entry.module, entry.module)
    return ft.Row(
        controls=[
            ft.Text(
                _fmt_time(entry.timestamp),
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                width=90,
            ),
            ft.Text(
                module_label,
                size=Type.caption.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
                width=90,
            ),
            ft.Text(
                entry.detail,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE,
                expand=True,
                no_wrap=False,
            ),
        ],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def build_activity_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the activity feed control plus an ``apply()`` refresher."""
    feed_col = ft.Column(spacing=Space.sm)
    empty_state = ft.Text(
        "Nenhuma atividade de ML registrada ainda.",
        size=Type.body.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    control = ft.Column(
        controls=[feed_col, empty_state],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def apply() -> None:
        entries = recent(load_activity(), limit=_FEED_LIMIT)
        feed_col.controls = [_entry_row(e) for e in entries]
        empty_state.visible = not entries
        try:
            control.update()
        except Exception:
            pass

    return control, apply
