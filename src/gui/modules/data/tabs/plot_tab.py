"""Gráfico tab — render the current query result as a chart (PNG).

Consumes the Plano 0 + charts foundation: it re-runs the last query over the full
result (off the UI thread) and shows the PNG in an ``ft.Image``. The chart kind
and x/y columns are pre-filled by ``charts.suggest_spec`` from the result schema
and can be overridden. Rendering happens in the worker; the GUI only swaps the
image ``src``. A missing extra ([analysis]/[data-plot]) surfaces as a clear error.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.data import charts
from src.gui.modules.data._state import (
    DataViewContext,
    make_progress,
    tab_empty_state,
)
from src.gui.modules.data.worker import start_plot
from src.gui.theme.components import Cursor, primary_button, secondary_button
from src.gui.theme.tokens import Color, IconSize, Radius, Space, Type

# 1x1 transparent PNG: ft.Image needs a src at construction; we swap it for the
# rendered chart on data_plot_done (same placeholder pattern as audio_player).
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass
class PlotTab:
    """Handles the central router/view needs from the Gráfico tab."""

    view: ft.Control
    on_show: Callable[[], None]  # tab becomes active → pre-fill from the result
    on_result_changed: Callable[[], None]  # a new data_result arrived
    on_plot_start: Callable[[dict], None]  # data_plot_start event
    on_plot_done: Callable[[dict], None]  # data_plot_done event
    on_error: Callable[[dict], None]  # task_error while plotting


def _palette() -> charts.ChartPalette:
    """Build the chart palette from the dark theme tokens (core stays GUI-free)."""
    return charts.ChartPalette(
        bg=Color.dark.surface,
        fg=Color.dark.text,
        accent=Color.dark.primary,
        grid=Color.dark.outline_variant,
        muted=Color.dark.text_secondary,
    )


def _unique_png(directory: Path, stem: str) -> Path:
    """Return a non-clobbering ``<stem>.png`` path under *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.png"
    i = 2
    while path.exists():
        path = directory / f"{stem}_{i}.png"
        i += 1
    return path


def build_plot_tab(ctx: DataViewContext) -> PlotTab:
    """Build the Gráfico tab and return its handles."""
    page = ctx.page
    prog = make_progress()

    _last_png: list[bytes | None] = [None]
    _saved_path: list[Path | None] = [None]

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _dd(label: str, width: int) -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            width=width,
            border_color=ft.Colors.OUTLINE,
            focused_border_color=ft.Colors.PRIMARY,
        )

    kind_dd = _dd("Tipo", 140)
    kind_dd.options = [ft.dropdown.Option(k) for k in charts.CHART_KINDS]
    x_dd = _dd("Eixo X", 180)
    y_dd = _dd("Eixo Y", 180)
    gen_btn = primary_button("Gerar gráfico", icon=ft.Icons.INSERT_CHART_OUTLINED)
    plot_hint = ft.Text("", size=Type.small.size, color=ft.Colors.ON_SURFACE_VARIANT)
    chart_image = ft.Image(
        _BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True, gapless_playback=True
    )

    save_btn = secondary_button("Salvar PNG", icon=ft.Icons.SAVE_OUTLINED)
    save_btn.disabled = True
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
                on_click=lambda _e: _saved_path[0] and _open_folder(_saved_path[0]),
                style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ------------------------------------------------------------------
    # Pre-fill from the current result (shared via ctx by the Consulta tab)
    # ------------------------------------------------------------------

    def _prefill() -> None:
        cols = ctx.last_columns
        has = bool(cols)
        plot_empty.visible = not has
        plot_content.visible = has
        if not has:
            return
        x_dd.options = [ft.dropdown.Option(c) for c in cols]
        y_dd.options = [ft.dropdown.Option(c) for c in cols]
        schema = charts.schema_from_rows(cols, ctx.last_rows)
        spec = charts.suggest_spec(schema)
        kind_dd.value = spec.kind
        x_dd.value = spec.x
        y_dd.value = spec.y
        plot_hint.value = "Ajuste o tipo e as colunas, depois gere o gráfico."

    def on_show() -> None:
        _prefill()

    def on_result_changed() -> None:
        # A new result replaces the suggestion; the central router repaints.
        _prefill()

    # ------------------------------------------------------------------
    # Generate / save
    # ------------------------------------------------------------------

    def _current_spec() -> charts.ChartSpec | None:
        kind = kind_dd.value
        if not kind or kind not in charts.CHART_KINDS:
            return None
        return charts.ChartSpec(kind=kind, x=x_dd.value or None, y=y_dd.value or None)

    def _on_generate(_e=None) -> None:
        if ctx.pipeline_running[0]:
            return
        files = ctx.form.get_files()
        if not files or not ctx.last_sql[0]:
            ctx.toast("Execute uma consulta antes de gerar o gráfico.")
            return
        spec = _current_spec()
        if spec is None or not spec.x:
            ctx.toast("Escolha o tipo e ao menos a coluna do eixo X.")
            return
        ctx.action[0] = "plot"
        ctx.pipeline_running[0] = True
        ctx.form.set_running(True)
        gen_btn.disabled = True
        save_btn.disabled = True
        prog.control.visible = True
        prog.pbar.value = None
        prog.status.value = "Renderizando…"
        # Flush visibility BEFORE start() so the spinner animates (golden rule).
        page.update()
        prog.start()
        start_plot(ctx.bus, files, ctx.last_sql[0], spec, _palette())

    def _end_plot() -> None:
        ctx.pipeline_running[0] = False
        ctx.form.set_running(False)
        gen_btn.disabled = False
        prog.stop()
        prog.control.visible = False

    def _on_save(_e=None) -> None:
        if not _last_png[0]:
            return
        from src.utils import DATA_DIR

        out = _unique_png(DATA_DIR, "grafico")
        try:
            out.write_bytes(_last_png[0])
        except Exception as exc:
            logging.getLogger(__name__).warning("[!] save chart failed: %s", exc)
            ctx.toast("Falha ao salvar o PNG.")
            return
        _saved_path[0] = out
        saved_row.visible = True
        saved_path_text.value = out.name
        ctx.toast(f"Salvo em output/data/{out.name}", error=False)
        page.update()

    def _open_folder(path: Path) -> None:
        try:
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        except Exception as exc:
            logging.debug("[d] explorer select failed for %s: %s", path, exc)

    gen_btn.on_click = _on_generate
    save_btn.on_click = _on_save

    # ------------------------------------------------------------------
    # Event handlers (called by the central router in view.py)
    # ------------------------------------------------------------------

    def on_plot_start(p: dict) -> None:
        # Scoped update + early return: a full page.update() while the spinner is
        # animating would interrupt its on_animation_end chain and stop the mill.
        prog.status.value = "Renderizando…"
        ctx.scoped_update(prog.status)

    def on_plot_done(p: dict) -> None:
        _end_plot()
        png = p.get("png")
        _last_png[0] = png
        if png:
            chart_image.src = png
            chart_image.visible = True
            save_btn.disabled = False
            plot_hint.value = "Gráfico gerado. Salve como PNG para guardá-lo."

    def on_error(p: dict) -> None:
        _end_plot()
        ctx.toast(p.get("message", "Não foi possível gerar o gráfico."))

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    controls_row = ft.Row(
        [kind_dd, x_dd, y_dd, gen_btn],
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.END,
        wrap=True,
    )
    image_frame = ft.Container(
        content=chart_image,
        expand=True,
        alignment=ft.Alignment.CENTER,
        bgcolor=Color.dark.surface,
        border_radius=Radius.md,
        padding=Space.sm,
    )
    plot_content = ft.Column(
        controls=[controls_row, plot_hint, image_frame],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )
    plot_empty = tab_empty_state(
        ft.Icons.INSERT_CHART_OUTLINED,
        "Visualize seus dados",
        "Execute uma consulta na aba Consulta; o gráfico sugere automaticamente "
        "o melhor tipo a partir das colunas do resultado.",
    )
    plot_footer = ft.Container(
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border(top=ft.BorderSide(1.5, ft.Colors.OUTLINE_VARIANT)),
        padding=ft.Padding(
            left=Space.md, right=Space.md, top=Space.sm, bottom=Space.sm
        ),
        content=ft.Column(
            controls=[
                saved_row,
                ft.Row(
                    [
                        ft.Text(
                            "O PNG fica em output/data/ (acessível pela Biblioteca).",
                            size=Type.small.size,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            expand=True,
                            no_wrap=False,
                        ),
                        save_btn,
                    ],
                    spacing=Space.sm,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=Space.xs,
        ),
    )
    plot_view = ft.Column(
        controls=[
            prog.control,
            ft.Stack([plot_empty, plot_content], expand=True),
            plot_footer,
        ],
        expand=True,
        spacing=Space.sm,
        visible=False,
    )

    return PlotTab(
        view=plot_view,
        on_show=on_show,
        on_result_changed=on_result_changed,
        on_plot_start=on_plot_start,
        on_plot_done=on_plot_done,
        on_error=on_error,
    )
