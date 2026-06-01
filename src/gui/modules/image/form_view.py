"""Formulário de entrada do módulo Imagens."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from src.gui.components.input_source import InputItem, build_input_source
from src.gui.theme.components import hairline, help_icon_for, section, segmented_selector

_ALLOWED_EXTS = [
    "jpg", "jpeg", "png", "webp", "avif",
    "tiff", "tif", "bmp", "gif", "ico",
]

_FMT_OPTIONS = ["jpg", "png", "webp", "avif", "tiff", "bmp", "gif", "ico"]

# Formatos cujo slider de qualidade é relevante
_LOSSY_FMTS: frozenset[str] = frozenset({"jpg", "webp"})

_QUALITY_DEFAULT = 90.0
_QUALITY_MIN = 50.0
_QUALITY_MAX = 100.0
_QUALITY_DIVISIONS = 10


@dataclass
class ImageArgs:
    """Parâmetros do pipeline de imagens recebidos do formulário."""

    items: list[InputItem] = field(default_factory=list)
    fmt: str = "jpg"
    quality: int = 90


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

    # ── Formato de saída — grade 4×2 ─────────────────────────────────────────

    _current_fmt: list[str] = ["jpg"]

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

    # ── Qualidade — slider (50–100, só para lossy) ───────────────────────────

    _quality_val: list[float] = [_QUALITY_DEFAULT]

    quality_value_text = ft.Text(
        f"{int(_QUALITY_DEFAULT)}",
        size=13,
        weight=ft.FontWeight.W_600,
        color=ft.Colors.PRIMARY,
    )

    from src.gui.theme.tokens import Space, Type
    _q_icon = help_icon_for("image.quality", page)
    _q_label_row = ft.Row(
        controls=[
            ft.Text("Qualidade", size=Type.label.size, weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE_VARIANT),
            *([_q_icon] if _q_icon else []),
            ft.Container(expand=True),
            quality_value_text,
        ],
        spacing=Space.xs,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    quality_slider = ft.Slider(
        value=_QUALITY_DEFAULT,
        min=_QUALITY_MIN,
        max=_QUALITY_MAX,
        divisions=_QUALITY_DIVISIONS,
        active_color=ft.Colors.PRIMARY,
        expand=True,
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

    quality_col = ft.Column(
        controls=[_q_label_row, quality_slider],
        spacing=Space.xs,
    )

    quality_container = ft.Container(
        content=quality_col,
        opacity=1.0,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_IN),
    )

    _quality_disabled: list[bool] = [False]

    def _update_quality_state(fmt: str, do_update: bool = True) -> None:
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

    # estado inicial — não chama update (controle ainda não está na página)
    _update_quality_state(_current_fmt[0], do_update=False)

    # ── Botão Iniciar ─────────────────────────────────────────────────────────

    start_btn = ft.FilledButton(
        "Iniciar",
        icon=ft.Icons.PLAY_ARROW_ROUNDED,
        disabled=True,
        on_click=lambda _: _on_start_click(),
    )

    def _on_start_click() -> None:
        items = input_source.get_items()
        if not items:
            return
        quality = int(_quality_val[0]) if not _quality_disabled[0] else 90
        on_start(ImageArgs(items=items, fmt=_get_fmt(), quality=quality))

    # ── set_running ───────────────────────────────────────────────────────────

    def _set_running(running: bool) -> None:
        start_btn.disabled = running or len(input_source.get_items()) == 0
        start_btn.text = "Executando..." if running else "Iniciar"
        start_btn.icon = ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
        input_source.set_enabled(not running)
        _set_fmt_disabled(running)
        if running:
            quality_container.opacity = 0.4
            quality_slider.disabled = True
        else:
            _update_quality_state(_current_fmt[0])
        page.update()

    # ── layout ────────────────────────────────────────────────────────────────

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
                        section("Formato de saída", fmt_grid,
                                help_key="image.format", page=page),
                        hairline(),
                        quality_container,
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
