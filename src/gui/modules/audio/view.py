"""Módulo Áudio — download, conversão e extração de áudio."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui.modules.audio.form_view import AudioArgs, AudioFormPanel, build_audio_form
from src.gui.modules.audio.worker import start_audio_pipeline
from src.gui.modules.base import Module
from src.gui.views.progress_view import ProgressPanel, build_progress_view

if TYPE_CHECKING:
    from src.gui.events import EventBus


def build_audio_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Constrói o módulo Áudio — split form|pipeline com suporte a fila.

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

    def _on_start(args: AudioArgs) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        progress_panel.reset()
        form_panel.set_running(True)
        start_audio_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    def _on_done(payload: dict) -> None:
        pipeline_running[0] = False
        form_panel.set_running(False)
        if not payload.get("error"):
            progress_panel.show_results(payload)

    # ------------------------------------------------------------------
    # Renderização dos resultados de áudio
    # ------------------------------------------------------------------

    def _render_audio_results(result: object, results_col: ft.Column) -> None:
        """Popula results_col com caminhos de saída + botões de bridge."""
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
            size=13,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_SURFACE,
        ))

        for path_str in output_paths:
            p = Path(path_str)
            results_col.controls.append(_make_output_card(p))

    def _make_output_card(p: Path) -> ft.Control:
        def _open_folder(_e) -> None:
            import subprocess
            import platform
            if platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", str(p)], check=False)

        def _transcribe(_e, _path=str(p)) -> None:
            if nav:
                nav[0]("transcription", {"file": _path})

        suffix = p.suffix.lower()
        is_audio = suffix in {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}

        return ft.Container(
            margin=ft.Margin(top=6, bottom=2, left=0, right=0),
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            border=ft.Border(
                left=ft.BorderSide(1, ft.Colors.BLUE_700),
                right=ft.BorderSide(1, ft.Colors.BLUE_700),
                top=ft.BorderSide(1, ft.Colors.BLUE_700),
                bottom=ft.BorderSide(1, ft.Colors.BLUE_700),
            ),
            border_radius=6,
            bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLUE_400),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.AUDIO_FILE_OUTLINED, size=16, color=ft.Colors.BLUE_300),
                            ft.Text(
                                p.name,
                                size=12,
                                color=ft.Colors.WHITE,
                                font_family="monospace",
                                expand=True,
                                selectable=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                no_wrap=True,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        str(p.parent),
                        size=11,
                        color=ft.Colors.GREY_400,
                        font_family="monospace",
                        selectable=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=True,
                    ),
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                "Abrir pasta",
                                icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                                on_click=_open_folder,
                                style=ft.ButtonStyle(color=ft.Colors.BLUE_300),
                            ),
                            *(
                                [ft.TextButton(
                                    "Transcrever",
                                    icon=ft.Icons.SUBTITLES_OUTLINED,
                                    on_click=_transcribe,
                                    style=ft.ButtonStyle(color=ft.Colors.GREEN_300),
                                )]
                                if is_audio else []
                            ),
                        ],
                        spacing=4,
                    ),
                ],
                spacing=4,
            ),
        )

    # ------------------------------------------------------------------
    # Painéis
    # ------------------------------------------------------------------

    form_panel: AudioFormPanel = build_audio_form(page, on_start=_on_start)
    progress_panel: ProgressPanel = build_progress_view(
        page,
        on_cancel=_on_cancel,
        on_done=_on_done,
        owner_id="audio",
        on_show_results=_render_audio_results,
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
    # on_mount: suporte a bridge de outros módulos (ex: Vídeo → Áudio)
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        if "file" in payload:
            form_panel.fill_from_path(str(payload["file"]))

    return Module(
        id="audio",
        label="Áudio",
        icon=ft.Icons.MUSIC_NOTE_OUTLINED,
        selected_icon=ft.Icons.MUSIC_NOTE,
        control=control,
        on_mount=_on_mount,
    )
