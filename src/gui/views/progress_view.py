"""View de progresso do pipeline de transcrição."""

from __future__ import annotations

from dataclasses import dataclass
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
            return []
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
# Card de resumo
# ---------------------------------------------------------------------------

def _make_summary_card(payload: dict) -> ft.Control:
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
        rows.append(ft.Text(
            f"  flagged  : {flagged} segment(s) [?]",
            size=12, color=ft.Colors.YELLOW_300, font_family="monospace",
        ))
    rows.append(ft.Text("=" * 52, size=10, color=ft.Colors.GREEN_300, font_family="monospace"))

    return ft.Container(
        margin=ft.Margin(top=8, bottom=4, left=0, right=0),
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.GREEN_700),
            right=ft.BorderSide(1, ft.Colors.GREEN_700),
            top=ft.BorderSide(1, ft.Colors.GREEN_700),
            bottom=ft.BorderSide(1, ft.Colors.GREEN_700),
        ),
        border_radius=6,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.GREEN_400),
        content=ft.Column(spacing=2, controls=rows),
    )


# ---------------------------------------------------------------------------
# ProgressPanel
# ---------------------------------------------------------------------------

@dataclass
class ProgressPanel:
    """Painel de progresso com métodos de controle de estado."""
    control: ft.Control
    reset: Callable[[], None]
    show_results: Callable[[object], None]


def build_progress_view(
    page: ft.Page,
    on_cancel: Callable[[], None],
    on_done: Callable[[dict], None],
) -> ProgressPanel:
    """Retorna um ProgressPanel com controle raiz e métodos reset/show_results.

    A assinatura permanece compatível com o PR1. O painel agora inclui tabs
    Pipeline | Resultados: Pipeline sempre visível durante execução; Resultados
    habilitado e selecionado automaticamente ao fim do pipeline.

    Args:
        page: Página Flet.
        on_cancel: Callable chamado ao clicar Cancelar.
        on_done: Callable chamado quando pipeline_done é recebido.
    """
    audio_duration: list[float] = [0.0]

    # --- widgets do painel Pipeline ---
    stage_label = ft.Text(
        "Aguardando...",
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

    pipeline_panel = ft.Column(
        controls=[
            ft.Column(
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
            ),
            ft.Container(
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
            ),
            ft.Row(controls=[cancel_button], alignment=ft.MainAxisAlignment.END),
        ],
        expand=True,
        spacing=8,
        visible=True,
    )

    # --- painel Resultados ---
    # Usa Column com controls (não content) para evitar diff None→tree no Flet 0.85
    results_inner = ft.Column(controls=[], expand=True)
    results_panel = ft.Column(
        controls=[results_inner],
        expand=True,
        visible=False,
    )

    # --- tab bar Pipeline | Resultados ---
    tab_btns: list[ft.TextButton] = []

    def _switch_tab(idx: int) -> None:
        pipeline_panel.visible = (idx == 0)
        results_panel.visible = (idx == 1)
        for i, btn in enumerate(tab_btns):
            btn.style = ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: ft.Colors.PRIMARY if i == idx else ft.Colors.ON_SURFACE_VARIANT,
                },
            )
        page.update()

    tab_btns.append(ft.TextButton(
        "Pipeline",
        style=ft.ButtonStyle(color={ft.ControlState.DEFAULT: ft.Colors.PRIMARY}),
        on_click=lambda _: _switch_tab(0),
    ))
    tab_btns.append(ft.TextButton(
        "Resultados",
        disabled=True,
        style=ft.ButtonStyle(color={ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE_VARIANT}),
        on_click=lambda _: _switch_tab(1),
    ))

    tab_bar = ft.Row(controls=[*tab_btns, ft.Container(expand=True)], spacing=0)

    # --- handler pubsub (assinatura persistente — não cancela entre runs) ---
    def _handle_event(event: PipelineEvent) -> None:
        label = _resolve_stage_label(event)
        if label is not None:
            stage_label.value = label

        prog = _resolve_progress(event, audio_duration)
        if prog is not None:
            progress_bar.value = prog
        elif event.type in (
            "metadata_start", "download_start", "whisper_loading",
            "transcribe_started", "format_started", "analyze_started",
            "analyze_merge_start", "translation_start", "prompt_started",
        ):
            progress_bar.value = None

        if event.type == "transcribe_summary":
            log_list.controls.append(_make_summary_card(event.payload))
            _trim_log()
            page.update()
            return

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

        if event.type == "pipeline_done":
            progress_bar.value = 1.0
            cancel_button.disabled = True
            # Não chama page.update() aqui — on_done vai acionar o update final
            on_done(event.payload)
            return

        page.update()

    def _trim_log() -> None:
        if len(log_list.controls) > _MAX_LOG_LINES:
            del log_list.controls[: len(log_list.controls) - _MAX_LOG_LINES]

    page.pubsub.subscribe(_handle_event)

    # --- métodos do ProgressPanel ---
    def _reset() -> None:
        """Limpa o log, reseta a barra e desabilita o tab Resultados."""
        log_list.controls.clear()
        progress_bar.value = None
        stage_label.value = "Iniciando pipeline..."
        cancel_button.disabled = False
        audio_duration[0] = 0.0
        tab_btns[1].disabled = True
        results_inner.controls.clear()
        results_panel.visible = False
        pipeline_panel.visible = True
        tab_btns[0].style = ft.ButtonStyle(
            color={ft.ControlState.DEFAULT: ft.Colors.PRIMARY},
        )
        tab_btns[1].style = ft.ButtonStyle(
            color={ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE_VARIANT},
        )
        page.update()

    def _show_results(result: object) -> None:
        """Popula o tab Resultados e o seleciona automaticamente."""
        from src.gui.views.result_view import build_result_view
        from src.gui.workers import PipelineResult

        if not isinstance(result, PipelineResult):
            return

        results_inner.controls.clear()
        results_inner.controls.append(build_result_view(
            page,
            raw_path=result.raw_path,
            analysis_path=result.analysis_path,
            prompt_path=result.prompt_path,
        ))
        tab_btns[1].disabled = False
        _switch_tab(1)

    # --- layout raiz ---
    root = ft.Column(
        controls=[
            tab_bar,
            ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
            pipeline_panel,
            results_panel,
        ],
        expand=True,
        spacing=0,
    )

    return ProgressPanel(control=root, reset=_reset, show_results=_show_results)
