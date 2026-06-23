"""Data module — query-first structured-data tool over DuckDB.

A NavigationRail tool (the 6th), but self-contained like the AI/Recipes hubs: it
subscribes to its own PipelineEvents (module_id="data") and updates the panel on
the UI thread. The right panel has three manual tabs (Flet 0.85 has no ft.Tabs),
mirroring the AI hub's Conversa|Índice toggle:

- **Consulta**: the "entendi assim" review card (editable SQL), a paginated
  preview of the query result, and a return-shaping block (rename columns, pick a
  format, Save / Conversar sobre / Salvar como Receita / Indexar no RAG).
- **Pré-visualização**: the first rows of a source file, with the inferred type
  per column in the header (a quality lens) and an XLSX sheet selector.
- **Análise com IA**: a data-quality narrative from the IA over a source file.

Privacy: the IA (NL→SQL and the assessment) only ever sees the column names +
statistics + a small sample — never the table rows.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import flet as ft

from src.core.data import convert
from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai import timing
from src.gui.modules.base import Module
from src.gui.modules.data.form_view import build_data_form
from src.gui.modules.data.table_view import build_paginated_table
from src.gui.modules.data.worker import (
    start_assess,
    start_index,
    start_query,
    start_save,
    start_scan,
    start_translate,
)
from src.gui.theme.components import (
    Cursor,
    action_button,
    hairline,
    primary_button,
    secondary_button,
    spinner,
)
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "data"
_PAGE_SIZE = 50  # rows shown per result-preview page (in-memory, like the Library)
_PREVIEW_LIMIT = 200  # rows pulled for the source preview tab (paginated 50 at a time)


def build_data_module(
    page: ft.Page,
    bus: EventBus,
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Data module — query files, preview, assess, shape and save.

    Args:
        page: Flet page.
        bus: Shared application EventBus (worker → UI).
        cancel_event: threading.Event (kept for signature symmetry; queries are
            short and synchronous, so there is nothing to cancel mid-step).
        pipeline_running: Shared [bool] guard with app.py — blocks navigation
            while a query/save runs.
        nav: List holding [navigate_to] — used by the "Conversar sobre" bridge.
    """
    cfg = settings.load()
    embed_model = cfg.get("last_embed_model", "nomic-embed-custom")

    # Result/query state shared across handlers.
    _result_columns: list[str] = []
    _result_rows: list[tuple] = []
    _page_idx: list[int] = [0]
    _rename_fields: dict[str, ft.TextField] = {}
    _last_saved: list[Path | None] = [None]
    _action: list[str] = ["query"]  # which flow the in-flight worker is running
    _pending_model: list[str] = [""]  # model of the in-flight translate (for timing)
    _last_error: list[str] = [""]  # last query/translate error (for IA refinement)
    _last_failed_sql: list[str] = [""]
    _has_result: list[bool] = [False]
    _tab: list[str] = ["consulta"]

    def _toast(message: str, *, error: bool = True) -> None:
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY,
        )
        page.snack_bar.open = True
        page.update()

    def _scoped_update(*controls: ft.Control) -> None:
        """Repaint only these controls — never page.update() while a spinner runs.

        A full page.update() interrupts a spinner's in-flight rotation so its
        on_animation_end chain never re-fires and the mill stops turning.
        """
        for c in controls:
            try:
                c.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Live timer: like the AI hub, a blocking IA invoke() has no honest
    # countdown, so we show elapsed + a per-model "typical" learned from a
    # rolling average. The ticker also keeps the spinner repainting (a daemon
    # thread's update() would not flush until the next UI-thread page.update()).
    # ------------------------------------------------------------------

    _t0: list[float] = [0.0]
    _ticker_stop = threading.Event()
    _ACTION_LABEL = {
        "translate": "Traduzindo a pergunta",
        "query": "Executando a consulta",
        "save": "Salvando",
        "converse": "Salvando",
    }

    async def _tick(typical: str | None) -> None:
        while not _ticker_stop.is_set():
            elapsed = time.monotonic() - _t0[0]
            label = _ACTION_LABEL.get(_action[0], "Processando")
            line = f"{label}… {timing.format_clock(elapsed)}"
            if typical:
                line += f" · {typical}"
            gen_status.value = line
            # Update ONLY the status text — a full page.update() here would
            # interrupt the spinner's in-flight rotation animation, so its
            # on_animation_end chain never re-fires and the mill stops turning.
            try:
                gen_status.update()
            except Exception:
                break
            await asyncio.sleep(1.0)

    def _start_ticker() -> None:
        _t0[0] = time.monotonic()
        _ticker_stop.clear()
        # Only the translate (NL→SQL) step has a per-model typical estimate.
        typical = None
        if _action[0] == "translate":
            times = (
                settings.load().get("data_query_times", {}).get(_pending_model[0], [])
            )
            typical = timing.format_typical(timing.average(times), _pending_model[0])
        label = _ACTION_LABEL.get(_action[0], "Processando")
        gen_status.value = f"{label}… 0:00" + (f" · {typical}" if typical else "")
        gen_status.visible = True
        page.run_task(_tick, typical)

    def _stop_ticker() -> None:
        _ticker_stop.set()
        gen_status.visible = False

    def _record_query_time(model: str, elapsed: float) -> None:
        """Fold a finished translation's wall-clock time into the model's history."""
        if not model or elapsed <= 0:
            return
        times_map = dict(settings.load().get("data_query_times", {}))
        times_map[model] = timing.record_duration(times_map.get(model, []), elapsed)
        settings.set("data_query_times", times_map)

    # ------------------------------------------------------------------
    # Form callbacks
    # ------------------------------------------------------------------

    def _on_pick(paths: list[Path]) -> None:
        start_scan(bus, paths)

    def _current_sql() -> str:
        """The SQL to run: the (possibly edited) review box, or the form text."""
        if form.get_mode() == "sql":
            return form.get_text()
        return (sql_box.value or "").strip()

    def _on_preview() -> None:
        if pipeline_running[0]:
            return
        if not form.get_files():
            _toast("Selecione ao menos um arquivo.")
            return
        if form.get_mode() == "sql":
            # SQL mode: no translation — just surface the SQL in the review card.
            sql = form.get_text()
            if not sql:
                _toast("Escreva uma consulta SQL.")
                return
            _show_review(sql, "")
            return
        question = form.get_text()
        if not question:
            _toast("Escreva uma pergunta.")
            return
        _action[0] = "translate"
        _begin()
        start_translate(bus, form.get_files(), question, model_name=form.get_model())

    def _on_run() -> None:
        if pipeline_running[0]:
            return
        if not form.get_files():
            _toast("Selecione ao menos um arquivo.")
            return
        sql = _current_sql()
        if not sql:
            _toast("Nada para executar — pré-visualize ou escreva a consulta.")
            return
        _action[0] = "query"
        _last_failed_sql[0] = sql  # remembered so an error can be sent back to the IA
        _begin()
        start_query(bus, form.get_files(), sql)

    def _on_refine_with_ai(_e=None) -> None:
        """Send the failed SQL + DuckDB error back to the IA to fix the query."""
        if pipeline_running[0] or not form.get_files() or not _last_error[0]:
            return
        base = form.get_text() or "Corrija a consulta SQL para responder à pergunta."
        augmented = (
            f"{base}\n\n"
            "A consulta SQL gerada anteriormente falhou ao executar no DuckDB.\n"
            f"SQL com erro: {_last_failed_sql[0] or '(desconhecido)'}\n"
            f"Mensagem de erro: {_last_error[0]}\n"
            "Gere uma nova consulta SELECT que corrija esse erro, usando apenas "
            "colunas existentes no esquema."
        )
        _action[0] = "translate"
        _begin()
        start_translate(bus, form.get_files(), augmented, model_name=form.get_model())

    # ------------------------------------------------------------------
    # Panel state helpers (Consulta tab)
    # ------------------------------------------------------------------

    def _begin() -> None:
        pipeline_running[0] = True
        form.set_running(True)
        _pending_model[0] = form.get_model()
        error_box.visible = False  # clear any previous error while we work
        empty_state.visible = False  # gone for good after the first action
        progress_row.visible = True
        progress_bar.value = None
        # Start the spin, then let the single page.update() below flush the
        # first rotation — exactly like progress_view (its page.update() comes
        # *after* _start_spin). The on_animation_end chain then keeps it turning
        # via control-level img.update()s; the ticker must NOT page.update()
        # (it would interrupt that animation — see _tick).
        spinner_start()
        _start_ticker()
        page.update()

    def _end() -> None:
        pipeline_running[0] = False
        form.set_running(False)
        progress_row.visible = False
        spinner_stop()
        _stop_ticker()

    def _show_review(sql: str, explanation: str) -> None:
        empty_state.visible = False  # SQL mode reaches here without _begin()
        review_card.visible = True
        explanation_text.value = explanation or "Revise e execute a consulta abaixo."
        explanation_text.visible = bool(explanation) or form.get_mode() == "sql"
        sql_box.value = sql
        page.update()

    # ------------------------------------------------------------------
    # Result preview table (paginated, in-memory) — Consulta tab
    # ------------------------------------------------------------------

    def _cell(value) -> str:
        return "" if value is None else str(value)

    def _render_table() -> None:
        total = len(_result_rows)
        start = _page_idx[0] * _PAGE_SIZE
        page_rows = _result_rows[start : start + _PAGE_SIZE]
        table.columns = [ft.DataColumn(ft.Text(c)) for c in _result_columns] or [
            ft.DataColumn(ft.Text(""))
        ]
        table.rows = [
            ft.DataRow(cells=[ft.DataCell(ft.Text(_cell(v))) for v in row])
            for row in page_rows
        ]
        last_page = max(0, (total - 1) // _PAGE_SIZE)
        page_label.value = (
            f"{start + 1}–{min(start + _PAGE_SIZE, total)} de {total}" if total else "—"
        )
        prev_btn.disabled = _page_idx[0] <= 0
        next_btn.disabled = _page_idx[0] >= last_page

    def _go_prev(_e=None) -> None:
        if _page_idx[0] > 0:
            _page_idx[0] -= 1
            _render_table()
            page.update()

    def _go_next(_e=None) -> None:
        if (_page_idx[0] + 1) * _PAGE_SIZE < len(_result_rows):
            _page_idx[0] += 1
            _render_table()
            page.update()

    def _build_rename_fields() -> None:
        _rename_fields.clear()
        rename_col.controls.clear()
        for c in _result_columns:
            tf = ft.TextField(
                label=c,
                hint_text="novo nome (opcional)",
                dense=True,
                text_size=Type.input.size,
                border_color=ft.Colors.OUTLINE_VARIANT,
                focused_border_color=ft.Colors.PRIMARY,
                width=200,
            )
            _rename_fields[c] = tf
            rename_col.controls.append(tf)

    def _renames() -> dict[str, str]:
        return {c: (tf.value or "").strip() for c, tf in _rename_fields.items()}

    def _show_result() -> None:
        empty_state.visible = False
        result_area.visible = True
        _has_result[0] = True
        footer.visible = _tab[0] == "consulta"  # actions belong to the query tab
        _page_idx[0] = 0
        _render_table()
        _build_rename_fields()

    # ------------------------------------------------------------------
    # Save / bridges (return-shaping block)
    # ------------------------------------------------------------------

    def _save_stem() -> str:
        return (name_field.value or "").strip() or "consulta"

    def _effective_sql() -> str:
        return convert.rename_sql(_current_sql(), _result_columns, _renames())

    def _on_save(_e=None) -> None:
        if pipeline_running[0] or not _result_columns:
            return
        _action[0] = "save"
        _begin()
        start_save(
            bus, form.get_files(), _effective_sql(), fmt_dd.value or "csv", _save_stem()
        )

    def _on_converse(_e=None) -> None:
        # Save first (if needed) and hand the saved file to the AI hub.
        if not _result_columns:
            return
        if _last_saved[0] and _last_saved[0].exists():
            nav[0]("ai", {"file": str(_last_saved[0])})
            return
        _action[0] = "converse"
        _begin()
        # JSON is the most chat-friendly export for a tabular answer.
        start_save(bus, form.get_files(), _effective_sql(), "json", _save_stem())

    def _on_save_recipe(_e=None) -> None:
        if not _current_sql():
            return
        from src.core.recipes.store import save_recipe
        from src.core.recipes.types import Recipe, RecipeStep

        name = _save_stem()
        recipe = Recipe(
            name=name,
            steps=[RecipeStep(op="data.query", params={"sql": _current_sql()})],
            description="Consulta de dados salva pelo módulo Dados.",
        )
        try:
            save_recipe(recipe)
            _toast(f'Receita "{name}" salva.', error=False)
        except Exception as exc:
            logging.getLogger(__name__).warning("[!] save recipe failed: %s", exc)
            _toast("Não foi possível salvar a receita.")

    def _open_folder(path: Path) -> None:
        try:
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        except Exception as exc:
            logging.debug("[d] explorer select failed for %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Preview-tab indexing (RAG) — footer button + progress/log at the top
    # ------------------------------------------------------------------

    def _on_index(_e=None) -> None:
        if pipeline_running[0]:
            return
        _action[0] = "index"
        pipeline_running[0] = True
        form.set_running(True)
        preview_index_btn.disabled = True
        preview_prog.control.visible = True
        preview_prog.pbar.value = None
        preview_prog.status.value = "Preparando indexação…"
        preview_prog.start()
        page.update()
        start_index(bus, embed_model=embed_model)

    def _end_index() -> None:
        pipeline_running[0] = False
        form.set_running(False)
        preview_index_btn.disabled = False
        preview_prog.stop()
        preview_prog.control.visible = False

    # ------------------------------------------------------------------
    # Analysis-tab assessment — footer button + live timer/log at the top
    # ------------------------------------------------------------------

    _assess_t0: list[float] = [0.0]
    _assess_ticker_stop = threading.Event()

    async def _assess_tick() -> None:
        while not _assess_ticker_stop.is_set():
            elapsed = time.monotonic() - _assess_t0[0]
            analysis_prog.status.value = (
                f"Avaliando com a IA… {timing.format_clock(elapsed)}"
            )
            try:
                analysis_prog.status.update()
            except Exception:
                break
            await asyncio.sleep(1.0)

    def _on_assess(_e=None) -> None:
        if pipeline_running[0]:
            return
        file = _analysis_file()
        if file is None:
            _toast("Selecione um arquivo para avaliar.")
            return
        _action[0] = "assess"
        pipeline_running[0] = True
        form.set_running(True)
        assess_btn.disabled = True
        assess_hint.visible = False
        assess_md.visible = False
        assess_status.value = ""
        analysis_prog.control.visible = True
        analysis_prog.pbar.value = None
        analysis_prog.status.value = "Avaliando com a IA… 0:00"
        analysis_prog.start()
        _assess_t0[0] = time.monotonic()
        _assess_ticker_stop.clear()
        page.run_task(_assess_tick)
        page.update()
        start_assess(bus, file, model_name=form.get_model())

    def _end_assess() -> None:
        pipeline_running[0] = False
        form.set_running(False)
        assess_btn.disabled = False
        _assess_ticker_stop.set()
        analysis_prog.stop()
        analysis_prog.control.visible = False

    # ------------------------------------------------------------------
    # Source-file selection (shared by the Preview + Analysis tabs)
    # ------------------------------------------------------------------

    def _file_by_name(name: str | None):
        for f in form.get_files():
            if f.path.name == name:
                return f
        files = form.get_files()
        return files[0] if files else None

    def _refresh_source_selectors() -> None:
        """Repopulate the per-tab file dropdowns from the current sources."""
        files = form.get_files()
        names = [f.path.name for f in files]
        has = bool(files)
        for dd in (preview_file_dd, analysis_file_dd):
            dd.options = [ft.dropdown.Option(n) for n in names]
            if dd.value not in names:
                dd.value = names[0] if names else None
            dd.visible = len(files) > 1
        # Empty vs content per tab.
        preview_empty.visible = not has
        preview_content.visible = has
        analysis_empty.visible = not has
        analysis_content.visible = has
        analysis_footer.visible = has  # "Avaliar" needs a selected file
        # If a source was added while already on the preview/analysis tab, load
        # it now so the tab isn't left blank until the user re-selects.
        if has and _tab[0] == "preview":
            _refresh_sheet_dd(_preview_file())
            page.run_task(_load_preview)
        elif has and _tab[0] == "analysis":
            _load_assessment_cache()

    # ------------------------------------------------------------------
    # Preview tab — first rows of a source file (types in the header)
    # ------------------------------------------------------------------

    def _preview_file():
        return _file_by_name(preview_file_dd.value)

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

    # ------------------------------------------------------------------
    # Analysis tab — IA data-quality narrative over a source file
    # ------------------------------------------------------------------

    def _analysis_file():
        return _file_by_name(analysis_file_dd.value)

    def _show_assessment(text: str) -> None:
        assess_md.value = text
        assess_md.visible = True
        assess_hint.visible = False

    def _load_assessment_cache() -> None:
        """Show a cached assessment for the selected file, or the CTA if none."""
        from src.core.data import assess as assess_mod

        file = _analysis_file()
        if file is None:
            return
        cached = None
        try:
            cached = assess_mod.load_cached_assessment(file.path)
        except Exception as exc:
            logging.debug("[d] assessment cache read failed: %s", exc)
        if cached:
            _show_assessment(cached)
            assess_status.value = "(do cache)"
        else:
            assess_md.visible = False
            assess_hint.visible = True
            assess_status.value = ""

    def _on_analysis_file_change(_e=None) -> None:
        _load_assessment_cache()
        page.update()

    # ------------------------------------------------------------------
    # Event subscription (UI thread)
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        match event.type:
            case "data_scanned":
                form.set_files(p.get("_files", []))
                _refresh_source_selectors()
            case "data_sql_ready":
                _record_query_time(p.get("model_name", ""), p.get("elapsed", 0.0))
                _end()
                _show_review(p.get("sql", ""), p.get("explanation", ""))
            case "data_result":
                _end()
                _result_columns[:] = p.get("columns", [])
                _result_rows[:] = p.get("rows", [])
                stat = f"{p.get('n_rows', 0)} linha(s) · {p.get('elapsed', 0):.3f}s"
                if p.get("truncated"):
                    stat += " · prévia limitada"
                result_status.value = stat
                _show_result()
            case "data_saved":
                _end()
                out = Path(p.get("output_path", ""))
                _last_saved[0] = out
                saved_row.visible = True
                saved_path_text.value = out.name
                if _action[0] == "converse" and out.exists():
                    nav[0]("ai", {"file": str(out)})
                    return
                _toast(f"Salvo em output/data/{out.name}", error=False)
            case "data_index_start":
                # Scoped update + early return: a full page.update() while the
                # spinner is animating would interrupt its on_animation_end chain
                # and stop the mill (same quirk as the Consulta ticker).
                preview_prog.status.value = "Indexando…"
                _scoped_update(preview_prog.status)
                return
            case "data_index_progress":
                cur, tot = p.get("current"), p.get("total")
                preview_prog.pbar.value = (cur / tot) if tot else None
                preview_prog.status.value = (
                    f"Indexando {cur}/{tot}…" if tot else "Indexando…"
                )
                _scoped_update(preview_prog.pbar, preview_prog.status)
                return
            case "data_indexed":
                _end_index()
                added = p.get("added", 0)
                _toast(
                    f"Índice atualizado: +{added} chunk(s)."
                    if added
                    else "Índice já estava atualizado.",
                    error=False,
                )
            case "data_assess_start":
                analysis_prog.status.value = "Avaliando com a IA…"
                _scoped_update(analysis_prog.status)
                return
            case "data_assessed":
                _end_assess()
                _show_assessment(p.get("text", ""))
                assess_status.value = ""
            case "log":
                # Route the worker's log line to the active tab's status (scoped,
                # to keep the spinner animation alive during indexing).
                msg = p.get("message", "")
                if msg and _action[0] == "index":
                    preview_prog.status.value = msg
                    _scoped_update(preview_prog.status)
                return
            case "task_error":
                message = p.get("message", "Erro.")
                if _action[0] == "index":
                    _end_index()
                    _toast(message)
                elif _action[0] == "assess":
                    _end_assess()
                    assess_hint.value = f"Não foi possível avaliar: {message}"
                    assess_hint.visible = True
                    assess_md.visible = False
                    _toast(message)
                else:
                    # A failed translate has no SQL; a failed query keeps the SQL
                    # it tried, so the IA refinement can reference both.
                    if _action[0] == "translate":
                        _record_query_time(_pending_model[0], time.monotonic() - _t0[0])
                    _end()
                    _last_error[0] = message
                    error_text.value = message
                    # Offer "fix with the IA" only with files to re-query.
                    refine_btn.visible = bool(form.get_files())
                    error_box.visible = True
                    _toast(message)
            case "task_done":
                pass  # terminal bookkeeping handled by the specific events above
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Controls — form
    # ------------------------------------------------------------------

    form = build_data_form(
        page, on_pick=_on_pick, on_preview=_on_preview, on_run=_on_run
    )

    # ------------------------------------------------------------------
    # Controls — shared progress/error (Consulta tab)
    # ------------------------------------------------------------------

    spinner_img, spinner_start, spinner_stop = spinner()
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
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
                [spinner_img, gen_status],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
        ],
        spacing=Space.xs,
        visible=False,
    )

    def _make_progress() -> SimpleNamespace:
        """A self-contained progress block (spinner + status + bar) for a tab.

        Mirrors the Consulta progress_row so the Preview/Análise tabs show their
        log/progress at the top in the same shape.
        """
        img, start, stop = spinner()
        status = ft.Text(
            "",
            size=Type.small.size,
            color=ft.Colors.PRIMARY,
            weight=ft.FontWeight.W_500,
        )
        pbar = ft.ProgressBar(
            value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
        )
        control = ft.Column(
            controls=[
                ft.Row(
                    [img, status],
                    spacing=Space.sm,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                pbar,
            ],
            spacing=Space.xs,
            visible=False,
        )
        return SimpleNamespace(
            control=control, start=start, stop=stop, status=status, pbar=pbar
        )

    preview_prog = _make_progress()
    analysis_prog = _make_progress()

    error_text = ft.Text(
        "",
        size=Type.body.size,
        color=ft.Colors.ON_SURFACE,
        no_wrap=False,
        expand=True,
    )
    refine_btn = action_button(
        "Corrigir com a IA",
        icon=ft.Icons.AUTO_FIX_HIGH_OUTLINED,
        on_click=_on_refine_with_ai,
        accent=ft.Colors.ERROR,
    )
    error_box = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.ERROR),
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.ERROR),
            top=ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.ERROR)),
            right=ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.ERROR)),
            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.4, ft.Colors.ERROR)),
        ),
        border_radius=Radius.md,
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.ERROR_OUTLINE,
                            size=IconSize.lg,
                            color=ft.Colors.ERROR,
                        ),
                        error_text,
                    ],
                    spacing=Space.sm,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Row([refine_btn], alignment=ft.MainAxisAlignment.END),
            ],
            spacing=Space.xs,
        ),
    )

    # ── review card ("entendi assim") ─────────────────────────────────────
    explanation_text = ft.Text(
        "",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        no_wrap=False,
    )
    sql_box = ft.TextField(
        multiline=True,
        min_lines=2,
        max_lines=8,
        text_size=Type.mono.size,
        text_style=ft.TextStyle(font_family=Type.FONT_MONO),
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    run_review_btn = secondary_button("Executar", icon=ft.Icons.PLAY_ARROW_OUTLINED)
    run_review_btn.on_click = lambda _e: _on_run()
    review_card = ft.Container(
        visible=False,
        bgcolor=Color.dark.surface_variant,
        border_radius=Radius.lg,
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.md, bottom=Space.md
        ),
        content=ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.LIGHTBULB_OUTLINE,
                            size=IconSize.lg,
                            color=ft.Colors.PRIMARY,
                        ),
                        ft.Text(
                            "Entendi assim",
                            size=Type.body_strong.size,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    spacing=Space.xs,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                explanation_text,
                sql_box,
                ft.Row([run_review_btn], alignment=ft.MainAxisAlignment.END),
            ],
            spacing=Space.sm,
        ),
    )

    # ── result preview table ──────────────────────────────────────────────
    result_status = ft.Text(
        "", size=Type.input.size, color=ft.Colors.ON_SURFACE_VARIANT
    )
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(""))], rows=[])
    table_scroll = ft.Column(
        controls=[ft.Row([table], scroll=ft.ScrollMode.AUTO)],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    page_label = ft.Text("—", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT)
    prev_btn = ft.IconButton(
        icon=ft.Icons.CHEVRON_LEFT,
        tooltip="Página anterior",
        on_click=_go_prev,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )
    next_btn = ft.IconButton(
        icon=ft.Icons.CHEVRON_RIGHT,
        tooltip="Próxima página",
        on_click=_go_next,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )
    pager = ft.Row(
        [result_status, ft.Container(expand=True), prev_btn, page_label, next_btn],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ── return shaping (rename + format + actions) ────────────────────────
    rename_col = ft.Column(controls=[], spacing=Space.xs, wrap=False)
    rename_wrap = ft.Row(controls=[rename_col], scroll=ft.ScrollMode.AUTO)
    name_field = ft.TextField(
        label="Nome do arquivo",
        value="consulta",
        dense=True,
        width=200,
        text_size=Type.input.size,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
    )
    fmt_dd = ft.Dropdown(
        label="Formato",
        value=cfg.get("last_data_format", "csv"),
        options=[ft.dropdown.Option(f) for f in convert.SUPPORTED_FORMATS],
        on_select=lambda e: settings.set("last_data_format", e.control.value or "csv"),
        width=140,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    save_btn = primary_button("Salvar", icon=ft.Icons.SAVE_OUTLINED, on_click=_on_save)
    converse_btn = secondary_button(
        "Conversar sobre", icon=ft.Icons.AUTO_AWESOME_OUTLINED
    )
    converse_btn.on_click = _on_converse
    recipe_btn = action_button(
        "Salvar como Receita",
        icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
        on_click=_on_save_recipe,
        accent=Color.log.muted,
    )
    # Fold saved data files into the RAG catalog (by choice, never automatic).
    # It indexes output/data/, so it is most useful after a Save.
    from src.gui.modules.ai.index_button import rag_index_button

    index_btn = rag_index_button(page)

    saved_path_text = ft.Text(
        "", size=Type.small.size, color=ft.Colors.ON_SURFACE, expand=True
    )
    saved_row = ft.Row(
        visible=False,
        controls=[
            ft.Icon(
                ft.Icons.CHECK_CIRCLE_OUTLINE, size=IconSize.md, color=Color.log.ok
            ),
            saved_path_text,
            ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                icon_size=IconSize.sm,
                tooltip="Abrir pasta",
                on_click=lambda _e: _last_saved[0] and _open_folder(_last_saved[0]),
                style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    shaping = ft.Column(
        controls=[
            hairline(),
            ft.Text(
                "Personalizar retorno",
                size=Type.label.size,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                "Renomeie colunas (opcional):",
                size=Type.small.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            rename_wrap,
            ft.Row(
                [name_field, fmt_dd],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
        ],
        spacing=Space.sm,
    )

    footer = ft.Container(
        visible=False,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border(top=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Column(
            controls=[
                saved_row,
                ft.Row(
                    [save_btn, converse_btn, recipe_btn, index_btn],
                    spacing=Space.sm,
                    wrap=True,
                ),
            ],
            spacing=Space.xs,
        ),
    )

    result_area = ft.Column(
        controls=[pager, table_scroll, shaping],
        visible=False,
        expand=True,
        spacing=Space.sm,
    )

    empty_state = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.TABLE_VIEW_OUTLINED,
                    size=IconSize.hero,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Consulte seus dados",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Selecione arquivos, descreva o que quer em português (ou "
                    "escreva SQL) e pré-visualize. As tabelas ficam 100% locais.",
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

    consulta_scroll = ft.Column(
        controls=[progress_row, error_box, review_card, result_area],
        expand=True,
        spacing=Space.sm,
        scroll=ft.ScrollMode.AUTO,
    )
    # The empty state is a centered overlay (a Stack at the view level, not inside
    # the scroll), so it centers vertically like the other tabs' empty states.
    consulta_body = ft.Stack([consulta_scroll, empty_state], expand=True)
    consulta_view = ft.Column(
        controls=[consulta_body, footer],
        expand=True,
        spacing=Space.sm,
    )

    # ------------------------------------------------------------------
    # Controls — Preview tab
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
    preview_empty = _tab_empty_state(
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
                    "Catalogue suas saídas em output/data/ no índice da IA "
                    "(incremental).",
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
            preview_prog.control,
            ft.Stack([preview_empty, preview_content], expand=True),
            preview_footer,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )

    # ------------------------------------------------------------------
    # Controls — Analysis tab
    # ------------------------------------------------------------------

    analysis_file_dd = ft.Dropdown(
        label="Arquivo",
        visible=False,
        on_select=_on_analysis_file_change,
        width=240,
        border_color=ft.Colors.OUTLINE,
        focused_border_color=ft.Colors.PRIMARY,
    )
    assess_btn = primary_button("Avaliar com a IA", icon=ft.Icons.AUTO_AWESOME_OUTLINED)
    assess_btn.on_click = _on_assess
    assess_status = ft.Text("", size=Type.small.size, color=ft.Colors.PRIMARY)
    assess_hint = ft.Text(
        "A IA examina o esquema, as estatísticas e uma amostra — nunca a tabela "
        "inteira — e aponta inconsistências de tipo, nomes e estrutura.",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
        no_wrap=False,
    )
    assess_md = ft.Markdown(
        "",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        visible=False,
    )
    analysis_content = ft.Column(
        controls=[
            ft.Row(
                [analysis_file_dd, assess_status],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            assess_hint,
            assess_md,
        ],
        expand=True,
        spacing=Space.sm,
        scroll=ft.ScrollMode.AUTO,
        visible=False,
    )
    analysis_empty = _tab_empty_state(
        ft.Icons.AUTO_AWESOME_OUTLINED,
        "Avalie a qualidade dos seus dados com a IA",
        "Selecione um arquivo e clique em “Avaliar com a IA”. A IA recebe apenas "
        "o esquema (nomes e tipos de coluna), o resumo estatístico do DuckDB "
        "(SUMMARIZE: nulos, valores distintos, mín/máx, média) e uma amostra de "
        "~10 linhas — nunca a tabela inteira. Em troca, aponta em Markdown: "
        "colunas com tipo suspeito (ex.: número guardado como texto), nomes mal "
        "escolhidos, possíveis duplicatas, valores fora de faixa ou nulos em "
        "excesso e problemas de estrutura (cabeçalho deslocado, esquema "
        "irregular). O parecer fica em cache e é reaproveitado na indexação. "
        "Com Gemini, só o esquema e as estatísticas saem da máquina.",
    )
    analysis_footer = ft.Container(
        visible=False,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border(top=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Row(
            [
                ft.Text(
                    "A IA vê só esquema + estatísticas + amostra; nunca as linhas.",
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                    no_wrap=False,
                ),
                assess_btn,
            ],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    analysis_view = ft.Column(
        controls=[
            analysis_prog.control,
            ft.Stack([analysis_empty, analysis_content], expand=True),
            analysis_footer,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )

    # ------------------------------------------------------------------
    # Tab bar (Consulta | Pré-visualização | Análise com IA)
    # ------------------------------------------------------------------

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_consulta = ft.TextButton(
        "Consulta", icon=ft.Icons.QUERY_STATS_OUTLINED, style=_tab_style(True)
    )
    tab_preview = ft.TextButton(
        "Pré-visualização", icon=ft.Icons.TABLE_ROWS_OUTLINED, style=_tab_style(False)
    )
    tab_analysis = ft.TextButton(
        "Análise com IA", icon=ft.Icons.AUTO_AWESOME_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str) -> None:
        _tab[0] = name
        consulta_view.visible = name == "consulta"
        preview_view.visible = name == "preview"
        analysis_view.visible = name == "analysis"
        tab_consulta.style = _tab_style(name == "consulta")
        tab_preview.style = _tab_style(name == "preview")
        tab_analysis.style = _tab_style(name == "analysis")
        # The return actions belong to the query result only.
        footer.visible = name == "consulta" and _has_result[0]
        settings.set("last_data_tab", name)
        if name == "preview" and form.get_files():
            _refresh_sheet_dd(_preview_file())
            page.run_task(_load_preview)
        elif name == "analysis" and form.get_files():
            _load_assessment_cache()
        page.update()

    tab_consulta.on_click = lambda _e: _show_tab("consulta")
    tab_preview.on_click = lambda _e: _show_tab("preview")
    tab_analysis.on_click = lambda _e: _show_tab("analysis")

    body_stack = ft.Stack([consulta_view, preview_view, analysis_view], expand=True)

    panel = ft.Column(
        controls=[
            ft.Row([tab_consulta, tab_preview, tab_analysis], spacing=Space.xs),
            hairline(),
            body_stack,
        ],
        expand=True,
        spacing=Space.sm,
    )

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
        # Bridge from the Library: a data file handed over becomes a source.
        file = payload.get("file") if payload else None
        if file:
            path = Path(file)
            if path.suffix.lower() in {
                ".csv",
                ".tsv",
                ".json",
                ".parquet",
                ".xlsx",
                ".pq",
            }:
                start_scan(bus, [path])
        _show_tab(settings.load().get("last_data_tab", "consulta"))

    return Module(
        id=_MODULE_ID,
        label="Dados",
        icon=ft.Icons.TABLE_CHART_OUTLINED,
        selected_icon=ft.Icons.TABLE_CHART,
        control=control,
        on_mount=_on_mount,
    )


def _tab_empty_state(icon: str, title: str, body: str) -> ft.Container:
    """Build a centered empty-state placeholder for a tab with no data yet."""
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(icon, size=IconSize.hero, color=ft.Colors.OUTLINE_VARIANT),
                ft.Text(
                    title,
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    body,
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
