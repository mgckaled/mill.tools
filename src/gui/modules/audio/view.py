"""Módulo Áudio — download, conversão e extração de áudio."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui.components.audio_player import build_audio_player
from src.gui.modules.audio import pipeline_log
from src.gui.modules.audio.form_view import AudioArgs, AudioFormPanel, build_audio_form
from src.gui.modules.audio.visualize_tab import build_visualize_tab
from src.gui.modules.audio.worker import start_audio_pipeline
from src.gui.modules.base import Module
from src.gui.theme.components import Cursor, action_button, hairline, output_card
from src.gui.theme.tokens import Color, Space, Type
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

    # Per-item metadata captured from audio_op_done (A/B source + loudness).
    # Keyed by final output_path → {"source_path", "loudness_stats", ...}.
    _item_meta: dict[str, dict] = {}

    def _capture_meta(event) -> None:
        if getattr(event, "module_id", "") != "audio":
            return
        if getattr(event, "type", "") == "audio_op_done":
            out = event.payload.get("output_path")
            if out:
                _item_meta[out] = event.payload

    page.pubsub.subscribe(_capture_meta)

    # ------------------------------------------------------------------
    # Handlers do ciclo de vida
    # ------------------------------------------------------------------

    def _on_start(args: AudioArgs) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        _item_meta.clear()
        progress_panel.reset()
        form_panel.set_running(True)
        start_audio_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    _AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}

    def _on_done(payload: dict) -> None:
        pipeline_running[0] = False
        form_panel.set_running(False)
        if not payload.get("error"):
            progress_panel.show_results(payload)
            # Carrega o primeiro arquivo de áudio da saída no reprodutor.
            for path_str in payload.get("output_paths", []):
                if Path(path_str).suffix.lower() in _AUDIO_EXTS:
                    source = _item_meta.get(path_str, {}).get("source_path")
                    if source:
                        player.set_compare(source, path_str)
                    else:
                        player.load(path_str)
                    break

    # ------------------------------------------------------------------
    # Renderização dos resultados de áudio
    # ------------------------------------------------------------------

    def _render_audio_results(result: object, results_col: ft.Column) -> None:
        """Popula results_col com caminhos de saída + botões de bridge."""
        payload = result if isinstance(result, dict) else {}
        output_paths: list[str] = payload.get("output_paths", [])

        if not output_paths:
            results_col.controls.append(
                ft.Text(
                    "Nenhum arquivo gerado.",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                )
            )
            return

        results_col.controls.append(
            ft.Text(
                f"Arquivo(s) gerado(s): {len(output_paths)}",
                size=Type.input.size,
                weight=ft.FontWeight.W_500,
                color=ft.Colors.ON_SURFACE,
            )
        )

        for path_str in output_paths:
            p = Path(path_str)
            results_col.controls.append(_make_output_card(p))
            meta = _item_meta.get(path_str, {})
            stats = meta.get("loudness_stats")
            if stats:
                results_col.controls.append(
                    _make_loudness_card(stats, meta.get("loudness_target", -14.0))
                )

    def _make_loudness_card(stats: dict, target: float) -> ft.Control:
        line = pipeline_log.fmt_loudness_card(stats, target)
        return ft.Container(
            margin=ft.Margin(top=0, bottom=4, left=0, right=0),
            padding=ft.Padding(left=10, right=10, top=6, bottom=6),
            border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.PRIMARY),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.GRAPHIC_EQ, size=14, color=ft.Colors.PRIMARY),
                    ft.Text(
                        line,
                        size=Type.small.size,
                        color=ft.Colors.ON_SURFACE,
                        font_family=Type.FONT_MONO,
                        selectable=True,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _make_output_card(p: Path) -> ft.Control:
        suffix = p.suffix.lower()
        is_audio = suffix in {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}
        icon = (
            ft.Icons.AUDIO_FILE_OUTLINED if is_audio else ft.Icons.VIDEO_FILE_OUTLINED
        )

        extra: list[ft.Control] = []
        if is_audio and nav:

            def _transcribe(_e, _path=str(p)) -> None:
                nav[0]("transcription", {"file": _path})

            extra.append(
                action_button(
                    "Transcrever",
                    icon=ft.Icons.SUBTITLES_OUTLINED,
                    on_click=_transcribe,
                    accent=Color.log.ok,
                )
            )

        return output_card(p, icon=icon, extra_actions=extra)

    # ------------------------------------------------------------------
    # Painéis
    # ------------------------------------------------------------------

    player = build_audio_player(page)

    form_panel: AudioFormPanel = build_audio_form(page, on_start=_on_start)
    progress_panel: ProgressPanel = build_progress_view(
        page,
        on_cancel=_on_cancel,
        on_done=_on_done,
        owner_id="audio",
        on_show_results=_render_audio_results,
    )

    # ------------------------------------------------------------------
    # Painel direito: player dedicado (expand) + divisória + pipeline (fixo)
    # ------------------------------------------------------------------

    right_panel = ft.Column(
        controls=[
            player.control,
            hairline(),
            progress_panel.control,
        ],
        expand=True,
        spacing=8,
    )

    # ------------------------------------------------------------------
    # Layout: toggle Converter | Visualizar (Stack com visible=)
    # ------------------------------------------------------------------

    converter_body = ft.Row(
        controls=[
            ft.Container(content=form_panel.control, width=380),
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=right_panel,
                expand=True,
                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    visualize_tab = build_visualize_tab(page, nav)
    visualize_tab.control.visible = False

    def _tab_style(active: bool) -> ft.ButtonStyle:
        return ft.ButtonStyle(
            color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            mouse_cursor=Cursor.interactive,
        )

    tab_conv = ft.TextButton(
        "Converter", icon=ft.Icons.GRAPHIC_EQ, style=_tab_style(True)
    )
    tab_viz = ft.TextButton(
        "Visualizar", icon=ft.Icons.INSIGHTS_OUTLINED, style=_tab_style(False)
    )

    def _show_tab(name: str) -> None:
        if pipeline_running[0]:
            return  # don't switch mid-run
        converter_body.visible = name == "converter"
        visualize_tab.control.visible = name == "visualize"
        tab_conv.style = _tab_style(name == "converter")
        tab_viz.style = _tab_style(name == "visualize")
        page.update()

    tab_conv.on_click = lambda _e: _show_tab("converter")
    tab_viz.on_click = lambda _e: _show_tab("visualize")

    control = ft.Column(
        controls=[
            ft.Row([tab_conv, tab_viz], spacing=Space.xs),
            hairline(),
            ft.Stack([converter_body, visualize_tab.control], expand=True),
        ],
        expand=True,
        spacing=Space.sm,
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
