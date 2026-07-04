"""RAG analytics ("Painel") sub-tab of the Observatório hub's Índice/RAG tab.

Migrated here from the AI hub (Plano 2), which now only shows Conversa —
Índice/Painel are RAG-index inspection, not chat, and Observatório is where
the rest of the app's ML-transparency surface already lives. Answers one
actionable question from data the hub already keeps: which documents
dominate the index (top by chunks). Numbers come from the pure
``core/rag/analytics`` core; the bar chart reuses the Plano 1 path via
``_charts`` and is gated on the extras (graceful degradation).

Per-model response timing used to live here too (Tier "model timing"), but it
duplicated the same data shown in the Observatório hub's Status tab — and
Observatório is the one that also covers VLM/embed, not just this RAG-scoped
LLM number. It was removed from this tab; see
``gui/modules/observatory/timing_section.py``.

``apply`` is invoked off the UI thread (from ``rag_tab``'s daemon worker, like
``index_tab.apply``), so the matplotlib render runs synchronously there —
never on the UI thread — and the controls are refreshed via a scoped
``control.update()``. The chart only renders when this tab is the visible one,
so a hidden panel never pays for a render.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.rag.analytics import index_health, top_docs_result
from src.core.rag.stats import IndexStats
from src.gui.modules import _charts
from src.gui.theme.components import hairline, help_icon_for, section_label
from src.gui.theme.tokens import IconSize, Space, Type

_TOP_N = 8


@dataclass
class AnalyticsTab:
    """Handles for the AI analytics tab."""

    control: ft.Control
    apply: Callable[[IndexStats], None]  # called off the UI thread


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
    _help = help_icon_for("observatory.rag_panel", page)
    if _help is not None:
        header_controls.append(_help)

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
            section_label("Documentos que dominam o índice"),
            docs_header,
            docs_body,
            docs_chart,
            chart_note,
            hairline(),
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    def _doc_row(d) -> ft.Control:
        return _data_row(
            _cell(Path(d.source_path).name, expand=True),
            _cell(str(d.n_chunks), width=72, right=True),
        )

    def _render_chart(health) -> None:
        """Render the bar chart synchronously (called off the UI thread)."""
        if not control.visible:  # hidden tab never pays for a render
            return
        if not _charts.extras_available():
            docs_chart.visible = False
            chart_note.value = _charts.setup_hint()
            chart_note.visible = True
            return
        chart_note.visible = False
        from src.core.data.charts import ChartSpec

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

    def apply(stats: IndexStats) -> None:
        """Refresh the table + chart from fresh index stats."""
        health = index_health(stats, top_n=_TOP_N)
        docs_body.controls = [_doc_row(d) for d in health.top_docs] or [
            _empty("Índice vazio — clique em Reindexar.")
        ]
        _render_chart(health)
        _safe_update(control)

    return AnalyticsTab(control=control, apply=apply)
