"""Shared state + pure helpers for the Data module's tabbed view.

The view is split into one builder per tab (``tabs/query_tab.py`` etc.). Those
builders capture mutable state and a few cross-cutting helpers; bundling them in
a ``DataViewContext`` lets each tab live in its own file without losing the
shared references. The pure logic (pagination math, prompt assembly, stem
normalization) lives here as free functions so it is unit-testable without Flet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, NamedTuple

import flet as ft

from src.gui.theme.components import spinner
from src.gui.theme.tokens import IconSize, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus
    from src.gui.modules.data.form_view import DataForm

# Source extensions accepted by the Library → Data bridge (on_mount payload).
_DATA_SUFFIXES = {".csv", ".tsv", ".json", ".parquet", ".xlsx", ".pq"}


def is_data_source(path: Path) -> bool:
    """True if the path is a structured-data file the module can open."""
    return path.suffix.lower() in _DATA_SUFFIXES


def save_stem(raw: str | None) -> str:
    """Normalize the output file stem, defaulting to 'consulta' when blank."""
    return (raw or "").strip() or "consulta"


def file_by_name(files: list, name: str | None):
    """Find a DataFile by its file name, falling back to the first source.

    Shared by the Preview and Analysis tabs to resolve their file dropdowns.
    """
    for f in files:
        if f.path.name == name:
            return f
    return files[0] if files else None


def result_status(n_rows: int, elapsed: float, truncated: bool) -> str:
    """Status line for a finished query result."""
    stat = f"{n_rows} linha(s) · {elapsed:.3f}s"
    if truncated:
        stat += " · prévia limitada"
    return stat


def build_refine_prompt(question: str | None, failed_sql: str, error: str) -> str:
    """Augment the question with the failed SQL + DuckDB error for IA refinement."""
    base = (
        question or ""
    ).strip() or "Corrija a consulta SQL para responder à pergunta."
    return (
        f"{base}\n\n"
        "A consulta SQL gerada anteriormente falhou ao executar no DuckDB.\n"
        f"SQL com erro: {failed_sql or '(desconhecido)'}\n"
        f"Mensagem de erro: {error}\n"
        "Gere uma nova consulta SELECT que corrija esse erro, usando apenas "
        "colunas existentes no esquema."
    )


class PageWindow(NamedTuple):
    """A computed pagination window over an in-memory result set."""

    start: int  # 0-based index of the first row on the page
    end: int  # exclusive index of the last row on the page (clamped to total)
    label: str  # "1–50 de 200" (or "—" when empty)
    has_prev: bool
    has_next: bool


def page_window(total: int, page_idx: int, page_size: int) -> PageWindow:
    """Compute the slice bounds, label and nav-button state for a result page."""
    start = page_idx * page_size
    end = min(start + page_size, total)
    last_page = max(0, (total - 1) // page_size)
    label = f"{start + 1}–{end} de {total}" if total else "—"
    return PageWindow(
        start=start,
        end=end,
        label=label,
        has_prev=page_idx > 0,
        has_next=page_idx < last_page,
    )


@dataclass
class DataViewContext:
    """Cross-tab references shared by the Data module's tab builders.

    Holds the page/bus/form and the small bits of state that more than one tab
    (or the central event router) needs to read: the in-flight ``action`` (which
    worker flow is running, used to route log/error events), the active ``tab``,
    and the ``pipeline_running`` navigation guard shared with app.py.
    """

    page: ft.Page
    bus: EventBus
    nav: list
    embed_model: str
    pipeline_running: list[bool]
    form: DataForm
    action: list[str] = field(default_factory=lambda: ["query"])
    tab: list[str] = field(default_factory=lambda: ["consulta"])
    # Last executed query, shared with the Gráfico tab so it can re-run the SQL
    # over the full result (not the truncated preview) and pre-fill its controls.
    last_sql: list[str] = field(default_factory=lambda: [""])
    last_columns: list[str] = field(default_factory=list)
    last_rows: list[tuple] = field(default_factory=list)

    def toast(self, message: str, *, error: bool = True) -> None:
        """Show a SnackBar (error-colored by default)."""
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY,
        )
        self.page.snack_bar.open = True
        self.page.update()

    def scoped_update(self, *controls: ft.Control) -> None:
        """Repaint only these controls — never page.update() while a spinner runs.

        A full page.update() interrupts a spinner's in-flight rotation so its
        on_animation_end chain never re-fires and the mill stops turning.
        """
        for c in controls:
            try:
                c.update()
            except Exception:
                pass


def make_progress() -> SimpleNamespace:
    """A self-contained progress block (spinner + status + bar) for a tab.

    Mirrors the Consulta progress row so the Preview/Análise tabs show their
    log/progress at the top in the same shape. Returns a namespace with
    ``control``/``start``/``stop``/``status``/``pbar``.
    """
    img, start, stop = spinner()
    status = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.PRIMARY,
        weight=ft.FontWeight.W_500,
    )
    pbar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    control = ft.Column(
        controls=[
            ft.Row(
                [img, status],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            pbar,
        ],
        spacing=Space.xs,
        visible=False,
    )
    return SimpleNamespace(
        control=control, start=start, stop=stop, status=status, pbar=pbar
    )


def tab_empty_state(icon: str, title: str, body: str) -> ft.Container:
    """Build a centered empty-state placeholder for a tab with no data yet."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(icon, size=IconSize.hero, color=ft.Colors.OUTLINE_VARIANT),
                ft.Text(
                    title,
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    body,
                    size=Type.input.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                    text_align=ft.TextAlign.CENTER,
                    no_wrap=False,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=Space.sm,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )
