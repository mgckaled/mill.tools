"""Observatório — aba Logs: falhas (task_error) cross-módulo, não só sucessos.

Mirrors activity_tab.py's shape: `build_logs_tab(page) -> (control, apply)`.
Reads core/observatory/logs.py's persisted log — never writes to it (writing
happens once, at the EventBus broadcast point in gui/events.py).
"""

from __future__ import annotations

import time
from typing import Callable

import flet as ft

from src.core.observatory.logs import LogEntry, load_logs, recent
from src.gui.theme.tokens import Space, Type

_MODULE_LABELS = {
    "transcription": "Transcrição",
    "audio": "Áudio",
    "video": "Vídeo",
    "image": "Imagens",
    "document": "Documentos",
    "data": "Dados",
    "ai": "IA",
    "recipes": "Receitas",
}

_FEED_LIMIT = 50


def _fmt_time(ts: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(ts))


def _entry_row(entry: LogEntry) -> ft.Row:
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
                color=ft.Colors.ERROR,
                width=90,
            ),
            ft.Text(
                entry.stage,
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                width=100,
                italic=True,
            ),
            ft.Text(
                entry.message,
                size=Type.body.size,
                color=ft.Colors.ON_SURFACE,
                expand=True,
                no_wrap=False,
            ),
        ],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def build_logs_tab(page: ft.Page) -> tuple[ft.Control, Callable[[], None]]:
    """Build the failure-log feed control plus an ``apply()`` refresher."""
    feed_col = ft.Column(spacing=Space.sm)
    empty_state = ft.Text(
        "Nenhuma falha registrada.",
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
        entries = recent(load_logs(), limit=_FEED_LIMIT)
        feed_col.controls = [_entry_row(e) for e in entries]
        empty_state.visible = not entries
        try:
            control.update()
        except Exception:
            pass

    return control, apply
