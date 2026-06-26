"""Análise com IA tab — a data-quality narrative from the IA over a source file.

The IA only ever sees the schema, the DuckDB SUMMARIZE statistics and a small
sample — never the table rows. The assessment is cached and reused; a live timer
shows at the top while it runs.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.gui.modules.ai import timing
from src.gui.modules.data._state import (
    DataViewContext,
    file_by_name,
    make_progress,
    tab_empty_state,
)
from src.gui.modules.data.worker import start_assess
from src.gui.theme.components import primary_button
from src.gui.theme.tokens import Space, Type


@dataclass
class AnalysisTab:
    """Handles the central router/view needs from the Análise com IA tab."""

    view: ft.Control
    on_sources_changed: Callable[[], None]  # data_scanned event
    on_show: Callable[[], None]  # called when the tab becomes active
    on_assess_start: Callable[[dict], None]  # data_assess_start event
    on_assessed: Callable[[dict], None]  # data_assessed event
    on_error: Callable[[dict], None]  # task_error while assessing


def build_analysis_tab(ctx: DataViewContext) -> AnalysisTab:
    """Build the Análise com IA tab and return its handles."""
    page = ctx.page
    form = ctx.form
    prog = make_progress()

    _assess_t0: list[float] = [0.0]
    _assess_ticker_stop = threading.Event()

    # ------------------------------------------------------------------
    # Source-file selection + cached assessment
    # ------------------------------------------------------------------

    def _analysis_file():
        return file_by_name(form.get_files(), analysis_file_dd.value)

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

    def on_sources_changed() -> None:
        """Repopulate the file dropdown and toggle empty/content for this tab."""
        files = form.get_files()
        names = [f.path.name for f in files]
        has = bool(files)
        analysis_file_dd.options = [ft.dropdown.Option(n) for n in names]
        if analysis_file_dd.value not in names:
            analysis_file_dd.value = names[0] if names else None
        analysis_file_dd.visible = len(files) > 1
        analysis_empty.visible = not has
        analysis_content.visible = has
        analysis_footer.visible = has  # "Avaliar" needs a selected file
        if has and ctx.tab[0] == "analysis":
            _load_assessment_cache()

    def on_show() -> None:
        if form.get_files():
            _load_assessment_cache()

    # ------------------------------------------------------------------
    # Assessment (footer button + live timer/log at the top)
    # ------------------------------------------------------------------

    async def _assess_tick() -> None:
        while not _assess_ticker_stop.is_set():
            elapsed = time.monotonic() - _assess_t0[0]
            prog.status.value = f"Avaliando com a IA… {timing.format_clock(elapsed)}"
            try:
                prog.status.update()
            except Exception:
                break
            await asyncio.sleep(1.0)

    def _on_assess(_e=None) -> None:
        if ctx.pipeline_running[0]:
            return
        file = _analysis_file()
        if file is None:
            ctx.toast("Selecione um arquivo para avaliar.")
            return
        ctx.action[0] = "assess"
        ctx.pipeline_running[0] = True
        form.set_running(True)
        assess_btn.disabled = True
        assess_hint.visible = False
        assess_md.visible = False
        assess_status.value = ""
        prog.control.visible = True
        prog.pbar.value = None
        prog.status.value = "Avaliando com a IA… 0:00"
        # Flush visibility BEFORE start() so the spinner animates (see query_tab).
        page.update()
        prog.start()
        _assess_t0[0] = time.monotonic()
        _assess_ticker_stop.clear()
        page.run_task(_assess_tick)
        start_assess(ctx.bus, file, model_name=form.get_model())

    def _end_assess() -> None:
        ctx.pipeline_running[0] = False
        form.set_running(False)
        assess_btn.disabled = False
        _assess_ticker_stop.set()
        prog.stop()
        prog.control.visible = False

    def on_assess_start(p: dict) -> None:
        prog.status.value = "Avaliando com a IA…"
        ctx.scoped_update(prog.status)

    def on_assessed(p: dict) -> None:
        _end_assess()
        _show_assessment(p.get("text", ""))
        assess_status.value = ""

    def on_error(p: dict) -> None:
        _end_assess()
        assess_hint.value = f"Não foi possível avaliar: {p.get('message', 'Erro.')}"
        assess_hint.visible = True
        assess_md.visible = False
        ctx.toast(p.get("message", "Erro."))

    # ------------------------------------------------------------------
    # Controls
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
    analysis_empty = tab_empty_state(
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
            prog.control,
            ft.Stack([analysis_empty, analysis_content], expand=True),
            analysis_footer,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )

    return AnalysisTab(
        view=analysis_view,
        on_sources_changed=on_sources_changed,
        on_show=on_show,
        on_assess_start=on_assess_start,
        on_assessed=on_assessed,
        on_error=on_error,
    )
