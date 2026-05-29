"""Layout raiz e navegação entre views do yt-transcriber GUI."""

from __future__ import annotations

import threading

import flet as ft

from src.gui import settings
from src.gui.events import EventBus
from src.gui.views.form_view import build_form_view
from src.gui.views.progress_view import build_progress_view
from src.gui.views.result_view import build_result_view
from src.gui.workers import PipelineArgs, PipelineResult, start_pipeline


def build_app(page: ft.Page) -> None:
    """Monta o app na página Flet com navegação form → progress → result.

    Carrega configurações de tema persistidas e instala AppBar com toggle
    dark/light. Gerencia o ciclo de vida do worker e do cancel_event.
    """
    cfg = settings.load()
    page.theme_mode = (
        ft.ThemeMode.DARK if cfg.get("theme_mode", "dark") == "dark" else ft.ThemeMode.LIGHT
    )

    cancel_event = threading.Event()
    _result: dict[str, PipelineResult] = {}

    # ------------------------------------------------------------------
    # AppBar com título e botão de tema
    # ------------------------------------------------------------------

    def _toggle_theme(_e) -> None:
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        theme_btn.icon = ft.Icons.DARK_MODE if is_dark else ft.Icons.LIGHT_MODE
        settings.set("theme_mode", "light" if is_dark else "dark")
        page.update()

    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE,
        tooltip="Alternar tema",
        on_click=_toggle_theme,
    )

    page.appbar = ft.AppBar(
        title=ft.Text("yt-transcriber", weight=ft.FontWeight.BOLD),
        center_title=False,
        actions=[theme_btn],
    )

    # ------------------------------------------------------------------
    # Navegação entre views
    # ------------------------------------------------------------------

    def _show(control: ft.Control) -> None:
        page.controls.clear()
        page.add(control)
        page.update()

    def _show_form() -> None:
        cancel_event.clear()
        _show(build_form_view(page, on_start=_on_start))

    def _show_progress() -> None:
        _show(build_progress_view(page, on_cancel=_on_cancel, on_done=_on_pipeline_done))  # type: ignore[arg-type]

    def _show_result(result: PipelineResult) -> None:
        _show(build_result_view(
            page,
            raw_path=result.raw_path,
            analysis_path=result.analysis_path,
            prompt_path=result.prompt_path,
            on_restart=_show_form,
        ))

    # ------------------------------------------------------------------
    # Handlers do ciclo de vida do worker
    # ------------------------------------------------------------------

    def _on_start(args: PipelineArgs) -> None:
        cancel_event.clear()
        bus = EventBus(page)

        # Captura o resultado do pipeline via pubsub antes de navegar para result_view
        def _capture_result(event: object) -> None:
            from src.gui.events import PipelineEvent
            if not isinstance(event, PipelineEvent):
                return
            if event.type == "pipeline_done":
                p = event.payload
                _result["last"] = PipelineResult(
                    raw_path=p.get("raw_path"),
                    analysis_path=p.get("analysis_path"),
                    prompt_path=p.get("prompt_path"),
                )
                page.pubsub.unsubscribe(_capture_result)
            elif event.type == "pipeline_error":
                _result["last"] = PipelineResult(error=event.payload.get("message"))
                page.pubsub.unsubscribe(_capture_result)

        _result["last"] = PipelineResult()
        page.pubsub.subscribe(_capture_result)
        _show_progress()
        start_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    def _on_pipeline_done() -> None:
        _show_result(_result.get("last", PipelineResult()))

    # ------------------------------------------------------------------
    # Inicia na view de formulário
    # ------------------------------------------------------------------

    _show_form()
