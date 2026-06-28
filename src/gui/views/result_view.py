"""View de resultados do pipeline — exibe transcrição, análise e prompt-ready em abas."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.modules.ai.index_button import rag_index_button
from src.gui.theme.components import hairline
from src.gui.views.insights_panel import build_insights_panel


def _read(path: Path | None) -> str:
    if path is None or not Path(path).exists():
        return "_Arquivo não gerado._"
    return Path(path).read_text(encoding="utf-8")


def _path_exists(path: Path | None) -> bool:
    return path is not None and Path(path).exists()


def _open_folder(path: Path | None) -> None:
    if path is None:
        return
    subprocess.Popen(["explorer", str(Path(path).parent)])


def _open_file(path: Path | None) -> None:
    """Open a file in the system default application (Windows shell)."""
    if not _path_exists(path):
        return
    try:
        os.startfile(str(Path(path)))  # Windows shell open
    except OSError:
        pass


def _pick_srt(subtitle_paths: list[Path] | None) -> Path | None:
    """Return the .srt path if any (preferred for the in-tab preview)."""
    if not subtitle_paths:
        return None
    for p in subtitle_paths:
        if Path(p).suffix.lower() == ".srt":
            return Path(p)
    # Fall back to the first one if no .srt is present
    return Path(subtitle_paths[0])


def build_result_view(
    page: ft.Page,
    raw_path: Path | None,
    analysis_path: Path | None,
    prompt_path: Path | None,
    subtitle_paths: list[Path] | None = None,
    on_restart: Callable | None = None,
) -> ft.Control:
    """Retorna o controle raiz da view de resultados.

    Implementa tab switching manual (ft.Tabs/ft.Tab incompatíveis com Flet 0.85).
    Exibe Transcrição, Análise e Prompt-ready com ações de copiar e abrir pasta.
    Quando subtitle_paths é fornecido, adiciona uma aba "Legendas" com prévia
    do .srt (mais legível que VTT) e um botão extra para abrir a pasta delas.
    on_restart é opcional — no layout split o usuário reinicia pelo formulário.
    """
    raw_content = _read(raw_path)
    analysis_content = _read(analysis_path)
    prompt_content = _read(prompt_path)
    srt_path = _pick_srt(subtitle_paths)
    srt_content = _read(srt_path) if srt_path else None

    tab_labels = ["Transcrição", "Análise", "Prompt-ready"]
    tab_contents = [raw_content, analysis_content, prompt_content]
    # Backing file per tab (parallel to tab_labels) — used by the "Abrir arquivo"
    # shortcut to open the active tab's file in the system default app.
    tab_paths: list[Path | None] = [
        Path(raw_path) if raw_path else None,
        Path(analysis_path) if analysis_path else None,
        Path(prompt_path) if prompt_path else None,
    ]
    if srt_content is not None:
        tab_labels.append("Legendas")
        tab_contents.append(srt_content)
        tab_paths.append(srt_path)
    selected: list[int] = [0]

    # --- painéis de conteúdo ---
    _md_style = ft.MarkdownStyleSheet(
        blockquote_decoration=ft.BoxDecoration(
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
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
        p.visible = i == 0

    # --- Insights tab (Plan 4B): keyphrases/summary/entities of the transcript ---
    # Built lazily — the engines run off-thread only when the tab is first opened.
    _insights_loader: Callable[[], None] | None = None
    _insights_idx = -1
    if raw_path is not None:
        insights_body, _insights_loader = build_insights_panel(page, Path(raw_path))
        insights_panel = ft.Container(
            content=insights_body,
            expand=True,
            visible=False,
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        )
        _insights_idx = len(tab_labels)
        tab_labels.append("Insights")
        tab_contents.append("")  # keep parallel for on_copy/index safety
        tab_paths.append(None)  # no backing file → "Abrir arquivo" stays disabled
        panels.append(insights_panel)

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
                    ft.ControlState.DEFAULT: ft.Colors.PRIMARY
                    if idx == 0
                    else ft.Colors.ON_SURFACE_VARIANT,
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
                    ft.ControlState.DEFAULT: ft.Colors.PRIMARY
                    if active
                    else ft.Colors.ON_SURFACE_VARIANT,
                },
            )
        # The "Abrir arquivo" shortcut only makes sense for a generated file.
        open_file_btn.disabled = not _path_exists(tab_paths[idx])
        # First time the Insights tab is shown, compute it off-thread.
        if idx == _insights_idx and _insights_loader is not None:
            _insights_loader()
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
        page.open(
            ft.SnackBar(
                content=ft.Text("Conteúdo copiado para a área de transferência."),
                duration=2000,
            )
        )

    def _current_path() -> Path | None:
        idx = selected[0]
        return tab_paths[idx] if 0 <= idx < len(tab_paths) else None

    def _open_current_folder(_: ft.ControlEvent) -> None:
        _open_folder(_current_path() or (Path(raw_path) if raw_path else None))

    def _open_current_file(_: ft.ControlEvent) -> None:
        _open_file(_current_path())

    open_file_btn = ft.IconButton(
        ft.Icons.OPEN_IN_NEW,
        tooltip="Abrir arquivo da aba atual",
        on_click=_open_current_file,
        disabled=not _path_exists(tab_paths[0]),
    )

    action_controls: list[ft.Control] = [
        ft.IconButton(
            ft.Icons.FOLDER_OPEN,
            tooltip="Abrir pasta da aba atual",
            on_click=_open_current_folder,
        ),
        open_file_btn,
        ft.IconButton(
            ft.Icons.COPY, tooltip="Copiar conteúdo da aba", on_click=on_copy
        ),
    ]
    if srt_path is not None:
        action_controls.append(
            ft.IconButton(
                ft.Icons.SUBTITLES,
                tooltip="Abrir pasta de legendas",
                on_click=lambda _, p=srt_path: _open_folder(p),
            )
        )
    action_controls.append(ft.Container(expand=True))
    # Offer indexing into the RAG corpus when there is any textual output to feed
    # it (transcription/analysis/prompt-ready are always .txt/.md).
    if any(_path_exists(p) for p in (raw_path, analysis_path, prompt_path)):
        action_controls.append(rag_index_button(page))
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
