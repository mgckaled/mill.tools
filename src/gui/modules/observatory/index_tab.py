"""Index inspector sub-tab of the Observatório hub's Índice/RAG tab (PR7.2.3).

A scrollable, paginated view of the persisted RAG index: a global summary card
plus a per-document table with a chunk drill-down. The data comes from the pure
core (``src.core.rag.stats``); this file only builds Flet controls and is not
unit-tested headless. Migrated here from the AI hub (which now only shows
Conversa). Fase 0b (PLANO_NL2CLI_HUB_IA.md) finishes that migration: "Reindexar"
now runs the pipeline itself (via ``on_reindex``/``on_cancel``, wired by
``rag_tab.py`` to ``observatory/index_worker.py``) instead of bridging back to
the AI hub — this tab owns its own progress row + cancel button, same spirit as
the tool modules' pipelines.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.rag.stats import (
    IndexStats,
    chunks_for,
    fmt_datetime,
    fmt_disk_size,
    fmt_thousands,
)
from src.gui.theme.components import (
    Cursor,
    danger_button,
    help_icon_for,
    secondary_button,
    section_label,
    spinner,
    summary_card,
)
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type

# Render the per-document table in pages so a large index never builds thousands
# of rows at once (same approach as the Library list mode).
_PAGE_SIZE = 120

_KIND_ICONS = {
    "transcription": ft.Icons.SUBTITLES_OUTLINED,
    "document": ft.Icons.DESCRIPTION_OUTLINED,
    "image": ft.Icons.IMAGE_OUTLINED,
}
_KIND_LABELS = {
    "transcription": "Transcrição",
    "document": "Documento",
    "image": "Imagem",
}

# Shared column widths so the header and the rows line up.
_W_KIND = 104
_W_CHUNKS = 60
_W_CHARS = 84
_W_DATE = 92
_W_LEAD = IconSize.sm  # leading type-icon column
_W_TRAIL = 40  # trailing drill-down button column


@dataclass
class IndexTab:
    """Handles for the index inspector tab."""

    control: ft.Control
    apply: Callable[[IndexStats], None]  # called on the UI thread with fresh stats
    set_running: Callable[[bool], None]  # toggles the progress row + button states
    set_progress: Callable[[int | None, int | None], None]  # (current, total)
    set_detail: Callable[[str], None]  # mono status line (log/summary/error text)


def _safe_update(*controls: ft.Control) -> None:
    for c in controls:
        try:
            c.update()
        except Exception:
            pass


def build_index_tab(
    page: ft.Page,
    *,
    on_reindex: Callable[[], None],
    on_cancel: Callable[[], None],
) -> IndexTab:
    """Build the index inspector tab and return its handles.

    ``on_reindex``/``on_cancel`` are wired by ``rag_tab.py`` to the real
    pipeline (``observatory/index_worker.py``) — this file only owns the
    controls and their visual state.
    """
    state: dict = {"docs": [], "shown": 0}

    # ── global summary card ────────────────────────────────────────────────
    def _stat_value(mono: bool = False) -> ft.Text:
        return ft.Text(
            "—",
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE,
            font_family=Type.FONT_MONO if mono else None,
            no_wrap=mono,
            overflow=ft.TextOverflow.ELLIPSIS if mono else None,
            expand=mono,
        )

    vals = {
        "docs": _stat_value(),
        "chunks": _stat_value(),
        "dim": _stat_value(),
        "model": _stat_value(),
        "size": _stat_value(),
        "updated": _stat_value(),
        "path": _stat_value(mono=True),
    }

    def _stat_line(label: str, value: ft.Text) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Text(
                    label,
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    width=96,
                ),
                value,
            ],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    summary = summary_card(
        ft.Column(
            controls=[
                _stat_line("Documentos", vals["docs"]),
                _stat_line("Chunks", vals["chunks"]),
                _stat_line("Dimensão", vals["dim"]),
                _stat_line("Modelo", vals["model"]),
                _stat_line("Tamanho", vals["size"]),
                _stat_line("Atualizado", vals["updated"]),
                _stat_line("Local", vals["path"]),
            ],
            spacing=Space.xs,
        )
    )

    reindex_btn = secondary_button("Reindexar", icon=ft.Icons.REFRESH)
    reindex_btn.on_click = lambda _e: on_reindex()

    header_controls: list[ft.Control] = [
        ft.Icon(
            ft.Icons.INVENTORY_2_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
        ),
        ft.Text(
            "Inspetor do índice",
            size=Type.heading.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
        ft.Container(expand=True),
        reindex_btn,
    ]
    _help = help_icon_for("observatory.rag_index", page)
    if _help is not None:
        header_controls.insert(2, _help)
    header_row = ft.Row(
        controls=header_controls,
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ── reindex progress (spinner + bar + status line + cancel) ────────────
    spinner_img, spinner_start, spinner_stop = spinner()
    stage_label = ft.Text(
        "Indexando…",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        weight=ft.FontWeight.W_500,
    )
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    cancel_btn = danger_button(
        "Cancelar", icon=ft.Icons.CANCEL_OUTLINED, on_click=lambda _e: on_cancel()
    )
    cancel_btn.disabled = True
    status_detail = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
        no_wrap=False,
    )
    progress_row = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    spinner_img,
                    stage_label,
                    ft.Container(expand=True),
                    cancel_btn,
                ],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
            status_detail,
        ],
        spacing=Space.xs,
        visible=False,
    )

    def set_running(active: bool) -> None:
        progress_row.visible = active
        reindex_btn.disabled = active
        cancel_btn.disabled = not active
        if active:
            progress_bar.value = None
            status_detail.value = ""
            spinner_start()
        else:
            spinner_stop()
        _safe_update(progress_row, reindex_btn)

    def set_progress(current: int | None, total: int | None) -> None:
        progress_bar.value = (current / total) if total else None
        if total:
            status_detail.value = f"Indexando {current}/{total}…"
        _safe_update(progress_bar, status_detail)

    def set_detail(message: str) -> None:
        status_detail.value = message
        _safe_update(status_detail)

    # ── per-document table ─────────────────────────────────────────────────
    def _header_cell(text: str, *, width=None, expand=False, right=False) -> ft.Control:
        return ft.Container(
            width=width,
            expand=expand,
            content=ft.Text(
                text,
                size=Type.tiny.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE_VARIANT,
                text_align=ft.TextAlign.RIGHT if right else ft.TextAlign.LEFT,
            ),
        )

    table_header = ft.Container(
        padding=ft.Padding(
            left=Space.xs, right=Space.xs, top=Space.xs, bottom=Space.xs
        ),
        border=ft.Border(bottom=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Row(
            controls=[
                ft.Container(width=_W_LEAD),
                _header_cell("Documento", expand=True),
                _header_cell("Tipo", width=_W_KIND),
                _header_cell("Chunks", width=_W_CHUNKS, right=True),
                _header_cell("Caracteres", width=_W_CHARS, right=True),
                _header_cell("Data", width=_W_DATE),
                ft.Container(width=_W_TRAIL),
            ],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    table_list = ft.Column(controls=[], spacing=0)

    empty_note = ft.Container(
        visible=False,
        padding=ft.Padding(left=0, right=0, top=Space.lg, bottom=Space.lg),
        content=ft.Text(
            "Nenhum documento indexado ainda. Clique em Reindexar.",
            size=Type.input.size,
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    )

    def _doc_row(doc) -> ft.Control:
        name = Path(doc.source_path).name
        icon = _KIND_ICONS.get(doc.kind, ft.Icons.INSERT_DRIVE_FILE_OUTLINED)
        drill = ft.IconButton(
            icon=ft.Icons.UNFOLD_MORE,
            icon_size=IconSize.sm,
            tooltip="Ver chunks",
            on_click=lambda _e, _d=doc: _open_chunks(_d),
            style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
        )
        return ft.Container(
            padding=ft.Padding(
                left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs
            ),
            border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            content=ft.Row(
                controls=[
                    ft.Icon(icon, size=IconSize.sm, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(
                        name,
                        size=Type.small.size,
                        color=ft.Colors.ON_SURFACE,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        expand=True,
                        tooltip=doc.source_path,
                    ),
                    ft.Container(
                        width=_W_KIND,
                        content=ft.Text(
                            _KIND_LABELS.get(doc.kind, doc.kind),
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ),
                    ft.Container(
                        width=_W_CHUNKS,
                        content=ft.Text(
                            fmt_thousands(doc.n_chunks),
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ),
                    ft.Container(
                        width=_W_CHARS,
                        content=ft.Text(
                            fmt_thousands(doc.char_total),
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ),
                    ft.Container(
                        width=_W_DATE,
                        content=ft.Text(
                            fmt_datetime(doc.mtime),
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ),
                    drill,
                ],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _render_more(_e=None) -> None:
        docs = state["docs"]
        start = state["shown"]
        page_docs = docs[start : start + _PAGE_SIZE]
        table_list.controls.extend(_doc_row(d) for d in page_docs)
        state["shown"] += len(page_docs)
        more_btn.visible = state["shown"] < len(docs)
        more_btn.text = (
            f"Carregar mais ({len(docs) - state['shown']})"
            if more_btn.visible
            else "Carregar mais"
        )
        _safe_update(table_list, more_btn)

    more_btn = secondary_button("Carregar mais", icon=ft.Icons.EXPAND_MORE)
    more_btn.on_click = _render_more
    more_btn.visible = False

    # ── chunk drill-down (reads meta.json off the UI thread) ───────────────
    def _chunk_item(idx: int, text: str) -> ft.Control:
        preview = text.strip()
        if len(preview) > 600:
            preview = preview[:600] + "…"
        badge = ft.Container(
            content=ft.Text(
                f"#{idx}",
                size=Type.tiny.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            border_radius=Radius.sm,
            padding=ft.Padding(
                left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs
            ),
        )
        return ft.Container(
            bgcolor=Color.dark.surface_variant,
            border_radius=Radius.sm,
            padding=ft.Padding(
                left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
            ),
            content=ft.Column(
                controls=[
                    badge,
                    ft.Text(
                        preview,
                        size=Type.small.size,
                        color=ft.Colors.ON_SURFACE,
                        selectable=True,
                        no_wrap=False,
                    ),
                ],
                spacing=Space.xs,
            ),
        )

    def _open_chunks(doc) -> None:
        body = ft.Column(
            controls=[
                ft.Text(
                    "Carregando chunks…",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=Space.sm,
            expand=True,
        )
        dlg = ft.AlertDialog(
            title=ft.Text(
                Path(doc.source_path).name,
                size=Type.heading.size,
                weight=ft.FontWeight.W_600,
                no_wrap=False,
            ),
            content=ft.Container(content=body, width=600, height=460),
            actions=[
                ft.TextButton(
                    "Fechar",
                    on_click=lambda _e: page.pop_dialog(),
                    style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
                )
            ],
        )
        page.show_dialog(dlg)

        def _load() -> None:
            from src.core.rag.indexer import index_dir

            try:
                rows = chunks_for(index_dir(), doc.source_path)
            except Exception as exc:  # defensive — a bad meta.json shouldn't crash
                logging.debug("[d] chunks_for failed: %s", exc)
                rows = []
            body.controls = [_chunk_item(i, t) for i, t in rows] or [
                ft.Text(
                    "Sem chunks para este documento.",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            ]
            _safe_update(body)

        threading.Thread(target=_load, daemon=True).start()

    # ── apply fresh stats (UI thread) ──────────────────────────────────────
    def apply(stats: IndexStats) -> None:
        vals["docs"].value = fmt_thousands(stats.n_docs)
        vals["chunks"].value = fmt_thousands(stats.n_chunks)
        vals["dim"].value = str(stats.dim) if stats.dim else "—"
        vals["model"].value = stats.embed_model
        vals["size"].value = fmt_disk_size(stats.disk_bytes)
        vals["updated"].value = (
            fmt_datetime(stats.updated_at) if stats.updated_at else "—"
        )
        vals["path"].value = str(Path.home() / ".mill-tools" / "rag")

        state["docs"] = list(stats.per_doc)
        state["shown"] = 0
        table_list.controls.clear()
        if stats.per_doc:
            empty_note.visible = False
            _render_more()
        else:
            empty_note.visible = True
            more_btn.visible = False
        _safe_update(control)

    control = ft.Column(
        controls=[
            header_row,
            progress_row,
            summary,
            section_label("Documentos indexados"),
            table_header,
            table_list,
            empty_note,
            ft.Row([more_btn], alignment=ft.MainAxisAlignment.CENTER),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    return IndexTab(
        control=control,
        apply=apply,
        set_running=set_running,
        set_progress=set_progress,
        set_detail=set_detail,
    )
