"""AI / Content module — local RAG chat over the Library corpus.

A hub module (reached from the AppBar, not the rail): split form | panel. The
form collects scope/model/question; the panel shows the index status (read-
only — reindexing lives in the Observatório hub) and a scrollable session of
cited answers.

Self-contained like the Library module: it subscribes to its own PipelineEvents
(module_id="ai") and updates the panel on the UI thread, instead of reusing the
generic ProgressPanel (whose log-line shape does not fit a Markdown answer +
clickable source cards). The Conversa flow lives in ``answer_view.py``; this
file is the thin orchestrator: shared progress chrome, the PipelineEvent
dispatcher, lifecycle and layout assembly.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai.answer_view import build_answer_view
from src.gui.modules.ai.form_view import build_ai_form
from src.gui.modules.ai.index_controls import build_index_controls
from src.gui.modules.ai.pipeline_log import resolve_status
from src.gui.modules.base import Module
from src.gui.theme.components import action_button, hairline, spinner
from src.gui.theme.tokens import IconSize, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "ai"
_DEFAULT_EMBED_MODEL = "nomic-embed-custom"


def build_ai_module(
    page: ft.Page,
    bus: EventBus,
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the AI module — RAG chat over the Library corpus.

    Args:
        page: Flet page.
        bus: Shared application EventBus (worker → UI).
        cancel_event: threading.Event (signature symmetry; the Conversa flow
            has nothing to cancel — a single blocking LLM invoke()).
        pipeline_running: Shared [bool] guard with app.py — blocks navigation
            while answering.
        nav: List holding [navigate_to] — bridges "Indexar no Observatório" to
            the Observatório hub's Índice/RAG tab (reindexing moved there).
    """
    cfg = settings.load()
    embed_model = cfg.get("last_embed_model", _DEFAULT_EMBED_MODEL)

    def _toast(message: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.ERROR)
        page.snack_bar.open = True
        page.update()

    def _begin_run() -> None:
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        status_detail.value = ""
        _set_progress(True)

    def _set_progress(active: bool) -> None:
        progress_row.visible = active
        if active:
            progress_bar.value = None  # indeterminate until first update
            spinner_start()
        else:
            spinner_stop()
            answer.stop_ticker()

    # ------------------------------------------------------------------
    # Event subscription (UI thread) — only the Conversa flow emits under
    # module_id="ai" now; indexing moved to the Observatório hub.
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        label = resolve_status(event)
        if label:
            stage_label.value = label

        match event.type:
            case "log":
                msg = p.get("message", "")
                if msg:
                    status_detail.value = msg
            case "answer_done":
                answer.handle_answer_done(p)
            case "task_done":
                progress_bar.value = 1.0
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                index_ctrl.refresh_status()
            case "task_error":
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                message = p.get("message", "Erro.")
                status_detail.value = f"[!] {message}"
                _toast(message)
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    form = build_ai_form(page, on_ask=lambda: answer.ask())

    index_ctrl = build_index_controls(
        page,
        embed_model=embed_model,
        on_availability_change=form.set_available,
    )

    answer = build_answer_view(
        page,
        bus,
        cancel_event,
        pipeline_running,
        embed_model=embed_model,
        get_query=form.get_query,
        get_scope=form.get_scope,
        get_model=form.get_model,
        on_begin=_begin_run,
        on_empty_query=lambda: _toast("Digite uma pergunta."),
        toast=_toast,
    )

    goto_observatory_btn = action_button(
        "Indexar no Observatório",
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=lambda _e: nav[0]("observatory", {"tab": "index"}),
    )

    status_row = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.STORAGE_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
            ),
            index_ctrl.status_text,
            answer.clear_btn,
            goto_observatory_btn,
        ],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    spinner_img, spinner_start, spinner_stop = spinner()
    stage_label = ft.Text(
        "",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        weight=ft.FontWeight.W_500,
    )
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    progress_row = ft.Column(
        controls=[
            ft.Row(
                controls=[spinner_img, stage_label],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
            answer.gen_status,
        ],
        spacing=Space.xs,
        visible=False,
    )

    status_detail = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
        no_wrap=False,
    )

    # ------------------------------------------------------------------
    # Panel: just the chat now — the RAG index inspector, analytics panel and
    # reindex pipeline all live in the Observatório hub's nested Índice/RAG tab.
    # ------------------------------------------------------------------

    conversa_view = ft.Column(
        controls=[
            status_row,
            hairline(),
            progress_row,
            status_detail,
            answer.session_area,
        ],
        expand=True,
        spacing=Space.sm,
    )

    # ------------------------------------------------------------------
    # Split layout form | panel
    # ------------------------------------------------------------------

    control = ft.Row(
        controls=[
            ft.Container(content=form.control, width=380),
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=conversa_view,
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
        # Bridge from the Library: "Conversar sobre" binds a single document and
        # pre-selects the "this document" scope.
        file = payload.get("file") if payload else None
        form.bind_document(str(file) if file else None)
        index_ctrl.refresh_status()  # computes stats once, updating the status line

    return Module(
        id=_MODULE_ID,
        label="IA",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        selected_icon=ft.Icons.AUTO_AWESOME,
        control=control,
        on_mount=_on_mount,
    )
