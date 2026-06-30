"""Visualizar tab for the audio module — audio→image (waveform / spectrogram).

Audio→image is a distinct nature from the main audio→audio flow, so it lives in
its own tab (mirroring ``image/describe_tab.py``). The static PNG is rendered ONCE
by ffmpeg off-thread (``page.run_task`` + ``asyncio.to_thread``) and shown in a
plain ``ft.Image`` — it never animates or re-renders per tick, so it is fully
separate from the live waveform cursor in the player (no perf risk).
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.theme.components import (
    Cursor,
    action_button,
    hairline,
    section,
    segmented_selector,
    spinner,
)
from src.gui.theme.tokens import Color, Radius, Space, Type
from src.utils import AUDIO_PROCESSED_DIR

_ALLOWED_EXTS = [
    "mp3",
    "wav",
    "flac",
    "ogg",
    "opus",
    "aac",
    "m4a",
    "mp4",
    "mkv",
    "webm",
]

# 1×1 px transparent PNG — Flet 0.85 requires src in the Image constructor.
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass
class VisualizeTab:
    """Visualizar tab control + drive hooks for view.py."""

    control: ft.Control
    set_running: Callable[[bool], None]
    fill_from_path: Callable[[str], None]


def build_visualize_tab(page: ft.Page, nav: list) -> VisualizeTab:
    """Build the Visualizar tab (source | generated image) and return its hooks."""
    _last_output: list[str | None] = [None]

    # ── Source ────────────────────────────────────────────────────────────────
    def _on_items_change(items: list[InputItem]) -> None:
        gen_btn.disabled = not any(it.kind == "local" for it in items)
        if gen_btn.page:
            gen_btn.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
    )

    kind_grid, _get_kind, _set_kind_disabled = segmented_selector(
        ["waveform", "spectrogram"],
        "waveform",
        page,
        labels={"waveform": "Waveform", "spectrogram": "Espectrograma"},
        columns=2,
    )

    gen_btn = ft.FilledButton(
        "Gerar",
        icon=ft.Icons.INSIGHTS_OUTLINED,
        disabled=True,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    form = ft.Column(
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
                            "Fonte",
                            input_source.control,
                            help_key="audio.input",
                            page=page,
                        ),
                        hairline(),
                        section("Tipo de imagem", kind_grid),
                        hairline(),
                        ft.Row([gen_btn], alignment=ft.MainAxisAlignment.END),
                    ],
                ),
            ),
        ],
    )

    # ── Result panel: image + footer actions ──────────────────────────────────
    result_img = ft.Image(_BLANK_PNG, fit=ft.BoxFit.CONTAIN, expand=True)
    img_pane = ft.Container(
        content=result_img,
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

    empty_hint = ft.Text(
        "A imagem aparecerá aqui.",
        italic=True,
        color=ft.Colors.ON_SURFACE_VARIANT,
        size=Type.input.size,
    )

    spin, _start_spin, _stop_spin = spinner()
    status_label = ft.Text(
        "Escolha um arquivo e clique em Gerar →",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    def _open_file(_e) -> None:
        out = _last_output[0]
        if out and Path(out).exists():
            os.startfile(out)  # noqa: S606 — Windows-only desktop app

    def _open_folder(_e) -> None:
        AUDIO_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["explorer", str(AUDIO_PROCESSED_DIR)], check=False)

    def _open_in_images(_e) -> None:
        out = _last_output[0]
        if out and nav:
            nav[0]("image", {"file": out})

    open_btn = action_button(
        "Abrir arquivo",
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=_open_file,
        accent=ft.Colors.PRIMARY,
    )
    folder_btn = action_button(
        "Abrir pasta",
        icon=ft.Icons.FOLDER_OPEN_OUTLINED,
        on_click=_open_folder,
        accent=ft.Colors.PRIMARY,
    )
    to_images_btn = action_button(
        "Abrir no módulo Imagens",
        icon=ft.Icons.IMAGE_OUTLINED,
        on_click=_open_in_images,
        accent=Color.log.ok,
    )
    footer = ft.Row(
        [open_btn, folder_btn, to_images_btn],
        spacing=Space.xs,
        visible=False,
    )

    result_panel = ft.Column(
        controls=[
            ft.Row(
                [spin, status_label],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Stack(
                [
                    img_pane,
                    ft.Container(
                        content=empty_hint, expand=True, alignment=ft.Alignment.CENTER
                    ),
                ],
                expand=True,
            ),
            footer,
        ],
        expand=True,
        spacing=8,
    )

    # ── Generate (off-thread) ─────────────────────────────────────────────────
    async def _render() -> None:
        from src.core.audio.visualize import (
            render_spectrogram_png,
            render_waveform_png,
        )

        locals_ = [it for it in input_source.get_items() if it.kind == "local"]
        if not locals_:
            return
        src = Path(locals_[0].value)
        kind = _get_kind()
        try:
            if kind == "spectrogram":
                out = await asyncio.to_thread(
                    render_spectrogram_png, src, AUDIO_PROCESSED_DIR
                )
            else:
                out = await asyncio.to_thread(
                    render_waveform_png, src, AUDIO_PROCESSED_DIR
                )
        except Exception as exc:  # defensive — never break the tab
            logging.getLogger(__name__).warning("[!] audio viz failed: %s", exc)
            status_label.value = "Falha ao gerar a imagem."
            _stop_spin()
            _set_running(False)
            page.update()
            return

        _last_output[0] = str(out)
        result_img.src = str(out)
        empty_hint.visible = False
        footer.visible = True
        status_label.value = f"Gerado: {out.name}"
        status_label.italic = False
        status_label.color = ft.Colors.ON_SURFACE
        _stop_spin()
        _set_running(False)
        page.update()

    def _on_generate(_e) -> None:
        locals_ = [it for it in input_source.get_items() if it.kind == "local"]
        if not locals_:
            return
        _set_running(True)
        status_label.value = "Gerando imagem…"
        status_label.italic = False
        status_label.color = ft.Colors.ON_SURFACE
        # Golden rule: show the "running" state first, then start the spinner.
        page.update()
        _start_spin()
        page.run_task(_render)

    gen_btn.on_click = _on_generate

    control = ft.Row(
        controls=[
            ft.Container(content=form, width=380),
            ft.VerticalDivider(width=2, thickness=1.5, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(
                content=result_panel,
                expand=True,
                padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            ),
        ],
        expand=True,
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # ── Drive hooks ───────────────────────────────────────────────────────────
    def _set_running(running: bool) -> None:
        gen_btn.disabled = running or not any(
            it.kind == "local" for it in input_source.get_items()
        )
        gen_btn.text = "Gerando..." if running else "Gerar"
        input_source.set_enabled(not running)
        _set_kind_disabled(running)

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    return VisualizeTab(
        control=control,
        set_running=_set_running,
        fill_from_path=_fill_from_path,
    )
