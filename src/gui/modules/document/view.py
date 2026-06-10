"""Módulo Documentos — visor adaptativo + log de pipeline."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from src.core.document.args import DocumentArgs
from src.gui.events import PipelineEvent
from src.gui.modules.base import Module
from src.gui.modules.document.form_view import DocumentFormPanel, build_document_form
from src.gui.modules.document import pipeline_log
from src.gui.modules.document.worker import start_document_pipeline
from src.gui.theme.tokens import Color, Radius, Space, Type
from src.gui.theme.components import (
    action_button,
    danger_button,
    hairline,
    log_line,
    output_card,
    spinner,
    summary_card,
)

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "document"
_MAX_LOG = 300

_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Viewer mode classification
_VISUAL_OPS     = {"rotate", "watermark", "stamp"}
_STRUCTURAL_OPS = {"merge", "split", "compress", "encrypt"}


def _rasterize_first_page(path: Path) -> bytes | None:
    """Rasterize first page at ~72dpi → PNG bytes for preview."""
    try:
        import pymupdf  # type: ignore[import-untyped]
        doc = pymupdf.open(str(path))
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.0, 1.0))
        data = pix.tobytes("png")
        doc.close()
        return data
    except Exception:
        return None


def build_document_module(
    page: ft.Page,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> Module:
    """Build the Documents module — form | adaptive viewer + log.

    Args:
        page: Flet page.
        bus: Shared application EventBus.
        cancel_event: threading.Event for cancellation.
        pipeline_running: Shared [bool] with app.py.
    """

    # ── Adaptive viewer — 3 modes in a Stack ──────────────────────────────────

    # Mode 1 — Before/After thumbnails (visual ops: rotate/watermark/stamp)
    _img_before = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    _img_after  = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    _last_input_thumb: list[bytes | None] = [None]

    _before_col = ft.Column(
        [
            ft.Text("Antes", size=Type.tiny.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(content=_img_before, expand=True, alignment=ft.Alignment.CENTER),
        ],
        expand=True, spacing=4,
    )
    _after_col = ft.Column(
        [
            ft.Text("Depois", size=Type.tiny.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(content=_img_after, expand=True, alignment=ft.Alignment.CENTER),
        ],
        expand=True, spacing=4,
    )
    _mode1_view = ft.Row(
        [_before_col, ft.VerticalDivider(width=1), _after_col],
        expand=True, visible=False,
    )

    # Mode 2 — Metadata diff card (structural ops: merge/split/compress/encrypt)
    _meta_content = ft.Column(spacing=4, expand=True)
    _mode2_view = ft.Container(
        content=_meta_content,
        expand=True, visible=False,
        padding=ft.Padding(left=Space.md, right=Space.md, top=Space.md, bottom=Space.md),
    )

    # Mode 3 — Single result pane (pdf_to_images, images_to_pdf, extract, analyze, qr)
    _result_img = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    _result_text = ft.Text(
        "", size=Type.mono.size, font_family=Type.FONT_MONO,
        color=Color.log.text, selectable=True, no_wrap=False,
        expand=True,
    )
    _result_text_scroll = ft.Column(
        [_result_text],
        scroll=ft.ScrollMode.AUTO, expand=True, visible=False,
    )
    _result_img_ctr = ft.Container(
        content=_result_img, expand=True,
        alignment=ft.Alignment.CENTER, visible=False,
    )
    _mode3_view = ft.Stack(
        [_result_img_ctr, _result_text_scroll],
        expand=True, visible=False,
    )

    # Placeholder
    _placeholder = ft.Container(
        content=ft.Text(
            "Selecione um PDF e a operação para começar",
            color=ft.Colors.ON_SURFACE_VARIANT, italic=True, size=Type.input.size,
        ),
        alignment=ft.Alignment.CENTER, expand=True, visible=True,
    )

    preview_container = ft.Container(
        content=ft.Stack(
            [_placeholder, _mode1_view, _mode2_view, _mode3_view],
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
        border_radius=Radius.sm,
        bgcolor=Color.dark.surface_variant,
    )

    def _show_placeholder() -> None:
        _placeholder.visible = True
        _mode1_view.visible = False
        _mode2_view.visible = False
        _mode3_view.visible = False

    def _show_mode1(before: bytes, after: bytes) -> None:
        _placeholder.visible = False
        _mode1_view.visible = True
        _mode2_view.visible = False
        _mode3_view.visible = False
        _img_before.src = before
        _img_after.src = after

    def _show_mode2(lines: list[str]) -> None:
        _placeholder.visible = False
        _mode1_view.visible = False
        _mode2_view.visible = True
        _mode3_view.visible = False
        _meta_content.controls = [
            ft.Text(l, size=Type.caption.size, selectable=True, no_wrap=False)
            for l in lines
        ]

    def _show_mode3_image(thumb: bytes) -> None:
        _placeholder.visible = False
        _mode1_view.visible = False
        _mode2_view.visible = False
        _mode3_view.visible = True
        _result_img.src = thumb
        _result_img_ctr.visible = True
        _result_text_scroll.visible = False

    def _show_mode3_text(text: str) -> None:
        _placeholder.visible = False
        _mode1_view.visible = False
        _mode2_view.visible = False
        _mode3_view.visible = True
        _result_text.value = text[:2000]
        _result_img_ctr.visible = False
        _result_text_scroll.visible = True

    # ── Log panel ─────────────────────────────────────────────────────────────

    spin_img, _start_spin, _stop_spin = spinner()

    stage_label = ft.Text(
        "Inicie o pipeline pelo formulário →",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    progress_bar = ft.ProgressBar(
        value=None, expand=True,
        color=ft.Colors.PRIMARY,
        bgcolor=ft.Colors.OUTLINE_VARIANT,
        visible=False,
    )

    log_list = ft.ListView(
        spacing=Space.xxs,
        padding=ft.Padding(left=6, right=6, top=4, bottom=4),
        auto_scroll=True,
    )

    def _append_log(text: str, mutable: bool = False) -> None:
        if mutable and log_list.controls:
            log_list.controls[-1] = log_line(text)
        else:
            log_list.controls.append(log_line(text))
        if len(log_list.controls) > _MAX_LOG:
            log_list.controls = log_list.controls[-_MAX_LOG:]

    cancel_btn = danger_button(
        "Cancelar",
        icon=ft.Icons.CANCEL_OUTLINED,
        on_click=lambda _: cancel_event.set(),
    )

    def _open_output_folder(_e) -> None:
        from src.utils import DOCUMENT_PROCESSED_DIR
        DOCUMENT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["explorer", str(DOCUMENT_PROCESSED_DIR)], check=False)

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
                border_radius=Radius.sm,
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

    # ── pubsub handler ─────────────────────────────────────────────────────────

    _last_op: list[str] = ["merge"]

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

        elif t == "document_op_start":
            op = p.get("operation", "")
            _last_op[0] = op

        elif t == "document_op_done":
            op = p.get("operation", _last_op[0])
            output_path = p.get("output_path", "")
            extra = p.get("extra_stats", {})
            src_bytes = p.get("src_size_bytes", 0)
            out_bytes = p.get("out_size_bytes", 0)

            if op in _VISUAL_OPS:
                # Mode 1: before/after thumbnails
                in_thumb = _last_input_thumb[0]
                out_thumb = _rasterize_first_page(Path(output_path)) if output_path else None
                if in_thumb and out_thumb:
                    _show_mode1(in_thumb, out_thumb)
                else:
                    _show_placeholder()

            elif op in _STRUCTURAL_OPS:
                # Mode 2: metadata diff card
                lines = _build_meta_lines(op, output_path, src_bytes, out_bytes, extra)
                _show_mode2(lines)

            elif op == "qr" and output_path:
                # Mode 3: QR image
                try:
                    thumb = Path(output_path).read_bytes()
                    _show_mode3_image(thumb)
                except Exception:
                    _show_placeholder()

            elif op == "extract" and output_path:
                # Mode 3: text preview
                try:
                    text = Path(output_path).read_text(encoding="utf-8")
                    _show_mode3_text(text[:500])
                except Exception:
                    _show_placeholder()

            elif op == "pdf_to_images" and output_path:
                # Mode 3: first image thumbnail
                try:
                    thumb = Path(output_path).read_bytes()
                    _show_mode3_image(thumb)
                except Exception:
                    _show_placeholder()

            elif op == "images_to_pdf" and output_path:
                # Mode 3: first page rasterized
                out_thumb = _rasterize_first_page(Path(output_path))
                if out_thumb:
                    _show_mode3_image(out_thumb)
                else:
                    _show_placeholder()

            progress_bar.value = 1.0

        for msg in pipeline_log.resolve_messages(event):
            mutable = p.get("mutable", False) if t == "log" else False
            _append_log(msg, mutable=mutable)

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

    # ── Form handlers ──────────────────────────────────────────────────────────

    def _on_start(args: DocumentArgs) -> None:
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
        _show_placeholder()
        _last_input_thumb[0] = None
        _last_op[0] = args.operation

        # Capture first-page thumb for visual ops before-after
        if args.operation in _VISUAL_OPS and args.input_paths:
            _last_input_thumb[0] = _rasterize_first_page(args.input_paths[0])

        form_panel.set_running(True)
        page.update()
        start_document_pipeline(args, bus, cancel_event, pipeline_running)

    # ── Panels + layout ────────────────────────────────────────────────────────

    form_panel: DocumentFormPanel = build_document_form(page, on_start=_on_start)

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
        id="document",
        label="Documentos",
        icon=ft.Icons.DESCRIPTION_OUTLINED,
        selected_icon=ft.Icons.DESCRIPTION,
        control=control,
    )


def _build_meta_lines(
    op: str,
    output_path: str,
    src_bytes: int,
    out_bytes: int,
    extra: dict,
) -> list[str]:
    """Build display lines for the metadata diff card (Mode 2)."""
    name = Path(output_path).name if output_path else "—"

    def _mb(b: int) -> str:
        return f"{b / 1_048_576:.1f} MB" if b >= 1_048_576 else f"{b / 1024:.0f} KB"

    match op:
        case "merge":
            page_total = extra.get("page_total", 0)
            file_count = extra.get("file_count", 0)
            return [
                f"📄  {name}",
                f"{file_count} arquivos  ·  {page_total} páginas  →  1 arquivo  ·  {page_total} páginas",
            ]
        case "split":
            files = extra.get("output_files", [])
            counts = extra.get("page_counts", [])
            lines = [f"📄  {name}  →  {len(files)} arquivos"]
            for fname, n in zip(files, counts):
                lines.append(f"  {fname}   {n} pág.")
            return lines
        case "compress":
            pct = extra.get("size_reduction_pct", 0.0)
            return [
                f"📄  {name}",
                f"{_mb(src_bytes)}  →  {_mb(out_bytes)}  ·  −{pct:.0f}%",
            ]
        case "encrypt":
            return [
                f"🔒  {name}",
                "Documento protegido com senha",
            ]
        case _:
            return [f"📄  {name}"]
