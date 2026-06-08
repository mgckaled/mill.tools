"""Módulo Vídeo — download, conversão e processamento de vídeo."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui.modules.base import Module
from src.gui.modules.video.form_view import VideoArgs, VideoFormPanel, build_video_form
from src.gui.modules.video.worker import start_video_pipeline
from src.gui.theme.components import action_button, output_card
from src.gui.theme.tokens import Color, Type
from src.gui.views.progress_view import ProgressPanel, build_progress_view

if TYPE_CHECKING:
    from src.gui.events import EventBus


def build_video_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Constrói o módulo Vídeo — split form|pipeline com suporte a fila.

    Args:
        page: Página Flet.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event para cancelamento do pipeline.
        pipeline_running: Lista de um bool compartilhada com app.py.
        nav: Lista com [navigate_to] — populada após build_app definir navigate_to.
    """

    # ------------------------------------------------------------------
    # Handlers do ciclo de vida
    # ------------------------------------------------------------------

    def _on_start(args: VideoArgs) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        progress_panel.reset()
        form_panel.set_running(True)
        start_video_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    def _on_done(payload: dict) -> None:
        pipeline_running[0] = False
        form_panel.set_running(False)
        if not payload.get("error"):
            progress_panel.show_results(payload)

    # ------------------------------------------------------------------
    # Renderização dos resultados de vídeo
    # ------------------------------------------------------------------

    def _render_video_results(result: object, results_col: ft.Column) -> None:
        payload = result if isinstance(result, dict) else {}
        output_paths: list[str] = payload.get("output_paths", [])

        if not output_paths:
            results_col.controls.append(ft.Text(
                "Nenhum arquivo gerado.",
                color=ft.Colors.ON_SURFACE_VARIANT,
                italic=True,
            ))
            return

        results_col.controls.append(ft.Text(
            f"Arquivo(s) gerado(s): {len(output_paths)}",
            size=Type.input.size,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE,
        ))

        for path_str in output_paths:
            p = Path(path_str)
            results_col.controls.append(_make_output_card(p))

    def _make_output_card(p: Path) -> ft.Control:
        suffix = p.suffix.lower()
        is_audio = suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
        is_video = suffix in {".mp4", ".mkv", ".webm", ".avi", ".mov"}
        icon = ft.Icons.AUDIO_FILE_OUTLINED if is_audio else ft.Icons.VIDEO_FILE_OUTLINED

        extra: list[ft.Control] = []
        if is_audio and nav:
            def _transcribe(_e, _path=str(p)) -> None:
                nav[0]("transcription", {"file": _path})

            def _to_audio(_e, _path=str(p)) -> None:
                nav[0]("audio", {"file": _path})

            extra.append(action_button(
                "Transcrever",
                icon=ft.Icons.SUBTITLES_OUTLINED,
                on_click=_transcribe,
                accent=Color.log.ok,
            ))
            extra.append(action_button(
                "Processar no Áudio",
                icon=ft.Icons.GRAPHIC_EQ_OUTLINED,
                on_click=_to_audio,
                accent=Color.log.info,
            ))

        return output_card(p, icon=icon, extra_actions=extra)

    # ------------------------------------------------------------------
    # Painéis
    # ------------------------------------------------------------------

    form_panel: VideoFormPanel = build_video_form(page, on_start=_on_start)
    progress_panel: ProgressPanel = build_progress_view(
        page,
        on_cancel=_on_cancel,
        on_done=_on_done,
        owner_id="video",
        on_show_results=_render_video_results,
    )

    # ------------------------------------------------------------------
    # Layout split form | pipeline
    # ------------------------------------------------------------------

    control = ft.Row(
        controls=[
            ft.Container(
                content=ft.Container(
                    content=form_panel.control,
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
    # on_mount: suporte a bridge de outros módulos
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        if "file" in payload:
            form_panel.fill_from_path(str(payload["file"]))

    return Module(
        id="video",
        label="Vídeo",
        icon=ft.Icons.VIDEO_FILE_OUTLINED,
        selected_icon=ft.Icons.VIDEO_FILE,
        control=control,
        on_mount=_on_mount,
    )
