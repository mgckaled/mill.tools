"""View de progresso do pipeline de transcrição."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.events import PipelineEvent
from src.transcriber import format_elapsed
from src.utils import format_duration

_MAX_LOG_LINES = 500


# ---------------------------------------------------------------------------
# Helpers de cor e formatação
# ---------------------------------------------------------------------------

def _color_for_prefix(msg: str) -> str:
    """Retorna cor Flet com base no prefixo estilo CLI da mensagem."""
    if msg.startswith("[*]"):
        return ft.Colors.CYAN_300
    if msg.startswith("[~]"):
        return ft.Colors.YELLOW_300
    if msg.startswith("[i]"):
        return ft.Colors.BLUE_300
    if msg.startswith("[✓]"):
        return ft.Colors.GREEN_300
    if msg.startswith("[!]"):
        return ft.Colors.RED_300
    if msg.startswith("[»]"):
        return ft.Colors.GREY_400
    if msg.startswith("[d]"):
        return ft.Colors.GREY_500
    return ft.Colors.WHITE


def _fmt_dur(seconds: int | float) -> str:
    return format_duration(int(seconds))


# ---------------------------------------------------------------------------
# Resolução de mensagens (retorna lista para suportar múltiplas linhas)
# ---------------------------------------------------------------------------

def _resolve_messages(event: PipelineEvent) -> list[str]:
    """Converte um PipelineEvent em zero ou mais linhas de log estilo CLI."""
    p = event.payload
    t = event.type

    match t:
        case "metadata_start":
            return ["[i] Fetching video metadata..."]

        case "metadata_done":
            title = p.get("title", "")
            dur = p.get("duration", 0)
            lines = []
            if title:
                lines.append(f"[i] Title: {title}")
            lines.append(f"[i] Duration: {_fmt_dur(dur)}")
            return lines

        case "audio_cached":
            path = p.get("audio_path", "")
            name = Path(path).name if path else path
            return [f"[»] Audio already exists, skipping download: {name}"]

        case "download_start":
            return ["[i] Downloading audio..."]

        case "download_done":
            path = p.get("audio_path", "")
            name = Path(path).name if path else path
            return [f"[✓] Audio downloaded: {name}"]

        case "whisper_loading":
            model = p.get("model_size", "?")
            device = p.get("device", "?").upper()
            ctype = p.get("compute_type", "?")
            return [f"[*] Loading model '{model}' on {device} ({ctype})..."]

        case "whisper_loaded":
            elapsed = p.get("elapsed", 0)
            return [f"[d] Model loaded in {elapsed:.1f}s"]

        case "transcribe_started":
            return ["[~] Transcribing... (this may take a while for long videos)"]

        case "language_detected":
            if event.stage == "transcribe":
                lang = p.get("language", "?")
                conf = p.get("confidence", 0)
                return [f"[i] Detected language: {lang} ({conf * 100:.0f}% confidence)"]
            else:
                lang = p.get("lang", p.get("language", "?"))
                return [
                    "[~] Detecting analysis language...",
                    f"[i] Detected language: {lang}",
                ]

        case "transcribe_segment":
            text = p.get("text", "").strip()
            if not text:
                return []
            suffix = " [?]" if p.get("is_low_confidence") else ""
            return [f"{text}{suffix}"]

        case "transcribe_done":
            lines = ["[✓] Transcription saved"]
            flagged = p.get("flagged_count", 0)
            if flagged:
                lines.append(
                    f"[!] {flagged} segment(s) flagged as low-confidence [?] — review recommended"
                )
            return lines

        case "transcribe_summary":
            return []  # tratado como card separado em _handle_event

        case "format_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Formatting: {name}")
            if model:
                lines.append(f"[*] Format model: {model}")
            return lines or ["[*] Formatting..."]

        case "format_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Formatting chunk {i}/{total}..."]

        case "format_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]

        case "format_done":
            elapsed = p.get("elapsed", 0)
            return [f"[✓] Formatted in place ({elapsed:.0f}s)"]

        case "analyze_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Analyzing: {name}")
            if model:
                lines.append(f"[*] Model: {model}")
            return lines or ["[*] Analyzing..."]

        case "analyze_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Analyzing chunk {i}/{total}..."]

        case "analyze_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]

        case "analyze_merge_start":
            n = p.get("total_chunks", "?")
            return [f"[~] Merging {n} partial analyses..."]

        case "translation_start":
            return ["[~] Translating analysis to PT-BR..."]

        case "translation_done":
            return ["[✓] Translation complete."]

        case "analyze_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", 0)
            name = Path(path).name if path else ""
            return [f"[✓] Analysis saved to: {name} ({elapsed:.0f}s)"]

        case "prompt_started":
            name = p.get("filename", "")
            model = p.get("model_name", "")
            lines = []
            if name:
                lines.append(f"[*] Building prompt-ready: {name}")
            if model:
                lines.append(f"[*] Prompt model: {model}")
            return lines or ["[*] Building prompt-ready..."]

        case "prompt_chunk_start":
            i = p.get("i", "?")
            total = p.get("total", "?")
            return [f"[~] Condensing chunk {i}/{total}..."]

        case "prompt_chunk_done":
            i = p.get("i", "?")
            elapsed = p.get("elapsed", 0)
            return [f"[d] Chunk {i} done in {elapsed:.1f}s"]

        case "prompt_done":
            path = p.get("output_path", "")
            elapsed = p.get("elapsed", 0)
            name = Path(path).name if path else ""
            return [f"[✓] Prompt-ready saved to: {name} ({elapsed:.0f}s)"]

        case "pipeline_done":
            return ["[✓] Pipeline complete."]

        case "pipeline_error":
            msg = p.get("message", "erro desconhecido")
            return [f"[!] Error: {msg}"]

        case "log":
            msg = p.get("message", "")
            return [msg] if msg else []

        case _:
            return []


# ---------------------------------------------------------------------------
# Progresso determinado
# ---------------------------------------------------------------------------

def _resolve_progress(event: PipelineEvent, audio_duration: list[float]) -> float | None:
    """Retorna progresso (0.0–1.0) ou None para manter barra indeterminada."""
    p = event.payload
    t = event.type

    if t == "language_detected" and event.stage == "transcribe":
        dur = p.get("audio_duration", 0)
        if dur:
            audio_duration[0] = dur

    if t == "transcribe_segment" and audio_duration[0] > 0:
        end = p.get("end", 0)
        return min(end / audio_duration[0], 1.0)

    if t in (
        "format_chunk_start", "format_chunk_done",
        "analyze_chunk_start", "analyze_chunk_done",
        "prompt_chunk_start", "prompt_chunk_done",
    ):
        chunk = p.get("i")
        total = p.get("total")
        if chunk is not None and total and total > 0:
            return chunk / total

    return None


# ---------------------------------------------------------------------------
# Stage label
# ---------------------------------------------------------------------------

def _resolve_stage_label(event: PipelineEvent) -> str | None:
    """Retorna o rótulo de etapa para o header da view, ou None."""
    match event.type:
        case "metadata_start":
            return "Buscando metadados..."
        case "audio_cached":
            return "Áudio em cache."
        case "download_start":
            return "Baixando áudio..."
        case "download_done":
            return "Áudio pronto."
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


# ---------------------------------------------------------------------------
# Card de resumo (substitui print_summary)
# ---------------------------------------------------------------------------

def _make_summary_card(payload: dict) -> ft.Control:
    """Cria um container estilizado com o resumo da transcrição."""
    title = payload.get("title", "n/a")
    duration = _fmt_dur(payload.get("duration", 0))
    output_path = payload.get("output_path", "n/a")
    elapsed = format_elapsed(payload.get("elapsed", 0))
    flagged = payload.get("flagged_count", 0)

    rows = [
        ft.Text("=" * 52, size=10, color=ft.Colors.GREEN_300, font_family="monospace"),
        ft.Text(f"  title    : {title}", size=12, color=ft.Colors.WHITE, font_family="monospace", selectable=True),
        ft.Text(f"  duration : {duration}", size=12, color=ft.Colors.WHITE, font_family="monospace"),
        ft.Text(f"  output   : {Path(output_path).name}", size=12, color=ft.Colors.WHITE, font_family="monospace", selectable=True),
        ft.Text(f"  elapsed  : {elapsed}", size=12, color=ft.Colors.WHITE, font_family="monospace"),
    ]
    if flagged:
        rows.append(
            ft.Text(
                f"  flagged  : {flagged} segment(s) [?]",
                size=12,
                color=ft.Colors.YELLOW_300,
                font_family="monospace",
            )
        )
    rows.append(ft.Text("=" * 52, size=10, color=ft.Colors.GREEN_300, font_family="monospace"))

    return ft.Container(
        margin=ft.Margin(top=8, bottom=4, left=0, right=0),
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        border=ft.border.all(1, ft.Colors.GREEN_700),
        border_radius=6,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.GREEN_400),
        content=ft.Column(spacing=2, controls=rows),
    )


# ---------------------------------------------------------------------------
# View principal
# ---------------------------------------------------------------------------

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
        on_cancel: Callable chamado ao clicar Cancelar.
        on_done: Callable chamado quando pipeline_done é recebido.
    """
    # estado de duração de áudio para progresso determinado
    audio_duration: list[float] = [0.0]

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

        # rótulo da etapa
        label = _resolve_stage_label(event)
        if label is not None:
            stage_label.value = label

        # barra de progresso
        prog = _resolve_progress(event, audio_duration)
        if prog is not None:
            progress_bar.value = prog
        elif event.type in (
            "metadata_start",
            "download_start",
            "whisper_loading",
            "transcribe_started",
            "format_started",
            "analyze_started",
            "analyze_merge_start",
            "translation_start",
            "prompt_started",
        ):
            progress_bar.value = None  # indeterminado entre etapas principais

        # card de resumo (tratado antes das linhas de texto)
        if event.type == "transcribe_summary":
            log_list.controls.append(_make_summary_card(event.payload))
            _trim_log()
            page.update()
            return

        # linhas de log
        msgs = _resolve_messages(event)
        for msg in msgs:
            color = _color_for_prefix(msg)
            log_list.controls.append(
                ft.Text(
                    msg,
                    size=12,
                    color=color,
                    selectable=True,
                    font_family="monospace" if msg.startswith("[") else None,
                )
            )

        _trim_log()

        # conclusão do pipeline
        if event.type == "pipeline_done":
            progress_bar.value = 1.0
            cancel_button.disabled = True
            page.update()
            page.pubsub.unsubscribe()
            on_done(event.payload)
            return

        page.update()

    def _trim_log() -> None:
        if len(log_list.controls) > _MAX_LOG_LINES:
            del log_list.controls[: len(log_list.controls) - _MAX_LOG_LINES]

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
        border=ft.border.all(1, ft.Colors.GREY_700),
        border_radius=6,
        bgcolor=ft.Colors.GREY_900,
    )

    footer = ft.Row(
        controls=[cancel_button],
        alignment=ft.MainAxisAlignment.END,
    )

    return ft.Column(
        controls=[header, log_container, footer],
        expand=True,
        spacing=8,
    )
