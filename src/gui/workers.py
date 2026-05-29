"""Worker do pipeline de transcrição rodando em thread separada."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from src import analyzer, formatter, prompter, transcriber
from src.gui.events import LogEventHandler
from src.utils import (
    AUDIOS_DIR,
    TRANSCRIPTIONS_RAW_DIR,
    check_dependencies,
    download_audio,
    extract_video_id,
    fetch_metadata,
    validate_url,
)

if TYPE_CHECKING:
    from src.gui.events import EventBus


@dataclass
class PipelineArgs:
    """Parâmetros do pipeline recebidos do form_view."""

    url: str
    whisper_model: str = "small"
    language: str = "auto"
    beam_size: int = 1
    threads: int = 2
    use_format: bool = False
    format_model: str = "phi4mini-custom"
    use_analyze: bool = False
    analyzer_model: str = "gemini-2.5-flash"
    use_prompt: bool = False
    prompt_model: str = "gemini-2.5-flash"


@dataclass
class PipelineResult:
    """Caminhos dos arquivos gerados pelo pipeline."""

    raw_path: Path | None = None
    analysis_path: Path | None = None
    prompt_path: Path | None = None
    error: str | None = None


def run_pipeline(
    args: PipelineArgs,
    bus: EventBus,
    cancel_event: threading.Event,
) -> PipelineResult:
    """Executa o pipeline completo em uma thread de background.

    Orquestra download → transcrição → formatação? → análise? → prompt-ready?.
    Emite PipelineEvents via bus para atualizar a progress_view em tempo real.
    Checa cancel_event entre etapas — não interrompe Whisper mid-segment.

    Args:
        args: Parâmetros do pipeline configurados no form.
        bus: EventBus para emissão de eventos thread-safe via pubsub.
        cancel_event: threading.Event setado pelo botão Cancelar.

    Returns:
        PipelineResult com paths dos arquivos gerados ou mensagem de erro.
    """
    # captura de estado entre eventos
    _capture: dict = {}

    def on_event(type: str, stage: str, payload: dict) -> None:
        bus.emit(type, stage, payload)
        if type == "transcribe_done":
            _capture.update(payload)

    def emit(type: str, stage: str = "pipeline", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {})

    # instala LogEventHandler no root logger para capturar logs granulares
    log_handler = LogEventHandler(bus)
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    result = PipelineResult()

    try:
        check_dependencies()

        if cancel_event.is_set():
            return result

        validate_url(args.url)

        if cancel_event.is_set():
            return result

        # --- metadados ---
        emit("metadata_start", "download", {"url": args.url})
        video_id = extract_video_id(args.url)
        meta = fetch_metadata(args.url)
        emit("metadata_done", "download", {
            "title": meta.get("title", ""),
            "channel": meta.get("uploader", ""),
            "duration": meta.get("duration", 0),
        })

        if cancel_event.is_set():
            return result

        # --- download ou cache ---
        audio_slug = video_id[:6]
        audio_path = AUDIOS_DIR / f"{audio_slug}.mp3"
        AUDIOS_DIR.mkdir(parents=True, exist_ok=True)

        if audio_path.exists():
            emit("audio_cached", "download", {"audio_path": str(audio_path)})
        else:
            emit("download_start", "download", {"url": args.url})
            download_audio(args.url, audio_path)
            emit("download_done", "download", {"audio_path": str(audio_path)})

        if cancel_event.is_set():
            return result

        # --- transcrição ---
        TRANSCRIPTIONS_RAW_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TRANSCRIPTIONS_RAW_DIR / f"transcricao_{audio_slug}.txt"

        pipeline_start = time()
        transcriber.transcribe(
            audio_path=audio_path,
            output_path=output_path,
            meta=meta,
            url=args.url,
            model_size=args.whisper_model,
            language=None if args.language == "auto" else args.language,
            threads=args.threads,
            beam_size=args.beam_size,
            on_event=on_event,
            force_overwrite=True,
        )
        result.raw_path = output_path

        # --- resumo de transcrição ---
        elapsed_transcribe = time() - pipeline_start
        flagged_count = _capture.get("flagged_count", 0)
        emit("transcribe_summary", "pipeline", {
            "title": meta.get("title", "n/a"),
            "duration": meta.get("duration", 0),
            "output_path": str(output_path),
            "elapsed": elapsed_transcribe,
            "flagged_count": flagged_count,
        })

        if cancel_event.is_set():
            return result

        formatted_body: str | None = None
        if args.use_format:
            formatted_body = formatter.format_transcription(
                input_path=output_path,
                model_name=args.format_model,
                on_event=on_event,
            )

        if cancel_event.is_set():
            return result

        if args.use_analyze:
            analysis_path = analyzer.analyze(
                input_path=output_path,
                model_name=args.analyzer_model,
                transcription=formatted_body,
                on_event=on_event,
            )
            result.analysis_path = analysis_path

        if cancel_event.is_set():
            return result

        if args.use_prompt:
            prompt_path = prompter.build_prompt_ready(
                input_path=output_path,
                model_name=args.prompt_model,
                on_event=on_event,
            )
            result.prompt_path = prompt_path

        emit("pipeline_done", "pipeline", {
            "raw_path": str(result.raw_path) if result.raw_path else None,
            "analysis_path": str(result.analysis_path) if result.analysis_path else None,
            "prompt_path": str(result.prompt_path) if result.prompt_path else None,
        })

    except Exception as exc:
        result.error = str(exc)
        emit("pipeline_error", "pipeline", {"message": str(exc)})

    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)

    return result


def start_pipeline(
    args: PipelineArgs,
    bus: EventBus,
    cancel_event: threading.Event,
) -> threading.Thread:
    """Inicia o pipeline em uma thread de background e retorna a thread.

    Args:
        args: Parâmetros do pipeline.
        bus: EventBus para comunicação thread-safe.
        cancel_event: threading.Event para cancelamento.

    Returns:
        Thread iniciada (daemon=True).
    """
    thread = threading.Thread(
        target=run_pipeline,
        args=(args, bus, cancel_event),
        daemon=True,
    )
    thread.start()
    return thread
