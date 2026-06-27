"""Library analytics panel — the archive dashboard (Plano 2).

A third view mode beside grid/list. Numbers and tables come from the pure
``core/library/analytics`` core (stdlib only, no extra needed); the single chart
reuses the Plano 1 path (``frames`` → pandas → ``charts.render_png``) rendered
off the UI thread and gated on the ``[analysis]``/``[data-plot]`` extras — when
they are absent the panel still shows every number and just hides the chart
(graceful degradation, §7 of the plan). No DataFrame ever crosses into the GUI.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Callable

import flet as ft

from src.core.library import analytics
from src.gui.modules import _charts
from src.gui.theme.components import hairline, section_label
from src.gui.theme.tokens import Color, Radius, Space, Type

if TYPE_CHECKING:
    from src.core.library.types import LibraryItem


def _fmt_size(num_bytes: int) -> str:
    """Human-readable size (B/KB/MB/GB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _fmt_date(ts: float | None) -> str:
    """Format an mtime epoch as 'DD/MM/YYYY' (or '—' when absent)."""
    return time.strftime("%d/%m/%Y", time.localtime(ts)) if ts else "—"


def _metric(label: str) -> tuple[ft.Container, ft.Text]:
    """A headline metric card; returns (card, value_text) so apply() can update it."""
    value = ft.Text(
        "—",
        size=Type.title.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.ON_SURFACE,
    )
    card = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    label, size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT
                ),
                value,
            ],
            spacing=Space.xxs,
        ),
        padding=Space.md,
        bgcolor=Color.dark.surface_variant,
        border_radius=Radius.lg,
        expand=True,
    )
    return card, value


def build_analytics_panel(
    page: ft.Page,
) -> tuple[ft.Control, Callable[[list[LibraryItem]], None]]:
    """Build the dashboard control plus an ``apply(items)`` refresher.

    ``apply`` recomputes every number synchronously (cheap, pure) and, when the
    chart extras are present, kicks off an off-thread render that swaps the PNG
    into an ``ft.Image`` — keeping matplotlib off the UI thread.
    """
    total_card, total_val = _metric("Arquivos")
    size_card, size_val = _metric("Tamanho total")
    span_card, span_val = _metric("Período")

    by_kind_col = ft.Column(spacing=Space.xs)
    largest_col = ft.Column(spacing=Space.xs)

    chart_status = ft.Text(
        "", size=Type.caption.size, color=ft.Colors.ON_SURFACE_VARIANT, italic=True
    )
    chart_img = ft.Image(
        _charts.BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        height=400,
        visible=False,
        gapless_playback=True,
    )

    panel = ft.Column(
        controls=[
            section_label("Resumo do acervo"),
            ft.Row([total_card, size_card, span_card], spacing=Space.md),
            hairline(),
            ft.Row(
                [
                    ft.Column(
                        [section_label("Por tipo"), by_kind_col],
                        expand=True,
                        spacing=Space.xs,
                    ),
                    ft.Column(
                        [section_label("Maiores arquivos"), largest_col],
                        expand=True,
                        spacing=Space.xs,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=Space.xl,
            ),
            hairline(),
            section_label("Tamanho por tipo"),
            chart_status,
            chart_img,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
        visible=False,
    )

    def _kind_row(kind: str, count: int, size_bytes: int) -> ft.Row:
        return ft.Row(
            [
                ft.Text(
                    kind, size=Type.body.size, color=ft.Colors.ON_SURFACE, expand=True
                ),
                ft.Text(
                    f"{count} · {_fmt_size(size_bytes)}",
                    size=Type.caption.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ]
        )

    def _largest_row(item: LibraryItem) -> ft.Row:
        return ft.Row(
            [
                ft.Text(
                    _fmt_size(item.size_bytes),
                    size=Type.caption.size,
                    color=ft.Colors.PRIMARY,
                    width=80,
                ),
                ft.Text(
                    item.path.name,
                    size=Type.caption.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    no_wrap=True,
                    expand=True,
                    tooltip=item.path.name,
                ),
            ]
        )

    def _maybe_render_chart(items: list[LibraryItem]) -> None:
        """Render the size-by-kind bar off-thread, gated on the chart extras."""
        chart_img.visible = False
        if not items:
            chart_status.value = "Sem dados para o gráfico."
            chart_status.visible = True
            return
        if not _charts.extras_available():
            chart_status.value = _charts.setup_hint()
            chart_status.visible = True
            return

        chart_status.value = "Gerando gráfico…"
        chart_status.visible = True
        from src.core.data.charts import ChartSpec

        result = analytics.size_by_kind(items)
        spec = ChartSpec(
            kind="bar", x="tipo", y="bytes", title="Tamanho por tipo (bytes)"
        )

        async def _render() -> None:
            try:
                png = await asyncio.to_thread(_charts.render_result_png, result, spec)
                chart_img.src = png  # Flet 0.85 accepts bytes directly
                chart_img.visible = True
                chart_status.visible = False
            except Exception as exc:  # render failure → message, never crash
                chart_status.value = f"Não foi possível gerar o gráfico: {exc}"
                chart_status.visible = True
            with contextlib.suppress(Exception):
                page.update()

        page.run_task(_render)

    def apply(items: list[LibraryItem]) -> None:
        """Recompute every number from *items* and refresh the chart."""
        s = analytics.summary(items)
        total_val.value = str(s.total_count)
        size_val.value = _fmt_size(s.total_bytes)
        span_val.value = (
            f"{_fmt_date(s.oldest)} → {_fmt_date(s.newest)}" if s.total_count else "—"
        )
        by_kind_col.controls = [
            _kind_row(kind, count, s.bytes_by_kind.get(kind, 0))
            for kind, count in s.count_by_kind.items()
        ]
        largest_col.controls = [_largest_row(it) for it in analytics.largest(items, 8)]
        _maybe_render_chart(items)

    return panel, apply
