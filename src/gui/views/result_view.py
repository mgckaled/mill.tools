"""View de resultados do pipeline — exibe transcrição, análise e prompt-ready em abas."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import flet as ft


def _read(path: Path | None) -> str:
    """Lê o conteúdo de um arquivo de resultado.

    Args:
        path: Caminho do arquivo a ser lido, ou None.

    Returns:
        Conteúdo do arquivo como string, ou mensagem informativa se indisponível.
    """
    if path is None or not Path(path).exists():
        return "_Arquivo não gerado._"
    return Path(path).read_text(encoding="utf-8")


def _open_folder(path: Path | None) -> None:
    """Abre o Explorer do Windows no diretório do arquivo.

    Args:
        path: Caminho do arquivo cujo diretório será aberto.
    """
    if path is None:
        return
    folder = Path(path).parent
    subprocess.Popen(["explorer", str(folder)])


def build_result_view(
    page: ft.Page,
    raw_path: Path | None,
    analysis_path: Path | None,
    prompt_path: Path | None,
    on_restart: Callable,
) -> ft.Control:
    """Retorna o controle raiz da view de resultados.

    Exibe os arquivos gerados pelo pipeline em três abas (Transcrição, Análise,
    Prompt-ready) com ações de abrir pasta, copiar conteúdo e reiniciar.

    Args:
        page: Instância da página Flet.
        raw_path: Caminho do arquivo de transcrição bruta (.txt), ou None.
        analysis_path: Caminho do arquivo de análise (.md), ou None.
        prompt_path: Caminho do arquivo prompt-ready (.txt), ou None.
        on_restart: Callback chamado ao clicar em "Nova transcrição".

    Returns:
        Controle raiz da view de resultados.
    """
    raw_content = _read(raw_path)
    analysis_content = _read(analysis_path)
    prompt_content = _read(prompt_path)

    contents = [raw_content, analysis_content, prompt_content]

    def _make_tab_content(text: str) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Markdown(
                        value=text,
                        expand=True,
                        selectable=True,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )

    tabs = ft.Tabs(
        selected_index=0,
        expand=True,
        tabs=[
            ft.Tab(
                text="Transcrição",
                content=_make_tab_content(raw_content),
            ),
            ft.Tab(
                text="Análise",
                content=_make_tab_content(analysis_content),
            ),
            ft.Tab(
                text="Prompt-ready",
                content=_make_tab_content(prompt_content),
            ),
        ],
    )

    def on_copy(_: ft.ControlEvent) -> None:
        idx = tabs.selected_index or 0
        page.set_clipboard(contents[idx])
        page.open(
            ft.SnackBar(
                content=ft.Text("Conteúdo copiado para a área de transferência."),
                duration=2000,
            )
        )

    def on_open_folder(_: ft.ControlEvent) -> None:
        _open_folder(raw_path)

    def on_new_transcription(_: ft.ControlEvent) -> None:
        on_restart()

    action_row = ft.Row(
        controls=[
            ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                tooltip="Abrir pasta",
                on_click=on_open_folder,
            ),
            ft.IconButton(
                icon=ft.Icons.COPY,
                tooltip="Copiar conteúdo da aba",
                on_click=on_copy,
            ),
            ft.Container(expand=True),
            ft.TextButton(
                text="Nova transcrição",
                on_click=on_new_transcription,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        controls=[
            action_row,
            ft.Divider(height=1),
            tabs,
        ],
        expand=True,
    )
