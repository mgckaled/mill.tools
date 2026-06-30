"""Convert/format section block for the image module.

Manages two sub-sections:
- _fmt_convert_col: segmented selector + quality slider (convert operation)
- _fmt_manip_col:   dropdown + quality slider (all manipulation operations)
"""

from __future__ import annotations

from typing import Callable, NamedTuple

import flet as ft

from src.gui.theme.components import (
    hairline,
    section,
    section_label,
    segmented_selector,
)
from src.gui.theme.components.sliders import labeled_slider
from src.gui.theme.tokens import Space, Type

_FMT_OPTIONS = ["jpg", "png", "webp", "avif", "tiff", "bmp", "gif", "ico"]
_LOSSY_FMTS: frozenset[str] = frozenset({"jpg", "webp"})

_QUALITY_DEFAULT = 90.0
_QUALITY_MIN = 50.0
_QUALITY_MAX = 100.0


class FmtRefs(NamedTuple):
    control: ft.Column
    set_operation: Callable[[str], None]
    set_disabled: Callable[[bool], None]
    get_fmt: Callable[[], str]
    get_quality: Callable[[], int]
    get_out_fmt: Callable[[], str | None]
    get_out_quality: Callable[[], int]


def build_fmt_section(page: ft.Page) -> FmtRefs:
    """Build the unified format/quality section.

    Returns FmtRefs with control (the Column to embed in layout) and
    set_operation / set_disabled callbacks.
    """
    _current_fmt: list[str] = ["jpg"]

    # ── Convert: segmented format + quality ───────────────────────────────────

    def _on_fmt_change(fmt: str) -> None:
        _current_fmt[0] = fmt
        _update_quality_state(fmt)

    fmt_grid, _get_fmt, _set_fmt_disabled = segmented_selector(
        _FMT_OPTIONS,
        _current_fmt[0],
        page,
        on_change=_on_fmt_change,
        columns=4,
    )

    quality_col, quality_slider = labeled_slider(
        label="Qualidade",
        value=_QUALITY_DEFAULT,
        min=_QUALITY_MIN,
        max=_QUALITY_MAX,
        divisions=10,
        fmt=lambda v: f"{int(v)}",
    )
    quality_container = ft.Container(
        content=quality_col,
        opacity=1.0,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _update_quality_state(fmt: str, do_update: bool = True) -> None:
        disabled = fmt not in _LOSSY_FMTS
        quality_container.opacity = 0.4 if disabled else 1.0
        quality_slider.disabled = disabled
        if do_update:
            try:
                if quality_container.page:
                    quality_container.update()
            except RuntimeError:
                pass

    _update_quality_state(_current_fmt[0], do_update=False)

    fmt_convert_col = ft.Column(
        visible=True,
        spacing=Space.sm,
        controls=[
            section("Formato de saída", fmt_grid, help_key="image.format", page=page),
            hairline(),
            quality_container,
        ],
    )

    # ── Manipulation: dropdown format + quality ───────────────────────────────

    _out_fmt_val: list[str] = ["preserve"]
    _out_fmt_options = ["preserve"] + _FMT_OPTIONS
    _out_fmt_labels = {
        "preserve": "Preservar original",
        "jpg": "JPG",
        "png": "PNG",
        "webp": "WebP",
        "avif": "AVIF",
        "tiff": "TIFF",
        "bmp": "BMP",
        "gif": "GIF",
        "ico": "ICO",
    }

    out_fmt_dd = ft.Dropdown(
        options=[
            ft.dropdown.Option(key=k, text=_out_fmt_labels[k]) for k in _out_fmt_options
        ],
        value="preserve",
        border_color=ft.Colors.OUTLINE_VARIANT,
        focused_border_color=ft.Colors.PRIMARY,
        text_size=Type.input.size,
        height=42,
        content_padding=ft.Padding(left=10, right=4, top=0, bottom=0),
    )

    out_quality_col, out_quality_slider = labeled_slider(
        label="Qualidade",
        value=90.0,
        min=_QUALITY_MIN,
        max=_QUALITY_MAX,
        divisions=10,
        fmt=lambda v: f"{int(v)}",
    )
    out_quality_slider.disabled = True
    out_quality_container = ft.Container(
        content=out_quality_col,
        opacity=0.4,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    def _on_out_fmt_change(e: ft.ControlEvent) -> None:
        v = e.control.value or "preserve"
        _out_fmt_val[0] = v
        lossy = v in _LOSSY_FMTS
        out_quality_slider.disabled = not lossy
        out_quality_container.opacity = 1.0 if lossy else 0.4
        try:
            if out_quality_container.page:
                out_quality_container.update()
        except RuntimeError:
            pass

    out_fmt_dd.on_change = _on_out_fmt_change

    fmt_manip_col = ft.Column(
        visible=False,
        spacing=Space.sm,
        controls=[
            section_label("Formato de saída"),
            out_fmt_dd,
            hairline(),
            out_quality_container,
        ],
    )

    # ── Unified container ─────────────────────────────────────────────────────

    control = ft.Column(
        visible=True,
        spacing=Space.sm,
        controls=[fmt_convert_col, fmt_manip_col],
    )

    def _set_operation(op: str) -> None:
        fmt_convert_col.visible = op == "convert"
        fmt_manip_col.visible = op not in ("convert", "favicon", "describe")
        control.visible = op not in ("favicon", "describe")

    def _set_disabled(running: bool) -> None:
        _set_fmt_disabled(running)
        if running:
            quality_container.opacity = 0.4
            quality_slider.disabled = True
        else:
            _update_quality_state(_current_fmt[0])

    return FmtRefs(
        control=control,
        set_operation=_set_operation,
        set_disabled=_set_disabled,
        get_fmt=_get_fmt,
        get_quality=lambda: (
            int(quality_slider.value) if not quality_slider.disabled else 90
        ),
        get_out_fmt=lambda: None if _out_fmt_val[0] == "preserve" else _out_fmt_val[0],
        get_out_quality=lambda: int(out_quality_slider.value),
    )
