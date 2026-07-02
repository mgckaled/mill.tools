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

import asyncio
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai import timing
from src.gui.modules.ai.analytics_tab import build_analytics_tab
from src.gui.modules.ai.form_view import build_ai_form
from src.gui.modules.ai.index_tab import build_index_tab
from src.gui.modules.ai.pipeline_log import resolve_status
from src.gui.modules.ai.worker import start_ai_answer, start_ai_index
from src.gui.modules.base import Module
from src.gui.theme.components import (
    Cursor,
    action_button,
    hairline,
    secondary_button,
    spinner,
)
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type
from src.gui.views.file_viewer import is_viewable, open_file_viewer

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "ai"
_DEFAULT_EMBED_MODEL = "nomic-embed-custom"
_TEXT_EXTS = {".txt", ".md"}


def _rel_from_output(path: Path) -> str:
    """Return the path relative to the 'output/' root (filename if not under it).

    e.g. C:\\...\\output\\transcriptions\\text\\foo.txt → output/transcriptions/text/foo.txt
    """
    parts = path.parts
    try:
        i = next(k for k, p in enumerate(parts) if p == "output")
        return "/".join(parts[i:])
    except StopIteration:
        return path.name


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
        model = form.get_model()
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        reindex_btn.disabled = True
        status_detail.value = ""
        _set_progress(True)
        # Live answer timer + a "typical time" learned from this model's history.
        _pending_model[0] = model
        times = settings.load().get("ai_answer_times", {}).get(model, [])
        typical = timing.format_typical(timing.average(times), model)
        _start_answer_ticker(typical)
        page.update()
        start_ai_answer(
            bus,
            cancel_event,
            query=query,
            scope=form.get_scope(),
            model_name=model,
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
            _stop_answer_ticker()

    # ------------------------------------------------------------------
    # Answer timer: a single blocking invoke() has no progress fraction, so we
    # show elapsed + a rolling per-model "typical" estimate instead of a fake ETA.
    # ------------------------------------------------------------------

    _answer_t0: list[float] = [0.0]
    _ticker_stop = threading.Event()
    _pending_model: list[str] = [""]

    async def _tick(typical: str | None) -> None:
        # Runs on the page's UI event loop (via page.run_task) so each update is
        # flushed to the client — a background thread's control.update() would
        # not repaint until the next UI-thread page.update().
        while not _ticker_stop.is_set():
            elapsed = time.monotonic() - _answer_t0[0]
            gen_status.value = timing.compose_status(elapsed, typical)
            try:
                page.update()
            except Exception:
                break
            await asyncio.sleep(1.0)

    def _start_answer_ticker(typical: str | None) -> None:
        _answer_t0[0] = time.monotonic()
        _ticker_stop.clear()
        gen_status.value = timing.compose_status(0, typical)
        gen_status.visible = True
        page.run_task(_tick, typical)

    def _stop_answer_ticker() -> None:
        _ticker_stop.set()
        gen_status.visible = False

    def _record_answer_time(model: str, elapsed: float) -> None:
        """Fold a finished answer's wall-clock time into the model's history."""
        if not model or elapsed <= 0:
            return
        times_map = dict(settings.load().get("ai_answer_times", {}))
        times_map[model] = timing.record_duration(times_map.get(model, []), elapsed)
        settings.set("ai_answer_times", times_map)

    # ------------------------------------------------------------------
    # Index status — counted off the UI thread (is_available pings Ollama).
    # ------------------------------------------------------------------

    def _refresh_status() -> None:
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

            if stats:
                index_tab.apply(stats)  # keep the inspector tab in sync
                analytics_tab.apply(stats)  # keep the panel in sync

            form.set_available(available)
            if not available:
                status_text.value = (
                    f"Ollama / {embed_model} indisponível — rode: {embedder.SETUP_HINT}"
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

    def _open_folder(path: Path) -> None:
        try:
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        except Exception as exc:
            logging.debug("[d] explorer select failed for %s: %s", path, exc)

    def _source_item(idx: int, path: Path) -> ft.Control:
        """Compact cited-source row: [n] badge · filename / output-relative folder.

        Replaces the heavy output_card — two tight lines instead of a card with
        the full absolute path, to save vertical space in the answer panel. The
        [n] badge ties the source back to the [n] markers in the answer; the row
        opens the file, the trailing icon opens its folder.
        """
        is_text = path.suffix.lower() in _TEXT_EXTS
        icon = (
            ft.Icons.ARTICLE_OUTLINED
            if is_text
            else ft.Icons.INSERT_DRIVE_FILE_OUTLINED
        )
        rel = _rel_from_output(path)  # output/transcriptions/text/foo.txt
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""

        badge = ft.Container(
            content=ft.Text(
                str(idx),
                size=Type.tiny.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            border_radius=Radius.sm,
            padding=ft.Padding(
                left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs
            ),
            alignment=ft.Alignment.CENTER,
        )
        name_row = ft.Row(
            controls=[
                badge,
                ft.Icon(icon, size=IconSize.sm, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(
                    path.name,
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    tooltip=path.name,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        folder_line = ft.Container(
            padding=ft.Padding(left=Space.lg, right=0, top=0, bottom=0),
            content=ft.Text(
                folder,
                size=Type.tiny.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
                tooltip=rel,
            ),
        )
        open_area = ft.GestureDetector(
            content=ft.Column([name_row, folder_line], spacing=0),
            on_tap=lambda _e, _p=path: _open_source(_p),
            mouse_cursor=Cursor.interactive,
            expand=True,
        )
        folder_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN_OUTLINED,
            icon_size=IconSize.sm,
            tooltip="Abrir pasta",
            on_click=lambda _e, _p=path: _open_folder(_p),
            style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
        )
        return ft.Container(
            padding=ft.Padding(left=Space.xs, right=0, top=Space.xxs, bottom=Space.xxs),
            content=ft.Row(
                controls=[open_area, folder_btn],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _scope_warning() -> ft.Control:
        """A banner shown when the corpus likely does not cover the question."""
        return ft.Container(
            bgcolor=Color.dark.surface,
            border_radius=Radius.md,
            padding=ft.Padding(
                left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
            ),
            content=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_ROUNDED,
                        size=IconSize.md,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.Text(
                        "O acervo provavelmente não cobre bem esta pergunta — "
                        "a resposta pode ser imprecisa.",
                        size=Type.caption.size,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        expand=True,
                        no_wrap=False,
                    ),
                ],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _make_turn(
        query: str, text: str, sources: list[str], *, low_confidence: bool = False
    ) -> ft.Control:
        controls: list[ft.Control] = [
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.HELP_OUTLINE,
                        size=IconSize.lg,
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
        ]
        if low_confidence:
            controls.append(_scope_warning())
        controls.append(
            ft.Markdown(
                value=text or "_(sem resposta)_",
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
                md_style_sheet=_MD_STYLE,
            )
        )
        if sources:
            controls.append(
                ft.Text(
                    "Fontes citadas",
                    size=Type.caption.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
            # Tight column so the compact source rows don't get the turn's sm gap.
            controls.append(
                ft.Column(
                    controls=[
                        _source_item(i, Path(s)) for i, s in enumerate(sources, 1)
                    ],
                    spacing=Space.xxs,
                )
            )

        return ft.Container(
            bgcolor=Color.dark.surface_variant,
            border_radius=Radius.lg,
            padding=ft.Padding(
                left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
            ),
            content=ft.Column(controls=controls, spacing=Space.sm),
        )

    def _append_turn(
        query: str, text: str, sources: list[str], *, low_confidence: bool = False
    ) -> None:
        empty_state.visible = False
        session_list.controls.append(
            _make_turn(query, text, sources, low_confidence=low_confidence)
        )
        clear_btn.visible = True

    def _clear_conversation(_e=None) -> None:
        """Reset only the visual Q&A list (no model/index state is involved)."""
        session_list.controls.clear()
        empty_state.visible = True
        clear_btn.visible = False
        page.update()

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
                    p.get("query", ""),
                    p.get("text", ""),
                    p.get("sources", []),
                    low_confidence=p.get("low_confidence", False),
                )
                _record_answer_time(
                    p.get("model_name", _pending_model[0]), p.get("elapsed", 0.0)
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

    # Clears only the visual session; hidden until there is at least one turn.
    clear_btn = action_button(
        "Limpar conversa",
        icon=ft.Icons.DELETE_SWEEP_OUTLINED,
        on_click=_clear_conversation,
        accent=Color.log.muted,
    )
    clear_btn.visible = False

    status_row = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.STORAGE_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
            ),
            status_text,
            clear_btn,
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
    # Live answer timer ("Gerando resposta… 0:14 · ~28s (típico do …)").
    gen_status = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.PRIMARY,
        weight=ft.FontWeight.W_500,
        visible=False,
    )
    progress_row = ft.Column(
        controls=[
            ft.Row(
                controls=[spinner_img, stage_label],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
            gen_status,
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
                    size=IconSize.hero,
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

    # ------------------------------------------------------------------
    # Panel: manual "Conversa | Índice" tabs over a Stack (Flet 0.85 has no
    # ft.Tabs). The Conversa view is the existing chat; the Índice view is the
    # RAG index inspector, kept in sync by _refresh_status → index_tab.apply.
    # ------------------------------------------------------------------

    conversa_view = ft.Column(
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

    index_tab = build_index_tab(page, on_reindex=lambda: _reindex_from_index())
    index_view = index_tab.control
    index_view.visible = False

    analytics_tab = build_analytics_tab(page)
    analytics_view = analytics_tab.control
    analytics_view.visible = False

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_conversa = ft.TextButton(
        "Conversa", icon=ft.Icons.CHAT_OUTLINED, style=_tab_style(True)
    )
    tab_indice = ft.TextButton(
        "Índice", icon=ft.Icons.INVENTORY_2_OUTLINED, style=_tab_style(False)
    )
    tab_painel = ft.TextButton(
        "Painel", icon=ft.Icons.INSIGHTS_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str, *, refresh: bool = True) -> None:
        conversa_view.visible = name == "conversa"
        index_view.visible = name == "indice"
        analytics_view.visible = name == "painel"
        tab_conversa.style = _tab_style(name == "conversa")
        tab_indice.style = _tab_style(name == "indice")
        tab_painel.style = _tab_style(name == "painel")
        settings.set("last_ai_tab", name)
        if name in ("indice", "painel") and refresh:
            _refresh_status()  # recompute stats → index_tab / analytics_tab.apply
        page.update()

    def _reindex_from_index() -> None:
        # Reindex triggered from the Índice tab — jump to Conversa to show progress.
        _show_tab("conversa", refresh=False)
        _on_reindex()

    tab_conversa.on_click = lambda _e: _show_tab("conversa")
    tab_indice.on_click = lambda _e: _show_tab("indice")
    tab_painel.on_click = lambda _e: _show_tab("painel")

    body_stack = ft.Stack([conversa_view, index_view, analytics_view], expand=True)

    panel = ft.Column(
        controls=[
            ft.Row([tab_conversa, tab_indice, tab_painel], spacing=Space.xs),
            hairline(),
            body_stack,
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
        # A document bridge means the user wants to ask → land on Conversa.
        saved = "conversa" if file else settings.load().get("last_ai_tab", "conversa")
        _show_tab(saved, refresh=False)
        _refresh_status()  # computes stats once, updating both status line + tab

    return Module(
        id=_MODULE_ID,
        label="IA",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        selected_icon=ft.Icons.AUTO_AWESOME,
        control=control,
        on_mount=_on_mount,
    )
