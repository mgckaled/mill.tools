"""Shared "Indexar no RAG" button for producer modules (PR7.2.4).

Dropped into a result panel (Transcrição, Documentos→Analisar, Receitas), it
lets the user fold a freshly produced text output into the RAG index *by
choice* — never automatically. It runs the existing ``run_ai_index`` worker
(incremental: unchanged files are skipped) in a daemon thread with a private
capture bus, so it does not interfere with the producing module's own pubsub
events. Disabled with a setup hint when the embedder is unavailable.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import flet as ft

from src.gui import settings
from src.gui.theme.components import secondary_button

_DEFAULT_EMBED_MODEL = "nomic-embed-custom"
_LABEL_IDLE = "Indexar no RAG"
_LABEL_RUNNING = "Indexando…"
_LABEL_DONE = "Indexado ✓"


class _Capture:
    """Minimal bus that captures the index outcome instead of using pubsub.

    Matches ``EventBus.emit`` so ``run_ai_index`` can drive it directly; the
    button reads ``added``/``error`` once the worker returns.
    """

    def __init__(self) -> None:
        self.added: int | None = None
        self.error: str | None = None

    def emit(self, type: str, stage: str, payload=None, module_id: str = "") -> None:
        p = payload or {}
        if type == "index_done":
            self.added = p.get("added")
        elif type == "task_error":
            self.error = p.get("message")


def rag_index_button(
    page: ft.Page,
    *,
    embed_model: str | None = None,
    on_started: Callable[[], None] | None = None,
    on_finished: Callable[[bool], None] | None = None,
) -> ft.Control:
    """Build the "Indexar no RAG" button (incremental index, inline feedback)."""
    model = embed_model or settings.load().get("last_embed_model", _DEFAULT_EMBED_MODEL)
    btn = secondary_button(_LABEL_IDLE, icon=ft.Icons.STORAGE_OUTLINED)
    state = {"running": False}

    def _safe_update(*controls: ft.Control) -> None:
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    def _toast(message: str) -> None:
        try:
            page.show_dialog(ft.SnackBar(content=ft.Text(message), duration=3000))
        except Exception as exc:
            logging.debug("[d] snackbar failed: %s", exc)

    def _set_btn(text: str, *, disabled: bool) -> None:
        btn.content = text  # OutlinedButton label lives in .content (Flet 0.85)
        btn.disabled = disabled
        _safe_update(btn)

    def _run() -> None:
        from src.gui.modules.observatory.index_worker import run_ai_index

        cap = _Capture()
        cancel = threading.Event()
        ok = run_ai_index(cap, cancel, embed_model=model, install_log_handler=False)
        state["running"] = False
        if ok:
            added = cap.added or 0
            _toast(
                f"Índice atualizado: +{added} chunk(s)."
                if added
                else "Índice já estava atualizado."
            )
            _set_btn(_LABEL_DONE, disabled=False)
        else:
            _toast(cap.error or "Falha ao indexar.")
            _set_btn(_LABEL_IDLE, disabled=False)
        if on_finished is not None:
            on_finished(ok)

    def _on_click(_e=None) -> None:
        if state["running"]:
            return
        state["running"] = True
        _set_btn(_LABEL_RUNNING, disabled=True)
        if on_started is not None:
            on_started()
        threading.Thread(target=_run, daemon=True).start()

    btn.on_click = _on_click

    # Availability gate, off the UI thread (is_available pings Ollama).
    def _gate() -> None:
        from src.core.rag import embedder

        if not embedder.is_available(model):
            btn.disabled = True
            btn.tooltip = f"Embedder indisponível. Rode: {embedder.SETUP_HINT}"
            _safe_update(btn)

    threading.Thread(target=_gate, daemon=True).start()

    return btn
