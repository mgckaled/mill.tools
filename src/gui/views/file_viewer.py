"""In-app viewer for already-generated text outputs (.md / .txt).

Opens a modal that renders the file's content (Markdown) so a processed result
can be read inside the app — without re-running the pipeline and without leaving
for an external editor. Used by the Library when a text item is opened.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import flet as ft

from src.gui.theme.tokens import Radius, Space, Type

# File types the in-app viewer renders. Everything else opens externally.
VIEWER_EXTS = {".md", ".txt"}

# Guard against rendering a pathologically large file in the modal.
_MAX_CHARS = 400_000

# Readable blockquote styling on the dark theme — Flet's default renders a light
# bluish background that makes "> quote" text unreadable. Subtle overlay + a
# left accent bar + explicit (light) text color instead.
_MD_STYLE = ft.MarkdownStyleSheet(
    blockquote_text_style=ft.TextStyle(color=ft.Colors.ON_SURFACE),
    blockquote_padding=ft.Padding(
        left=Space.sm, right=Space.sm, top=Space.xs, bottom=Space.xs
    ),
    blockquote_decoration=ft.BoxDecoration(
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
        border_radius=Radius.sm,
        border=ft.Border(
            left=ft.BorderSide(3, ft.Colors.with_opacity(0.6, ft.Colors.PRIMARY))
        ),
    ),
)


def is_viewable(path: Path) -> bool:
    """True when *path* is a text output the in-app viewer can render."""
    return Path(path).suffix.lower() in VIEWER_EXTS


def open_file_viewer(page: ft.Page, path: Path) -> None:
    """Open a modal rendering the text/markdown content of *path*."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logging.debug("[d] viewer read failed for %s: %s", p, exc)
        text = "_Não foi possível ler o arquivo._"
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n\n… _(conteúdo truncado para exibição)_"

    body = ft.Markdown(
        value=text,
        selectable=True,
        expand=True,
        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        md_style_sheet=_MD_STYLE,
    )

    async def _copy(_e: ft.ControlEvent) -> None:
        await ft.Clipboard().set(text)
        page.show_dialog(
            ft.SnackBar(content=ft.Text("Conteúdo copiado."), duration=2000)
        )

    def _open_external(_e: ft.ControlEvent) -> None:
        try:
            os.startfile(str(p))  # Windows shell open
        except OSError:
            pass

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.ARTICLE_OUTLINED, color=ft.Colors.PRIMARY, size=20),
                ft.Text(
                    p.name,
                    size=Type.body.size,
                    weight=ft.FontWeight.W_600,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
            ],
            spacing=Space.xs,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(
            width=760,
            height=560,
            content=ft.Column(controls=[body], scroll=ft.ScrollMode.AUTO, expand=True),
        ),
        actions=[
            ft.TextButton("Copiar", icon=ft.Icons.COPY, on_click=_copy),
            ft.TextButton(
                "Abrir externamente",
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=_open_external,
            ),
            ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog()),
        ],
    )
    page.show_dialog(dlg)
