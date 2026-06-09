"""Worker do pipeline de transcrição rodando em thread separada."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from src import analyzer, formatter, prompter, transcriber
from src.gui.events import LogEventHandler
from src.core.audio.converter import AUDIO_EXTENSIONS as _AUDIO_EXTS
from src.utils import (
    AUDIO_SOURCE_DIR,
    TRANSCRIPTIONS_TEXT_DIR,
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
    reprocess: bool = False


@dataclass
class PipelineResult:
    """Caminhos dos arquivos gerados pelo pipeline."""

    raw_path: Path | None = None
    analysis_path: Path | None = None
    prompt_path: Path | None = None
    error: str | None = None
    completed: bool = False  # True apenas quando pipeline_done foi emitido


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
    _MID = "transcription"

    # captura de estado entre eventos
    _capture: dict = {}

    def on_event(type: str, stage: str, payload: dict) -> None:
        bus.emit(type, stage, payload, module_id=_MID)
        if type == "transcribe_done":
            _capture.update(payload)

    def emit(type: str, stage: str = "pipeline", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {}, module_id=_MID)

    # instala LogEventHandler no root logger para capturar logs granulares
    log_handler = LogEventHandler(bus, module_id=_MID)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    # INFO evita flood de DEBUG de libs terceiras (faster_whisper, ctranslate2, langchain)
    root_logger.setLevel(logging.INFO)
    for _noisy in ("httpx", "httpcore", "faster_whisper", "huggingface_hub",
                   "langchain", "langchain_core", "ctranslate2"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    result = PipelineResult()

    try:
        check_dependencies()

        if cancel_event.is_set():
            return result

        _input = args.url.strip()
        _local = Path(_input)

        # --- arquivo local (bridge do módulo Áudio) ---
        if _local.is_file():
            if _local.suffix.lower() not in _AUDIO_EXTS:
                emit("task_error", "pipeline", {
                    "message": f"Formato não suportado para transcrição: {_local.suffix}"
                })
                return result
            audio_path = _local
            meta = {"title": _local.stem, "duration": 0}
            emit("audio_cached", "download", {"audio_path": str(audio_path)})

        else:
            # --- URL: validar, buscar metadados e baixar ---
            validate_url(_input)

            if cancel_event.is_set():
                return result

            emit("metadata_start", "download", {"url": _input})
            video_id = extract_video_id(_input)
            meta = fetch_metadata(_input)
            emit("metadata_done", "download", {
                "title": meta.get("title", ""),
                "channel": meta.get("uploader", ""),
                "duration": meta.get("duration", 0),
            })

            if cancel_event.is_set():
                return result

            audio_slug = video_id[:6]
            audio_path = AUDIO_SOURCE_DIR / f"{audio_slug}.mp3"
            AUDIO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

            if audio_path.exists():
                emit("audio_cached", "download", {"audio_path": str(audio_path)})
            else:
                emit("download_start", "download", {"url": _input})
                download_audio(_input, audio_path)
                emit("download_done", "download", {"audio_path": str(audio_path)})

        if cancel_event.is_set():
            return result

        # --- transcrição ---
        TRANSCRIPTIONS_TEXT_DIR.mkdir(parents=True, exist_ok=True)
        _slug = audio_slug if not _local.is_file() else audio_path.stem[:6]
        output_path = TRANSCRIPTIONS_TEXT_DIR / f"transcricao_{_slug}.txt"

        pipeline_start = time()
        if output_path.exists() and not args.reprocess:
            emit("log", "transcribe", {
                "message": f"[»] Reusing existing transcription: {output_path.name}",
                "level": "info",
            })
        else:
            transcriber.transcribe(
                audio_path=audio_path,
                output_path=output_path,
                meta=meta,
                url=_input,
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

        _done_payload = {
            "raw_path": str(result.raw_path) if result.raw_path else None,
            "analysis_path": str(result.analysis_path) if result.analysis_path else None,
            "prompt_path": str(result.prompt_path) if result.prompt_path else None,
        }
        result.completed = True
        emit("task_done", "pipeline", _done_payload)

    except Exception as exc:
        result.error = str(exc)
        emit("task_error", "pipeline", {"message": str(exc)})
    except SystemExit as exc:
        # sys.exit() em funções de biblioteca — não deve mais ocorrer após as correções,
        # mas mantido como rede de segurança para garantir que task_error seja emitido.
        _msg = f"Erro de inicialização (código {exc.code}) — verifique dependências e configuração."
        result.error = _msg
        emit("task_error", "pipeline", {"message": _msg})

    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)

    return result


def start_pipeline(
    args: PipelineArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
) -> threading.Thread:
    """Inicia o pipeline em uma thread de background e retorna a thread.

    Detecta cancelamento (retorno antecipado sem pipeline_done/pipeline_error)
    e emite pipeline_cancelled para que o ProgressPanel possa resetar o estado.

    Args:
        args: Parâmetros do pipeline.
        bus: EventBus para comunicação thread-safe.
        cancel_event: threading.Event para cancelamento.

    Returns:
        Thread iniciada (daemon=True).
    """
    def _run() -> None:
        result = run_pipeline(args, bus, cancel_event)
        # Cancelamento: sem completed e sem erro → retorno antecipado via cancel_event
        if not result.completed and result.error is None:
            bus.emit("pipeline_cancelled", "pipeline", {}, module_id="transcription")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
