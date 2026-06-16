"""Formulário de entrada do módulo Documentos — 12 operações PDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.document.args import DocumentArgs
from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.modules.document.blocks.analyze_block import build_analyze_block
from src.gui.modules.document.blocks.compress_block import build_compress_block
from src.gui.modules.document.blocks.encrypt_block import build_encrypt_block
from src.gui.modules.document.blocks.extract_text_block import build_extract_text_block
from src.gui.modules.document.blocks.images_to_pdf_block import (
    build_images_to_pdf_block,
)
from src.gui.modules.document.blocks.merge_block import build_merge_block
from src.gui.modules.document.blocks.ocr_block import build_ocr_block
from src.gui.modules.document.blocks.pdf_to_images_block import (
    build_pdf_to_images_block,
)
from src.gui.modules.document.blocks.qr_block import build_qr_block
from src.gui.modules.document.blocks.rotate_block import build_rotate_block
from src.gui.modules.document.blocks.split_block import build_split_block
from src.gui.modules.document.blocks.stamp_block import build_stamp_block
from src.gui.modules.document.blocks.watermark_block import build_watermark_block
from src.gui.theme.components import Cursor, hairline, section
from src.gui.theme.tokens import Space, Type

_ALLOWED_EXTS = ["pdf"]
_ALLOWED_IMG_EXTS = ["jpg", "jpeg", "png", "webp", "tiff", "bmp"]

_OPS: list[tuple[str, str, str]] = [
    ("merge", ft.Icons.MERGE_TYPE, "Unir"),
    ("split", ft.Icons.CALL_SPLIT, "Dividir"),
    ("compress", ft.Icons.COMPRESS, "Comprimir"),
    ("rotate", ft.Icons.ROTATE_90_DEGREES_CW, "Girar"),
    ("watermark", ft.Icons.WATER_DROP_OUTLINED, "Marca\nd'água"),
    ("stamp", ft.Icons.APPROVAL_OUTLINED, "Carimbo"),
    ("encrypt", ft.Icons.LOCK_OUTLINED, "Criptografar"),
    ("pdf_to_images", ft.Icons.IMAGE_OUTLINED, "PDF→\nImagens"),
    ("images_to_pdf", ft.Icons.PICTURE_AS_PDF_OUTLINED, "Imagens\n→PDF"),
    ("extract", ft.Icons.TEXT_SNIPPET_OUTLINED, "Extrair\ntexto"),
    ("ocr", ft.Icons.DOCUMENT_SCANNER_OUTLINED, "OCR"),
    ("analyze", ft.Icons.AUTO_AWESOME_OUTLINED, "Analisar"),
    ("qr", ft.Icons.QR_CODE_2, "QR Code"),
]

# Operations that accept multiple input files
_MULTI_INPUT_OPS = {"merge", "images_to_pdf"}
# Operations that accept only images as input
_IMAGE_INPUT_OPS = {"images_to_pdf"}
# Operations with no file input (standalone)
_NO_FILE_OPS = {"qr"}


@dataclass
class DocumentFormPanel:
    """Form panel with control methods."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


def build_document_form(
    page: ft.Page,
    on_start: Callable[[DocumentArgs], None],
) -> DocumentFormPanel:
    """Build the document module form.

    Args:
        page: Flet page.
        on_start: Called with DocumentArgs when the user clicks Start.
    """

    # ── Selected operation state ───────────────────────────────────────────────

    _current_op: list[str] = ["merge"]
    _card_ctr_refs: dict[str, ft.Container] = {}
    _card_icon_refs: dict[str, ft.Icon] = {}
    _card_text_refs: dict[str, ft.Text] = {}
    _param_blocks: dict[str, ft.Column] = {}

    # ── InputSource ────────────────────────────────────────────────────────────

    def _on_items_change(items: list[InputItem]) -> None:
        op = _current_op[0]
        has_items = len(items) > 0 or op in _NO_FILE_OPS
        start_btn.disabled = not has_items
        try:
            start_btn.update()
        except RuntimeError:
            pass

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
        url_hint="URL direta de um PDF para download",
    )

    # ── Operation Card Grid ────────────────────────────────────────────────────

    def _refresh_cards() -> None:
        for oid, ctr in _card_ctr_refs.items():
            active = oid == _current_op[0]
            color = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
            bw = 2 if active else 1
            bc = ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT
            side = ft.BorderSide(bw, bc)
            _card_icon_refs[oid].color = color
            _card_text_refs[oid].color = color
            ctr.border = ft.Border(left=side, right=side, top=side, bottom=side)

    def _select_op(op_id: str) -> None:
        _current_op[0] = op_id
        _refresh_cards()
        _refresh_param_blocks()
        # Adjust input source for multi-file vs single-file operations
        _update_input_source(op_id)
        page.update()

    def _update_input_source(op_id: str) -> None:
        """Narrow the picker's allowed extensions to the selected operation.

        Flet's pick_files() takes allowed_extensions per call, so InputSource
        reads this list on each open (see set_allowed_extensions). 'analyze'
        also accepts text files (.txt/.md) so an extracted/described text can be
        analyzed directly, without a PDF.
        """
        if op_id == "analyze":
            exts = ["pdf", "txt", "md"]
        elif op_id in _IMAGE_INPUT_OPS:
            exts = _ALLOWED_IMG_EXTS
        elif op_id in _NO_FILE_OPS:
            exts = []
        else:
            exts = _ALLOWED_EXTS
        input_source.set_allowed_extensions(exts)

    def _make_card(op_id: str, icon_name: str, label: str) -> ft.GestureDetector:
        ic = ft.Icon(icon_name, size=22, color=ft.Colors.PRIMARY)
        tx = ft.Text(
            label,
            size=Type.small.size,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.PRIMARY,
            max_lines=2,
        )
        _card_icon_refs[op_id] = ic
        _card_text_refs[op_id] = tx
        side = ft.BorderSide(2, ft.Colors.PRIMARY)
        ctr = ft.Container(
            content=ft.Column(
                [ic, tx],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                tight=True,
            ),
            height=64,
            padding=6,
            border_radius=8,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border(left=side, right=side, top=side, bottom=side),
            shadow=ft.BoxShadow(
                blur_radius=8,
                spread_radius=0,
                offset=ft.Offset(0, 3),
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            ),
            on_click=lambda e, oid=op_id: _select_op(oid),
            alignment=ft.Alignment.CENTER,
        )
        _card_ctr_refs[op_id] = ctr
        return ft.GestureDetector(
            mouse_cursor=Cursor.interactive, content=ctr, expand=True
        )

    _cards = [_make_card(oid, icon, lbl) for oid, icon, lbl in _OPS]
    _cols = 3
    card_grid = ft.Column(
        spacing=6,
        controls=[
            ft.Row(controls=_cards[i : i + _cols], spacing=6)
            for i in range(0, len(_cards), _cols)
        ],
    )
    _refresh_cards()

    # ── Parameter blocks ───────────────────────────────────────────────────────

    merge_block = build_merge_block()
    split_block, split_refs = build_split_block(page)
    compress_block, compress_refs = build_compress_block(page)
    rotate_block, rotate_refs = build_rotate_block(page)
    watermark_block, wm_refs = build_watermark_block(page)
    stamp_block, stamp_refs = build_stamp_block(page)
    encrypt_block, encrypt_refs = build_encrypt_block(page)
    pdf_to_images_block, p2i_refs = build_pdf_to_images_block(page)
    images_to_pdf_block, i2p_refs = build_images_to_pdf_block()
    extract_text_block = build_extract_text_block()
    ocr_block, ocr_refs = build_ocr_block(page)
    analyze_block, analyze_refs = build_analyze_block(page)
    qr_block, qr_refs = build_qr_block(page)

    _param_blocks["merge"] = merge_block
    _param_blocks["split"] = split_block
    _param_blocks["compress"] = compress_block
    _param_blocks["rotate"] = rotate_block
    _param_blocks["watermark"] = watermark_block
    _param_blocks["stamp"] = stamp_block
    _param_blocks["encrypt"] = encrypt_block
    _param_blocks["pdf_to_images"] = pdf_to_images_block
    _param_blocks["images_to_pdf"] = images_to_pdf_block
    _param_blocks["extract"] = extract_text_block
    _param_blocks["ocr"] = ocr_block
    _param_blocks["analyze"] = analyze_block
    _param_blocks["qr"] = qr_block

    # Disable the OCR card when Tesseract isn't available (graceful degradation).
    if not ocr_refs.available:
        _ocr_card = _card_ctr_refs["ocr"]
        _ocr_card.disabled = True
        _ocr_card.tooltip = (
            "Tesseract não encontrado — instale o binário + uv sync --extra ocr"
        )

    def _refresh_param_blocks() -> None:
        for op_id, blk in _param_blocks.items():
            blk.visible = op_id == _current_op[0]

    _refresh_param_blocks()
    # Set merge as initially visible
    merge_block.visible = True

    # ── Start button ───────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _on_start_click() -> None:
        op = _current_op[0]
        items = input_source.get_items() if op not in _NO_FILE_OPS else []

        if op not in _NO_FILE_OPS and not items:
            return

        input_paths = [Path(it.value) for it in items if it.kind == "local"]

        args = DocumentArgs(
            input_paths=input_paths,
            operation=op,
            pages=split_refs.get_pages()
            if op == "split"
            else rotate_refs.get_pages()
            if op == "rotate"
            else "",
            image_quality=compress_refs.get_image_quality(),
            angle=rotate_refs.get_angle(),
            rotate_pages=rotate_refs.get_pages(),
            watermark_text=wm_refs.get_text(),
            watermark_opacity=wm_refs.get_opacity(),
            watermark_position=wm_refs.get_position(),
            stamp_text=stamp_refs.get_text(),
            password=encrypt_refs.get_password(),
            image_fmt=p2i_refs.get_fmt(),
            dpi=p2i_refs.get_dpi(),
            output_name=i2p_refs.get_output_name(),
            qr_data=qr_refs.get_data(),
            qr_size=qr_refs.get_size(),
            qr_fmt=qr_refs.get_fmt(),
            analyze_model=analyze_refs.get_model(),
            ocr_lang=ocr_refs.get_lang(),
            ocr_dpi=ocr_refs.get_dpi(),
        )
        on_start(args)

    def _set_running(running: bool) -> None:
        start_btn.disabled = running
        try:
            start_btn.update()
        except RuntimeError:
            pass

    # ── fill_from_path (bridge on_mount) ─────────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── Layout ─────────────────────────────────────────────────────────────────

    params_stack = ft.Stack(
        controls=list(_param_blocks.values()),
        expand=False,
    )

    form_col = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        expand=True,
        controls=[
            ft.Container(
                padding=Space.xl,
                content=ft.Column(
                    spacing=Space.md,
                    controls=[
                        section(
                            "Entrada",
                            input_source.control,
                            help_key="document.input",
                            page=page,
                        ),
                        hairline(),
                        section("Operação", card_grid),
                        hairline(),
                        params_stack,
                        hairline(),
                        ft.Row(
                            controls=[start_btn],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                ),
            ),
        ],
    )

    return DocumentFormPanel(
        control=form_col,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
