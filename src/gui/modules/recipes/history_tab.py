"""History tab for the Recipes hub (Plano 2): reliability and speed per recipe.

A second panel mode beside the live "Execução" view. Reads the append-only run
history (``core/recipes/history``) the worker/CLI record at each terminal event
and answers: which recipes are reliable, which are slow, and what breaks most.
Numbers are pure stdlib; the bar chart reuses the Plano 1 path via ``_charts``
(off the UI thread, gated on the extras). Building it here keeps ``view.py`` from
inflating (divide-se ao tocar).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.core.recipes import history
from src.gui.modules import _charts
from src.gui.theme.components import section_label
from src.gui.theme.tokens import IconSize, Space, Type


@dataclass
class HistoryTab:
    """Handles for the Recipes history tab."""

    control: ft.Control
    apply: Callable[[], None]  # reload + refresh; called on the UI thread


def _cell(
    text: str, *, width=None, expand=False, right=False, muted=False
) -> ft.Control:
    return ft.Container(
        width=width,
        expand=expand,
        content=ft.Text(
            text,
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE_VARIANT if muted else ft.Colors.ON_SURFACE,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            text_align=ft.TextAlign.RIGHT if right else ft.TextAlign.LEFT,
        ),
    )


def _hcell(text: str, *, width=None, expand=False, right=False) -> ft.Control:
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


def _row(cells: list[ft.Control], *, header: bool = False) -> ft.Container:
    return ft.Container(
        padding=ft.Padding(
            left=Space.xs,
            right=Space.xs,
            top=Space.xs if header else Space.xxs,
            bottom=Space.xs if header else Space.xxs,
        ),
        border=ft.Border(
            bottom=ft.BorderSide(1.5 if header else 1, ft.Colors.OUTLINE_VARIANT)
        ),
        content=ft.Row(
            cells, spacing=Space.sm, vertical_alignment=ft.CrossAxisAlignment.CENTER
        ),
    )


def build_history_tab(page: ft.Page) -> HistoryTab:
    """Build the history tab and return its handles."""
    summary = ft.Text(
        "", size=Type.input.size, color=ft.Colors.ON_SURFACE_VARIANT, no_wrap=False
    )
    table_body = ft.Column(controls=[], spacing=0)
    chart_status = ft.Text(
        "",
        size=Type.caption.size,
        italic=True,
        color=ft.Colors.ON_SURFACE_VARIANT,
        visible=False,
    )
    chart_img = ft.Image(
        _charts.BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        height=360,
        visible=False,
        gapless_playback=True,
    )

    table_header = _row(
        [
            _hcell("Receita", expand=True),
            _hcell("Execs", width=56, right=True),
            _hcell("Sucesso", width=68, right=True),
            _hcell("Média (s)", width=72, right=True),
            _hcell("Mais falha", width=132),
        ],
        header=True,
    )

    # Wrapped in a Row (which fills the panel width, unlike a bare Column that
    # shrinks to its content) so MainAxisAlignment.CENTER truly centers it.
    empty_state = ft.Container(
        visible=False,
        padding=ft.Padding(left=0, right=0, top=Space.xxxl, bottom=Space.xxxl),
        content=ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.HISTORY,
                            size=IconSize.hero,
                            color=ft.Colors.OUTLINE_VARIANT,
                        ),
                        ft.Text(
                            "Sem histórico ainda",
                            size=Type.heading.size,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Rode uma receita — cada execução é registrada aqui.",
                            size=Type.input.size,
                            italic=True,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=Space.sm,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        ),
    )

    table_card = ft.Column(
        controls=[
            section_label("Confiabilidade e velocidade por receita"),
            table_header,
            table_body,
            chart_status,
            chart_img,
        ],
        spacing=Space.sm,
        visible=False,
    )

    control = ft.Column(
        controls=[summary, table_card, empty_state],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def _agg_row(a) -> ft.Container:
        return _row(
            [
                _cell(a.recipe_name, expand=True),
                _cell(str(a.n_runs), width=56, right=True, muted=True),
                _cell(f"{a.success_rate * 100:.0f}%", width=68, right=True),
                _cell(f"{a.avg_duration:.1f}", width=72, right=True, muted=True),
                _cell(a.most_failing_op or "—", width=132, muted=True),
            ]
        )

    def _render_chart(aggs) -> None:
        chart_img.visible = False
        if not _charts.extras_available():
            chart_status.value = _charts.setup_hint()
            chart_status.visible = True
            return
        chart_status.value = "Gerando gráfico…"
        chart_status.visible = True
        from src.core.data.charts import ChartSpec

        result = history.aggregate_result(aggs)
        spec = ChartSpec(
            kind="bar",
            x="receita",
            y="duração_média_s",
            title="Duração média por receita (s)",
        )

        async def _go() -> None:
            try:
                png = await asyncio.to_thread(_charts.render_result_png, result, spec)
                chart_img.src = png
                chart_img.visible = True
                chart_status.visible = False
            except Exception as exc:
                chart_status.value = f"Não foi possível gerar o gráfico: {exc}"
                chart_status.visible = True
            with contextlib.suppress(Exception):
                page.update()

        page.run_task(_go)

    def apply() -> None:
        """Reload the history from disk and refresh the table + chart."""
        aggs = history.aggregate(history.load_runs())
        if not aggs:
            empty_state.visible = True
            table_card.visible = False
            summary.value = ""
            return

        empty_state.visible = False
        table_card.visible = True
        total_runs = sum(a.n_runs for a in aggs)
        total_ok = sum(a.n_ok for a in aggs)
        rate = (total_ok / total_runs * 100) if total_runs else 0
        plural = "execução" if total_runs == 1 else "execuções"
        summary.value = f"{total_runs} {plural} · {rate:.0f}% de sucesso"
        table_body.controls = [_agg_row(a) for a in aggs]
        _render_chart(aggs)

    return HistoryTab(control=control, apply=apply)
