"""Avaliação sub-tab of the Observatório hub's Índice/RAG tab (PLANO_RAG_EVAL).

The summary of the last evaluation run — hit-rate@k, MRR, average cosines and
the coverage-flag accuracy — plus the delta against the previous *comparable*
run (same ``embed_space_id``; a run under a different embedding space is shown
as incomparable, never as a regression) and a "Rodar avaliação" button that runs
the pipeline itself (via ``on_run``/``on_cancel``, wired by ``rag_tab.py`` to
``observatory/eval_worker.py``). Same worker+view shape as ``index_tab.py``.

This file only builds Flet controls and is not unit-tested headless; the metrics
come from the pure core (``src.core.rag.eval``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.core.rag.eval import EvalData, EvalRunResult, latest_and_previous
from src.core.rag.stats import fmt_datetime
from src.gui.theme.components import (
    danger_button,
    help_icon_for,
    secondary_button,
    spinner,
    summary_card,
)
from src.gui.theme.tokens import IconSize, Space, Type


@dataclass
class EvalTab:
    """Handles for the evaluation tab."""

    control: ft.Control
    apply: Callable[[EvalData], None]  # called on the UI thread with fresh data
    set_running: Callable[[bool], None]  # toggles the progress row + button states
    set_progress: Callable[[int | None, int | None], None]  # (current, total)
    set_detail: Callable[[str], None]  # mono status line (log/error text)


def _safe_update(*controls: ft.Control) -> None:
    for c in controls:
        try:
            c.update()
        except Exception:
            pass


def _fmt_pct(x: float) -> str:
    return f"{x:.0%}"


def build_eval_tab(
    page: ft.Page,
    *,
    on_run: Callable[[], None],
    on_cancel: Callable[[], None],
) -> EvalTab:
    """Build the evaluation tab and return its handles.

    ``on_run``/``on_cancel`` are wired by ``rag_tab.py`` to the real pipeline
    (``observatory/eval_worker.py``) — this file only owns the controls and
    their visual state.
    """

    # ── metric summary card ────────────────────────────────────────────────
    def _value() -> ft.Text:
        return ft.Text("—", size=Type.small.size, color=ft.Colors.ON_SURFACE)

    vals = {
        "hit_rate": _value(),
        "mrr": _value(),
        "cos_covered": _value(),
        "cos_out": _value(),
        "flag": _value(),
        "questions": _value(),
        "scheme": _value(),
        "when": _value(),
    }

    def _stat_line(label: str, value: ft.Text) -> ft.Control:
        return ft.Row(
            controls=[
                ft.Text(
                    label,
                    size=Type.small.size,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    width=150,
                ),
                value,
            ],
            spacing=Space.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    delta_line = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        no_wrap=False,
        visible=False,
    )

    summary = summary_card(
        ft.Column(
            controls=[
                _stat_line("hit-rate@k", vals["hit_rate"]),
                _stat_line("MRR", vals["mrr"]),
                _stat_line("cosseno médio (cob.)", vals["cos_covered"]),
                _stat_line("cosseno médio (fora)", vals["cos_out"]),
                _stat_line("acurácia do flag", vals["flag"]),
                _stat_line("perguntas", vals["questions"]),
                _stat_line("esquema", vals["scheme"]),
                _stat_line("última rodada", vals["when"]),
                delta_line,
            ],
            spacing=Space.xs,
        )
    )

    empty_note = ft.Container(
        visible=False,
        padding=ft.Padding(left=0, right=0, top=Space.lg, bottom=Space.lg),
        content=ft.Text(
            "Nenhuma rodada de avaliação ainda. Adicione perguntas com "
            '"uv run main.py ai eval add" e clique em Rodar avaliação.',
            size=Type.input.size,
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
            no_wrap=False,
        ),
    )

    run_btn = secondary_button("Rodar avaliação", icon=ft.Icons.FACT_CHECK_OUTLINED)
    run_btn.on_click = lambda _e: on_run()

    header_controls: list[ft.Control] = [
        ft.Icon(
            ft.Icons.FACT_CHECK_OUTLINED, size=IconSize.lg, color=ft.Colors.PRIMARY
        ),
        ft.Text(
            "Avaliação do RAG",
            size=Type.heading.size,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        ),
        ft.Container(expand=True),
        run_btn,
    ]
    _help = help_icon_for("observatory.rag_eval", page)
    if _help is not None:
        header_controls.insert(2, _help)
    header_row = ft.Row(
        controls=header_controls,
        spacing=Space.sm,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # ── run progress (spinner + bar + status line + cancel) ────────────────
    spinner_img, spinner_start, spinner_stop = spinner()
    stage_label = ft.Text(
        "Avaliando…",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        weight=ft.FontWeight.W_500,
    )
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    cancel_btn = danger_button(
        "Cancelar", icon=ft.Icons.CANCEL_OUTLINED, on_click=lambda _e: on_cancel()
    )
    cancel_btn.disabled = True
    status_detail = ft.Text(
        "",
        size=Type.small.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        font_family=Type.FONT_MONO,
        no_wrap=False,
    )
    progress_row = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    spinner_img,
                    stage_label,
                    ft.Container(expand=True),
                    cancel_btn,
                ],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
            status_detail,
        ],
        spacing=Space.xs,
        visible=False,
    )

    def set_running(active: bool) -> None:
        progress_row.visible = active
        run_btn.disabled = active
        cancel_btn.disabled = not active
        if active:
            progress_bar.value = None
            status_detail.value = ""
            spinner_start()
        else:
            spinner_stop()
        _safe_update(progress_row, run_btn)

    def set_progress(current: int | None, total: int | None) -> None:
        progress_bar.value = (current / total) if total else None
        if total:
            status_detail.value = f"Avaliando {current}/{total}…"
        _safe_update(progress_bar, status_detail)

    def set_detail(message: str) -> None:
        status_detail.value = message
        _safe_update(status_detail)

    # ── apply fresh data (UI thread) ───────────────────────────────────────
    def _apply_delta(latest: EvalRunResult, data: EvalData) -> None:
        _, previous = latest_and_previous(data)
        if previous is not None:
            d_hit = latest.metrics.hit_rate - previous.metrics.hit_rate
            d_mrr = latest.metrics.mrr - previous.metrics.mrr
            delta_line.value = (
                f"Δ vs. anterior comparável: hit-rate {d_hit:+.0%} · MRR {d_mrr:+.2f}"
            )
            delta_line.visible = True
        elif len(data.runs) > 1:
            delta_line.value = (
                "Rodada anterior em espaço de embedding diferente — incomparável "
                "(o modelo/esquema mudou)."
            )
            delta_line.visible = True
        else:
            delta_line.visible = False

    def apply(data: EvalData) -> None:
        latest, _ = latest_and_previous(data)
        if latest is None:
            empty_note.visible = True
            summary.visible = False
            _safe_update(control)
            return

        empty_note.visible = False
        summary.visible = True
        m = latest.metrics
        vals["hit_rate"].value = (
            f"{_fmt_pct(m.hit_rate)} ({m.n_covered} coberta(s))"
            if m.n_covered
            else "— (sem cobertas)"
        )
        vals["mrr"].value = f"{m.mrr:.2f}" if m.n_covered else "—"
        vals["cos_covered"].value = (
            f"{m.mean_covered_score:.2f}" if m.n_covered else "—"
        )
        vals["cos_out"].value = f"{m.mean_out_score:.2f}" if m.n_out_of_corpus else "—"
        vals["flag"].value = _fmt_pct(m.flag_accuracy)
        vals[
            "questions"
        ].value = f"{m.n_covered} coberta(s) + {m.n_out_of_corpus} fora-do-acervo (k={latest.k})"
        vals["scheme"].value = latest.embed_scheme
        vals["when"].value = fmt_datetime(latest.timestamp)
        _apply_delta(latest, data)
        _safe_update(control)

    control = ft.Column(
        controls=[header_row, progress_row, summary, empty_note],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=Space.md,
    )

    return EvalTab(
        control=control,
        apply=apply,
        set_running=set_running,
        set_progress=set_progress,
        set_detail=set_detail,
    )
