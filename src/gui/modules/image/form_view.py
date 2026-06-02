"""Formulário de entrada do módulo Imagens — operações de conversão e manipulação."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.components.input_source import InputItem, build_input_source
from src.gui.theme.components import (
    hairline,
    help_icon_for,
    section,
    section_label,
    segmented_selector,
)
from src.gui.theme.tokens import Space, Type

_ALLOWED_EXTS = [
    "jpg", "jpeg", "png", "webp", "avif",
    "tiff", "tif", "bmp", "gif", "ico",
]

_FMT_OPTIONS = ["jpg", "png", "webp", "avif", "tiff", "bmp", "gif", "ico"]
_LOSSY_FMTS: frozenset[str] = frozenset({"jpg", "webp"})

_QUALITY_DEFAULT = 90.0
_QUALITY_MIN = 50.0
_QUALITY_MAX = 100.0

_OPS: list[tuple[str, str, str]] = [
    ("convert",       ft.Icons.SWAP_HORIZ,          "Converter"),
    ("resize",        ft.Icons.OPEN_IN_FULL,         "Redimensionar"),
    ("crop",          ft.Icons.CROP,                 "Cortar"),
    ("rotate",        ft.Icons.ROTATE_90_DEGREES_CW, "Girar"),
    ("watermark",     ft.Icons.WATER_DROP_OUTLINED,  "Marca d'água"),
    ("border",        ft.Icons.BORDER_OUTER,         "Borda"),
    ("adjust",        ft.Icons.TUNE,                 "Ajustes"),
    ("filter",        ft.Icons.FILTER,               "Filtros"),
    ("favicon",       ft.Icons.GRID_VIEW,            "Favicon"),
    ("contact_sheet", ft.Icons.DASHBOARD_OUTLINED,   "Colagem"),
]


@dataclass
class ImageArgs:
    """Parâmetros do pipeline de imagens recebidos do formulário."""

    items: list[InputItem] = field(default_factory=list)
    operation: str = "convert"

    # ── convert ──────────────────────────────────────────────
    fmt: str = "jpg"
    quality: int = 90

    # ── saída para manipulação (None = preserva original) ────
    out_fmt: str | None = None
    out_quality: int = 90

    # ── resize ───────────────────────────────────────────────
    resize_mode: str = "contain"
    resize_width: int | None = None
    resize_height: int | None = None
    resize_scale_pct: float = 100.0

    # ── crop ─────────────────────────────────────────────────
    crop_mode: str = "manual"
    crop_left: int = 0
    crop_top: int = 0
    crop_width: int = 0
    crop_height: int = 0
    crop_ratio: str = "1:1"
    crop_trim_color: str = "#ffffff"

    # ── rotate ───────────────────────────────────────────────
    rotate_angle: int = 0
    rotate_flip_h: bool = False
    rotate_flip_v: bool = False
    rotate_exif_auto: bool = False

    # ── watermark ────────────────────────────────────────────
    wm_mode: str = "text"
    wm_text: str = ""
    wm_text_color: str = "#ffffff"
    wm_text_size: int = 40
    wm_path: Path | None = None
    wm_position: str = "bottom-right"
    wm_opacity: float = 0.5

    # ── border ───────────────────────────────────────────────
    border_padding: int = 20
    border_color: str = "#000000"
    border_fill_alpha: bool = False

    # ── adjust ───────────────────────────────────────────────
    adj_brightness: float = 1.0
    adj_contrast: float = 1.0
    adj_color: float = 1.0
    adj_sharpness: float = 1.0

    # ── filter ───────────────────────────────────────────────
    filter_type: str = "blur"

    # ── favicon ──────────────────────────────────────────────
    favicon_sizes: list[int] = field(default_factory=lambda: [16, 32, 48, 64, 128, 256])

    # ── contact_sheet ────────────────────────────────────────
    cs_cols: int = 4
    cs_thumb_size: int = 200
    cs_gap: int = 10
    cs_bg_color: str = "#ffffff"


@dataclass
class ImageFormPanel:
    """Painel do formulário de imagens com métodos de controle."""

    control: ft.Control
    set_running: Callable[[bool], None]


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
        _refresh_format_block()
        page.update()

    def _make_card(op_id: str, icon_name: str, label: str) -> ft.Container:
        ic = ft.Icon(icon_name, size=24, color=ft.Colors.PRIMARY)
        tx = ft.Text(
            label, size=11, text_align=ft.TextAlign.CENTER,
            color=ft.Colors.PRIMARY, max_lines=2,
        )
        _card_icon_refs[op_id] = ic
        _card_text_refs[op_id] = tx
        side = ft.BorderSide(2, ft.Colors.PRIMARY)
        ctr = ft.Container(
            content=ft.Column(
                [ic, tx],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=6, tight=True,
            ),
            height=70, padding=8, border_radius=8,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border(left=side, right=side, top=side, bottom=side),
            shadow=ft.BoxShadow(
                blur_radius=8, spread_radius=0,
                offset=ft.Offset(0, 3),
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            ),
            on_click=lambda e, oid=op_id: _select_op(oid),
            alignment=ft.Alignment.CENTER,
        )
        _card_ctr_refs[op_id] = ctr
        return ft.GestureDetector(mouse_cursor=ft.MouseCursor.CLICK, content=ctr, expand=True)

    # Grade fixa 3 colunas × 4 linhas — spacers invisíveis completam a última linha
    _cards = [_make_card(oid, icon, lbl) for oid, icon, lbl in _OPS]
    _cols = 3
    while len(_cards) % _cols != 0:
        _cards.append(ft.Container(expand=True))  # slot vazio para alinhar
    card_grid = ft.Column(
        spacing=6,
        controls=[
            ft.Row(controls=_cards[i:i + _cols], spacing=6)
            for i in range(0, len(_cards), _cols)
        ],
    )

    # Deixar "convert" ativo visualmente (sem update — ainda não montado)
    _refresh_cards()

    # ── Blocos de parâmetros ──────────────────────────────────────────────────

    # -- resize ---------------------------------------------------------------
    _resize_mode_get: list[Callable] = []
    _resize_w_tf = ft.TextField(
        hint_text="Largura px (opcional)", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _resize_h_tf = ft.TextField(
        hint_text="Altura px (opcional)", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _resize_scale_val: list[float] = [100.0]
    _resize_scale_lbl = ft.Text("100%", size=13, weight=ft.FontWeight.W_600,
                                 color=ft.Colors.PRIMARY)
    _resize_scale_slider = ft.Slider(
        value=100.0, min=1.0, max=400.0, divisions=399,
        active_color=ft.Colors.PRIMARY, expand=True,
    )

    def _on_resize_scale_change(e: ft.ControlEvent) -> None:
        _resize_scale_val[0] = float(e.control.value)

    def _on_resize_scale_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _resize_scale_val[0] = v
        _resize_scale_lbl.value = f"{int(v)}%"
        try:
            if _resize_scale_lbl.page:
                _resize_scale_lbl.update()
        except RuntimeError:
            pass

    _resize_scale_slider.on_change = _on_resize_scale_change
    _resize_scale_slider.on_change_end = _on_resize_scale_end

    _resize_wh_row = ft.Row([_resize_w_tf, _resize_h_tf], spacing=8)
    _resize_scale_row = ft.Row(
        [_resize_scale_slider, _resize_scale_lbl], spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    def _on_resize_mode_change(mode: str) -> None:
        _resize_wh_row.visible = mode in ("contain", "exact")
        _resize_scale_row.visible = mode == "scale_pct"
        try:
            if card_grid.page:
                card_grid.page.update()
        except RuntimeError:
            pass

    _rsz_grid, _rsz_get, _rsz_set_disabled = segmented_selector(
        ["contain", "exact", "scale_pct"],
        "contain", page,
        on_change=_on_resize_mode_change,
        labels={"contain": "Caber", "exact": "Exato", "scale_pct": "Escala %"},
        columns=3,
    )
    _resize_mode_get.append(_rsz_get)
    _resize_scale_row.visible = False  # "contain" é padrão

    resize_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Redimensionar"), ft.Container(expand=True), help_icon_for("image.resize", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Modo"),
            _rsz_grid,
            ft.Row([section_label("Dimensões")]),
            _resize_wh_row,
            ft.Row([section_label("Escala"), ft.Container(expand=True), _resize_scale_lbl]),
            _resize_scale_row,
        ],
    )
    _param_blocks["resize"] = resize_block

    # -- crop -----------------------------------------------------------------
    _crop_mode_get: list[Callable] = []
    _crop_left_tf = ft.TextField(
        hint_text="Esquerda px", value="0", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _crop_top_tf = ft.TextField(
        hint_text="Topo px", value="0", keyboard_type=ft.KeyboardType.NUMBER,
        text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _crop_w_tf = ft.TextField(
        hint_text="Largura px (0=até borda)", value="0",
        keyboard_type=ft.KeyboardType.NUMBER, text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _crop_h_tf = ft.TextField(
        hint_text="Altura px (0=até borda)", value="0",
        keyboard_type=ft.KeyboardType.NUMBER, text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _crop_trim_color_tf = ft.TextField(
        value="#ffffff", text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
    )

    _crop_manual_col = ft.Column([
        ft.Row([_crop_left_tf, _crop_top_tf], spacing=8),
        ft.Row([_crop_w_tf, _crop_h_tf], spacing=8),
    ], spacing=Space.sm)

    _crop_ratio_get: list[Callable] = []
    _ratio_grid, _ratio_get, _ratio_set_disabled = segmented_selector(
        ["1:1", "4:3", "16:9", "3:2"],
        "1:1", page, columns=4,
    )
    _crop_ratio_get.append(_ratio_get)
    _crop_ratio_col = ft.Column([section_label("Proporção"), _ratio_grid], spacing=Space.sm)

    _crop_autotrim_col = ft.Column([
        section_label("Cor de fundo a remover"),
        _crop_trim_color_tf,
    ], spacing=Space.sm)

    def _on_crop_mode_change(mode: str) -> None:
        _crop_manual_col.visible = mode == "manual"
        _crop_ratio_col.visible = mode == "ratio"
        _crop_autotrim_col.visible = mode == "autotrim"
        try:
            if card_grid.page:
                card_grid.page.update()
        except RuntimeError:
            pass

    _crop_grid, _crop_get, _crop_set_disabled = segmented_selector(
        ["manual", "ratio", "autotrim"],
        "manual", page,
        on_change=_on_crop_mode_change,
        labels={"manual": "Manual", "ratio": "Proporção", "autotrim": "Auto-trim"},
        columns=3,
    )
    _crop_mode_get.append(_crop_get)
    _crop_ratio_col.visible = False
    _crop_autotrim_col.visible = False

    crop_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Cortar"), ft.Container(expand=True), help_icon_for("image.crop", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Modo"), _crop_grid,
            _crop_manual_col, _crop_ratio_col, _crop_autotrim_col,
        ],
    )
    _param_blocks["crop"] = crop_block

    # -- rotate ---------------------------------------------------------------
    _rotate_angle_get: list[Callable] = []
    _rot_grid, _rot_get, _rot_set_disabled = segmented_selector(
        ["0", "90", "180", "270"],
        "0", page,
        labels={"0": "0°", "90": "90°", "180": "180°", "270": "270°"},
        columns=4,
    )
    _rotate_angle_get.append(_rot_get)

    _rotate_flip_h_sw = ft.Switch(
        label="Espelhar horizontal",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )
    _rotate_flip_v_sw = ft.Switch(
        label="Espelhar vertical",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )
    _rotate_exif_sw = ft.Switch(
        label="Corrigir orientação EXIF",
        value=False,
        active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )

    rotate_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Girar"), ft.Container(expand=True), help_icon_for("image.rotate", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Ângulo (sentido horário)"), _rot_grid,
            _rotate_flip_h_sw, _rotate_flip_v_sw, _rotate_exif_sw,
        ],
    )
    _param_blocks["rotate"] = rotate_block

    # -- watermark ------------------------------------------------------------
    _wm_mode_get: list[Callable] = []
    _wm_path: list[Path | None] = [None]
    _wm_path_text = ft.Text(
        "Nenhum arquivo selecionado",
        size=12, color=ft.Colors.ON_SURFACE_VARIANT,
        overflow=ft.TextOverflow.ELLIPSIS,
        expand=True,
    )

    wm_picker = ft.FilePicker()
    page.services.append(wm_picker)

    async def _pick_wm_image(_e) -> None:
        files = await wm_picker.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.IMAGE,
        )
        if files and files[0].path:
            _wm_path[0] = Path(files[0].path)
            _wm_path_text.value = Path(files[0].path).name
            try:
                if _wm_path_text.page:
                    _wm_path_text.update()
            except RuntimeError:
                pass

    _wm_text_tf = ft.TextField(
        hint_text="Texto da marca d'água",
        text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _wm_text_color_tf = ft.TextField(
        value="#ffffff", label="Cor (hex)", text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
    )
    _wm_text_size_val: list[float] = [40.0]
    _wm_text_size_lbl = ft.Text("40", size=13, weight=ft.FontWeight.W_600,
                                  color=ft.Colors.PRIMARY)
    _wm_text_size_slider = ft.Slider(
        value=40.0, min=8.0, max=120.0, divisions=112,
        active_color=ft.Colors.PRIMARY, expand=True,
    )

    def _on_wm_size_change(e: ft.ControlEvent) -> None:
        _wm_text_size_val[0] = float(e.control.value)

    def _on_wm_size_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _wm_text_size_val[0] = v
        _wm_text_size_lbl.value = str(int(v))
        try:
            if _wm_text_size_lbl.page:
                _wm_text_size_lbl.update()
        except RuntimeError:
            pass

    _wm_text_size_slider.on_change = _on_wm_size_change
    _wm_text_size_slider.on_change_end = _on_wm_size_end

    _wm_opacity_val: list[float] = [0.5]
    _wm_opacity_lbl = ft.Text("50%", size=13, weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY)
    _wm_opacity_slider = ft.Slider(
        value=0.5, min=0.0, max=1.0, divisions=20,
        active_color=ft.Colors.PRIMARY, expand=True,
    )

    def _on_wm_opacity_change(e: ft.ControlEvent) -> None:
        _wm_opacity_val[0] = float(e.control.value)

    def _on_wm_opacity_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _wm_opacity_val[0] = v
        _wm_opacity_lbl.value = f"{int(v * 100)}%"
        try:
            if _wm_opacity_lbl.page:
                _wm_opacity_lbl.update()
        except RuntimeError:
            pass

    _wm_opacity_slider.on_change = _on_wm_opacity_change
    _wm_opacity_slider.on_change_end = _on_wm_opacity_end

    _wm_position_get: list[Callable] = []
    _wm_pos_grid, _wm_pos_get, _wm_pos_set_disabled = segmented_selector(
        ["top-left", "top-right", "center", "bottom-left", "bottom-right"],
        "bottom-right", page,
        labels={
            "top-left": "↖", "top-right": "↗", "center": "⬤",
            "bottom-left": "↙", "bottom-right": "↘",
        },
        columns=5,
    )
    _wm_position_get.append(_wm_pos_get)

    _wm_text_col = ft.Column([
        section_label("Texto"),
        _wm_text_tf,
        ft.Row([section_label("Cor"), _wm_text_color_tf], spacing=8,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([section_label("Tamanho"), ft.Container(expand=True), _wm_text_size_lbl]),
        ft.Row([_wm_text_size_slider], spacing=0),
    ], spacing=Space.sm)

    _wm_image_col = ft.Column([
        section_label("Arquivo de imagem"),
        ft.Row([
            _wm_path_text,
            ft.OutlinedButton(
                "Selecionar", icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                on_click=_pick_wm_image,
                style=ft.ButtonStyle(
                    padding=ft.Padding(left=8, right=8, top=4, bottom=4),
                ),
            ),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ], spacing=Space.sm, visible=False)

    def _on_wm_mode_change(mode: str) -> None:
        _wm_text_col.visible = mode == "text"
        _wm_image_col.visible = mode == "image"
        try:
            if card_grid.page:
                card_grid.page.update()
        except RuntimeError:
            pass

    _wm_mode_grid, _wm_mode_get_fn, _wm_mode_set_disabled = segmented_selector(
        ["text", "image"], "text", page,
        on_change=_on_wm_mode_change,
        labels={"text": "Texto", "image": "Imagem"},
        columns=2,
    )
    _wm_mode_get.append(_wm_mode_get_fn)

    watermark_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Marca d'água"), ft.Container(expand=True), help_icon_for("image.watermark", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Modo"), _wm_mode_grid,
            _wm_text_col, _wm_image_col,
            section_label("Posição"), _wm_pos_grid,
            ft.Row([section_label("Opacidade"), ft.Container(expand=True), _wm_opacity_lbl]),
            ft.Row([_wm_opacity_slider], spacing=0),
        ],
    )
    _param_blocks["watermark"] = watermark_block

    # -- border ---------------------------------------------------------------
    _border_padding_val: list[float] = [20.0]
    _border_padding_lbl = ft.Text("20px", size=13, weight=ft.FontWeight.W_600,
                                   color=ft.Colors.PRIMARY)
    _border_padding_slider = ft.Slider(
        value=20.0, min=1.0, max=200.0, divisions=199,
        active_color=ft.Colors.PRIMARY, expand=True,
    )

    def _on_border_padding_change(e: ft.ControlEvent) -> None:
        _border_padding_val[0] = float(e.control.value)

    def _on_border_padding_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _border_padding_val[0] = v
        _border_padding_lbl.value = f"{int(v)}px"
        try:
            if _border_padding_lbl.page:
                _border_padding_lbl.update()
        except RuntimeError:
            pass

    _border_padding_slider.on_change = _on_border_padding_change
    _border_padding_slider.on_change_end = _on_border_padding_end

    _border_color_tf = ft.TextField(
        value="#000000", label="Cor da borda (hex)", text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
    )
    _border_fill_alpha_sw = ft.Switch(
        label="Preencher alpha pela cor da borda",
        value=False, active_color=ft.Colors.PRIMARY,
        label_text_style=ft.TextStyle(size=Type.body.size),
    )

    border_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Borda"), ft.Container(expand=True), help_icon_for("image.border", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([section_label("Espessura"), ft.Container(expand=True), _border_padding_lbl]),
            ft.Row([_border_padding_slider], spacing=0),
            _border_color_tf,
            _border_fill_alpha_sw,
        ],
    )
    _param_blocks["border"] = border_block

    # -- adjust ---------------------------------------------------------------
    def _make_adj_slider(label: str, default: float) -> tuple[ft.Column, ft.Slider, ft.Text]:
        lbl = ft.Text(f"{default:.1f}", size=13, weight=ft.FontWeight.W_600,
                      color=ft.Colors.PRIMARY)
        val: list[float] = [default]
        slider = ft.Slider(
            value=default, min=0.1, max=2.0, divisions=19,
            active_color=ft.Colors.PRIMARY, expand=True,
        )

        def _on_chg(e: ft.ControlEvent) -> None:
            val[0] = float(e.control.value)

        def _on_end(e: ft.ControlEvent) -> None:
            v = float(e.control.value)
            val[0] = v
            lbl.value = f"{v:.1f}"
            try:
                if lbl.page:
                    lbl.update()
            except RuntimeError:
                pass

        slider.on_change = _on_chg
        slider.on_change_end = _on_end
        col = ft.Column([
            ft.Row([section_label(label), ft.Container(expand=True), lbl]),
            ft.Row([slider], spacing=0),
        ], spacing=Space.xs)
        return col, slider, lbl

    _adj_bright_col, _adj_bright_slider, _ = _make_adj_slider("Brilho", 1.0)
    _adj_contrast_col, _adj_contrast_slider, _ = _make_adj_slider("Contraste", 1.0)
    _adj_color_col, _adj_color_slider, _ = _make_adj_slider("Saturação", 1.0)
    _adj_sharpness_col, _adj_sharpness_slider, _ = _make_adj_slider("Nitidez", 1.0)

    adjust_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Ajustes"), ft.Container(expand=True), help_icon_for("image.adjust", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            _adj_bright_col, _adj_contrast_col,
            _adj_color_col, _adj_sharpness_col,
        ],
    )
    _param_blocks["adjust"] = adjust_block

    # -- filter ---------------------------------------------------------------
    _filter_type_get: list[Callable] = []
    _flt_grid, _flt_get, _flt_set_disabled = segmented_selector(
        ["blur", "sharpen", "autocontrast", "equalize", "grayscale"],
        "blur", page,
        labels={
            "blur": "Blur", "sharpen": "Nitidez",
            "autocontrast": "Autocontraste", "equalize": "Equalizar",
            "grayscale": "Cinza",
        },
        columns=3,
    )
    _filter_type_get.append(_flt_get)

    filter_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Filtros"), ft.Container(expand=True), help_icon_for("image.filter", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Tipo de filtro"), _flt_grid,
        ],
    )
    _param_blocks["filter"] = filter_block

    # -- favicon --------------------------------------------------------------
    _favicon_all_sizes = [16, 32, 48, 64, 128, 256]
    _favicon_checks: dict[int, ft.Checkbox] = {
        s: ft.Checkbox(
            label=f"{s}px", value=(s in [16, 32, 48, 64, 128, 256]),
            active_color=ft.Colors.PRIMARY,
            label_style=ft.TextStyle(size=Type.body.size),
        )
        for s in _favicon_all_sizes
    }

    favicon_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Favicon"), ft.Container(expand=True), help_icon_for("image.favicon", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            section_label("Tamanhos (.ico multires)"),
            ft.Row(
                [_favicon_checks[s] for s in _favicon_all_sizes],
                wrap=True, spacing=8, run_spacing=4,
            ),
        ],
    )
    _param_blocks["favicon"] = favicon_block

    # -- contact_sheet --------------------------------------------------------
    def _make_cs_slider(
        label: str, default: float, min_v: float, max_v: float, divs: int
    ) -> tuple[ft.Column, ft.Slider]:
        lbl = ft.Text(str(int(default)), size=13, weight=ft.FontWeight.W_600,
                      color=ft.Colors.PRIMARY)
        val: list[float] = [default]
        slider = ft.Slider(
            value=default, min=min_v, max=max_v, divisions=divs,
            active_color=ft.Colors.PRIMARY, expand=True,
        )

        def _on_chg(e: ft.ControlEvent) -> None:
            val[0] = float(e.control.value)

        def _on_end(e: ft.ControlEvent) -> None:
            v = float(e.control.value)
            val[0] = v
            lbl.value = str(int(v))
            try:
                if lbl.page:
                    lbl.update()
            except RuntimeError:
                pass

        slider.on_change = _on_chg
        slider.on_change_end = _on_end
        col = ft.Column([
            ft.Row([section_label(label), ft.Container(expand=True), lbl]),
            ft.Row([slider], spacing=0),
        ], spacing=Space.xs)
        return col, slider

    _cs_cols_col, _cs_cols_slider = _make_cs_slider("Colunas", 4, 1, 10, 9)
    _cs_thumb_col, _cs_thumb_slider = _make_cs_slider("Tamanho das miniaturas (px)", 200, 50, 500, 45)
    _cs_gap_col, _cs_gap_slider = _make_cs_slider("Espaçamento (px)", 10, 0, 50, 50)

    _cs_bg_color_tf = ft.TextField(
        value="#ffffff", label="Cor de fundo (hex)", text_size=13, height=38,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
        border_color=ft.Colors.OUTLINE_VARIANT, focused_border_color=ft.Colors.PRIMARY,
    )

    contact_sheet_block = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            ft.Row([section_label("Colagem"), ft.Container(expand=True), help_icon_for("image.contact_sheet", page)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            _cs_cols_col, _cs_thumb_col, _cs_gap_col, _cs_bg_color_tf,
        ],
    )
    _param_blocks["contact_sheet"] = contact_sheet_block

    # -- convert / vazio -------------------------------------------------------
    _param_blocks["convert"] = ft.Column(visible=False, spacing=0)

    # ── Bloco de formato de saída ─────────────────────────────────────────────

    # -- convert: segmented selector original --
    _current_fmt: list[str] = ["jpg"]
    _quality_val: list[float] = [_QUALITY_DEFAULT]
    _quality_disabled: list[bool] = [False]

    def _on_fmt_change(fmt: str) -> None:
        _current_fmt[0] = fmt
        _update_convert_quality_state(fmt)

    fmt_grid, _get_fmt, _set_fmt_disabled = segmented_selector(
        _FMT_OPTIONS, _current_fmt[0], page,
        on_change=_on_fmt_change, columns=4,
    )

    quality_value_text = ft.Text(
        f"{int(_QUALITY_DEFAULT)}", size=13,
        weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY,
    )
    _q_icon = help_icon_for("image.quality", page)
    _q_label_row = ft.Row(
        controls=[
            ft.Text("Qualidade", size=Type.label.size, weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT),
            *([_q_icon] if _q_icon else []),
            ft.Container(expand=True),
            quality_value_text,
        ],
        spacing=Space.xs, vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    quality_slider = ft.Slider(
        value=_QUALITY_DEFAULT, min=_QUALITY_MIN, max=_QUALITY_MAX, divisions=10,
        active_color=ft.Colors.PRIMARY, expand=True,
    )

    def _on_quality_change(e: ft.ControlEvent) -> None:
        _quality_val[0] = float(e.control.value)

    def _on_quality_change_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _quality_val[0] = v
        quality_value_text.value = str(int(v))
        try:
            if quality_value_text.page:
                quality_value_text.update()
        except RuntimeError:
            pass

    quality_slider.on_change = _on_quality_change
    quality_slider.on_change_end = _on_quality_change_end

    quality_container = ft.Container(
        content=ft.Column([_q_label_row, quality_slider], spacing=Space.xs),
        opacity=1.0,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )
    _quality_disabled: list[bool] = [False]

    def _update_convert_quality_state(fmt: str, do_update: bool = True) -> None:
        disabled = fmt not in _LOSSY_FMTS
        _quality_disabled[0] = disabled
        quality_container.opacity = 0.4 if disabled else 1.0
        quality_slider.disabled = disabled
        if do_update:
            try:
                if quality_container.page:
                    quality_container.update()
            except RuntimeError:
                pass

    _update_convert_quality_state(_current_fmt[0], do_update=False)

    _fmt_convert_col = ft.Column(
        visible=True, spacing=Space.sm,
        controls=[
            section("Formato de saída", fmt_grid, help_key="image.format", page=page),
            hairline(),
            quality_container,
        ],
    )

    # -- manipulação: dropdown out_fmt + quality --
    _out_fmt_val: list[str] = ["preserve"]
    _out_quality_val: list[float] = [90.0]
    _out_quality_disabled: list[bool] = [True]

    _out_fmt_options = ["preserve"] + _FMT_OPTIONS
    _out_fmt_labels = {
        "preserve": "Preservar original",
        "jpg": "JPG", "png": "PNG", "webp": "WebP",
        "avif": "AVIF", "tiff": "TIFF",
        "bmp": "BMP", "gif": "GIF", "ico": "ICO",
    }

    out_fmt_dd = ft.Dropdown(
        options=[ft.dropdown.Option(key=k, text=_out_fmt_labels[k]) for k in _out_fmt_options],
        value="preserve",
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=13,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    _out_quality_lbl = ft.Text("90", size=13, weight=ft.FontWeight.W_600,
                                color=ft.Colors.PRIMARY)
    out_quality_slider = ft.Slider(
        value=90.0, min=_QUALITY_MIN, max=_QUALITY_MAX, divisions=10,
        active_color=ft.Colors.PRIMARY, expand=True, disabled=True,
    )
    out_quality_container = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Qualidade", size=Type.label.size, weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(expand=True),
                _out_quality_lbl,
            ], spacing=Space.xs),
            out_quality_slider,
        ], spacing=Space.xs),
        opacity=0.4,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_out_fmt_change(e: ft.ControlEvent) -> None:
        v = e.control.value or "preserve"
        _out_fmt_val[0] = v
        lossy = v in _LOSSY_FMTS
        _out_quality_disabled[0] = not lossy
        out_quality_slider.disabled = not lossy
        out_quality_container.opacity = 1.0 if lossy else 0.4
        try:
            if out_quality_container.page:
                out_quality_container.update()
        except RuntimeError:
            pass

    def _on_out_quality_change(e: ft.ControlEvent) -> None:
        _out_quality_val[0] = float(e.control.value)

    def _on_out_quality_end(e: ft.ControlEvent) -> None:
        v = float(e.control.value)
        _out_quality_val[0] = v
        _out_quality_lbl.value = str(int(v))
        try:
            if _out_quality_lbl.page:
                _out_quality_lbl.update()
        except RuntimeError:
            pass

    out_fmt_dd.on_change = _on_out_fmt_change
    out_quality_slider.on_change = _on_out_quality_change
    out_quality_slider.on_change_end = _on_out_quality_end

    _fmt_manip_col = ft.Column(
        visible=False, spacing=Space.sm,
        controls=[
            section_label("Formato de saída"),
            out_fmt_dd,
            hairline(),
            out_quality_container,
        ],
    )

    # Container unificado do bloco de formato
    _fmt_section = ft.Column(
        visible=True, spacing=Space.sm,
        controls=[_fmt_convert_col, _fmt_manip_col],
    )

    def _refresh_format_block() -> None:
        op = _current_op[0]
        _fmt_convert_col.visible = op == "convert"
        _fmt_manip_col.visible = op not in ("convert", "favicon")
        _fmt_section.visible = op != "favicon"

    # ── Refresh dos blocos de parâmetros ──────────────────────────────────────

    def _refresh_param_blocks() -> None:
        for op_id, blk in _param_blocks.items():
            blk.visible = op_id == _current_op[0]

    # ── Botão Iniciar ─────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
    )

    def _parse_int(tf: ft.TextField, default: int) -> int:
        try:
            v = int((tf.value or "").strip())
            return v if v >= 0 else default
        except ValueError:
            return default

    def _on_start_click() -> None:
        items = input_source.get_items()
        if not items:
            return
        op = _current_op[0]

        out_fmt_str = _out_fmt_val[0]
        resolved_out_fmt: str | None = None if out_fmt_str == "preserve" else out_fmt_str

        favicon_sizes = [s for s, chk in _favicon_checks.items() if chk.value]
        if not favicon_sizes:
            favicon_sizes = [32]

        args = ImageArgs(
            items=items,
            operation=op,
            # convert
            fmt=_get_fmt() if op == "convert" else "jpg",
            quality=int(_quality_val[0]) if not _quality_disabled[0] else 90,
            # shared output
            out_fmt=resolved_out_fmt,
            out_quality=int(_out_quality_val[0]),
            # resize
            resize_mode=_resize_mode_get[0]() if _resize_mode_get else "contain",
            resize_width=_parse_int(_resize_w_tf, 0) or None,
            resize_height=_parse_int(_resize_h_tf, 0) or None,
            resize_scale_pct=_resize_scale_val[0],
            # crop
            crop_mode=_crop_mode_get[0]() if _crop_mode_get else "manual",
            crop_left=_parse_int(_crop_left_tf, 0),
            crop_top=_parse_int(_crop_top_tf, 0),
            crop_width=_parse_int(_crop_w_tf, 0),
            crop_height=_parse_int(_crop_h_tf, 0),
            crop_ratio=_crop_ratio_get[0]() if _crop_ratio_get else "1:1",
            crop_trim_color=(_crop_trim_color_tf.value or "#ffffff").strip(),
            # rotate
            rotate_angle=int(_rotate_angle_get[0]()) if _rotate_angle_get else 0,
            rotate_flip_h=_rotate_flip_h_sw.value or False,
            rotate_flip_v=_rotate_flip_v_sw.value or False,
            rotate_exif_auto=_rotate_exif_sw.value or False,
            # watermark
            wm_mode=_wm_mode_get[0]() if _wm_mode_get else "text",
            wm_text=(_wm_text_tf.value or "").strip(),
            wm_text_color=(_wm_text_color_tf.value or "#ffffff").strip(),
            wm_text_size=int(_wm_text_size_val[0]),
            wm_path=_wm_path[0],
            wm_position=_wm_position_get[0]() if _wm_position_get else "bottom-right",
            wm_opacity=_wm_opacity_val[0],
            # border
            border_padding=int(_border_padding_val[0]),
            border_color=(_border_color_tf.value or "#000000").strip(),
            border_fill_alpha=_border_fill_alpha_sw.value or False,
            # adjust
            adj_brightness=float(_adj_bright_slider.value or 1.0),
            adj_contrast=float(_adj_contrast_slider.value or 1.0),
            adj_color=float(_adj_color_slider.value or 1.0),
            adj_sharpness=float(_adj_sharpness_slider.value or 1.0),
            # filter
            filter_type=_filter_type_get[0]() if _filter_type_get else "blur",
            # favicon
            favicon_sizes=favicon_sizes,
            # contact_sheet
            cs_cols=max(1, int(_cs_cols_slider.value or 4)),
            cs_thumb_size=max(10, int(_cs_thumb_slider.value or 200)),
            cs_gap=max(0, int(_cs_gap_slider.value or 10)),
            cs_bg_color=(_cs_bg_color_tf.value or "#ffffff").strip(),
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
        for ctr in _card_ctr_refs.values():
            ctr.disabled = running
        _set_fmt_disabled(running)
        if running:
            quality_container.opacity = 0.4
            quality_slider.disabled = True
        else:
            _update_convert_quality_state(_current_fmt[0])
        page.update()

    # ── Layout ────────────────────────────────────────────────────────────────

    params_container = ft.Column(
        spacing=Space.sm,
        controls=[v for v in _param_blocks.values()],
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
                        section("Entrada", input_source.control,
                                help_key="image.input", page=page),
                        hairline(),
                        section("Operação", card_grid),
                        hairline(),
                        params_container,
                        hairline(),
                        _fmt_section,
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

    return ImageFormPanel(control=control, set_running=_set_running)
