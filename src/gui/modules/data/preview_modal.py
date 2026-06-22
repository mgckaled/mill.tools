"""Source-preview modal for the Data module (PR9.3).

An eye icon on each source chip opens this ``AlertDialog`` floating over the two
views. It has two panes (toggled like manual tabs): a paginated **preview** of
the first rows — the column header shows each inferred type, so the preview
doubles as a quality lens — and an **IA assessment** narrating data-quality
issues. XLSX files with several sheets get a sheet selector.

DuckDB reads and the LLM call run off the UI event loop via
``asyncio.to_thread`` inside ``page.run_task`` coroutines, so the modal stays
responsive and the controls repaint correctly (back on the loop after ``await``).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import flet as ft

from src.core.data.types import DataFile
from src.gui import settings
from src.gui.modules.data.table_view import build_paginated_table
from src.gui.theme.components import Cursor, primary_button
from src.gui.theme.tokens import Space, Type

_LOG = logging.getLogger(__name__)

# Rows pulled into the preview (capped; paginated 50 at a time by the table).
PREVIEW_LIMIT = 200


def open_preview_modal(page: ft.Page, file: DataFile) -> None:
    """Open the preview/assessment modal for a scanned *file*."""
    from src.core.data.engine import xlsx_sheet_names

    path = Path(file.path)
    types = {c.name: c.dtype for c in file.columns}
    sheets = xlsx_sheet_names(path)
    state: dict = {"sheet": sheets[0] if sheets else None, "mode": "preview"}

    # ── preview pane ──────────────────────────────────────────────────────
    ptable = build_paginated_table(page)
    preview_status = ft.Text(
        "Carregando…", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT
    )
    preview_pane = ft.Column(
        controls=[preview_status, ptable.control],
        expand=True,
        spacing=Space.sm,
    )

    async def _load_preview() -> None:
        from src.core.data.engine import DataEngineError, preview

        preview_status.value = "Carregando…"
        preview_status.update()
        try:
            res = await asyncio.to_thread(
                preview, path, limit=PREVIEW_LIMIT, sheet=state["sheet"]
            )
        except DataEngineError as exc:
            preview_status.value = f"Não foi possível ler: {exc}"
            preview_status.update()
            return
        except Exception as exc:  # defensive — never break the modal
            _LOG.warning("[!] preview load failed: %s", exc)
            preview_status.value = "Falha ao carregar a prévia."
            preview_status.update()
            return
        ptable.set_data(res.columns, res.rows, types)
        capped = " (primeiras linhas)" if res.n_rows >= PREVIEW_LIMIT else ""
        preview_status.value = f"{res.n_rows} linha(s){capped}"
        page.update()

    # ── assessment pane ───────────────────────────────────────────────────
    assess_md = ft.Markdown(
        "", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
    )
    assess_status = ft.Text("", size=Type.small.size, color=ft.Colors.PRIMARY)
    assess_btn = primary_button("Avaliar com a IA", icon=ft.Icons.AUTO_AWESOME_OUTLINED)
    assess_empty = ft.Text(
        "A IA examina o esquema, as estatísticas e uma amostra — nunca a tabela "
        "inteira — e aponta inconsistências de tipo, nomes e estrutura.",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
        no_wrap=False,
    )
    assess_pane = ft.Column(
        controls=[
            ft.Row(
                [assess_btn, assess_status],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            assess_empty,
            assess_md,
        ],
        expand=True,
        spacing=Space.sm,
        scroll=ft.ScrollMode.AUTO,
    )

    def _show_assessment(text: str) -> None:
        assess_md.value = text
        assess_empty.visible = False

    async def _run_assessment() -> None:
        from src.core.data import assess as assess_mod
        from src.core.data.datacard import sample_to_text
        from src.core.data.engine import preview as engine_preview
        from src.core.data.profile import profile_text
        from src.core.data.scanner import schema_text

        model = settings.load().get("last_data_model", "gemma3-4b-custom")
        assess_btn.disabled = True
        assess_status.value = "Avaliando…"
        assess_empty.visible = True
        assess_empty.value = "Consultando a IA…"
        page.update()

        def _work() -> str:
            schema = schema_text([file])
            prof = profile_text(path)
            sample = sample_to_text(
                engine_preview(path, limit=10, sheet=state["sheet"])
            )
            text = assess_mod.assess(schema, prof, sample, model_name=model)
            assess_mod.save_assessment(path, text)  # cache → reused by indexing
            return text

        try:
            text = await asyncio.to_thread(_work)
        except Exception as exc:
            _LOG.warning("[!] assessment failed: %s", exc)
            assess_status.value = ""
            assess_btn.disabled = False
            assess_empty.value = f"Não foi possível avaliar: {exc}"
            page.update()
            return
        _show_assessment(text)
        assess_status.value = ""
        assess_btn.disabled = False
        page.update()

    assess_btn.on_click = lambda _e: page.run_task(_run_assessment)

    # Reuse a cached assessment if one exists for this exact file version.
    from src.core.data import assess as _assess_mod

    cached = None
    try:
        cached = _assess_mod.load_cached_assessment(path)
    except Exception as exc:
        _LOG.debug("[d] assessment cache read failed: %s", exc)
    if cached:
        _show_assessment(cached)
        assess_status.value = "(do cache)"

    # ── pane toggle (Prévia | Avaliação da IA) ────────────────────────────
    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_preview = ft.TextButton("Prévia", icon=ft.Icons.TABLE_ROWS_OUTLINED)
    tab_assess = ft.TextButton("Avaliação da IA", icon=ft.Icons.AUTO_AWESOME_OUTLINED)

    def _set_mode(mode: str) -> None:
        state["mode"] = mode
        is_preview = mode == "preview"
        tab_preview.style = _tab_style(is_preview)
        tab_assess.style = _tab_style(not is_preview)
        preview_pane.visible = is_preview
        assess_pane.visible = not is_preview
        page.update()

    tab_preview.on_click = lambda _e: _set_mode("preview")
    tab_assess.on_click = lambda _e: _set_mode("assess")

    # ── sheet selector (XLSX with multiple sheets only) ───────────────────
    header_controls: list[ft.Control] = [
        ft.Row([tab_preview, tab_assess], spacing=Space.xs)
    ]
    if len(sheets) > 1:

        def _on_sheet(e: ft.ControlEvent) -> None:
            state["sheet"] = e.control.value or sheets[0]
            page.run_task(_load_preview)

        sheet_dd = ft.Dropdown(
            label="Aba",
            value=state["sheet"],
            options=[ft.dropdown.Option(s) for s in sheets],
            on_select=_on_sheet,
            width=180,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )
        header_controls.append(ft.Container(expand=True))
        header_controls.append(sheet_dd)

    body = ft.Column(
        controls=[
            ft.Row(header_controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Stack([preview_pane, assess_pane], expand=True),
        ],
        expand=True,
        spacing=Space.sm,
    )
    assess_pane.visible = False

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.TABLE_VIEW_OUTLINED, color=ft.Colors.PRIMARY, size=20),
                ft.Text(
                    f"{path.name}  ·  {file.n_rows} × {file.n_cols}",
                    size=Type.body.size,
                    weight=ft.FontWeight.W_600,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(width=820, height=600, content=body),
        actions=[ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog())],
    )
    page.show_dialog(dlg)
    page.run_task(_load_preview)
