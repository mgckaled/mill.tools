"""View de progresso do pipeline de transcrição."""

from __future__ import annotations

from typing import Callable

import flet as ft

from src.gui.events import PipelineEvent

_MAX_LOG_LINES = 200

_STAGE_COLORS: dict[str, str] = {
    "download": ft.Colors.BLUE_300,
    "transcribe": ft.Colors.GREEN_300,
    "format": ft.Colors.ORANGE_300,
    "analyze": ft.Colors.PURPLE_300,
    "prompt": ft.Colors.TEAL_300,
    "pipeline": ft.Colors.WHITE,
    "system": ft.Colors.GREY_400,
}


def _resolve_message(event: PipelineEvent) -> str | None:
    """Converte um PipelineEvent em uma string legível para o log.

    Args:
        event: Evento recebido do pipeline worker.

    Returns:
        String de mensagem ou None se o evento não produz saída visível.
    """
    p = event.payload
    t = event.type

    match t:
        case "download_start":
            return "Baixando áudio..."
        case "download_done":
            return "Áudio baixado."
        case "whisper_loading":
            return "Carregando modelo Whisper..."
        case "whisper_loaded":
            return "Modelo carregado."
        case "transcribe_started":
            return "Transcrevendo..."
        case "transcribe_segment":
            return p.get("text", "")
        case "transcribe_done":
            return "Transcrição concluída."
        case "format_started":
            n = p.get("total", "?")
            return f"Formatando parágrafos ({n} chunks)..."
        case "format_chunk_start":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            return f"Formatando chunk {i}/{total}..."
        case "format_chunk_done":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            elapsed = p.get("elapsed", "?")
            return f"Chunk {i}/{total} concluído ({elapsed}s)."
        case "format_done":
            return "Formatação concluída."
        case "analyze_started":
            n = p.get("total", "?")
            return f"Analisando ({n} chunks)..."
        case "analyze_chunk_start":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            return f"Analisando chunk {i}/{total}..."
        case "analyze_chunk_done":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            return f"Chunk {i}/{total} concluído."
        case "analyze_merge_start":
            return "Consolidando análises..."
        case "language_detected":
            lang = p.get("language", "?")
            return f"Idioma detectado: {lang}"
        case "translation_start":
            return "Traduzindo para PT-BR..."
        case "translation_done":
            return "Tradução concluída."
        case "analyze_done":
            return "Análise concluída."
        case "prompt_started":
            n = p.get("total", "?")
            return f"Condensando para prompt-ready ({n} chunks)..."
        case "prompt_chunk_start":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            return f"Condensando chunk {i}/{total}..."
        case "prompt_chunk_done":
            i = p.get("chunk", "?")
            total = p.get("total", "?")
            elapsed = p.get("elapsed", "?")
            return f"Chunk {i}/{total} concluído ({elapsed}s)."
        case "prompt_done":
            ratio = p.get("ratio", "?")
            return f"Prompt-ready gerado ({ratio}% do original)."
        case "pipeline_done":
            return "Pipeline concluído!"
        case "pipeline_error":
            msg = p.get("message", "erro desconhecido")
            return f"Erro: {msg}"
        case "log":
            return p.get("message", "")
        case _:
            return None


def _resolve_progress(event: PipelineEvent) -> float | None:
    """Retorna o valor de progresso (0.0–1.0) para eventos de chunk.

    Retorna None para manter a barra indeterminada.

    Args:
        event: Evento recebido do pipeline worker.

    Returns:
        Float entre 0 e 1, ou None.
    """
    p = event.payload
    t = event.type

    if t in ("format_chunk_start", "format_chunk_done",
             "analyze_chunk_start", "analyze_chunk_done",
             "prompt_chunk_start", "prompt_chunk_done"):
        chunk = p.get("chunk")
        total = p.get("total")
        if chunk is not None and total and total > 0:
            return chunk / total

    return None


def _resolve_stage_label(event: PipelineEvent) -> str | None:
    """Retorna o texto de etapa atual para o header da view.

    Args:
        event: Evento recebido do pipeline worker.

    Returns:
        String de rótulo de etapa ou None se não deve atualizar o label.
    """
    t = event.type
    match t:
        case "download_start":
            return "Baixando áudio..."
        case "whisper_loading":
            return "Carregando modelo Whisper..."
        case "transcribe_started":
            return "Transcrevendo..."
        case "format_started":
            return "Formatando parágrafos..."
        case "analyze_started":
            return "Analisando..."
        case "analyze_merge_start":
            return "Consolidando análises..."
        case "translation_start":
            return "Traduzindo para PT-BR..."
        case "prompt_started":
            return "Gerando prompt-ready..."
        case "pipeline_done":
            return "Pipeline concluído!"
        case "pipeline_error":
            return "Erro no pipeline."
        case _:
            return None


def build_progress_view(
    page: ft.Page,
    on_cancel: Callable[[], None],
    on_done: Callable[[dict], None],
) -> ft.Control:
    """Retorna o controle raiz da view de progresso.

    Assina page.pubsub para receber PipelineEvents emitidos pelo worker e
    atualiza a UI de forma thread-safe. O handler roda na thread da UI, então
    page.update() pode ser chamado diretamente.

    Args:
        page: Página Flet.
        on_cancel: Callable chamado ao clicar Cancelar — deve setar um
            threading.Event para sinalizar ao worker que deve parar.
        on_done: Callable chamado quando pipeline_done é recebido — deve
            navegar para a result_view.
    """

    # --- widgets mutáveis ---
    stage_label = ft.Text(
        "Iniciando pipeline...",
        size=16,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.WHITE,
    )

    progress_bar = ft.ProgressBar(
        value=None,
        width=float("inf"),
        expand=True,
        color=ft.Colors.BLUE_400,
        bgcolor=ft.Colors.GREY_800,
    )

    log_list = ft.ListView(
        expand=True,
        spacing=2,
        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        auto_scroll=True,
    )

    cancel_button = ft.TextButton(
        "Cancelar",
        icon=ft.Icons.CANCEL_OUTLINED,
        icon_color=ft.Colors.RED_300,
        style=ft.ButtonStyle(color=ft.Colors.RED_300),
        on_click=lambda _: on_cancel(),
    )

    # --- handler pubsub ---
    def _handle_event(event: PipelineEvent) -> None:
        """Processa um PipelineEvent e atualiza os widgets da view."""

        # rótulo da etapa atual
        label = _resolve_stage_label(event)
        if label is not None:
            stage_label.value = label

        # progresso determinado vs indeterminado
        prog = _resolve_progress(event)
        if prog is not None:
            progress_bar.value = prog
        elif event.type in (
            "download_start",
            "whisper_loading",
            "transcribe_started",
            "format_started",
            "analyze_started",
            "analyze_merge_start",
            "translation_start",
            "prompt_started",
        ):
            progress_bar.value = None  # indeterminado entre etapas

        # linha de log
        msg = _resolve_message(event)
        if msg:
            color = _STAGE_COLORS.get(event.stage, ft.Colors.WHITE)
            log_list.controls.append(
                ft.Text(
                    msg,
                    size=12,
                    color=color,
                    selectable=True,
                )
            )
            # limita o buffer para evitar uso excessivo de memória
            if len(log_list.controls) > _MAX_LOG_LINES:
                del log_list.controls[: len(log_list.controls) - _MAX_LOG_LINES]

        # conclusão do pipeline
        if event.type == "pipeline_done":
            progress_bar.value = 1.0
            cancel_button.disabled = True
            page.update()
            page.pubsub.unsubscribe()
            on_done(event.payload)
            return

        page.update()

    page.pubsub.subscribe(_handle_event)

    # --- layout ---
    header = ft.Column(
        controls=[
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SETTINGS_SUGGEST_ROUNDED, color=ft.Colors.BLUE_300),
                    stage_label,
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                content=progress_bar,
                padding=ft.Padding(left=0, right=0, top=4, bottom=8),
            ),
        ],
        spacing=4,
    )

    log_container = ft.Container(
        content=log_list,
        expand=True,
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.GREY_700),
            right=ft.BorderSide(1, ft.Colors.GREY_700),
            top=ft.BorderSide(1, ft.Colors.GREY_700),
            bottom=ft.BorderSide(1, ft.Colors.GREY_700),
        ),
        border_radius=6,
        bgcolor=ft.Colors.GREY_900,
    )

    footer = ft.Row(
        controls=[cancel_button],
        alignment=ft.MainAxisAlignment.END,
    )

    root = ft.Column(
        controls=[
            header,
            log_container,
            footer,
        ],
        expand=True,
        spacing=8,
    )

    return root
