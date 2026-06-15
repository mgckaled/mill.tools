"""Formulário de entrada do módulo Imagens — operações de conversão e manipulação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from src.core.image.background import is_available as _rembg_ok
from src.core.image.args import ImageArgs
from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.modules.image.blocks.adjust import build_adjust_block
from src.gui.modules.image.blocks.ai import build_ai_blocks
from src.gui.modules.image.blocks.border import build_border_block
from src.gui.modules.image.blocks.contact_sheet import build_contact_sheet_block
from src.gui.modules.image.blocks.convert_fmt import build_fmt_section
from src.gui.modules.image.blocks.crop import build_crop_block
from src.gui.modules.image.blocks.favicon import build_favicon_block
from src.gui.modules.image.blocks.filter import build_filter_block
from src.gui.modules.image.blocks.resize import build_resize_block
from src.gui.modules.image.blocks.rotate import build_rotate_block
from src.gui.modules.image.blocks.watermark import build_watermark_block
from src.gui.theme.components import (
    Cursor,
    hairline,
    section,
)
from src.gui.theme.tokens import Space, Type

_ALLOWED_EXTS = [
    "jpg",
    "jpeg",
    "png",
    "webp",
    "avif",
    "tiff",
    "tif",
    "bmp",
    "gif",
    "ico",
]

_OPS: list[tuple[str, str, str]] = [
    ("convert", ft.Icons.SWAP_HORIZ, "Converter"),
    ("resize", ft.Icons.OPEN_IN_FULL, "Redimensionar"),
    ("crop", ft.Icons.CROP, "Cortar"),
    ("rotate", ft.Icons.ROTATE_90_DEGREES_CW, "Girar"),
    ("watermark", ft.Icons.WATER_DROP_OUTLINED, "Marca d'água"),
    ("border", ft.Icons.BORDER_OUTER, "Borda"),
    ("adjust", ft.Icons.TUNE, "Ajustes"),
    ("filter", ft.Icons.FILTER, "Filtros"),
    ("favicon", ft.Icons.GRID_VIEW, "Favicon"),
    ("contact_sheet", ft.Icons.DASHBOARD_OUTLINED, "Colagem"),
    ("remove_bg", ft.Icons.AUTO_FIX_HIGH, "Remover\nfundo"),
    ("describe", ft.Icons.DESCRIPTION_OUTLINED, "Descrever"),
]

_UNAVAILABLE: dict[str, str] = {}
if not _rembg_ok():
    _UNAVAILABLE["remove_bg"] = "Instale com: uv sync --extra ai-image"


@dataclass
class ImageFormPanel:
    """Painel do formulário de imagens com métodos de controle."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


def build_image_form(
    page: ft.Page,
    on_start: Callable[[ImageArgs], None],
) -> ImageFormPanel:
    """Constrói o formulário do módulo Imagens.

    Args:
        page: Página Flet.
        on_start: Chamado com ImageArgs ao clicar Iniciar.
    """

    # ── Estado da operação selecionada ────────────────────────────────────────

    _current_op: list[str] = ["convert"]
    _card_ctr_refs: dict[str, ft.Container] = {}
    _card_icon_refs: dict[str, ft.Icon] = {}
    _card_text_refs: dict[str, ft.Text] = {}
    _param_blocks: dict[str, ft.Column] = {}

    # ── InputSource ───────────────────────────────────────────────────────────

    def _on_items_change(items: list[InputItem]) -> None:
        start_btn.disabled = len(items) == 0
        if start_btn.page:
            start_btn.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
        url_hint="URL direta da imagem (unsplash, pexels…)",
    )

    # ── Operation Card Grid ───────────────────────────────────────────────────

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
        fmt_refs.set_operation(op_id)
        page.update()

    def _make_card(op_id: str, icon_name: str, label: str) -> ft.Container:
        ic = ft.Icon(icon_name, size=24, color=ft.Colors.PRIMARY)
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
                spacing=6,
                tight=True,
            ),
            height=70,
            padding=8,
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
        if op_id in _UNAVAILABLE:
            ctr.tooltip = _UNAVAILABLE[op_id]
            ctr.disabled = True
            ic.color = ft.Colors.ON_SURFACE_VARIANT
            tx.color = ft.Colors.ON_SURFACE_VARIANT
            ctr.on_click = None
        return ft.GestureDetector(
            mouse_cursor=Cursor.interactive, content=ctr, expand=True
        )

    _cards = [_make_card(oid, icon, lbl) for oid, icon, lbl in _OPS]
    _cols = 3
    while len(_cards) % _cols != 0:
        _cards.append(ft.Container(expand=True))
    card_grid = ft.Column(
        spacing=6,
        controls=[
            ft.Row(controls=_cards[i : i + _cols], spacing=6)
            for i in range(0, len(_cards), _cols)
        ],
    )

    _refresh_cards()

    # ── Blocos de parâmetros ──────────────────────────────────────────────────

    resize_block, resize_refs = build_resize_block(page)
    crop_block, crop_refs = build_crop_block(page)
    rotate_block, rotate_refs = build_rotate_block(page)
    watermark_block, wm_refs = build_watermark_block(page)
    border_block, border_refs = build_border_block(page)
    adjust_block, adjust_refs = build_adjust_block(page)
    filter_block, filter_refs = build_filter_block(page)
    favicon_block, favicon_refs = build_favicon_block(page)
    cs_block, cs_refs = build_contact_sheet_block(page)
    ai_refs = build_ai_blocks(page)

    _param_blocks["convert"] = ft.Column(visible=False, spacing=0)
    _param_blocks["resize"] = resize_block
    _param_blocks["crop"] = crop_block
    _param_blocks["rotate"] = rotate_block
    _param_blocks["watermark"] = watermark_block
    _param_blocks["border"] = border_block
    _param_blocks["adjust"] = adjust_block
    _param_blocks["filter"] = filter_block
    _param_blocks["favicon"] = favicon_block
    _param_blocks["contact_sheet"] = cs_block
    _param_blocks["remove_bg"] = ai_refs.rembg_block
    _param_blocks["describe"] = ai_refs.describe_block

    # ── Format section ────────────────────────────────────────────────────────

    fmt_refs = build_fmt_section(page)

    # ── Refresh param blocks ──────────────────────────────────────────────────

    def _refresh_param_blocks() -> None:
        for op_id, blk in _param_blocks.items():
            blk.visible = op_id == _current_op[0]

    # ── Botão Iniciar ─────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _on_start_click() -> None:
        items = input_source.get_items()
        if not items:
            return
        op = _current_op[0]

        args = ImageArgs(
            items=items,
            operation=op,
            # convert
            fmt=fmt_refs.get_fmt() if op == "convert" else "jpg",
            quality=fmt_refs.get_quality(),
            # shared output
            out_fmt=fmt_refs.get_out_fmt(),
            out_quality=fmt_refs.get_out_quality(),
            # resize
            resize_mode=resize_refs.get_mode(),
            resize_width=resize_refs.get_width(),
            resize_height=resize_refs.get_height(),
            resize_scale_pct=resize_refs.get_scale_pct(),
            # crop
            crop_mode=crop_refs.get_mode(),
            crop_left=crop_refs.get_left(),
            crop_top=crop_refs.get_top(),
            crop_width=crop_refs.get_width(),
            crop_height=crop_refs.get_height(),
            crop_ratio=crop_refs.get_ratio(),
            crop_trim_color=crop_refs.get_trim_color(),
            # rotate
            rotate_angle=rotate_refs.get_angle(),
            rotate_flip_h=rotate_refs.get_flip_h(),
            rotate_flip_v=rotate_refs.get_flip_v(),
            rotate_exif_auto=rotate_refs.get_exif_auto(),
            # watermark
            wm_mode=wm_refs.get_mode(),
            wm_text=wm_refs.get_text(),
            wm_text_color=wm_refs.get_text_color(),
            wm_text_size=wm_refs.get_text_size(),
            wm_path=wm_refs.get_path(),
            wm_position=wm_refs.get_position(),
            wm_opacity=wm_refs.get_opacity(),
            # border
            border_padding=border_refs.get_padding(),
            border_color=border_refs.get_color(),
            border_fill_alpha=border_refs.get_fill_alpha(),
            # adjust
            adj_brightness=adjust_refs.get_brightness(),
            adj_contrast=adjust_refs.get_contrast(),
            adj_color=adjust_refs.get_color(),
            adj_sharpness=adjust_refs.get_sharpness(),
            # filter
            filter_type=filter_refs.get_type(),
            # favicon
            favicon_sizes=favicon_refs.get_sizes(),
            # contact_sheet
            cs_cols=cs_refs.get_cols(),
            cs_thumb_size=cs_refs.get_thumb_size(),
            cs_gap=cs_refs.get_gap(),
            cs_bg_color=cs_refs.get_bg_color(),
            # remove_bg
            rembg_model=ai_refs.get_rembg_model() if op == "remove_bg" else "u2net",
            # describe
            describe_model=ai_refs.get_desc_model()
            if op == "describe"
            else "moondream-custom",
            describe_prompt=ai_refs.get_desc_prompt() if op == "describe" else "",
        )
        on_start(args)

    # ── set_running ───────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = (
            ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        )
        input_source.set_enabled(not running)
        for oid, ctr in _card_ctr_refs.items():
            ctr.disabled = running or (oid in _UNAVAILABLE)
        fmt_refs.set_disabled(running)
        ai_refs.set_rembg_disabled(running or not _rembg_ok())
        ai_refs.set_desc_disabled(running)
        page.update()

    # ── fill_from_path (bridge on_mount) ──────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── Layout ────────────────────────────────────────────────────────────────

    params_container = ft.Column(
        spacing=Space.sm,
        controls=list(_param_blocks.values()),
    )

    control = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        spacing=0,
        expand=True,
        controls=[
            ft.Container(
                padding=20,
                content=ft.Column(
                    spacing=16,
                    controls=[
                        section(
                            "Entrada",
                            input_source.control,
                            help_key="image.input",
                            page=page,
                        ),
                        hairline(),
                        section("Operação", card_grid),
                        hairline(),
                        params_container,
                        hairline(),
                        fmt_refs.control,
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

    return ImageFormPanel(
        control=control,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
