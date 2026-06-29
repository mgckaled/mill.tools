"""Descrição IA tab for the image module.

``describe`` is image→text (unlike the 11 image→image ops), so it lives in its
own tab instead of the operation grid: the source image on the left, the rendered
Markdown description on the right. Reuses ``build_ai_blocks`` (the vision model
dropdown, incl. gemma3-4b) and ``build_input_source``; the actual run goes through
the shared image worker (``operation="describe"``) via the ``on_run`` callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.core.image.args import ImageArgs
from src.core.io_types import InputItem
from src.gui.components.input_source import build_input_source
from src.gui.events import PipelineEvent
from src.gui.modules.image.blocks.ai import build_ai_blocks
from src.gui.theme.components import Cursor, hairline, section, spinner
from src.gui.theme.tokens import Color, Radius, Space, Type

_ALLOWED_EXTS = ["jpg", "jpeg", "png", "webp", "avif", "tiff", "tif", "bmp", "gif"]

# 1×1 px transparent PNG — Flet 0.85 requires src in the Image constructor.
_BLANK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@dataclass
class DescribeTab:
    """Describe tab control + drive hooks for view.py."""

    control: ft.Control
    set_running: Callable[[bool], None]
    on_event: Callable[[PipelineEvent], None]
    fill_from_path: Callable[[str], None]


def build_describe_tab(
    page: ft.Page, on_run: Callable[[ImageArgs], None]
) -> DescribeTab:
    """Build the Descrição IA tab (source | description) and return its hooks."""
    ai_refs = build_ai_blocks(page)
    describe_block = ai_refs.describe_block
    describe_block.visible = True  # always shown in this tab

    # ── Source ────────────────────────────────────────────────────────────────
    def _on_items_change(items: list[InputItem]) -> None:
        run_btn.disabled = len(items) == 0
        if run_btn.page:
            run_btn.update()

    input_source = build_input_source(
        page,
        allowed_extensions=_ALLOWED_EXTS,
        on_change=_on_items_change,
        url_hint="URL direta da imagem (unsplash, pexels…)",
    )

    run_btn = ft.FilledButton(
        "Descrever",
        icon=ft.Icons.AUTO_AWESOME_OUTLINED,
        disabled=True,
        style=ft.ButtonStyle(mouse_cursor=Cursor.btn),
    )

    def _on_run_click(_e) -> None:
        items = input_source.get_items()
        if not items:
            return
        args = ImageArgs(
            items=items,
            operation="describe",
            describe_model=ai_refs.get_desc_model(),
            describe_prompt=ai_refs.get_desc_prompt(),
        )
        on_run(args)

    run_btn.on_click = _on_run_click

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
                            "Imagem",
                            input_source.control,
                            help_key="image.input",
                            page=page,
                        ),
                        hairline(),
                        describe_block,
                        hairline(),
                        ft.Row([run_btn], alignment=ft.MainAxisAlignment.END),
                    ],
                ),
            ),
        ],
    )

    # ── Result panel: image | markdown ────────────────────────────────────────
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

    desc_md = ft.Markdown("", selectable=True)
    empty_hint = ft.Text(
        "A descrição aparecerá aqui.",
        italic=True,
        color=ft.Colors.ON_SURFACE_VARIANT,
        size=Type.input.size,
    )
    desc_pane = ft.Container(
        content=ft.Column(
            [empty_hint, desc_md], scroll=ft.ScrollMode.AUTO, expand=True
        ),
        expand=True,
        padding=Space.sm,
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        ),
        border_radius=Radius.sm,
    )

    spin, _start_spin, _stop_spin = spinner()
    status_label = ft.Text(
        "Escolha uma imagem e clique em Descrever →",
        size=Type.input.size,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    result_panel = ft.Column(
        controls=[
            ft.Row(
                [spin, status_label],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row([img_pane, desc_pane], expand=True, spacing=8),
        ],
        expand=True,
        spacing=8,
    )

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
        run_btn.disabled = running or len(input_source.get_items()) == 0
        run_btn.text = "Descrevendo..." if running else "Descrever"
        input_source.set_enabled(not running)
        ai_refs.set_desc_disabled(running)

    def _on_event(event: PipelineEvent) -> None:
        t = event.type
        p = event.payload
        if t == "image_op_start" and p.get("operation") == "describe":
            thumb = p.get("thumb")
            if thumb:
                result_img.src = thumb
            desc_md.value = ""
            empty_hint.visible = True
            status_label.value = "Analisando imagem (Ollama)…"
            status_label.italic = False
            status_label.color = ft.Colors.ON_SURFACE
            _start_spin()
        elif t == "image_op_done":
            out = p.get("output_path", "")
            if out.endswith(".txt"):
                try:
                    desc_md.value = Path(out).read_text(encoding="utf-8")
                    empty_hint.visible = False
                except Exception:
                    pass
        elif t == "task_done":
            status_label.value = "Concluído."
            _stop_spin()
        elif t == "task_error":
            status_label.value = p.get("message", "Erro na descrição.")
            _stop_spin()

    def _fill_from_path(path: str) -> None:
        input_source.add_item(InputItem(kind="local", value=path))

    return DescribeTab(
        control=control,
        set_running=_set_running,
        on_event=_on_event,
        fill_from_path=_fill_from_path,
    )
