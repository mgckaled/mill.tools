"""Formulário de entrada do módulo Vídeo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from src.gui import settings
from src.core.io_types import InputItem
from src.core.video.args import VideoArgs
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import (
    Cursor,
    hairline,
    help_icon_for,
    section,
    segmented_selector,
    switch_row,
)
from src.gui.theme.tokens import Space, Type

_ALLOWED_EXTS = ["mp4", "mkv", "webm", "avi", "mov"]

_OP_ICONS: list[tuple[str, str, str]] = [
    ("download",      ft.Icons.DOWNLOAD_OUTLINED,      "Baixar"),
    ("convert",       ft.Icons.COMPARE_ARROWS,          "Converter"),
    ("trim",          ft.Icons.CONTENT_CUT,              "Recortar"),
    ("compress",      ft.Icons.COMPRESS,                 "Comprimir"),
    ("resize",        ft.Icons.OPEN_IN_FULL,             "Redimensionar"),
    ("extract_audio", ft.Icons.AUDIO_FILE_OUTLINED,     "Extrair áudio"),
    ("thumbnail",     ft.Icons.IMAGE_OUTLINED,           "Thumbnail"),
]

_RES_OPTIONS = ["best", "2160", "1080", "720", "480", "360"]
_RES_LABELS  = {"best": "Melhor", "2160": "4K", "1080": "1080p", "720": "720p", "480": "480p", "360": "360p"}

_CONTAINER_OPTIONS = ["mp4", "mkv", "webm"]
_CONTAINER_LABELS  = {"mp4": "MP4", "mkv": "MKV", "webm": "WebM"}

_CODEC_OPTIONS = ["copy", "h264", "h265", "vp9"]
_CODEC_LABELS  = {"copy": "Copy", "h264": "H.264", "h265": "H.265", "vp9": "VP9"}

_OUT_CONTAINER_OPTIONS = ["mp4", "mkv", "webm", "avi"]
_OUT_CONTAINER_LABELS  = {"mp4": "MP4", "mkv": "MKV", "webm": "WebM", "avi": "AVI"}

_PRESET_OPTIONS = ["ultrafast", "fast", "medium", "slow"]

_AUDIO_FMT_OPTIONS = ["mp3", "m4a", "wav"]
_AUDIO_FMT_LABELS  = {"mp3": "MP3", "m4a": "M4A", "wav": "WAV"}

_THUMB_FMT_OPTIONS = ["jpg", "png"]
_THUMB_FMT_LABELS  = {"jpg": "JPG", "png": "PNG"}


@dataclass
class VideoFormPanel:
    """Painel do formulário de vídeo com métodos de controle."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


# ─── build_video_form ─────────────────────────────────────────────────────────

def build_video_form(
    page: ft.Page,
    on_start: Callable[[VideoArgs], None],
) -> VideoFormPanel:
    """Constrói o formulário do módulo Vídeo.

    Args:
        page: Página Flet.
        on_start: Chamado com VideoArgs ao clicar Iniciar.
    """
    cfg = settings.load()

    # ── Controle de estado interno ─────────────────────────────────────────────
    _has_url_items: list[bool] = [False]
    _sel_disable_fns: list[Callable[[bool], None]] = []
    _text_fields: list[ft.TextField] = []
    _switches_extra: list[ft.Switch] = []
    _sliders_extra: list[ft.Slider] = []

    # ── InputSource ───────────────────────────────────────────────────────────

    def _on_items_change(items: list[InputItem]) -> None:
        has_url = any(i.kind == "url" for i in items)
        has_local = any(i.kind == "local" for i in items)
        _has_url_items[0] = has_url
        start_btn.disabled = len(items) == 0
        if has_url:
            _op_grid_disabled[0] = True
            if _current_op[0] != "download":
                _current_op[0] = "download"
                _refresh_op_cards()
        else:
            _op_grid_disabled[0] = False
            if has_local and _current_op[0] == "download":
                _current_op[0] = "convert"
                _refresh_op_cards()
        _show_op_block("download" if has_url else _get_op())
        page.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
        url_hint="URL do vídeo (YouTube, Vimeo, Twitter, TikTok…)",
    )

    # ── Seletor de operação (card grid) ───────────────────────────────────────

    initial_op = cfg.get("last_video_operation", "download")
    _current_op: list[str] = [initial_op]
    _op_card_ctr_refs: dict[str, ft.Container] = {}
    _op_card_icon_refs: dict[str, ft.Icon] = {}
    _op_card_text_refs: dict[str, ft.Text] = {}
    _op_grid_disabled: list[bool] = [False]

    def _refresh_op_cards() -> None:
        sel = _current_op[0]
        for oid, ctr in _op_card_ctr_refs.items():
            active = oid == sel
            color = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
            bw = 2 if active else 1
            bc = ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT
            side = ft.BorderSide(bw, bc)
            _op_card_icon_refs[oid].color = color
            _op_card_text_refs[oid].color = color
            ctr.border = ft.Border(left=side, right=side, top=side, bottom=side)

    def _on_op_card_click(op_id: str) -> None:
        if _op_grid_disabled[0]:
            return
        _current_op[0] = op_id
        _refresh_op_cards()
        _show_op_block(op_id)
        page.update()

    def _make_op_card(op_id: str, icon_name: str, label: str) -> ft.GestureDetector:
        active = op_id == initial_op
        color = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
        bw = 2 if active else 1
        bc = ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT
        side = ft.BorderSide(bw, bc)
        ic = ft.Icon(icon_name, size=24, color=color)
        tx = ft.Text(label, size=Type.small.size, text_align=ft.TextAlign.CENTER, color=color, max_lines=2)
        _op_card_icon_refs[op_id] = ic
        _op_card_text_refs[op_id] = tx
        ctr = ft.Container(
            content=ft.Column([ic, tx], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, tight=True),
            height=70, padding=8, border_radius=8,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border(left=side, right=side, top=side, bottom=side),
            shadow=ft.BoxShadow(
                blur_radius=8, spread_radius=0,
                offset=ft.Offset(0, 3),
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            ),
            alignment=ft.Alignment.CENTER,
        )
        _op_card_ctr_refs[op_id] = ctr
        return ft.GestureDetector(
            mouse_cursor=Cursor.interactive,
            on_tap=lambda e, oid=op_id: _on_op_card_click(oid),
            content=ctr,
            expand=True,
        )

    _OP_COLS = 3
    _op_card_list = [_make_op_card(oid, icon, lbl) for oid, icon, lbl in _OP_ICONS]
    _refresh_op_cards()
    while len(_op_card_list) % _OP_COLS != 0:
        _op_card_list.append(ft.Container(expand=True))
    op_grid = ft.Column(
        spacing=6,
        controls=[
            ft.Row(controls=_op_card_list[i:i + _OP_COLS], spacing=6)
            for i in range(0, len(_op_card_list), _OP_COLS)
        ],
    )

    def _get_op() -> str:
        return _current_op[0]

    def _set_op_disabled(disabled: bool) -> None:
        _op_grid_disabled[0] = disabled
        for ctr in _op_card_ctr_refs.values():
            ctr.disabled = disabled
        # sem update individual — o chamador é responsável pelo page.update()

    _sel_disable_fns.append(_set_op_disabled)

    # ── Bloco: Download ────────────────────────────────────────────────────────

    res_grid, _get_resolution, _set_res_disabled = segmented_selector(
        _RES_OPTIONS,
        cfg.get("last_video_resolution", "1080"),
        page,
        columns=3,
        labels=_RES_LABELS,
    )
    _sel_disable_fns.append(_set_res_disabled)

    dl_container_grid, _get_dl_container, _set_dl_container_disabled = segmented_selector(
        _CONTAINER_OPTIONS,
        cfg.get("last_video_container", "mp4"),
        page,
        columns=3,
        labels=_CONTAINER_LABELS,
    )
    _sel_disable_fns.append(_set_dl_container_disabled)

    embed_switch = ft.Switch(
        label="Embutir metadados",
        value=cfg.get("last_video_embed_meta", True),
        label_text_style=ft.TextStyle(size=Type.input.size),
        active_color=ft.Colors.PRIMARY,
    )
    _switches_extra.append(embed_switch)

    _download_block_content = ft.Column(
        controls=[
            section("Resolução máxima", res_grid, help_key="video.resolution", page=page),
            section("Container", dl_container_grid),
            ft.Row(
                [embed_switch, help_icon_for("video.embed_meta", page) or ft.Container()],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=Space.md,
    )

    # ── Bloco: Convert ─────────────────────────────────────────────────────────

    codec_grid, _get_vcodec, _set_codec_disabled = segmented_selector(
        _CODEC_OPTIONS,
        cfg.get("last_video_vcodec", "copy"),
        page,
        columns=4,
        labels=_CODEC_LABELS,
    )
    _sel_disable_fns.append(_set_codec_disabled)

    conv_container_grid, _get_out_container, _set_conv_container_disabled = segmented_selector(
        _OUT_CONTAINER_OPTIONS,
        cfg.get("last_video_out_container", "mp4"),
        page,
        columns=4,
        labels=_OUT_CONTAINER_LABELS,
    )
    _sel_disable_fns.append(_set_conv_container_disabled)

    _convert_block_content = ft.Column(
        controls=[
            section("Codec de vídeo", codec_grid, help_key="video.codec", page=page),
            section("Container de saída", conv_container_grid),
        ],
        spacing=Space.md,
    )

    # ── Bloco: Trim ────────────────────────────────────────────────────────────

    trim_start_field = ft.TextField(
        hint_text="Início (HH:MM:SS)",
        value="",
        dense=True,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    trim_end_field = ft.TextField(
        hint_text="Fim (HH:MM:SS)",
        value="",
        dense=True,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _text_fields += [trim_start_field, trim_end_field]

    trim_reenc_switch = switch_row(
        "Frame-preciso (reencoda — mais lento)",
        cfg.get("last_video_trim_reenc", False),
        label_size=Type.input.size,
    )
    _switches_extra.append(trim_reenc_switch)

    _trim_block_content = ft.Column(
        controls=[
            section(
                "Intervalo",
                ft.Row([trim_start_field, trim_end_field], spacing=Space.sm),
                help_key="video.trim",
                page=page,
            ),
            ft.Row(
                [trim_reenc_switch],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=Space.md,
    )

    # ── Bloco: Compress ────────────────────────────────────────────────────────

    crf_values: list[int] = [cfg.get("last_video_crf", 23)]
    crf_text = ft.Text(
        f"CRF {crf_values[0]}",
        size=Type.label.size,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.PRIMARY,
    )
    crf_ctl = ft.Slider(
        value=float(crf_values[0]),
        min=18.0,
        max=28.0,
        divisions=10,
        active_color=ft.Colors.PRIMARY,
        label="{value:.0f}",
        expand=True,
    )
    _sliders_extra.append(crf_ctl)

    def _on_crf_change(e) -> None:
        crf_values[0] = int(e.control.value)
        crf_text.value = f"CRF {crf_values[0]}"
        if crf_text.page:
            crf_text.update()

    crf_ctl.on_change = _on_crf_change

    _crf_icon = help_icon_for("video.crf", page)
    _crf_col = ft.Column(
        controls=[
            ft.Row(
                [
                    ft.Text(
                        "CRF (qualidade)",
                        size=Type.label.size,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ]
                + ([_crf_icon] if _crf_icon else [])
                + [ft.Container(expand=True), crf_text],
                spacing=Space.xs,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            crf_ctl,
        ],
        spacing=Space.xs,
    )

    preset_grid, _get_preset, _set_preset_disabled = segmented_selector(
        _PRESET_OPTIONS,
        cfg.get("last_video_preset", "medium"),
        page,
        columns=4,
    )
    _sel_disable_fns.append(_set_preset_disabled)

    _compress_block_content = ft.Column(
        controls=[
            _crf_col,
            section("Preset de encoding", preset_grid, help_key="video.preset", page=page),
        ],
        spacing=Space.md,
    )

    # ── Bloco: Resize ──────────────────────────────────────────────────────────

    resize_width_field = ft.TextField(
        hint_text="Largura (px)",
        value="",
        dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    resize_height_field = ft.TextField(
        hint_text="Altura (px)",
        value="",
        dense=True,
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _text_fields += [resize_width_field, resize_height_field]

    _resize_block_content = ft.Column(
        controls=[
            section(
                "Dimensões de saída",
                ft.Row([resize_width_field, resize_height_field], spacing=Space.sm),
                help_key="video.resize",
                page=page,
            ),
            ft.Text(
                "Deixe em branco para calcular automaticamente (aspect ratio preservado)",
                size=Type.caption.size,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ],
        spacing=Space.sm,
    )

    # ── Bloco: Extract audio ───────────────────────────────────────────────────

    audio_fmt_grid, _get_audio_fmt, _set_audio_fmt_disabled = segmented_selector(
        _AUDIO_FMT_OPTIONS,
        cfg.get("last_video_audio_fmt", "mp3"),
        page,
        columns=3,
        labels=_AUDIO_FMT_LABELS,
    )
    _sel_disable_fns.append(_set_audio_fmt_disabled)

    _extract_audio_block_content = ft.Column(
        controls=[
            section("Formato de áudio", audio_fmt_grid),
        ],
        spacing=Space.md,
    )

    # ── Bloco: Thumbnail ───────────────────────────────────────────────────────

    thumb_time_field = ft.TextField(
        hint_text="Tempo (HH:MM:SS)",
        value=cfg.get("last_video_thumb_time", "00:00:01"),
        dense=True,
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        expand=True,
    )
    _text_fields.append(thumb_time_field)

    thumb_fmt_grid, _get_thumb_fmt, _set_thumb_fmt_disabled = segmented_selector(
        _THUMB_FMT_OPTIONS,
        cfg.get("last_video_thumb_fmt", "jpg"),
        page,
        columns=2,
        labels=_THUMB_FMT_LABELS,
    )
    _sel_disable_fns.append(_set_thumb_fmt_disabled)

    _thumbnail_block_content = ft.Column(
        controls=[
            section("Frame em", thumb_time_field),
            section("Formato de imagem", thumb_fmt_grid),
        ],
        spacing=Space.md,
    )

    # ── Blocos condicionais ────────────────────────────────────────────────────

    _op_blocks: dict[str, ft.Container] = {}

    def _make_op_block(op: str, content: ft.Control) -> ft.Container:
        c = ft.Container(
            content=content,
            visible=(op == initial_op),
            animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
        )
        _op_blocks[op] = c
        return c

    def _show_op_block(op: str) -> None:
        for k, blk in _op_blocks.items():
            blk.visible = (k == op)

    blocks_col = ft.Column(
        controls=[
            _make_op_block("download",      _download_block_content),
            _make_op_block("convert",       _convert_block_content),
            _make_op_block("trim",          _trim_block_content),
            _make_op_block("compress",      _compress_block_content),
            _make_op_block("resize",        _resize_block_content),
            _make_op_block("extract_audio", _extract_audio_block_content),
            _make_op_block("thumbnail",     _thumbnail_block_content),
        ],
        spacing=0,
    )

    # ── Botão Iniciar ──────────────────────────────────────────────────────────

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
        op = "download" if _has_url_items[0] else _get_op()
        settings.save({
            "last_video_operation":   _get_op(),
            "last_video_resolution":  _get_resolution(),
            "last_video_container":   _get_dl_container(),
            "last_video_embed_meta":  bool(embed_switch.value),
            "last_video_vcodec":      _get_vcodec(),
            "last_video_out_container": _get_out_container(),
            "last_video_crf":         crf_values[0],
            "last_video_preset":      _get_preset(),
            "last_video_audio_fmt":   _get_audio_fmt(),
            "last_video_thumb_time":  thumb_time_field.value or "00:00:01",
            "last_video_thumb_fmt":   _get_thumb_fmt(),
        })
        on_start(VideoArgs(
            items=items,
            operation=op,
            resolution=_get_resolution(),
            container=_get_dl_container(),
            embed_meta=bool(embed_switch.value),
            vcodec=_get_vcodec(),
            out_container=_get_out_container(),
            trim_start=trim_start_field.value or "",
            trim_end=trim_end_field.value or "",
            trim_reenc=bool(trim_reenc_switch.value),
            crf=crf_values[0],
            preset=_get_preset(),
            resize_width=int(resize_width_field.value or 0),
            resize_height=int(resize_height_field.value or 0),
            audio_fmt=_get_audio_fmt(),
            thumb_time=thumb_time_field.value or "00:00:01",
            thumb_fmt=_get_thumb_fmt(),
        ))

    # ── set_running ────────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        input_source.set_enabled(not running)
        for fn in _sel_disable_fns:
            fn(running)
        for tf in _text_fields:
            tf.disabled = running
        for sw in _switches_extra:
            sw.disabled = running
        for sl in _sliders_extra:
            sl.disabled = running
        page.update()

    # ── fill_from_path (bridge on_mount) ──────────────────────────────────────

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    # ── Layout ────────────────────────────────────────────────────────────────

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
                        # Entrada
                        section("Entrada", input_source.control,
                                help_key="video.input", page=page),

                        hairline(),

                        # Operação
                        section("Operação", op_grid,
                                help_key="video.operation", page=page),

                        hairline(),

                        # Bloco condicional
                        blocks_col,

                        hairline(),

                        # Botão Iniciar
                        ft.Row(
                            controls=[start_btn],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                ),
            ),
        ],
    )

    return VideoFormPanel(
        control=control,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
