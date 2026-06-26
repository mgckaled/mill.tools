"""Data module — query-first structured-data tool over DuckDB.

A NavigationRail tool (the 6th), but self-contained like the AI/Recipes hubs: it
subscribes to its own PipelineEvents (module_id="data") and updates the panel on
the UI thread. The right panel has three manual tabs (Flet 0.85 has no ft.Tabs),
mirroring the AI hub's Conversa|Índice toggle:

- **Consulta** (``tabs/query_tab.py``): review card, paginated result, save block.
- **Pré-visualização** (``tabs/preview_tab.py``): first rows + column types.
- **Análise com IA** (``tabs/analysis_tab.py``): a data-quality narrative.

This module is the thin shell: it builds the shared ``DataViewContext``, the
three tabs and the form, then subscribes once and routes each ``data_*`` event to
the owning tab. Shared state and pure logic live in ``_state.py``.

Privacy: the IA (NL→SQL and the assessment) only ever sees the column names +
statistics + a small sample — never the table rows.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.base import Module
from src.gui.modules.data._state import DataViewContext, is_data_source
from src.gui.modules.data.form_view import build_data_form
from src.gui.modules.data.tabs.analysis_tab import build_analysis_tab
from src.gui.modules.data.tabs.plot_tab import build_plot_tab
from src.gui.modules.data.tabs.preview_tab import build_preview_tab
from src.gui.modules.data.tabs.query_tab import build_query_tab
from src.gui.modules.data.worker import start_scan
from src.gui.theme.components import Cursor, hairline
from src.gui.theme.tokens import Space

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "data"


def build_data_module(
    page: ft.Page,
    bus: EventBus,
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Data module — query files, preview, assess, shape and save.

    Args:
        page: Flet page.
        bus: Shared application EventBus (worker → UI).
        cancel_event: threading.Event (kept for signature symmetry; queries are
            short and synchronous, so there is nothing to cancel mid-step).
        pipeline_running: Shared [bool] guard with app.py — blocks navigation
            while a query/save runs.
        nav: List holding [navigate_to] — used by the "Conversar sobre" bridge.
    """
    cfg = settings.load()
    embed_model = cfg.get("last_embed_model", "nomic-embed-custom")

    # ------------------------------------------------------------------
    # Form (left panel). Its preview/run buttons drive the Consulta tab; the
    # tab is built just below, so the callbacks defer to it via late binding.
    # ------------------------------------------------------------------

    def _on_pick(paths: list[Path]) -> None:
        start_scan(bus, paths)

    form = build_data_form(
        page,
        on_pick=_on_pick,
        on_preview=lambda: query.on_preview(),
        on_run=lambda: query.on_run(),
    )

    ctx = DataViewContext(
        page=page,
        bus=bus,
        nav=nav,
        embed_model=embed_model,
        pipeline_running=pipeline_running,
        form=form,
    )

    query = build_query_tab(ctx)
    preview = build_preview_tab(ctx)
    analysis = build_analysis_tab(ctx)
    plot = build_plot_tab(ctx)

    # ------------------------------------------------------------------
    # Event subscription (UI thread) — route each event to the owning tab.
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        match event.type:
            case "data_scanned":
                form.set_files(p.get("_files", []))
                preview.on_sources_changed()
                analysis.on_sources_changed()
            case "data_sql_ready":
                query.on_sql_ready(p)
            case "data_result":
                query.on_result(p)
                plot.on_result_changed()
            case "data_saved":
                query.on_saved(p)
            case "data_index_start":
                # Scoped update + early return: a full page.update() while the
                # spinner is animating would interrupt its on_animation_end chain.
                preview.on_index_start(p)
                return
            case "data_index_progress":
                preview.on_index_progress(p)
                return
            case "data_indexed":
                preview.on_indexed(p)
            case "data_assess_start":
                analysis.on_assess_start(p)
                return
            case "data_assessed":
                analysis.on_assessed(p)
            case "data_plot_start":
                # Scoped update + early return: a page.update() during the
                # spinner animation would break its on_animation_end chain.
                plot.on_plot_start(p)
                return
            case "data_plot_done":
                plot.on_plot_done(p)
            case "log":
                # Route the worker's log line to the active tab's status (scoped,
                # to keep the spinner animation alive during indexing).
                msg = p.get("message", "")
                if msg and ctx.action[0] == "index":
                    preview.on_log(msg)
                return
            case "task_error":
                if ctx.action[0] == "index":
                    preview.on_error(p)
                elif ctx.action[0] == "assess":
                    analysis.on_error(p)
                elif ctx.action[0] == "plot":
                    plot.on_error(p)
                else:
                    query.on_error(p)
            case "task_done":
                pass  # terminal bookkeeping handled by the specific events above
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Tab bar (Consulta | Pré-visualização | Análise com IA)
    # ------------------------------------------------------------------

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_consulta = ft.TextButton(
        "Consulta", icon=ft.Icons.QUERY_STATS_OUTLINED, style=_tab_style(True)
    )
    tab_preview = ft.TextButton(
        "Pré-visualização", icon=ft.Icons.TABLE_ROWS_OUTLINED, style=_tab_style(False)
    )
    tab_analysis = ft.TextButton(
        "Análise com IA", icon=ft.Icons.AUTO_AWESOME_OUTLINED, style=_tab_style(False)
    )
    tab_plot = ft.TextButton(
        "Gráfico", icon=ft.Icons.INSERT_CHART_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str) -> None:
        ctx.tab[0] = name
        query.view.visible = name == "consulta"
        preview.view.visible = name == "preview"
        analysis.view.visible = name == "analysis"
        plot.view.visible = name == "plot"
        tab_consulta.style = _tab_style(name == "consulta")
        tab_preview.style = _tab_style(name == "preview")
        tab_analysis.style = _tab_style(name == "analysis")
        tab_plot.style = _tab_style(name == "plot")
        settings.set("last_data_tab", name)
        if name == "consulta":
            query.on_show()
        elif name == "preview":
            preview.on_show()
        elif name == "analysis":
            analysis.on_show()
        elif name == "plot":
            plot.on_show()
        page.update()

    tab_consulta.on_click = lambda _e: _show_tab("consulta")
    tab_preview.on_click = lambda _e: _show_tab("preview")
    tab_analysis.on_click = lambda _e: _show_tab("analysis")
    tab_plot.on_click = lambda _e: _show_tab("plot")

    body_stack = ft.Stack(
        [query.view, preview.view, analysis.view, plot.view], expand=True
    )

    panel = ft.Column(
        controls=[
            ft.Row(
                [tab_consulta, tab_preview, tab_analysis, tab_plot], spacing=Space.xs
            ),
            hairline(),
            body_stack,
        ],
        expand=True,
        spacing=Space.sm,
    )

    control = ft.Row(
        controls=[
            ft.Container(content=form.control, width=380),
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=panel,
                expand=True,
                padding=ft.Padding(
                    left=Space.sm, right=Space.sm, top=Space.sm, bottom=Space.sm
                ),
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        # Bridge from the Library: a data file handed over becomes a source.
        file = payload.get("file") if payload else None
        if file:
            path = Path(file)
            if is_data_source(path):
                start_scan(bus, [path])
        _show_tab(settings.load().get("last_data_tab", "consulta"))

    return Module(
        id=_MODULE_ID,
        label="Dados",
        icon=ft.Icons.TABLE_CHART_OUTLINED,
        selected_icon=ft.Icons.TABLE_CHART,
        control=control,
        on_mount=_on_mount,
    )
