"""AI / Content module — local RAG chat + NL→CLI over the Library corpus.

A hub module (reached from the AppBar, not the rail): split form | panel. The
form's "Corpus | Comandos CLI" toggle (Fase 3, PLANO_NL2CLI_HUB_IA.md) picks
between two mutually exclusive flows sharing one Ask button and one progress
chrome: Conversa (RAG chat, ``answer_view.py``) and Comandos CLI (NL→CLI
generation, ``command_view.py``). The panel shows the index status (read-
only — reindexing lives in the Observatório hub) and a scrollable session for
whichever mode is active.

Self-contained like the Library module: it subscribes to its own PipelineEvents
(module_id="ai") and updates the panel on the UI thread, instead of reusing the
generic ProgressPanel (whose log-line shape does not fit a Markdown answer +
clickable source cards, nor a command card). This file is the thin
orchestrator: shared progress chrome, the PipelineEvent dispatcher, mode
switching, lifecycle and layout assembly.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai.answer_view import build_answer_view
from src.gui.modules.ai.command_view import build_command_view
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
    """Build the AI module — RAG chat + NL→CLI over the Library corpus.

    Args:
        page: Flet page.
        bus: Shared application EventBus (worker → UI).
        cancel_event: threading.Event (signature symmetry; neither flow here
            has anything mid-run to cancel — each is a single blocking LLM
            invoke()).
        pipeline_running: Shared [bool] guard with app.py — blocks navigation
            while answering/generating.
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
    # Mode switch (Corpus | Comandos CLI) — toggles which session area is
    # visible; the CLI mode's gate (Ollama chat, not the embedder) is
    # (re)checked every time it becomes active.
    # ------------------------------------------------------------------

    def _refresh_cli_availability() -> None:
        def _worker() -> None:
            from src.core.observatory.status import ollama_inventory
            from src.llm_factory import is_cloud_model

            available = is_cloud_model(form.get_model()) or ollama_inventory().reachable
            form.set_cli_available(available)

        threading.Thread(target=_worker, daemon=True).start()

    def _set_mode(mode: str) -> None:
        is_cli = mode == "cli"
        corpus_header.visible = not is_cli
        cli_header.visible = is_cli
        answer.session_area.visible = not is_cli
        command_view.session_area.visible = is_cli
        if is_cli:
            _refresh_cli_availability()
        page.update()

    def _ask_dispatch() -> None:
        if form.get_mode() == "cli":
            command_view.ask()
        else:
            answer.ask()

    # ------------------------------------------------------------------
    # Event subscription (UI thread) — only Conversa/Comandos CLI emit under
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
            case "command_done":
                command_view.handle_command_done(p)
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

    form = build_ai_form(page, on_ask=_ask_dispatch, on_mode_change=_set_mode)

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
        get_k=form.get_k,
        on_begin=_begin_run,
        on_empty_query=lambda: _toast("Digite uma pergunta."),
        toast=_toast,
    )

    command_view = build_command_view(
        page,
        bus,
        cancel_event,
        pipeline_running,
        get_query=form.get_query,
        get_model=form.get_model,
        on_begin=_begin_run,
        on_empty_query=lambda: _toast("Descreva o que você quer fazer."),
        start_ticker=answer.start_ticker,
    )

    goto_observatory_btn = action_button(
        "Indexar no Observatório",
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=lambda _e: nav[0]("observatory", {"tab": "index"}),
    )

    corpus_header = ft.Row(
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
    cli_header = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.TERMINAL_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
            ),
            ft.Text(
                "Comandos CLI — revise e copie, nada roda sozinho.",
                size=Type.input.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                expand=True,
                no_wrap=False,
            ),
            command_view.clear_btn,
        ],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        visible=False,
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
    # Panel: header + progress chrome are shared; the session area below
    # swaps between Conversa and Comandos CLI depending on the form's mode.
    # ------------------------------------------------------------------

    session_stack = ft.Stack(
        [answer.session_area, command_view.session_area], expand=True
    )
    command_view.session_area.visible = False

    panel_view = ft.Column(
        controls=[
            corpus_header,
            cli_header,
            hairline(),
            progress_row,
            status_detail,
            session_stack,
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
                content=panel_view,
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
        # Sync both the form's mode-dependent widgets and this panel's header/
        # session visibility to the persisted mode — the toggle's on_change
        # only fires on a user click, not for the initial/restored value.
        form.sync_mode_ui()
        _set_mode(form.get_mode())

    return Module(
        id=_MODULE_ID,
        label="IA",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        selected_icon=ft.Icons.AUTO_AWESOME,
        control=control,
        on_mount=_on_mount,
    )
