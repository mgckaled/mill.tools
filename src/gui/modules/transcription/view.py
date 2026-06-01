"""Módulo Transcrição — wrap do pipeline yt-transcriber existente."""

from __future__ import annotations

import threading

import flet as ft

from src.gui.modules.base import Module
from src.gui.views.form_view import build_form_view
from src.gui.views.progress_view import build_progress_view
from src.gui.workers import PipelineArgs, PipelineResult, start_pipeline

if __import__("typing").TYPE_CHECKING:
    from src.gui.events import EventBus


def build_transcription_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> Module:
    """Constrói o módulo Transcrição — split form|pipeline idêntico ao app.py anterior.

    Args:
        page: Página Flet.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event para cancelamento do pipeline.
        pipeline_running: lista de um bool compartilhada com app.py para
            bloquear navigate_to durante execução.
    """

    # ------------------------------------------------------------------
    # Handlers do ciclo de vida do pipeline
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
        if not payload.get("error") and not payload.get("cancelled"):
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
    progress_panel = build_progress_view(
        page,
        on_cancel=_on_cancel,
        on_done=_on_pipeline_done,
        owner_id="transcription",
    )

    # ------------------------------------------------------------------
    # Legenda de atalhos (rodapé esquerdo)
    # ------------------------------------------------------------------

    def _key_chip(label: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                label, size=11, font_family="monospace",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
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
                _key_chip("Ctrl"),
                ft.Text("+", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                _key_chip("Enter"),
                ft.Text(" Iniciar", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(width=12),
                _key_chip("Esc"),
                ft.Text(" Cancelar", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=3,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(left=12, right=8, top=6, bottom=6),
        border=ft.Border(top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
    )

    # ------------------------------------------------------------------
    # Layout split form | pipeline
    # ------------------------------------------------------------------

    control = ft.Row(
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
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
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
    # on_mount: preenche URL se payload contiver {"file": path} (bridge PR3)
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        if "file" in payload:
            _fill_url(str(payload["file"]))

    def _fill_url(path: str) -> None:
        """Preenche o campo URL do formulário com um caminho local (bridge Áudio → Transcrição)."""
        # Acessa url_field via walk na árvore do form_panel
        _walk_fill(form_panel.control, path)

    def _walk_fill(ctrl: ft.Control, path: str) -> bool:
        """Walk na árvore do form_panel procurando o TextField de URL."""
        if isinstance(ctrl, ft.TextField) and (
            "youtube" in (ctrl.hint_text or "").lower()
            or "url" in (ctrl.hint_text or "").lower()
        ):
            ctrl.value = path
            if ctrl.page:
                ctrl.update()
            return True
        for attr in ("controls", "content", "actions"):
            child = getattr(ctrl, attr, None)
            if isinstance(child, list):
                for c in child:
                    if c and _walk_fill(c, path):
                        return True
            elif child is not None:
                if _walk_fill(child, path):
                    return True
        return False

    return Module(
        id="transcription",
        label="Transcrição",
        icon=ft.Icons.SUBTITLES_OUTLINED,
        selected_icon=ft.Icons.SUBTITLES,
        control=control,
        on_mount=_on_mount,
    )


def get_form_start_button(module_control: ft.Control) -> ft.FilledButton | None:
    """Walk na árvore do módulo Transcrição para encontrar o botão Iniciar."""
    queue = [module_control]
    while queue:
        item = queue.pop(0)
        if isinstance(item, ft.FilledButton) and getattr(item, "text", "") == "Iniciar":
            return item
        for attr in ("controls", "content", "actions"):
            child = getattr(item, attr, None)
            if isinstance(child, list):
                queue.extend(c for c in child if c is not None)
            elif child is not None:
                queue.append(child)
    return None
