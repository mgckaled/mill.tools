"""AI / Content module — local RAG chat over the Library corpus.

A hub module (reached from the AppBar, not the rail): split form | panel. The
form collects scope/model/question; the panel shows the index status with a
Reindex action, a progress line, and a scrollable session of cited answers.

Self-contained like the Library module: it subscribes to its own PipelineEvents
(module_id="ai") and updates the panel on the UI thread, instead of reusing the
generic ProgressPanel (whose log-line shape does not fit a Markdown answer +
clickable source cards).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai.form_view import build_ai_form
from src.gui.modules.ai.pipeline_log import resolve_status
from src.gui.modules.ai.worker import start_ai_answer, start_ai_index
from src.gui.modules.base import Module
from src.gui.theme.components import (
    action_button,
    hairline,
    output_card,
    secondary_button,
    spinner,
)
from src.gui.theme.tokens import Color, Radius, Space, Type
from src.gui.views.file_viewer import is_viewable, open_file_viewer

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "ai"
_DEFAULT_EMBED_MODEL = "nomic-embed-text"
_TEXT_EXTS = {".txt", ".md"}

# Readable blockquote styling on the dark theme (mirrors the in-app file viewer).
_MD_STYLE = ft.MarkdownStyleSheet(
    blockquote_text_style=ft.TextStyle(color=ft.Colors.ON_SURFACE),
    blockquote_padding=ft.Padding(
        left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
    ),
    blockquote_decoration=ft.BoxDecoration(
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        border_radius=Radius.sm,
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.with_opacity(0.6, ft.Colors.PRIMARY))
        ),
    ),
)


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
    # Handlers (reference `form` / panel controls defined below — resolved
    # at call time, so forward references are fine).
    # ------------------------------------------------------------------

    def _on_ask() -> None:
        if pipeline_running[0]:
            return
        query = form.get_query()
        if not query:
            _toast("Digite uma pergunta.")
            return
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        reindex_btn.disabled = True
        status_detail.value = ""
        _set_progress(True)
        page.update()
        start_ai_answer(
            bus,
            cancel_event,
            query=query,
            scope=form.get_scope(),
            model_name=form.get_model(),
            embed_model=embed_model,
            k=6,
        )

    def _on_reindex(_e=None) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        reindex_btn.disabled = True
        status_detail.value = ""
        _set_progress(True)
        page.update()
        start_ai_index(bus, cancel_event, embed_model=embed_model)

    def _set_progress(active: bool) -> None:
        progress_row.visible = active
        if active:
            progress_bar.value = None  # indeterminate until first update
            spinner_start()
        else:
            spinner_stop()

    # ------------------------------------------------------------------
    # Index status — counted off the UI thread (is_available pings Ollama).
    # ------------------------------------------------------------------

    def _refresh_status() -> None:
        def _worker() -> None:
            from src.core.rag import embedder
            from src.core.rag.indexer import index_dir

            n_docs = n_chunks = 0
            updated: float | None = None
            meta_path = index_dir() / "meta.json"
            try:
                if meta_path.exists():
                    raw = json.loads(meta_path.read_text(encoding="utf-8"))
                    n_chunks = len(raw)
                    n_docs = len({m["source_path"] for m in raw})
                    updated = (index_dir() / "vectors.npz").stat().st_mtime
            except (OSError, ValueError, KeyError) as exc:
                logging.debug("[d] status read failed: %s", exc)

            available = embedder.is_available(embed_model)

            if n_chunks:
                when = (
                    time.strftime("%H:%M", time.localtime(updated)) if updated else "?"
                )
                status_text.value = (
                    f"{n_docs} documento(s) · {n_chunks} chunk(s) · atualizado {when}"
                )
            else:
                status_text.value = "Índice vazio — clique em Reindexar para começar."

            form.set_available(available)
            if not available:
                status_text.value = (
                    "Ollama / nomic-embed-text indisponível — "
                    "rode: ollama pull nomic-embed-text"
                )
            reindex_btn.disabled = (not available) or pipeline_running[0]
            try:
                status_text.update()
                reindex_btn.update()
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Session rendering: one card per Q&A turn, with cited source cards.
    # ------------------------------------------------------------------

    def _open_source(path: Path) -> None:
        if is_viewable(path):
            open_file_viewer(page, path)
            return
        try:
            os.startfile(str(path))  # Windows shell open
        except Exception as exc:
            logging.debug("[d] startfile failed for %s: %s", path, exc)
            _toast(f"Não foi possível abrir {path.name}")

    def _source_card(path: Path) -> ft.Control:
        is_text = path.suffix.lower() in _TEXT_EXTS
        icon = (
            ft.Icons.ARTICLE_OUTLINED
            if is_text
            else ft.Icons.INSERT_DRIVE_FILE_OUTLINED
        )
        extra = [
            action_button(
                "Abrir",
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=lambda _e, _p=path: _open_source(_p),
                accent=Color.log.info,
            )
        ]
        return output_card(path, icon=icon, extra_actions=extra)

    def _make_turn(query: str, text: str, sources: list[str]) -> ft.Control:
        controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.HELP_OUTLINE,
                        size=18,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        query,
                        size=Type.body_strong.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE,
                        expand=True,
                        no_wrap=False,
                    ),
                ],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            hairline(),
            ft.Markdown(
                value=text or "_(sem resposta)_",
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
                md_style_sheet=_MD_STYLE,
            ),
        ]
        if sources:
            controls.append(
                ft.Text(
                    "Fontes citadas",
                    size=Type.caption.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
            controls.extend(_source_card(Path(s)) for s in sources)

        return ft.Container(
            bgcolor=Color.dark.surface_variant,
            border_radius=Radius.lg,
            padding=ft.Padding(
                left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
            ),
            content=ft.Column(controls=controls, spacing=Space.sm),
        )

    def _append_turn(query: str, text: str, sources: list[str]) -> None:
        empty_state.visible = False
        session_list.controls.append(_make_turn(query, text, sources))

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
                _append_turn(
                    p.get("query", ""), p.get("text", ""), p.get("sources", [])
                )
            case "task_done":
                progress_bar.value = 1.0
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                reindex_btn.disabled = False
                _refresh_status()
            case "task_error":
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                reindex_btn.disabled = False
                message = p.get("message", "Erro.")
                status_detail.value = f"[!] {message}"
                _toast(message)
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    form = build_ai_form(page, on_ask=_on_ask)

    status_text = ft.Text(
        "Carregando índice…",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        expand=True,
        no_wrap=False,
    )
    reindex_btn = secondary_button("Reindexar", icon=ft.Icons.REFRESH)
    reindex_btn.on_click = _on_reindex

    status_row = ft.Row(
        controls=[
            ft.Icon(ft.Icons.STORAGE_OUTLINED, size=18, color=ft.Colors.PRIMARY),
            status_text,
            reindex_btn,
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

    empty_state = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.AUTO_AWESOME_OUTLINED,
                    size=48,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Converse com o seu acervo",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Indexe (Reindexar) e faça uma pergunta. As respostas citam "
                    "as fontes do seu próprio conteúdo.",
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

    session_list = ft.ListView(expand=True, spacing=Space.md, auto_scroll=True)

    session_area = ft.Stack([session_list, empty_state], expand=True)

    panel = ft.Column(
        controls=[
            status_row,
            hairline(),
            progress_row,
            status_detail,
            session_area,
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
        # Bridge from the Library: "Conversar sobre" binds a single document and
        # pre-selects the "this document" scope.
        file = payload.get("file") if payload else None
        form.bind_document(str(file) if file else None)
        _refresh_status()

    return Module(
        id=_MODULE_ID,
        label="IA",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        selected_icon=ft.Icons.AUTO_AWESOME,
        control=control,
        on_mount=_on_mount,
    )
