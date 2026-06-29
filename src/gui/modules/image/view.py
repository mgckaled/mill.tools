"""Módulo Imagens — operações de imagem com visor Before/After."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import TYPE_CHECKING

import flet as ft

from src.gui.events import PipelineEvent
from src.gui.modules.base import Module
from src.gui.modules.image.form_view import ImageArgs, ImageFormPanel, build_image_form
from src.gui.modules.image import pipeline_log
from src.gui.modules.image.preview import build_preview
from src.gui.modules.image.worker import start_image_pipeline
from src.gui.theme.tokens import Color, Radius, Space, Type
from src.gui.theme.components import (
    action_button,
    danger_button,
    hairline,
    log_line,
    spinner,
)

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "image"
_MAX_LOG = 300

# Output modes that carry transparency → show the checkerboard backdrop.
_ALPHA_MODES = frozenset({"RGBA", "LA", "PA", "RGBa", "La"})


def build_image_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
    nav: list,
) -> Module:
    """Constrói o módulo Imagens — form | Before/After viewer + log compacto.

    Args:
        page: Página Flet.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event para cancelamento.
        pipeline_running: Lista [bool] compartilhada com app.py.
        nav: Lista [navigate_to] (forward reference) para bridges entre módulos.
    """

    # ------------------------------------------------------------------
    # Visor Before/After (extraído para preview.py)
    # ------------------------------------------------------------------

    _last_input_thumb: list[bytes | None] = [None]
    _last_output_path: list[str | None] = [None]

    preview = build_preview()

    # ------------------------------------------------------------------
    # Painel direito — spinner, barra, log
    # ------------------------------------------------------------------

    spin_img, _start_spin, _stop_spin = spinner()

    stage_label = ft.Text(
        "Inicie o pipeline pelo formulário →",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    progress_bar = ft.ProgressBar(
        value=None,
        expand=True,
        color=ft.Colors.PRIMARY,
        bgcolor=ft.Colors.OUTLINE_VARIANT,
        visible=False,
    )

    log_list = ft.ListView(
        spacing=Space.xxs,
        padding=ft.Padding(left=6, right=6, top=4, bottom=4),
        auto_scroll=True,
    )

    def _append_log(text: str) -> None:
        log_list.controls.append(log_line(text))
        if len(log_list.controls) > _MAX_LOG:
            log_list.controls = log_list.controls[-_MAX_LOG:]

    cancel_btn = danger_button(
        "Cancelar",
        icon=ft.Icons.CANCEL_OUTLINED,
        on_click=lambda _: cancel_event.set(),
    )

    def _open_output_folder(_e) -> None:
        from src.utils import IMAGE_PROCESSED_DIR

        IMAGE_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["explorer", str(IMAGE_PROCESSED_DIR)], check=False)

    open_folder_btn = action_button(
        "Abrir pasta de saída",
        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
        on_click=_open_output_folder,
        accent=ft.Colors.PRIMARY,
    )

    def _open_last_file(_e) -> None:
        out = _last_output_path[0]
        if not out:
            return
        try:
            os.startfile(out)  # Windows shell open
        except Exception:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Não foi possível abrir {os.path.basename(out)}"),
                bgcolor=ft.Colors.ERROR,
            )
            page.snack_bar.open = True
            page.update()

    open_file_btn = action_button(
        "Abrir arquivo",
        icon=ft.Icons.IMAGE_OUTLINED,
        on_click=_open_last_file,
        accent=ft.Colors.PRIMARY,
    )
    open_file_btn.visible = False

    def _open_in_library(_e) -> None:
        out = _last_output_path[0]
        if nav:
            nav[0]("library", {"file": out} if out else None)

    library_btn = action_button(
        "Ver na Biblioteca",
        icon=ft.Icons.PHOTO_LIBRARY_OUTLINED,
        on_click=_open_in_library,
        accent=ft.Colors.PRIMARY,
    )
    library_btn.visible = False

    right_panel = ft.Column(
        controls=[
            preview.control,
            hairline(),
            ft.Row(
                controls=[spin_img, stage_label],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                content=progress_bar,
                padding=ft.Padding(left=0, right=0, top=2, bottom=4),
            ),
            ft.Container(
                content=log_list,
                height=140,
                border=ft.Border(
                    left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                ),
                border_radius=Radius.sm,
                bgcolor=Color.dark.surface_variant,
            ),
            ft.Row(
                controls=[
                    open_folder_btn,
                    open_file_btn,
                    library_btn,
                    ft.Container(expand=True),
                    cancel_btn,
                ],
                spacing=4,
            ),
        ],
        expand=True,
        spacing=8,
    )

    # ------------------------------------------------------------------
    # Handler pubsub
    # ------------------------------------------------------------------

    def _handle_event(event: PipelineEvent) -> None:
        if event.module_id and event.module_id != _MODULE_ID:
            return

        t = event.type
        p = event.payload

        _label = pipeline_log.resolve_stage_label(event)
        if _label is not None:
            stage_label.value = _label
            stage_label.color = ft.Colors.ON_SURFACE
            stage_label.italic = False

        if t == "progress_start":
            progress_bar.visible = True
            progress_bar.value = None
            _start_spin()

        elif t == "queue_progress":
            cur = p.get("current_item", 0)
            tot = p.get("total_items", 1)
            progress_bar.value = (cur - 1) / max(tot, 1)

        elif t == "image_op_start":
            thumb = p.get("thumb")
            _last_input_thumb[0] = thumb
            preview.show_single(thumb, False)

        elif t == "image_op_done":
            out_thumb = p.get("thumb")
            in_thumb = _last_input_thumb[0]
            after_alpha = p.get("out_mode", "?") in _ALPHA_MODES
            if in_thumb and out_thumb:
                preview.show_before_after(in_thumb, out_thumb, after_alpha)
            elif out_thumb:
                preview.show_single(out_thumb, after_alpha)
            meta_text = pipeline_log.fmt_meta_strip(
                p.get("src_w", 0),
                p.get("src_h", 0),
                p.get("src_fmt"),
                p.get("src_size_bytes", 0),
                p.get("out_w", 0),
                p.get("out_h", 0),
                p.get("out_fmt"),
                p.get("out_size_bytes", 0),
            )
            preview.set_meta(meta_text)
            preview.add_batch_item(in_thumb, out_thumb, after_alpha, meta_text)
            out_path = p.get("output_path")
            if out_path:
                _last_output_path[0] = out_path
                open_file_btn.visible = True
                library_btn.visible = True
            cur_item = p.get("item_idx", 1)
            tot_items = p.get("total_items", 1)
            progress_bar.value = cur_item / max(tot_items, 1)

        for msg in pipeline_log.resolve_messages(event):
            _append_log(msg)

        if t == "task_done":
            progress_bar.value = 1.0
            cancel_btn.disabled = True
            _stop_spin()
            form_panel.set_running(False)

        elif t == "task_error":
            progress_bar.visible = False
            cancel_btn.disabled = True
            _stop_spin()
            form_panel.set_running(False)

        page.update()

    page.pubsub.subscribe(_handle_event)

    # ------------------------------------------------------------------
    # Handlers do formulário
    # ------------------------------------------------------------------

    def _on_start(args: ImageArgs) -> None:
        if pipeline_running[0]:
            return
        pipeline_running[0] = True
        cancel_event.clear()
        cancel_btn.disabled = False
        log_list.controls.clear()
        progress_bar.visible = True
        progress_bar.value = None
        stage_label.value = "Iniciando..."
        stage_label.color = ft.Colors.ON_SURFACE
        stage_label.italic = False
        preview.reset()
        _last_input_thumb[0] = None
        _last_output_path[0] = None
        open_file_btn.visible = False
        library_btn.visible = False
        form_panel.set_running(True)
        page.update()
        start_image_pipeline(args, bus, cancel_event, pipeline_running)

    # ------------------------------------------------------------------
    # Painéis + layout
    # ------------------------------------------------------------------

    form_panel: ImageFormPanel = build_image_form(page, on_start=_on_start)

    control = ft.Row(
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

    # ------------------------------------------------------------------
    # on_mount: bridge from other modules (e.g. Library → Imagens)
    # ------------------------------------------------------------------

    def _on_mount(payload: dict) -> None:
        if "file" in payload:
            form_panel.fill_from_path(str(payload["file"]))

    return Module(
        id="image",
        label="Imagens",
        icon=ft.Icons.IMAGE_OUTLINED,
        selected_icon=ft.Icons.IMAGE,
        control=control,
        on_mount=_on_mount,
    )
