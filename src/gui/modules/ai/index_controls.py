"""Index status + Reindexar controls for the AI hub.

Owns the index-stats status line, the Reindexar button and its click handler,
and the status refresh (index stats + embedder availability). Packaged as a
standalone unit on purpose: Fase 0b of PLANO_NL2CLI_HUB_IA.md moves the
worker-triggering logic here almost intact to the Observatório hub's Índice/RAG
tab, once the reindex pipeline moves ownership there.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.gui.modules.ai.worker import start_ai_index
from src.gui.theme.components import secondary_button
from src.gui.theme.tokens import Type

if TYPE_CHECKING:
    from src.gui.events import EventBus


@dataclass
class IndexControls:
    """Handles for the index status/Reindexar block."""

    status_text: ft.Text
    reindex_btn: ft.Control
    trigger_reindex: Callable[[], None]
    refresh_status: Callable[[], None]
    set_disabled: Callable[[bool], None]
    on_task_done: Callable[[], None]
    on_task_error: Callable[[], None]


def build_index_controls(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    *,
    embed_model: str,
    on_begin: Callable[[], None],
    on_availability_change: Callable[[bool], None],
) -> IndexControls:
    """Build the index status line + Reindexar button and return its handles.

    ``on_begin`` is the shared "starting a run" orchestration (owned by the
    caller — it flips ``pipeline_running``, disables the ask form, resets the
    progress chrome). ``on_availability_change`` gates the caller's own action
    (e.g. the Ask button) on embedder availability, since both flows share the
    same Ollama dependency.
    """

    status_text = ft.Text(
        "Carregando índice…",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        expand=True,
        no_wrap=False,
    )
    reindex_btn = secondary_button("Reindexar", icon=ft.Icons.REFRESH)

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    def refresh_status() -> None:
        def _worker() -> None:
            from src.core.rag import embedder
            from src.core.rag.indexer import index_dir
            from src.core.rag.stats import fmt_status_line, index_stats

            try:
                stats = index_stats(index_dir())
            except Exception as exc:  # pure read, but stay defensive
                logging.debug("[d] status read failed: %s", exc)
                stats = None

            available = embedder.is_available(embed_model)

            if stats and stats.n_chunks:
                status_text.value = fmt_status_line(stats)
            else:
                status_text.value = "Índice vazio — clique em Reindexar para começar."

            on_availability_change(available)
            if not available:
                status_text.value = (
                    f"Ollama / {embed_model} indisponível — rode: {embedder.SETUP_HINT}"
                )
            reindex_btn.disabled = (not available) or pipeline_running[0]
            _safe_update(status_text, reindex_btn)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_reindex(_e=None) -> None:
        if pipeline_running[0]:
            return
        on_begin()
        reindex_btn.disabled = True
        page.update()
        start_ai_index(bus, cancel_event, embed_model=embed_model)

    def set_disabled(disabled: bool) -> None:
        reindex_btn.disabled = disabled

    def on_task_done() -> None:
        reindex_btn.disabled = False
        refresh_status()

    def on_task_error() -> None:
        reindex_btn.disabled = False

    reindex_btn.on_click = _on_reindex

    return IndexControls(
        status_text=status_text,
        reindex_btn=reindex_btn,
        trigger_reindex=_on_reindex,
        refresh_status=refresh_status,
        set_disabled=set_disabled,
        on_task_done=on_task_done,
        on_task_error=on_task_error,
    )
