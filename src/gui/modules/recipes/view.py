"""Recipes module — run reusable cross-module automation chains.

A hub module (reached from the AppBar, not the rail): split form | panel. The
form lists recipes and collects the input; the panel shows step-by-step progress,
a live log and the final output cards (with a bridge to the Library).

Self-contained like the AI/Library hubs: it subscribes to its own PipelineEvents
(module_id="recipes") and updates the panel on the UI thread.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui import settings
from src.gui.events import PipelineEvent
from src.gui.modules.ai.index_button import rag_index_button
from src.gui.modules.base import Module
from src.gui.modules.recipes.form_view import build_recipes_form
from src.gui.modules.recipes.pipeline_log import resolve_status
from src.gui.modules.recipes.worker import start_recipe_pipeline
from src.gui.theme.components import (
    action_button,
    hairline,
    log_line,
    output_card,
    secondary_button,
    spinner,
)
from src.gui.theme.tokens import IconSize, Space, Type

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "recipes"


def build_recipes_module(
    page: ft.Page,
    bus: EventBus,
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Build the Recipes module — run presets/saved recipes end to end.

    Args:
        page: Flet page.
        bus: Shared application EventBus (worker → UI).
        cancel_event: threading.Event set to cancel between steps.
        pipeline_running: Shared [bool] guard with app.py — blocks navigation.
        nav: List holding [navigate_to] — used to bridge results to the Library.
    """
    settings.load()

    def _toast(message: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.ERROR)
        page.snack_bar.open = True
        page.update()

    def _toast_info(message: str) -> None:
        page.snack_bar = ft.SnackBar(content=ft.Text(message))
        page.snack_bar.open = True
        page.update()

    def _set_progress(active: bool) -> None:
        progress_row.visible = active
        cancel_btn.visible = active
        if active:
            progress_bar.value = None  # indeterminate until first update
            spinner_start()
        else:
            spinner_stop()

    # ------------------------------------------------------------------
    # Run handler (references controls defined below — resolved at call time)
    # ------------------------------------------------------------------

    def _on_run() -> None:
        if pipeline_running[0]:
            return
        recipe = form.get_recipe()
        if recipe is None:
            _toast("Selecione uma receita.")
            return
        items = form.get_inputs()
        if not items:
            _toast("Adicione uma entrada (URL ou arquivo).")
            return

        from src.core.recipes.inputs import kind_for
        from src.gui.modules._pipeline_runner import item_label

        # Batch: one independent run per input. Otherwise a single run consuming
        # all inputs (so merge/images_to_pdf get the whole list).
        try:
            if form.get_batch():
                runs = [
                    ([it.value], kind_for(it.kind, it.value), item_label(it))
                    for it in items
                ]
            else:
                runs = [
                    (
                        [it.value for it in items],
                        kind_for(items[0].kind, items[0].value),
                        item_label(items[0]),
                    )
                ]
        except ValueError as exc:
            _toast(str(exc))
            return

        log_view.controls.clear()
        results_col.controls.clear()
        results_card.visible = False
        empty_state.visible = False
        stage_label.value = ""
        pipeline_running[0] = True
        cancel_event.clear()
        form.set_running(True)
        _set_progress(True)
        page.update()

        start_recipe_pipeline(
            bus,
            cancel_event,
            recipe=recipe,
            runs=runs,
            clean_intermediates=form.get_clean(),
        )

    def _on_cancel(_e=None) -> None:
        cancel_event.set()
        stage_label.value = "Cancelando após o passo atual…"
        page.update()

    # ------------------------------------------------------------------
    # Results rendering
    # ------------------------------------------------------------------

    def _show_results(paths: list[str]) -> None:
        results_col.controls.clear()
        for raw in paths:
            path = Path(raw)
            results_col.controls.append(
                output_card(
                    path,
                    extra_actions=[
                        action_button(
                            "Abrir na Biblioteca",
                            icon=ft.Icons.COLLECTIONS_BOOKMARK_OUTLINED,
                            on_click=lambda _e: nav[0]("library") if nav else None,
                        )
                    ],
                )
            )
        # Offer RAG indexing only when at least one output is text.
        index_row.visible = any(
            Path(p).suffix.lower() in (".txt", ".md") for p in paths
        )
        results_card.visible = bool(paths)

    # ------------------------------------------------------------------
    # Event subscription (UI thread)
    # ------------------------------------------------------------------

    def _on_event(event) -> None:
        if not isinstance(event, PipelineEvent) or event.module_id != _MODULE_ID:
            return
        p = event.payload
        label = resolve_status(event)
        if label:
            stage_label.value = label

        match event.type:
            case "progress_update":
                cur, tot = p.get("current"), p.get("total")
                progress_bar.value = (cur / tot) if tot else None
            case "log":
                msg = p.get("message", "")
                if msg:
                    log_view.controls.append(log_line(msg))
            case "task_done":
                progress_bar.value = 1.0
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                _show_results(p.get("output_paths", []))
            case "task_error":
                _set_progress(False)
                pipeline_running[0] = False
                form.set_running(False)
                message = p.get("message", "Erro.")
                log_view.controls.append(log_line(f"[!] {message}"))
                _toast(message)
        page.update()

    page.pubsub.subscribe(_on_event)

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    from src.core.recipes import store

    form = build_recipes_form(
        page, on_run=_on_run, load_saved=store.load_recipes, on_notify=_toast_info
    )

    spinner_img, spinner_start, spinner_stop = spinner()
    stage_label = ft.Text(
        "",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE,
        weight=ft.FontWeight.W_500,
        expand=True,
        no_wrap=False,
    )
    cancel_btn = secondary_button("Cancelar", icon=ft.Icons.CLOSE)
    cancel_btn.on_click = _on_cancel
    cancel_btn.visible = False
    progress_bar = ft.ProgressBar(
        value=None, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.OUTLINE_VARIANT
    )
    progress_row = ft.Column(
        controls=[
            ft.Row(
                controls=[spinner_img, stage_label, cancel_btn],
                spacing=Space.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            progress_bar,
        ],
        spacing=Space.xs,
        visible=False,
    )

    log_view = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    results_col = ft.Column(spacing=0)
    # Shown when the recipe produced any textual output (.txt/.md) worth indexing.
    index_row = ft.Row(
        [ft.Container(expand=True), rag_index_button(page)], visible=False
    )
    results_card = ft.Container(
        visible=False,
        content=ft.Column(
            controls=[
                ft.Text(
                    "Resultados",
                    size=Type.caption.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                results_col,
                index_row,
            ],
            spacing=Space.xs,
        ),
    )

    empty_state = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.ACCOUNT_TREE_OUTLINED,
                    size=IconSize.hero,
                    color=ft.Colors.OUTLINE_VARIANT,
                ),
                ft.Text(
                    "Automatize uma cadeia",
                    size=Type.heading.size,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    "Escolha uma receita, informe a entrada e rode — cada passo "
                    "alimenta o próximo, atravessando os módulos.",
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

    content_col = ft.Column(
        controls=[log_view, results_card],
        expand=True,
        spacing=Space.sm,
    )
    session_area = ft.Stack([content_col, empty_state], expand=True)

    panel = ft.Column(
        controls=[progress_row, hairline(), session_area],
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

    def _on_mount(payload: dict) -> None:
        # Re-list recipes so a recipe saved in another session shows up.
        try:
            form.refresh()
        except Exception as exc:
            logging.getLogger(__name__).debug("[d] recipe refresh failed: %s", exc)

    return Module(
        id=_MODULE_ID,
        label="Receitas",
        icon=ft.Icons.ACCOUNT_TREE_OUTLINED,
        selected_icon=ft.Icons.ACCOUNT_TREE,
        control=control,
        on_mount=_on_mount,
    )
