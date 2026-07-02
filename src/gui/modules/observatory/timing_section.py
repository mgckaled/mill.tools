"""Reusable per-domain timing table (+ optional bar chart) for the Observatório's
Status tab. Extracted so LLM/VLM/embed each render the exact same table+chart
shape without tripling the code — this rendering used to live only in the AI
hub's Painel tab (LLM-only); it moved here as the single home for every domain.

``apply()`` only mutates the section's own controls — it never calls
``.update()`` itself. The caller (``status_tab.py``) refreshes the whole tab
with one ``control.update()`` after all sections are populated, same pattern
as ``analytics_tab.py``'s ``_safe_update``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.core.rag.analytics import ModelTiming, model_timings_result
from src.gui.modules import _charts
from src.gui.theme.components import section_label
from src.gui.theme.tokens import IconSize, Space, Type
from src.llm_factory import is_cloud_model


@dataclass
class TimingSection:
    """Handles for one domain's timing table (+ optional chart)."""

    control: ft.Control
    apply: Callable[[tuple[ModelTiming, ...]], None]


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
        padding=ft.Padding(left=0, right=0, top=Space.xs, bottom=Space.xs),
        content=ft.Text(
            text,
            size=Type.caption.size,
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    )


def _model_cell(model: str) -> ft.Control:
    """The model-name cell, prefixed with a cloud icon for gemini-*/glm-* models."""
    controls: list[ft.Control] = []
    if is_cloud_model(model):
        controls.append(
            ft.Icon(ft.Icons.CLOUD_OUTLINED, size=IconSize.sm, color=ft.Colors.PRIMARY)
        )
    controls.append(
        ft.Text(
            model,
            size=Type.small.size,
            color=ft.Colors.ON_SURFACE,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
    )
    return ft.Container(
        expand=True, content=ft.Row(controls, spacing=Space.xxs, tight=True)
    )


def _timing_row(t: ModelTiming) -> ft.Control:
    return _data_row(
        _model_cell(t.model),
        _cell(str(t.count), width=72, right=True, muted=True),
        _cell(f"{t.mean:.1f}", width=72, right=True),
        _cell(f"{t.median:.1f}", width=64, right=True, muted=True),
        _cell(f"{t.p90:.1f}", width=56, right=True, muted=True),
    )


def build_timing_section(title: str, *, show_chart: bool) -> TimingSection:
    """Build one domain's section: title, table, and (when ``show_chart``) a
    bar chart. ``show_chart=False`` fits a single-model domain (embed) where a
    comparison bar would be meaningless."""
    body = ft.Column(controls=[], spacing=0)
    header = _header(
        _hcell("Modelo", expand=True),
        _hcell("Respostas", width=72, right=True),
        _hcell("Média (s)", width=72, right=True),
        _hcell("Mediana", width=64, right=True),
        _hcell("p90", width=56, right=True),
    )

    chart: ft.Image | None = None
    chart_note: ft.Text | None = None
    controls: list[ft.Control] = [section_label(title), header, body]
    if show_chart:
        chart = ft.Image(
            _charts.BLANK_PNG,
            fit=ft.BoxFit.CONTAIN,
            height=260,
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
        controls.extend([chart, chart_note])

    control = ft.Column(controls=controls, spacing=Space.xs)

    def apply(timings: tuple[ModelTiming, ...]) -> None:
        body.controls = [_timing_row(t) for t in timings] or [
            _empty("Nenhuma resposta registrada ainda.")
        ]
        if chart is None:
            return

        chart.visible = False
        if not _charts.extras_available():
            if chart_note is not None:
                chart_note.value = _charts.setup_hint()
                chart_note.visible = bool(timings)
            return

        if chart_note is not None:
            chart_note.visible = False
        if not timings:
            return

        from src.core.data.charts import ChartSpec

        try:
            chart.src = _charts.render_result_png(
                model_timings_result(timings),
                ChartSpec(
                    kind="bar",
                    x="modelo",
                    y="média_s",
                    title=f"{title} — tempo médio (s)",
                ),
            )
            chart.visible = True
        except Exception:
            chart.visible = False

    return TimingSection(control=control, apply=apply)
