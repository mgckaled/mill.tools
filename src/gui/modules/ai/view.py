"""AI / Content module — local RAG chat over the Library corpus.

A hub module (reached from the AppBar, not the rail): split form | panel. The
form collects scope/model/question; the panel shows the index status with a
Reindex action, a progress line, and a scrollable session of cited answers.

Self-contained like the Library module: it subscribes to its own PipelineEvents
(module_id="ai") and updates the panel on the UI thread, instead of reusing the
generic ProgressPanel (whose log-line shape does not fit a Markdown answer +
clickable source cards). The two "worlds" that used to coexist here — indexing
and conversing — now live in ``index_controls.py`` and ``answer_view.py``; this
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
from src.gui.theme.components import hairline, spinner
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
        cancel_event: threading.Event set to cancel a running index.
        pipeline_running: Shared [bool] guard with app.py — blocks navigation
            while indexing/answering.
        nav: List holding [navigate_to] (signature symmetry with other hubs).
    """
    cfg = settings.load()
    embed_model = cfg.get("last_embed_model", _DEFAULT_EMBED_MODEL)

    def _toast(message: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.ERROR)
        page.snack_bar.open = True
        page.update()

    # ------------------------------------------------------------------
    # Shared "starting a run" orchestration — both indexing and answering
    # flip pipeline_running, disable each other's action, reset the shared
    # progress chrome. Each flow adds its own bits after calling this.
    # ------------------------------------------------------------------

    def _begin_run() -> None:
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        index_ctrl.set_disabled(True)
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
    # Event subscription (UI thread)
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        label = resolve_status(event)
        if label:
            stage_label.value = label

        match event.type:
            case "progress_update":
                cur, tot = p.get("current"), p.get("total")
                progress_bar.value = (cur / tot) if tot else None
                status_detail.value = (
                    f"Indexando {cur}/{tot}…" if tot else status_detail.value
                )
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
                index_ctrl.on_task_done()
            case "task_error":
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                index_ctrl.on_task_error()
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
        bus,
        cancel_event,
        pipeline_running,
        embed_model=embed_model,
        on_begin=_begin_run,
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

    status_row = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.STORAGE_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
            ),
            index_ctrl.status_text,
            answer.clear_btn,
            index_ctrl.reindex_btn,
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
    # Panel: just the chat now — the RAG index inspector and analytics panel
    # (formerly "Índice"/"Painel" tabs beside this one) moved to the
    # Observatório hub's nested Índice/RAG tab.
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
        # Bridge from the Observatório hub's Índice/RAG tab: its own
        # "Reindexar" can't run a pipeline there (that hub stays read-only),
        # so it navigates here and asks us to kick off the reindex.
        if payload and payload.get("trigger_reindex"):
            index_ctrl.trigger_reindex()

    return Module(
        id=_MODULE_ID,
        label="IA",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        selected_icon=ft.Icons.AUTO_AWESOME,
        control=control,
        on_mount=_on_mount,
    )
