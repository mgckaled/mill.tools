"""Conversa (RAG chat) session for the AI hub: turns, cited sources, ticker.

Owns the Q&A session rendering (one card per turn, with cited source rows and
the out-of-scope warning), the live answer-time ticker, and the ``_on_ask``
handler that kicks off ``run_ai_answer``. Split out of ``view.py`` (Fase 0 of
PLANO_NL2CLI_HUB_IA.md) so the hub's two "worlds" — indexing and conversing —
each get their own file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.gui import settings
from src.gui.modules.ai import timing
from src.gui.modules.ai.worker import start_ai_answer
from src.gui.theme.components import Cursor, action_button, hairline
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type
from src.gui.views.file_viewer import is_viewable, open_file_viewer

if TYPE_CHECKING:
    from src.gui.events import EventBus

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


@dataclass
class AnswerView:
    """Handles for the Conversa session block."""

    clear_btn: ft.Control
    session_area: ft.Control
    gen_status: ft.Text
    ask: Callable[[], None]
    handle_answer_done: Callable[[dict], None]
    stop_ticker: Callable[[], None]


def build_answer_view(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    *,
    embed_model: str,
    get_query: Callable[[], str],
    get_scope: Callable[[], str | None],
    get_model: Callable[[], str],
    on_begin: Callable[[], None],
    on_empty_query: Callable[[], None],
    toast: Callable[[str], None],
) -> AnswerView:
    """Build the Conversa session view and return its handles."""

    # ------------------------------------------------------------------
    # Answer timer: a single blocking invoke() has no progress fraction, so we
    # show elapsed + a rolling per-model "typical" estimate instead of a fake ETA.
    # ------------------------------------------------------------------

    _answer_t0: list[float] = [0.0]
    _ticker_stop = threading.Event()
    _pending_model: list[str] = [""]

    gen_status = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.PRIMARY,
        weight=ft.FontWeight.W_500,
        visible=False,
    )

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

    def stop_ticker() -> None:
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
            toast(f"Não foi possível abrir {path.name}")

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

    def handle_answer_done(payload: dict) -> None:
        _append_turn(
            payload.get("query", ""),
            payload.get("text", ""),
            payload.get("sources", []),
            low_confidence=payload.get("low_confidence", False),
        )
        _record_answer_time(
            payload.get("model_name", _pending_model[0]), payload.get("elapsed", 0.0)
        )

    def ask() -> None:
        if pipeline_running[0]:
            return
        query = get_query()
        if not query:
            on_empty_query()
            return
        model = get_model()
        on_begin()
        _pending_model[0] = model
        times = settings.load().get("ai_answer_times", {}).get(model, [])
        typical = timing.format_typical(timing.average(times), model)
        _start_answer_ticker(typical)
        page.update()
        start_ai_answer(
            bus,
            cancel_event,
            query=query,
            scope=get_scope(),
            model_name=model,
            embed_model=embed_model,
            k=6,
        )

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    # Clears only the visual session; hidden until there is at least one turn.
    clear_btn = action_button(
        "Limpar conversa",
        icon=ft.Icons.DELETE_SWEEP_OUTLINED,
        on_click=_clear_conversation,
        accent=Color.log.muted,
    )
    clear_btn.visible = False

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

    return AnswerView(
        clear_btn=clear_btn,
        session_area=session_area,
        gen_status=gen_status,
        ask=ask,
        handle_answer_done=handle_answer_done,
        stop_ticker=stop_ticker,
    )
