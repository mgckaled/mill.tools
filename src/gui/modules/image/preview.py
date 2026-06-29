"""Before/After image viewer for the image module.

Extracted from ``view.py`` (architecture rule "split when you touch it"): hosts the
single/placeholder/before-after panes, a checkerboard backdrop that makes PNG
transparency legible (``remove_bg`` output), and a before→after metadata strip.
``view.py`` only routes pipeline events into the callables exposed by ``PreviewRefs``.
"""

from __future__ import annotations

import io
from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.tokens import Color, Radius, Type

# 1×1 px transparent PNG — Flet 0.85 requires src in the Image constructor.
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _checkerboard_png(square: int = 10) -> bytes:
    """Build a small 2×2 checkerboard tile (dark-theme grays) for transparency backdrop."""
    from PIL import Image

    light = (84, 84, 90)
    dark = (58, 58, 64)
    size = square * 2
    im = Image.new("RGB", (size, size), light)
    block = Image.new("RGB", (square, square), dark)
    im.paste(block, (0, 0))
    im.paste(block, (square, square))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class PreviewRefs(NamedTuple):
    """Controls + callables to drive the viewer from view.py."""

    control: ft.Control
    show_placeholder: Callable[[], None]
    show_single: Callable[[bytes | None, bool], None]
    show_before_after: Callable[[bytes, bytes, bool], None]
    set_meta: Callable[[str | None], None]
    reset: Callable[[], None]


def build_preview() -> PreviewRefs:
    """Build the Before/After viewer and return its control + drive callables."""
    _tile = _checkerboard_png()

    # ── Images ────────────────────────────────────────────────────────────────
    _img_single = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    _img_before = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    _img_after = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)

    # ── Checkerboard backdrops (shown only when the displayed image has alpha) ─
    _chk_single = ft.Image(
        _tile, repeat=ft.ImageRepeat.REPEAT, fit=ft.BoxFit.NONE, visible=False
    )
    _chk_after = ft.Image(
        _tile, repeat=ft.ImageRepeat.REPEAT, fit=ft.BoxFit.NONE, visible=False
    )

    # ── Placeholder ───────────────────────────────────────────────────────────
    _placeholder = ft.Container(
        content=ft.Text(
            "Selecione imagens para começar",
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
            size=Type.input.size,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        visible=True,
    )

    # ── Single pane: placeholder OR (checkerboard + single image) ─────────────
    _single_img_ctr = ft.Container(
        content=ft.Stack([_chk_single, _img_single], expand=True),
        alignment=ft.Alignment.CENTER,
        expand=True,
        visible=False,
    )
    _single_pane = ft.Stack([_placeholder, _single_img_ctr], expand=True)

    # ── Before/After pane ─────────────────────────────────────────────────────
    _before_col = ft.Column(
        [
            ft.Text("Antes", size=Type.tiny.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(
                content=_img_before, expand=True, alignment=ft.Alignment.CENTER
            ),
        ],
        expand=True,
        spacing=4,
    )
    _after_col = ft.Column(
        [
            ft.Text("Depois", size=Type.tiny.size, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(
                content=ft.Stack([_chk_after, _img_after], expand=True),
                expand=True,
                alignment=ft.Alignment.CENTER,
            ),
        ],
        expand=True,
        spacing=4,
    )
    _before_after_row = ft.Row(
        [_before_col, ft.VerticalDivider(width=1), _after_col],
        expand=True,
        visible=False,
    )

    preview_container = ft.Container(
        content=ft.Row([_single_pane, _before_after_row], expand=True),
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

    # ── Before→after metadata strip ───────────────────────────────────────────
    _meta_label = ft.Text(
        "",
        size=Type.tiny.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        text_align=ft.TextAlign.CENTER,
        visible=False,
    )

    # ── Drive callables ───────────────────────────────────────────────────────
    def _show_placeholder() -> None:
        _single_pane.visible = True
        _before_after_row.visible = False
        _single_img_ctr.visible = False
        _placeholder.visible = True
        _chk_single.visible = False

    def _show_single(thumb: bytes | None = None, alpha: bool = False) -> None:
        _single_pane.visible = True
        _before_after_row.visible = False
        if thumb:
            _img_single.src = thumb
            _single_img_ctr.visible = True
            _placeholder.visible = False
            _chk_single.visible = alpha
        else:
            _single_img_ctr.visible = False
            _placeholder.visible = True
            _chk_single.visible = False

    def _show_before_after(
        before: bytes, after: bytes, after_alpha: bool = False
    ) -> None:
        _single_pane.visible = False
        _before_after_row.visible = True
        _img_before.src = before
        _img_after.src = after
        _chk_after.visible = after_alpha

    def _set_meta(text: str | None) -> None:
        _meta_label.value = text or ""
        _meta_label.visible = bool(text)

    def _reset() -> None:
        _show_placeholder()
        _set_meta(None)

    control = ft.Column(
        [preview_container, _meta_label],
        expand=True,
        spacing=4,
    )

    return PreviewRefs(
        control=control,
        show_placeholder=_show_placeholder,
        show_single=_show_single,
        show_before_after=_show_before_after,
        set_meta=_set_meta,
        reset=_reset,
    )
