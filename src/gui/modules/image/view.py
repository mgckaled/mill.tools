"""Módulo Imagens — conversão com visor de pré-visualização."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.gui.events import PipelineEvent
from src.gui.modules.base import Module
from src.gui.modules.image.form_view import ImageArgs, ImageFormPanel, build_image_form
from src.gui.modules.image.worker import start_image_pipeline
from src.gui.theme.tokens import Color
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


def build_image_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> Module:
    """Constrói o módulo Imagens — form | visor + log compacto.

    Args:
        page: Página Flet.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event para cancelamento.
        pipeline_running: Lista [bool] compartilhada com app.py.
    """

    # ------------------------------------------------------------------
    # Painel direito — visor + CLI compacto
    # ------------------------------------------------------------------

    # Visor de pré-visualização — src é obrigatório no Flet 0.85; usa 1×1 px transparente
    _BLANK_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    preview_img = ft.Image(
        _BLANK_PNG,
        fit=ft.BoxFit.CONTAIN,
        expand=True,
    )
    preview_placeholder = ft.Text(
        "Selecione imagens para começar",
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
        size=13,
    )
    preview_container = ft.Container(
        content=ft.Stack(
            controls=[
                ft.Container(
                    content=preview_placeholder,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
                ft.Container(
                    content=preview_img,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                    visible=False,
                ),
            ],
            expand=True,
        ),
        expand=True,
        alignment=ft.Alignment.CENTER,
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=6,
        bgcolor=Color.dark.surface_variant,
    )
    _preview_stack: ft.Stack = preview_container.content  # type: ignore[assignment]
    _preview_placeholder_ctr: ft.Container = _preview_stack.controls[0]  # type: ignore[index]
    _preview_img_ctr: ft.Container = _preview_stack.controls[1]  # type: ignore[index]

    def _set_preview(data: bytes | None) -> None:
        if data:
            preview_img.src = data
            _preview_placeholder_ctr.visible = False
            _preview_img_ctr.visible = True
        else:
            _preview_placeholder_ctr.visible = True
            _preview_img_ctr.visible = False

    # Spinner + stage label
    spin_img, _start_spin, _stop_spin = spinner()

    stage_label = ft.Text(
        "Inicie o pipeline pelo formulário →",
        size=13,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    # Barra de progresso
    progress_bar = ft.ProgressBar(
        value=None,
        expand=True,
        color=ft.Colors.PRIMARY,
        bgcolor=ft.Colors.OUTLINE_VARIANT,
        visible=False,
    )

    # Log compacto
    log_list = ft.ListView(
        spacing=2,
        padding=ft.Padding(left=6, right=6, top=4, bottom=4),
        auto_scroll=True,
    )

    def _append_log(text: str) -> None:
        log_list.controls.append(log_line(text))
        if len(log_list.controls) > _MAX_LOG:
            log_list.controls = log_list.controls[-_MAX_LOG:]

    # Botão Cancelar
    cancel_btn = danger_button(
        "Cancelar",
        icon=ft.Icons.CANCEL_OUTLINED,
        on_click=lambda _: cancel_event.set(),
    )

    # Botão "Abrir pasta de saída"
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

    right_panel = ft.Column(
        controls=[
            preview_container,
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
                border_radius=6,
                bgcolor=Color.dark.surface_variant,
            ),
            ft.Row(
                controls=[open_folder_btn, ft.Container(expand=True), cancel_btn],
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

        # Stage label
        _label = _resolve_stage_label(event)
        if _label is not None:
            stage_label.value = _label
            stage_label.color = ft.Colors.ON_SURFACE
            stage_label.italic = False

        # Progresso
        if t == "progress_start":
            progress_bar.visible = True
            progress_bar.value = None
            _start_spin()

        elif t == "queue_progress":
            cur = p.get("current_item", 0)
            tot = p.get("total_items", 1)
            progress_bar.value = (cur - 1) / max(tot, 1)

        # Visor — input thumbnail
        elif t == "image_op_start":
            thumb = p.get("thumb")
            if thumb:
                _set_preview(thumb)

        # Visor — resultado thumbnail
        elif t == "image_op_done":
            thumb = p.get("thumb")
            if thumb:
                _set_preview(thumb)
            cur_item = p.get("item_idx", 1)
            tot_items = p.get("total_items", 1)
            progress_bar.value = cur_item / max(tot_items, 1)

        # Log lines
        for msg in _resolve_messages(event):
            _append_log(msg)

        # Fim
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
        _set_preview(None)
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

    return Module(
        id="image",
        label="Imagens",
        icon=ft.Icons.IMAGE_OUTLINED,
        selected_icon=ft.Icons.IMAGE,
        control=control,
    )


# ------------------------------------------------------------------
# Helpers de mensagens e stage label
# ------------------------------------------------------------------

def _fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def _resolve_messages(event: PipelineEvent) -> list[str]:
    p = event.payload
    t = event.type
    match t:
        case "image_op_start":
            op = p.get("operation", "")
            name = p.get("item_name", "")
            verb = {"download": "Baixando", "convert": "Convertendo"}.get(op, op)
            return [f"[~] {verb}: {name}"]
        case "image_op_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", "")
            name = Path(path).name if path else path
            src_sz = p.get("src_size_bytes")
            out_sz = p.get("out_size_bytes")
            sz = f" | {_fmt_size(src_sz)} → {_fmt_size(out_sz)}" if src_sz and out_sz else ""
            return [f"[✓] Salvo: {name} ({elapsed}){sz}"]
        case "image_op_error":
            name = p.get("item_name", "")
            msg = p.get("message", "")
            return [f"[!] Erro em '{name}': {msg}"]
        case "task_done":
            paths = p.get("output_paths", [])
            failed = p.get("failed_count", 0)
            lines = [f"[✓] Concluído — {len(paths)} arquivo(s) gerado(s)."]
            if failed:
                lines.append(f"[!] {failed} item(ns) com erro.")
            return lines
        case "task_error":
            return [f"[!] {p.get('message', 'erro desconhecido')}"]
        case "log":
            msg = p.get("message", "")
            return [msg] if msg else []
        case _:
            return []


def _resolve_stage_label(event: PipelineEvent) -> str | None:
    p = event.payload
    match event.type:
        case "progress_start":
            return "Iniciando..."
        case "queue_progress":
            cur = p.get("current_item", "?")
            tot = p.get("total_items", "?")
            name = p.get("item_name", "")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "image_op_start":
            op = p.get("operation", "")
            return {"download": "Baixando...", "convert": "Convertendo..."}.get(op, "Processando...")
        case "image_op_done":
            return "Concluído."
        case "image_op_error":
            return "Erro — continuando fila..."
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
            return "Erro no pipeline."
        case _:
            return None
