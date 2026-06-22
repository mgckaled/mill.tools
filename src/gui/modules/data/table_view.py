"""Reusable paginated table for the Data module.

Shared by the query-result panel and the source-preview modal, so both render
rows identically. Pure UI: callers push data with ``set_data`` (columns, rows and
an optional per-column type map for the header) and the component handles
in-memory pagination. Rows are expected to be pre-capped by the caller (the
engine's ``max_rows``/``limit``), so the table never holds an unbounded result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.gui.theme.components import Cursor
from src.gui.theme.tokens import Space, Type

_PAGE_SIZE = 50


@dataclass
class PaginatedTable:
    """Handles for a paginated table the caller drives via ``set_data``."""

    control: ft.Control
    set_data: Callable[[list[str], list[tuple], dict], None]


def _cell(value) -> str:
    return "" if value is None else str(value)


def build_paginated_table(
    page: ft.Page, *, page_size: int = _PAGE_SIZE
) -> PaginatedTable:
    """Build a paginated DataTable + pager. Returns handles to feed it."""
    state: dict = {"columns": [], "rows": [], "types": {}, "idx": 0}

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(""))], rows=[])
    table_scroll = ft.Column(
        controls=[ft.Row([table], scroll=ft.ScrollMode.AUTO)],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    page_label = ft.Text("—", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT)

    def _column_header(name: str) -> ft.Control:
        dtype = state["types"].get(name)
        if not dtype:
            return ft.Text(name)
        # Type under the name turns the header into a lightweight quality lens
        # (e.g. seeing `valor: VARCHAR` at a glance).
        return ft.Column(
            controls=[
                ft.Text(name, weight=ft.FontWeight.W_600),
                ft.Text(dtype, size=Type.tiny.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=0,
            tight=True,
        )

    def _render() -> None:
        cols = state["columns"]
        rows = state["rows"]
        total = len(rows)
        start = state["idx"] * page_size
        page_rows = rows[start : start + page_size]
        table.columns = [ft.DataColumn(_column_header(c)) for c in cols] or [
            ft.DataColumn(ft.Text(""))
        ]
        table.rows = [
            ft.DataRow(cells=[ft.DataCell(ft.Text(_cell(v))) for v in row])
            for row in page_rows
        ]
        last_page = max(0, (total - 1) // page_size)
        page_label.value = (
            f"{start + 1}–{min(start + page_size, total)} de {total}" if total else "—"
        )
        prev_btn.disabled = state["idx"] <= 0
        next_btn.disabled = state["idx"] >= last_page

    def _go_prev(_e=None) -> None:
        if state["idx"] > 0:
            state["idx"] -= 1
            _render()
            page.update()

    def _go_next(_e=None) -> None:
        if (state["idx"] + 1) * page_size < len(state["rows"]):
            state["idx"] += 1
            _render()
            page.update()

    prev_btn = ft.IconButton(
        icon=ft.Icons.CHEVRON_LEFT,
        tooltip="Página anterior",
        on_click=_go_prev,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )
    next_btn = ft.IconButton(
        icon=ft.Icons.CHEVRON_RIGHT,
        tooltip="Próxima página",
        on_click=_go_next,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )
    pager = ft.Row(
        [ft.Container(expand=True), prev_btn, page_label, next_btn],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def set_data(
        columns: list[str], rows: list[tuple], types: dict | None = None
    ) -> None:
        state["columns"] = list(columns)
        state["rows"] = list(rows)
        state["types"] = dict(types or {})
        state["idx"] = 0
        _render()

    control = ft.Column(
        controls=[table_scroll, pager],
        expand=True,
        spacing=Space.sm,
    )
    return PaginatedTable(control=control, set_data=set_data)
