"""Read-only index status line for the AI hub.

Fase 0b (PLANO_NL2CLI_HUB_IA.md) moved the reindex pipeline itself to the
Observatório hub's Índice/RAG tab — the AI hub only shows whether the index/
embedder is available (it gates the Ask button on that) and points the user to
Observatório to (re)index.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.gui.theme.tokens import Type


@dataclass
class IndexControls:
    """Handles for the index status line."""

    status_text: ft.Text
    refresh_status: Callable[[], None]


def build_index_controls(
    page: ft.Page,
    *,
    embed_model: str,
    on_availability_change: Callable[[bool], None],
) -> IndexControls:
    """Build the read-only index status line and return its handles.

    ``on_availability_change`` gates the caller's own action (the Ask button)
    on embedder availability, since the Conversa flow needs the same Ollama
    dependency the index does.
    """

    status_text = ft.Text(
        "Carregando índice…",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        expand=True,
        no_wrap=False,
    )

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
                status_text.value = (
                    "Índice vazio — indexe no Observatório para começar."
                )

            on_availability_change(available)
            if not available:
                status_text.value = (
                    f"Ollama / {embed_model} indisponível — rode: {embedder.SETUP_HINT}"
                )
            try:
                status_text.update()
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    return IndexControls(status_text=status_text, refresh_status=refresh_status)
