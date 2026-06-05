"""View de progresso do pipeline de transcrição."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

from src.gui.events import PipelineEvent
from src.gui.theme.components import danger_button, log_line, spinner
from src.gui.theme.tokens import Color, Type
from src.transcriber import format_elapsed
from src.utils import format_duration

_MAX_LOG_LINES = 500


# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------

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
        case "audio_op_start" | "audio_op_done":
            from src.gui.modules.audio import pipeline_log as _audio_log
            return _audio_log.resolve_messages(event)
        case "video_op_start" | "video_op_done" | "video_op_error":
            from src.gui.modules.video import pipeline_log as _video_log
            return _video_log.resolve_messages(event)
        case "queue_progress" | "progress_start" | "progress_update":
            return []
        case "task_done":
            paths = p.get("output_paths", [])
            if paths:
                return [f"[✓] Concluído — {len(paths)} arquivo(s) gerado(s)."]
            return ["[✓] Pipeline concluído."]
        case "task_error":
            msg = p.get("message", "erro desconhecido")
            return [f"[!] Erro: {msg}"]
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

    if t == "progress_update":
        current = p.get("current", 0.0)
        return min(float(current), 1.0)

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
        case "queue_progress":
            p = event.payload
            name = p.get("item_name", "")
            cur = p.get("current_item", "?")
            tot = p.get("total_items", "?")
            return f"Item {cur}/{tot}" + (f" — {name}" if name else "")
        case "audio_op_start" | "audio_op_done":
            from src.gui.modules.audio import pipeline_log as _audio_log
            return _audio_log.resolve_stage_label(event)
        case "video_op_start" | "video_op_done" | "video_op_error":
            from src.gui.modules.video import pipeline_log as _video_log
            return _video_log.resolve_stage_label(event)
        case "task_done":
            return "Pipeline concluído!"
        case "task_error":
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
        ft.Text("=" * 52, size=10, color=Color.log.ok, font_family=Type.FONT_MONO),
        ft.Text(f"  title    : {title}", size=12, color=Color.log.text, font_family=Type.FONT_MONO, selectable=True),
        ft.Text(f"  duration : {duration}", size=12, color=Color.log.text, font_family=Type.FONT_MONO),
        ft.Text(
            f"  output   : {Path(output_path).name}",
            size=12, color=Color.log.text, font_family=Type.FONT_MONO, selectable=True,
        ),
        ft.Text(f"  elapsed  : {elapsed}", size=12, color=Color.log.text, font_family=Type.FONT_MONO),
    ]
    if flagged:
        rows.append(ft.Text(
            f"  flagged  : {flagged} segment(s) [?]",
            size=12, color=Color.log.work, font_family=Type.FONT_MONO,
        ))
    rows.append(ft.Text("=" * 52, size=10, color=Color.log.ok, font_family=Type.FONT_MONO))

    return ft.Container(
        margin=ft.Margin(top=8, bottom=4, left=0, right=0),
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        border=ft.Border(
            left=ft.BorderSide(1, ft.Colors.with_opacity(0.5, Color.log.ok)),
            right=ft.BorderSide(1, ft.Colors.with_opacity(0.5, Color.log.ok)),
            top=ft.BorderSide(1, ft.Colors.with_opacity(0.5, Color.log.ok)),
            bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.5, Color.log.ok)),
        ),
        border_radius=6,
        bgcolor=ft.Colors.with_opacity(0.05, Color.log.ok),
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
    owner_id: str = "",
    on_show_results: Callable[[object, ft.Column], None] | None = None,
    extra_header: ft.Control | None = None,
) -> ProgressPanel:
    """Retorna um ProgressPanel com controle raiz e métodos reset/show_results.

    Args:
        page: Página Flet.
        on_cancel: Callable chamado ao clicar Cancelar.
        on_done: Callable chamado quando pipeline_done é recebido.
        owner_id: Identificador do módulo dono (ex: "transcription", "audio").
            Eventos com module_id diferente são ignorados — evita cross-talk entre painéis.
        on_show_results: Renderização customizada dos resultados. Recebe (result, results_inner).
            Se None, usa a renderização padrão de Transcrição (PipelineResult).
        extra_header: Widget opcional inserido acima do log (ex: reprodutor de áudio).
            Deve ser um controle Flet com visible=False por padrão.
    """
    audio_duration: list[float] = [0.0]
    _done_called: list[bool] = [False]  # guard contra duplo on_done
    _mutable_line: list[ft.Text | None] = [None]  # última linha "viva" de progresso

    def _call_on_done(payload: dict) -> None:
        if not _done_called[0]:
            _done_called[0] = True
            on_done(payload)

    # --- widgets do painel Pipeline ---
    stage_label = ft.Text(
        "Inicie o pipeline pelo formulário →",
        size=14,
        weight=ft.FontWeight.W_400,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    progress_bar = ft.ProgressBar(
        value=None,
        width=float("inf"),
        expand=True,
        color=ft.Colors.PRIMARY,
        bgcolor=ft.Colors.OUTLINE_VARIANT,
        visible=False,
    )

    log_list = ft.ListView(
        expand=True,
        spacing=2,
        padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        auto_scroll=True,
    )

    cancel_button = danger_button(
        "Cancelar",
        icon=ft.Icons.CANCEL_OUTLINED,
        on_click=lambda _: on_cancel(),
    )

    # --- moinho giratório no header do pipeline ---
    status_icon, _start_spin, _stop_spin = spinner()

    _pipeline_controls: list[ft.Control] = [
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        status_icon,
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
    ]
    if extra_header is not None:
        _pipeline_controls.append(extra_header)
    _pipeline_controls.extend([
        ft.Container(
            content=log_list,
            expand=True,
            border=ft.Border(
                left=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                top=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
            ),
            border_radius=6,
            bgcolor=Color.dark.surface_variant,
        ),
        ft.Row(controls=[cancel_button], alignment=ft.MainAxisAlignment.END),
    ])

    pipeline_panel = ft.Column(
        controls=_pipeline_controls,
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
        pipeline_panel.visible = idx == 0
        results_panel.visible = idx == 1
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
        # Filtro de cross-talk: ignora eventos de outros módulos
        if owner_id and event.module_id and event.module_id != owner_id:
            return

        label = _resolve_stage_label(event)
        if label is not None:
            stage_label.value = label
            stage_label.color = ft.Colors.ON_SURFACE
            stage_label.italic = False
            stage_label.size = 16
            stage_label.weight = ft.FontWeight.W_500

        prog = _resolve_progress(event, audio_duration)
        if prog is not None:
            progress_bar.value = prog
        elif event.type in (
            "progress_start",
            "metadata_start", "download_start", "whisper_loading",
            "transcribe_started", "format_started", "analyze_started",
            "analyze_merge_start", "translation_start", "prompt_started",
        ):
            progress_bar.visible = True
            progress_bar.value = None
            _start_spin()

        if event.type == "transcribe_summary":
            log_list.controls.append(_make_summary_card(event.payload))
            _trim_log()
            page.update()
            return

        msgs = _resolve_messages(event)
        mutable = isinstance(event.payload, dict) and event.payload.get("mutable", False)
        for msg in msgs:
            if mutable and _mutable_line[0] is not None:
                _mutable_line[0].value = msg
            else:
                new_line = log_line(msg)
                log_list.controls.append(new_line)
                _mutable_line[0] = new_line if mutable else None
        _trim_log()

        # --- eventos genéricos (usados por todos os módulos em PR3+) ---
        if event.type == "task_done":
            progress_bar.value = 1.0
            cancel_button.disabled = True
            _stop_spin()
            _call_on_done(event.payload)
            return

        if event.type == "task_error":
            progress_bar.visible = False
            cancel_button.disabled = True
            _stop_spin()
            _call_on_done({"error": True})
            page.update()
            return

        # --- eventos legados de Transcrição (TODO(PR3): remover) ---
        if event.type == "pipeline_done":
            progress_bar.value = 1.0
            cancel_button.disabled = True
            _stop_spin()
            _call_on_done(event.payload)  # no-op se task_done já processado
            page.update()  # renderiza "[✓] Pipeline complete." e mudanças de barra
            return

        if event.type == "pipeline_error":
            progress_bar.visible = False
            cancel_button.disabled = True
            _stop_spin()
            _call_on_done({"error": True})
            page.update()
            return

        if event.type == "pipeline_cancelled":
            cancel_button.disabled = False
            stage_label.value = "Pipeline cancelado."
            stage_label.color = ft.Colors.ON_SURFACE_VARIANT
            stage_label.italic = True
            progress_bar.visible = False
            _stop_spin()
            _call_on_done({"cancelled": True})
            page.update()
            return

        page.update()

    def _trim_log() -> None:
        if len(log_list.controls) > _MAX_LOG_LINES:
            log_list.controls = log_list.controls[-_MAX_LOG_LINES:]

    page.pubsub.subscribe(_handle_event)

    # --- métodos do ProgressPanel ---
    def _reset() -> None:
        """Limpa o log, reseta a barra e desabilita o tab Resultados."""
        _done_called[0] = False
        _mutable_line[0] = None
        _stop_spin()
        log_list.controls.clear()
        progress_bar.value = None
        stage_label.value = "Inicie o pipeline pelo formulário →"
        stage_label.color = ft.Colors.ON_SURFACE_VARIANT
        stage_label.italic = True
        stage_label.size = 14
        stage_label.weight = ft.FontWeight.W_400
        progress_bar.visible = False
        progress_bar.value = None
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
        """Popula o tab Resultados e o seleciona automaticamente.

        Se on_show_results foi fornecido, delega a renderização para ele.
        Caso contrário, usa a renderização padrão de Transcrição (PipelineResult).
        """
        results_inner.controls.clear()

        if on_show_results is not None:
            on_show_results(result, results_inner)
        else:
            from src.gui.views.result_view import build_result_view
            from src.gui.workers import PipelineResult

            if isinstance(result, PipelineResult):
                results_inner.controls.append(build_result_view(
                    page,
                    raw_path=result.raw_path,
                    analysis_path=result.analysis_path,
                    prompt_path=result.prompt_path,
                ))

        # Renderizar o conteúdo ENQUANTO o painel ainda está invisível —
        # evita diff visible=False → visible=True+conteúdo complexo no Flet 0.85
        page.update()
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
