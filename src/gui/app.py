"""Layout raiz do yt-transcriber GUI — layout split form | pipeline."""

from __future__ import annotations

import threading

import flet as ft

from src.gui import settings
from src.gui.events import EventBus
from src.gui.views.form_view import build_form_view
from src.gui.views.progress_view import build_progress_view
from src.gui.workers import PipelineArgs, PipelineResult, start_pipeline


def build_app(page: ft.Page) -> None:
    """Monta o layout split: formulário fixo à esquerda, pipeline expansível à direita.

    Não há mais navegação entre views — ambos os painéis são sempre visíveis.
    O EventBus é criado uma única vez e reutilizado entre execuções. O botão
    Iniciar é desabilitado durante a execução e reabilitado ao fim.
    """
    cfg = settings.load()
    page.theme_mode = (
        ft.ThemeMode.DARK if cfg.get("theme_mode", "dark") == "dark" else ft.ThemeMode.LIGHT
    )

    cancel_event = threading.Event()
    bus = EventBus(page)
    pipeline_running: list[bool] = [False]

    # ------------------------------------------------------------------
    # AppBar
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
        title=ft.Text("mill.tools", weight=ft.FontWeight.BOLD),
        center_title=False,
        actions=[theme_btn],
    )

    # ------------------------------------------------------------------
    # Handlers do ciclo de vida
    # ------------------------------------------------------------------

    def _on_start(args: PipelineArgs) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        progress_panel.reset()
        form_panel.set_running(True)
        start_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    def _on_pipeline_done(payload: dict) -> None:
        pipeline_running[0] = False
        form_panel.set_running(False)
        result = PipelineResult(
            raw_path=payload.get("raw_path"),
            analysis_path=payload.get("analysis_path"),
            prompt_path=payload.get("prompt_path"),
        )
        progress_panel.show_results(result)

    # ------------------------------------------------------------------
    # Painéis
    # ------------------------------------------------------------------

    form_panel = build_form_view(page, on_start=_on_start)
    progress_panel = build_progress_view(page, on_cancel=_on_cancel, on_done=_on_pipeline_done)

    # ------------------------------------------------------------------
    # Legenda de atalhos de teclado (sempre visível, rodapé esquerdo)
    # ------------------------------------------------------------------

    def _key_chip(label: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(label, size=11, font_family="monospace", color=ft.Colors.ON_SURFACE_VARIANT),
            padding=ft.Padding(left=6, right=6, top=2, bottom=2),
            border=ft.Border(
                left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                bottom=ft.BorderSide(2, ft.Colors.OUTLINE_VARIANT),
            ),
            border_radius=4,
        )

    shortcuts_bar = ft.Container(
        content=ft.Row(
            controls=[
                _key_chip("Ctrl"), ft.Text("+", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                _key_chip("Enter"), ft.Text(" Iniciar", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(width=12),
                _key_chip("Esc"), ft.Text(" Cancelar", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(left=12, right=8, top=6, bottom=6),
        border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )

    # ------------------------------------------------------------------
    # Layout split
    # ------------------------------------------------------------------

    layout = ft.Row(
        controls=[
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(content=form_panel.control, expand=True),
                        shortcuts_bar,
                    ],
                    spacing=0,
                    expand=True,
                ),
                width=380,
            ),
            ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=progress_panel.control,
                expand=True,
                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # ------------------------------------------------------------------
    # Atalhos de teclado
    # ------------------------------------------------------------------

    def _on_keyboard(e: ft.KeyboardEvent) -> None:
        if e.ctrl and e.key == "Enter" and not pipeline_running[0]:
            for ctrl in _walk(page):
                if (
                    isinstance(ctrl, ft.FilledButton)
                    and getattr(ctrl, "text", "") == "Iniciar"
                    and not ctrl.disabled
                    and ctrl.on_click
                ):
                    ctrl.on_click(e)
                    break
        if e.key == "Escape" and pipeline_running[0]:
            _on_cancel()

    def _walk(root):
        queue = [root]
        while queue:
            item = queue.pop(0)
            yield item
            for attr in ("controls", "content", "actions"):
                child = getattr(item, attr, None)
                if isinstance(child, list):
                    queue.extend(c for c in child if c is not None)
                elif child is not None:
                    queue.append(child)

    page.on_keyboard_event = _on_keyboard

    # ------------------------------------------------------------------
    # Montar página
    # ------------------------------------------------------------------

    page.controls.clear()
    page.add(layout)
    page.update()
