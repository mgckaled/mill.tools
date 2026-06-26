"""Pré-visualização tab — first rows of a source file, with column types.

Reads a window straight from the file (paginated 50 at a time), shows the
inferred type per column in the header and an XLSX sheet selector, and offers an
"Indexar no RAG" action that folds the selected files into the IA index. The
indexing progress/log shows at the top in the shared progress shape.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.gui.modules.data._state import (
    DataViewContext,
    file_by_name,
    make_progress,
    tab_empty_state,
)
from src.gui.modules.data.table_view import build_paginated_table
from src.gui.modules.data.worker import start_index
from src.gui.theme.components import secondary_button
from src.gui.theme.tokens import Space, Type

_PREVIEW_LIMIT = 200  # rows pulled for the source preview (paginated 50 at a time)


@dataclass
class PreviewTab:
    """Handles the central router/view needs from the Pré-visualização tab."""

    view: ft.Control
    on_sources_changed: Callable[[], None]  # data_scanned event
    on_show: Callable[[], None]  # called when the tab becomes active
    on_index_start: Callable[[dict], None]  # data_index_start event
    on_index_progress: Callable[[dict], None]  # data_index_progress event
    on_indexed: Callable[[dict], None]  # data_indexed event
    on_log: Callable[[str], None]  # log event while indexing
    on_error: Callable[[dict], None]  # task_error while indexing


def build_preview_tab(ctx: DataViewContext) -> PreviewTab:
    """Build the Pré-visualização tab and return its handles."""
    page = ctx.page
    form = ctx.form
    prog = make_progress()

    # ------------------------------------------------------------------
    # Source-file selection + sheet selector
    # ------------------------------------------------------------------

    def _preview_file():
        return file_by_name(form.get_files(), preview_file_dd.value)

    def _refresh_sheet_dd(file) -> None:
        """Rebuild the XLSX sheet selector for the selected file (hidden otherwise)."""
        from src.core.data.engine import xlsx_sheet_names

        sheets = xlsx_sheet_names(file.path) if file else []
        preview_sheet_dd.options = [ft.dropdown.Option(s) for s in sheets]
        if preview_sheet_dd.value not in sheets:
            preview_sheet_dd.value = sheets[0] if sheets else None
        preview_sheet_dd.visible = len(sheets) > 1

    async def _load_preview() -> None:
        from src.core.data.engine import DataEngineError, preview

        file = _preview_file()
        if file is None:
            return
        types = {c.name: c.dtype for c in file.columns}
        preview_status.value = "Carregando…"
        try:
            preview_status.update()
        except Exception:
            pass
        try:
            res = await asyncio.to_thread(
                preview, file.path, limit=_PREVIEW_LIMIT, sheet=preview_sheet_dd.value
            )
        except DataEngineError as exc:
            preview_status.value = f"Não foi possível ler: {exc}"
            preview_status.update()
            return
        except Exception as exc:  # defensive — never break the tab
            logging.getLogger(__name__).warning("[!] preview load failed: %s", exc)
            preview_status.value = "Falha ao carregar a prévia."
            preview_status.update()
            return
        ptable.set_data(res.columns, res.rows, types)
        capped = " (primeiras linhas)" if res.n_rows >= _PREVIEW_LIMIT else ""
        preview_status.value = f"{file.path.name} · {res.n_rows} linha(s){capped}"
        page.update()

    def _on_preview_file_change(_e=None) -> None:
        _refresh_sheet_dd(_preview_file())
        page.run_task(_load_preview)

    def on_sources_changed() -> None:
        """Repopulate the file dropdown and toggle empty/content for this tab."""
        files = form.get_files()
        names = [f.path.name for f in files]
        has = bool(files)
        preview_file_dd.options = [ft.dropdown.Option(n) for n in names]
        if preview_file_dd.value not in names:
            preview_file_dd.value = names[0] if names else None
        preview_file_dd.visible = len(files) > 1
        preview_empty.visible = not has
        preview_content.visible = has
        # If a source was added while already on this tab, load it now so the tab
        # isn't left blank until the user re-selects.
        if has and ctx.tab[0] == "preview":
            _refresh_sheet_dd(_preview_file())
            page.run_task(_load_preview)

    def on_show() -> None:
        if form.get_files():
            _refresh_sheet_dd(_preview_file())
            page.run_task(_load_preview)

    # ------------------------------------------------------------------
    # RAG indexing (footer button + progress/log at the top)
    # ------------------------------------------------------------------

    def _on_index(_e=None) -> None:
        if ctx.pipeline_running[0]:
            return
        files = form.get_files()
        if not files:
            ctx.toast("Selecione um arquivo para indexar.")
            return
        ctx.action[0] = "index"
        ctx.pipeline_running[0] = True
        form.set_running(True)
        preview_index_btn.disabled = True
        prog.control.visible = True
        prog.pbar.value = None
        prog.status.value = "Preparando indexação…"
        # Flush visibility BEFORE start() so the spinner animates (see query_tab).
        page.update()
        prog.start()
        start_index(ctx.bus, files, embed_model=ctx.embed_model)

    def _end_index() -> None:
        ctx.pipeline_running[0] = False
        form.set_running(False)
        preview_index_btn.disabled = False
        prog.stop()
        prog.control.visible = False

    def on_index_start(p: dict) -> None:
        # Scoped update + early return: a full page.update() while the spinner is
        # animating would interrupt its on_animation_end chain and stop the mill.
        prog.status.value = "Indexando…"
        ctx.scoped_update(prog.status)

    def on_index_progress(p: dict) -> None:
        cur, tot = p.get("current"), p.get("total")
        prog.pbar.value = (cur / tot) if tot else None
        prog.status.value = f"Indexando {cur}/{tot}…" if tot else "Indexando…"
        ctx.scoped_update(prog.pbar, prog.status)

    def on_indexed(p: dict) -> None:
        _end_index()
        added = p.get("added", 0)
        ctx.toast(
            f"Índice atualizado: +{added} chunk(s)."
            if added
            else "Índice já estava atualizado.",
            error=False,
        )

    def on_log(msg: str) -> None:
        prog.status.value = msg
        ctx.scoped_update(prog.status)

    def on_error(p: dict) -> None:
        _end_index()
        ctx.toast(p.get("message", "Erro."))

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    ptable = build_paginated_table(page)
    preview_file_dd = ft.Dropdown(
        label="Arquivo",
        visible=False,
        on_select=_on_preview_file_change,
        width=240,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    preview_sheet_dd = ft.Dropdown(
        label="Aba",
        visible=False,
        on_select=lambda _e: page.run_task(_load_preview),
        width=180,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    preview_status = ft.Text(
        "", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT
    )
    preview_content = ft.Column(
        controls=[
            ft.Row(
                [preview_file_dd, preview_sheet_dd],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            preview_status,
            ptable.control,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )
    preview_empty = tab_empty_state(
        ft.Icons.TABLE_ROWS_OUTLINED,
        "Pré-visualize seus dados",
        "Selecione arquivos para ver as primeiras linhas e o tipo inferido de "
        "cada coluna. A leitura é 100% local.",
    )
    preview_index_btn = secondary_button(
        "Indexar no RAG", icon=ft.Icons.STORAGE_OUTLINED
    )
    preview_index_btn.on_click = _on_index
    preview_footer = ft.Container(
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border(top=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Row(
            [
                ft.Text(
                    "Adiciona o cartão dos arquivos selecionados ao índice da IA "
                    "(aparece no hub IA, citável nas respostas).",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    no_wrap=False,
                ),
                preview_index_btn,
            ],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    preview_view = ft.Column(
        controls=[
            prog.control,
            ft.Stack([preview_empty, preview_content], expand=True),
            preview_footer,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )

    return PreviewTab(
        view=preview_view,
        on_sources_changed=on_sources_changed,
        on_show=on_show,
        on_index_start=on_index_start,
        on_index_progress=on_index_progress,
        on_indexed=on_indexed,
        on_log=on_log,
        on_error=on_error,
    )
