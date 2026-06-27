"""Analytics tab for the AI hub (Plano 2): index health + per-model timing.

A third tab beside Conversa | Índice. Answers two actionable questions from data
the hub already keeps: which documents dominate the index (top by chunks) and
which model answers fastest on this machine (mean/median/p90). Numbers come from
the pure ``core/rag/analytics`` core; the bar charts reuse the Plano 1 path via
``_charts`` and are gated on the extras (graceful degradation).

``apply`` is invoked off the UI thread (from ``view._refresh_status``'s daemon
worker, like ``index_tab.apply``), so the matplotlib render runs synchronously
there — never on the UI thread — and the controls are refreshed via a scoped
``control.update()``. The charts only render when this tab is the visible one, so
a hidden panel never pays for a render.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.rag.analytics import (
    index_health,
    model_timings,
    model_timings_result,
    top_docs_result,
)
from src.core.rag.stats import IndexStats
from src.gui.modules import _charts
from src.gui.theme.components import hairline, help_icon_for, section_label
from src.gui.theme.tokens import IconSize, Space, Type

_TOP_N = 8


@dataclass
class AnalyticsTab:
    """Handles for the AI analytics tab."""

    control: ft.Control
    apply: Callable[[IndexStats, dict], None]  # called off the UI thread


def _safe_update(*controls: ft.Control) -> None:
    for c in controls:
        try:
            c.update()
        except Exception:
            pass


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


def _header(*cells: ft.Control) -> ft.Container:
    return ft.Container(
        padding=ft.Padding(
            left=Space.xs, right=Space.xs, top=Space.xs, bottom=Space.xs
        ),
        border=ft.Border(bottom=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Row(
            list(cells),
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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


def _data_row(*cells: ft.Control) -> ft.Container:
    return ft.Container(
        padding=ft.Padding(
            left=Space.xs, right=Space.xs, top=Space.xxs, bottom=Space.xxs
        ),
        border=ft.Border(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
        content=ft.Row(
            list(cells),
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def _empty(text: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding(left=0, right=0, top=Space.sm, bottom=Space.sm),
        content=ft.Text(
            text, size=Type.input.size, italic=True, color=ft.Colors.ON_SURFACE_VARIANT
        ),
    )


def build_analytics_tab(page: ft.Page) -> AnalyticsTab:
    """Build the analytics tab and return its handles."""
    timing_body = ft.Column(controls=[], spacing=0)
    timing_chart = ft.Image(
        _charts.BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        height=320,
        visible=False,
        gapless_playback=True,
    )
    docs_body = ft.Column(controls=[], spacing=0)
    docs_chart = ft.Image(
        _charts.BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        height=320,
        visible=False,
        gapless_playback=True,
    )
    chart_note = ft.Text(
        "",
        size=Type.caption.size,
        italic=True,
        color=ft.Colors.ON_SURFACE_VARIANT,
        visible=False,
    )

    header_controls: list[ft.Control] = [
        ft.Icon(ft.Icons.INSIGHTS_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY),
        ft.Text(
            "Painel da IA",
            size=Type.heading.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
    ]
    _help = help_icon_for("ai", page)
    if _help is not None:
        header_controls.append(_help)

    timing_header = _header(
        _hcell("Modelo", expand=True),
        _hcell("Respostas", width=72, right=True),
        _hcell("Média (s)", width=72, right=True),
        _hcell("Mediana", width=64, right=True),
        _hcell("p90", width=56, right=True),
    )
    docs_header = _header(
        _hcell("Documento", expand=True),
        _hcell("Chunks", width=72, right=True),
    )

    control = ft.Column(
        controls=[
            ft.Row(
                header_controls,
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            section_label("Tempo de resposta por modelo"),
            timing_header,
            timing_body,
            timing_chart,
            hairline(),
            section_label("Documentos que dominam o índice"),
            docs_header,
            docs_body,
            docs_chart,
            chart_note,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def _timing_row(t) -> ft.Control:
        return _data_row(
            _cell(t.model, expand=True),
            _cell(str(t.count), width=72, right=True, muted=True),
            _cell(f"{t.mean:.1f}", width=72, right=True),
            _cell(f"{t.median:.1f}", width=64, right=True, muted=True),
            _cell(f"{t.p90:.1f}", width=56, right=True, muted=True),
        )

    def _doc_row(d) -> ft.Control:
        return _data_row(
            _cell(Path(d.source_path).name, expand=True),
            _cell(str(d.n_chunks), width=72, right=True),
        )

    def _render_charts(timings, health) -> None:
        """Render both bar charts synchronously (called off the UI thread)."""
        if not control.visible:  # hidden tab never pays for a render
            return
        if not _charts.extras_available():
            timing_chart.visible = False
            docs_chart.visible = False
            chart_note.value = _charts.setup_hint()
            chart_note.visible = True
            return
        chart_note.visible = False
        from src.core.data.charts import ChartSpec

        timing_chart.visible = False
        if timings:
            try:
                timing_chart.src = _charts.render_result_png(
                    model_timings_result(timings),
                    ChartSpec(
                        kind="bar",
                        x="modelo",
                        y="média_s",
                        title="Tempo médio por modelo (s)",
                    ),
                )
                timing_chart.visible = True
            except Exception:
                timing_chart.visible = False

        docs_chart.visible = False
        if health.top_docs:
            try:
                docs_chart.src = _charts.render_result_png(
                    top_docs_result(health),
                    ChartSpec(
                        kind="bar",
                        x="documento",
                        y="chunks",
                        title="Documentos por nº de chunks",
                    ),
                )
                docs_chart.visible = True
            except Exception:
                docs_chart.visible = False

    def apply(stats: IndexStats, times_map: dict) -> None:
        """Refresh tables + charts from fresh stats and the answer-time history."""
        timings = model_timings(times_map)
        health = index_health(stats, top_n=_TOP_N)
        timing_body.controls = [_timing_row(t) for t in timings] or [
            _empty("Sem histórico de respostas ainda — faça algumas perguntas.")
        ]
        docs_body.controls = [_doc_row(d) for d in health.top_docs] or [
            _empty("Índice vazio — clique em Reindexar.")
        ]
        _render_charts(timings, health)
        _safe_update(control)

    return AnalyticsTab(control=control, apply=apply)
