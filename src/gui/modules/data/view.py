"""Data module — query-first structured-data tool over DuckDB.

A NavigationRail tool (the 6th), but self-contained like the AI/Recipes hubs: it
subscribes to its own PipelineEvents (module_id="data") and updates the panel on
the UI thread. The panel holds the "entendi assim" review card (with an editable
SQL box), a paginated preview of the result, and a return-shaping block (rename
columns, pick a format, Save / Conversar sobre / Salvar como Receita).

Privacy: with Gemini selected, only the column names reach the cloud (NL→SQL);
the table contents stay 100% local in DuckDB.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.core.data import convert
from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai import timing
from src.gui.modules.base import Module
from src.gui.modules.data.form_view import build_data_form
from src.gui.modules.data.worker import (
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
_PAGE_SIZE = 50  # rows shown per preview page (in-memory, like the Library)


def build_data_module(
    page: ft.Page,
    bus: EventBus,
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Data module — query files, preview, shape and save the result.

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

    def _toast(message: str, *, error: bool = True) -> None:
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY,
        )
        page.snack_bar.open = True
        page.update()

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
            try:
                page.update()
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
    # Panel state helpers
    # ------------------------------------------------------------------

    def _begin() -> None:
        pipeline_running[0] = True
        form.set_running(True)
        _pending_model[0] = form.get_model()
        error_box.visible = False  # clear any previous error while we work
        empty_state.visible = False  # gone for good after the first action
        progress_row.visible = True
        progress_bar.value = None
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
        review_card.visible = True
        explanation_text.value = explanation or "Revise e execute a consulta abaixo."
        explanation_text.visible = bool(explanation) or form.get_mode() == "sql"
        sql_box.value = sql
        page.update()

    # ------------------------------------------------------------------
    # Preview table (paginated, in-memory)
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
        footer.visible = True  # actions become available with a valid result
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
    # Event subscription (UI thread)
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        match event.type:
            case "data_scanned":
                form.set_files(p.get("_files", []))
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
            case "task_error":
                # A failed translate has no SQL; a failed query keeps the SQL it
                # tried, so the IA refinement can reference both.
                if _action[0] == "translate":
                    _record_query_time(_pending_model[0], time.monotonic() - _t0[0])
                _end()
                message = p.get("message", "Erro.")
                _last_error[0] = message
                error_text.value = message
                # Offer "fix with the IA" only when there are files to re-query.
                refine_btn.visible = bool(form.get_files())
                error_box.visible = True
                _toast(message)
            case "task_done":
                pass  # terminal bookkeeping handled by the specific events above
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    form = build_data_form(
        page, on_pick=_on_pick, on_preview=_on_preview, on_run=_on_run
    )

    spinner_img, spinner_start, spinner_stop = spinner()
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    # Live status line ("Traduzindo a pergunta… 0:14 · ~12s (típico do …)").
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

    # ── highlighted error block (with an "ask the IA to fix it" action) ────
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

    # ── preview table ─────────────────────────────────────────────────────
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

    # Fixed footer: the return actions live here, pinned to the bottom of the
    # panel (outside the scroll). Hidden until there is a valid result.
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
                    [save_btn, converse_btn, recipe_btn],
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

    scroll_content = ft.Column(
        controls=[
            progress_row,
            error_box,
            review_card,
            ft.Stack([empty_state, result_area], expand=True),
        ],
        expand=True,
        spacing=Space.sm,
        scroll=ft.ScrollMode.AUTO,
    )
    panel = ft.Column(
        controls=[scroll_content, footer],
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

    return Module(
        id=_MODULE_ID,
        label="Dados",
        icon=ft.Icons.TABLE_CHART_OUTLINED,
        selected_icon=ft.Icons.TABLE_CHART,
        control=control,
        on_mount=_on_mount,
    )
