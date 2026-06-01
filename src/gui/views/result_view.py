"""View de resultados do pipeline — exibe transcrição, análise e prompt-ready em abas."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.theme.components import hairline


def _read(path: Path | None) -> str:
    if path is None or not Path(path).exists():
        return "_Arquivo não gerado._"
    return Path(path).read_text(encoding="utf-8")


def _open_folder(path: Path | None) -> None:
    if path is None:
        return
    subprocess.Popen(["explorer", str(Path(path).parent)])


def build_result_view(
    page: ft.Page,
    raw_path: Path | None,
    analysis_path: Path | None,
    prompt_path: Path | None,
    on_restart: Callable | None = None,
) -> ft.Control:
    """Retorna o controle raiz da view de resultados.

    Implementa tab switching manual (ft.Tabs/ft.Tab incompatíveis com Flet 0.85).
    Exibe Transcrição, Análise e Prompt-ready com ações de copiar e abrir pasta.
    on_restart é opcional — no layout split o usuário reinicia pelo formulário.
    """
    raw_content = _read(raw_path)
    analysis_content = _read(analysis_path)
    prompt_content = _read(prompt_path)

    tab_labels = ["Transcrição", "Análise", "Prompt-ready"]
    tab_contents = [raw_content, analysis_content, prompt_content]
    selected: list[int] = [0]

    # --- painéis de conteúdo ---
    _md_style = ft.MarkdownStyleSheet(
        blockquote_decoration=ft.BoxDecoration(
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
            border_radius=4,
        ),
    )

    def _make_panel(text: str) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Markdown(
                        value=text,
                        expand=True,
                        selectable=True,
                        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
                        md_style_sheet=_md_style,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        )

    panels = [_make_panel(c) for c in tab_contents]
    for i, p in enumerate(panels):
        p.visible = (i == 0)

    content_stack = ft.Column(
        controls=panels,
        expand=True,
    )

    # --- cabeçalho de abas ---
    tab_buttons: list[ft.TextButton] = []

    def _make_tab_btn(label: str, idx: int) -> ft.TextButton:
        return ft.TextButton(
            label,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: ft.Colors.PRIMARY if idx == 0 else ft.Colors.ON_SURFACE_VARIANT,
                },
            ),
            on_click=lambda _, i=idx: _switch(i),
        )

    def _switch(idx: int) -> None:
        selected[0] = idx
        for i, (btn, panel) in enumerate(zip(tab_buttons, panels)):
            active = i == idx
            panel.visible = active
            btn.style = ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
                },
            )
        page.update()

    tab_buttons.extend(_make_tab_btn(label, i) for i, label in enumerate(tab_labels))

    tab_bar = ft.Row(
        controls=[
            *tab_buttons,
            ft.Container(expand=True),
        ],
        spacing=0,
    )

    # --- ações ---
    def on_copy(_: ft.ControlEvent) -> None:
        page.set_clipboard(tab_contents[selected[0]])
        page.open(ft.SnackBar(
            content=ft.Text("Conteúdo copiado para a área de transferência."),
            duration=2000,
        ))

    action_controls: list[ft.Control] = [
        ft.IconButton(ft.Icons.FOLDER_OPEN, tooltip="Abrir pasta",
                      on_click=lambda _: _open_folder(raw_path)),
        ft.IconButton(ft.Icons.COPY, tooltip="Copiar conteúdo da aba",
                      on_click=on_copy),
        ft.Container(expand=True),
    ]
    if on_restart is not None:
        action_controls.append(
            ft.TextButton("Nova transcrição", on_click=lambda _: on_restart())
        )

    action_row = ft.Row(
        controls=action_controls,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        controls=[
            action_row,
            hairline(),
            tab_bar,
            ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
            content_stack,
        ],
        expand=True,
    )
