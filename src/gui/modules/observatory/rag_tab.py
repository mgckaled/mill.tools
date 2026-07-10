"""Observatório — aba Índice/RAG: 3 sub-abas (Índice · Painel · Uso de disco).

Nested manual tabs — Flet 0.85 has no ``ft.Tabs``, so "aba" here is just the
same ``Row(TextButton) + Stack(visible=)`` pattern used by the outer
Observatório tab bar, repeated one level deeper (there is no special nesting
support needed, or missing, in the framework for this).

Migrated from the AI hub (PR7.2/Plano 2): Índice and Painel used to live
beside Conversa there. Fase 0b (PLANO_NL2CLI_HUB_IA.md) finishes that
migration by moving the reindex pipeline itself here too — this tab now owns
the ``pipeline_running``/``cancel_event`` orchestration and the PipelineEvent
subscription for ``module_id="observatory"``, the same shape as a tool
module's worker/view pair, instead of bridging "Reindexar" back to the AI hub.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.observatory.disk_usage_tab import build_disk_usage_tab
from src.gui.modules.observatory.eval_tab import build_eval_tab
from src.gui.modules.observatory.eval_worker import start_eval_pipeline
from src.gui.modules.observatory.index_tab import build_index_tab
from src.gui.modules.observatory.index_worker import start_ai_index
from src.gui.modules.observatory.rag_analytics_tab import build_analytics_tab
from src.gui.theme.components import Cursor, hairline
from src.gui.theme.tokens import Space

if TYPE_CHECKING:
    from src.gui.events import EventBus

_DEFAULT_SUBTAB = "indice"
_DEFAULT_EMBED_MODEL = "nomic-embed-custom"
_MODULE_ID = "observatory"


def build_rag_tab(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> tuple[ft.Control, Callable[[], None]]:
    """Build the nested Índice/RAG tab, including the real reindex pipeline."""
    embed_model = settings.load().get("last_embed_model", _DEFAULT_EMBED_MODEL)

    # Which pipeline owns the shared events (task_done/task_error/log): the
    # reindex and the eval both emit under module_id="observatory", and only one
    # runs at a time (pipeline_running blocks the other), so a single marker set
    # at begin routes the generic events to the right tab. Their per-item events
    # are already distinct (progress_update vs. eval_progress).
    _active: list[str] = [""]

    def _begin_index() -> None:
        if pipeline_running[0]:
            return
        _active[0] = "index"
        pipeline_running[0] = True
        cancel_event.clear()
        index_tab.set_running(True)
        page.update()
        start_ai_index(bus, cancel_event, embed_model=embed_model)

    def _cancel_index() -> None:
        cancel_event.set()

    def _begin_eval() -> None:
        if pipeline_running[0]:
            return
        _active[0] = "eval"
        pipeline_running[0] = True
        cancel_event.clear()
        eval_tab.set_running(True)
        page.update()
        start_eval_pipeline(bus, cancel_event, embed_model=embed_model)

    def _cancel_eval() -> None:
        cancel_event.set()

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        active = _active[0]
        match event.type:
            case "progress_update":  # reindex, per item
                index_tab.set_progress(p.get("current"), p.get("total"))
            case "eval_progress":  # eval, per question
                eval_tab.set_progress(p.get("current"), p.get("total"))
            case "log":
                msg = p.get("message", "")
                if msg:
                    (eval_tab if active == "eval" else index_tab).set_detail(msg)
            case "task_done":
                pipeline_running[0] = False
                if active == "eval":
                    eval_tab.set_running(False)
                    _refresh_eval_status()
                else:
                    index_tab.set_running(False)
                    _refresh_rag_status()
            case "task_error":
                pipeline_running[0] = False
                tab = eval_tab if active == "eval" else index_tab
                tab.set_running(False)
                tab.set_detail(f"[!] {p.get('message', 'Erro.')}")
        page.update()

    page.pubsub.subscribe(_on_event)

    index_tab = build_index_tab(page, on_reindex=_begin_index, on_cancel=_cancel_index)
    index_view = index_tab.control

    eval_tab = build_eval_tab(page, on_run=_begin_eval, on_cancel=_cancel_eval)
    eval_view = eval_tab.control
    eval_view.visible = False

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
    tab_aval = ft.TextButton(
        "Avaliação", icon=ft.Icons.FACT_CHECK_OUTLINED, style=_tab_style(False)
    )
    tab_painel = ft.TextButton(
        "Painel", icon=ft.Icons.INSIGHTS_OUTLINED, style=_tab_style(False)
    )
    tab_disco = ft.TextButton(
        "Uso de disco", icon=ft.Icons.STORAGE_OUTLINED, style=_tab_style(False)
    )

    def _show_subtab(name: str) -> None:
        index_view.visible = name == "indice"
        eval_view.visible = name == "avaliacao"
        analytics_view.visible = name == "painel"
        disk_view.visible = name == "disco"
        tab_indice.style = _tab_style(name == "indice")
        tab_aval.style = _tab_style(name == "avaliacao")
        tab_painel.style = _tab_style(name == "painel")
        tab_disco.style = _tab_style(name == "disco")
        settings.set("last_observatory_rag_subtab", name)
        if name == "avaliacao":
            _refresh_eval_status()
        elif name == "disco":
            apply_disk()
        page.update()

    tab_indice.on_click = lambda _e: _show_subtab("indice")
    tab_aval.on_click = lambda _e: _show_subtab("avaliacao")
    tab_painel.on_click = lambda _e: _show_subtab("painel")
    tab_disco.on_click = lambda _e: _show_subtab("disco")

    body_stack = ft.Stack(
        [index_view, eval_view, analytics_view, disk_view], expand=True
    )

    control = ft.Column(
        controls=[
            ft.Row([tab_indice, tab_aval, tab_painel, tab_disco], spacing=Space.xs),
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

    def _refresh_eval_status() -> None:
        def _worker() -> None:
            from src.core.rag.eval import load_eval_data

            try:
                data = load_eval_data()
            except Exception as exc:  # pure read, but stay defensive
                logging.debug("[d] RAG eval status read failed: %s", exc)
                return
            eval_tab.apply(data)

        threading.Thread(target=_worker, daemon=True).start()

    def apply(force_indice: bool = False) -> None:
        """Refresh the sub-tabs — called by the outer Observatório view.

        ``force_indice=True`` also switches to the Índice sub-tab — used by
        the "Indexar no Observatório" bridge from the AI hub, which wants to
        land the user on the reindex button regardless of the last-visited
        sub-tab.
        """
        if force_indice and not index_view.visible:
            _show_subtab("indice")
        _refresh_rag_status()
        if eval_view.visible:
            _refresh_eval_status()
        if disk_view.visible:
            apply_disk()

    # Restore the saved sub-tab's visibility directly (no page.update() — the
    # control isn't mounted yet at build time); the outer view's own apply()
    # call during on_mount is what actually refreshes the data.
    saved = settings.load().get("last_observatory_rag_subtab", _DEFAULT_SUBTAB)
    index_view.visible = saved == "indice"
    eval_view.visible = saved == "avaliacao"
    analytics_view.visible = saved == "painel"
    disk_view.visible = saved == "disco"
    tab_indice.style = _tab_style(saved == "indice")
    tab_aval.style = _tab_style(saved == "avaliacao")
    tab_painel.style = _tab_style(saved == "painel")
    tab_disco.style = _tab_style(saved == "disco")

    return control, apply
