"""Worker for the transcription pipeline running in a background thread."""

from __future__ import annotations

import logging
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from src import analyzer, formatter, prompter, transcriber
from src.core.audio.downloader import download_audio as _core_download_audio
from src.core.audio.converter import AUDIO_EXTENSIONS as _AUDIO_EXTS
from src.core.audio.converter import VIDEO_EXTENSIONS as _VIDEO_EXTS
from src.core.metadata import fetch_metadata
from src.gui.events import LogEventHandler
from src.utils import (
    AUDIO_SOURCE_DIR,
    TRANSCRIPTIONS_TEXT_DIR,
    check_dependencies,
    sanitize_filename,
)

if TYPE_CHECKING:
    from src.gui.events import EventBus

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*m")

# Local text files (.txt/.md) skip download + Whisper and feed the LLM steps
# directly. faster-whisper decodes audio AND video containers via PyAV, so both
# media families go through transcription.
_TEXT_EXTS = {".txt", ".md"}


@dataclass
class PipelineArgs:
    """Parameters for the transcription pipeline received from the form."""

    url: str
    whisper_model: str = "small"
    language: str = "auto"
    beam_size: int = 1
    threads: int = 2
    use_format: bool = False
    format_model: str = "phi4mini-custom"
    use_analyze: bool = False
    analyzer_model: str = "gemini-2.5-flash"
    analysis_profile: str = "default"
    use_prompt: bool = False
    prompt_model: str = "gemini-2.5-flash"
    reprocess: bool = False
    export_subtitles: bool = False  # exports .srt + .vtt alongside the .txt


@dataclass
class PipelineResult:
    """Output file paths produced by the pipeline."""

    raw_path: Path | None = None
    analysis_path: Path | None = None
    prompt_path: Path | None = None
    subtitle_paths: list[Path] | None = None
    error: str | None = None
    completed: bool = False  # True only when task_done was emitted


def run_pipeline(
    args: PipelineArgs,
    bus: EventBus,
    cancel_event: threading.Event,
) -> PipelineResult:
    """Execute the full transcription pipeline in a background thread.

    Orchestrates download → transcription → formatting? → analysis? → prompt?.
    Emits PipelineEvents via bus to update the progress_view in real time.
    Checks cancel_event between stages — does not interrupt Whisper mid-segment.

    Args:
        args: Pipeline parameters configured in the form.
        bus: EventBus for thread-safe event emission via pubsub.
        cancel_event: threading.Event set by the Cancel button.

    Returns:
        PipelineResult with paths of generated files or an error message.
    """
    _MID = "transcription"

    _capture: dict = {}

    def on_event(type: str, stage: str, payload: dict) -> None:
        bus.emit(type, stage, payload, module_id=_MID)
        if type == "transcribe_done":
            _capture.update(payload)
        elif type == "subtitles_done":
            _capture["subtitle_paths"] = payload.get("paths", [])

    def emit(type: str, stage: str = "pipeline", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {}, module_id=_MID)

    # Install LogEventHandler on the root logger to capture granular logs
    log_handler = LogEventHandler(bus, module_id=_MID)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    # INFO prevents flooding from third-party libs (faster_whisper, ctranslate2, langchain)
    root_logger.setLevel(logging.INFO)
    for _noisy in (
        "httpx",
        "httpcore",
        "faster_whisper",
        "huggingface_hub",
        "langchain",
        "langchain_core",
        "ctranslate2",
    ):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    result = PipelineResult()

    try:
        check_dependencies()

        if cancel_event.is_set():
            return result

        _input = args.url.strip()
        _local = Path(_input)
        _is_local = _local.is_file()
        _is_text = _is_local and _local.suffix.lower() in _TEXT_EXTS

        TRANSCRIPTIONS_TEXT_DIR.mkdir(parents=True, exist_ok=True)

        if _is_text:
            # --- text file: skip download + Whisper, run only the LLM steps ---
            if not (args.use_format or args.use_analyze or args.use_prompt):
                emit(
                    "task_error",
                    "pipeline",
                    {
                        "message": (
                            "Select at least one analysis (Formatação, Análise or "
                            "Prompt-ready) for a text file."
                        )
                    },
                )
                return result
            # Work on a copy under transcriptions/text/ so the user's source file
            # is never modified in place (the formatter rewrites its input_path).
            output_path = TRANSCRIPTIONS_TEXT_DIR / f"{_local.stem}.txt"
            if output_path.resolve() != _local.resolve():
                shutil.copyfile(_local, output_path)
            result.raw_path = output_path
            emit(
                "log",
                "pipeline",
                {
                    "message": f"[i] Text loaded: {_local.name} — skipping transcription",
                    "level": "info",
                },
            )
        else:
            # --- media: local audio/video or remote URL → transcription ---
            if _is_local:
                if _local.suffix.lower() not in (_AUDIO_EXTS | _VIDEO_EXTS):
                    emit(
                        "task_error",
                        "pipeline",
                        {
                            "message": f"Unsupported format for transcription: {_local.suffix}"
                        },
                    )
                    return result
                audio_path = _local
                meta = {"title": _local.stem, "duration": 0}
                emit("audio_cached", "download", {"audio_path": str(audio_path)})

            else:
                # --- URL: fetch metadata and download ---
                if cancel_event.is_set():
                    return result

                emit("metadata_start", "download", {"url": _input})
                meta = fetch_metadata(_input)
                emit(
                    "metadata_done",
                    "download",
                    {
                        "title": meta.get("title", ""),
                        "channel": meta.get("uploader", ""),
                        "duration": meta.get("duration", 0),
                    },
                )

                if cancel_event.is_set():
                    return result

                AUDIO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
                _title_slug = sanitize_filename(meta.get("title", "download"))
                audio_path = AUDIO_SOURCE_DIR / f"{_title_slug}.mp3"

                if audio_path.exists():
                    emit("audio_cached", "download", {"audio_path": str(audio_path)})
                else:
                    emit("download_start", "download", {"url": _input})

                    def _dl_hook(d: dict) -> None:
                        if d.get("status") == "downloading":
                            pct = _ANSI_ESC.sub("", d.get("_percent_str", "")).strip()
                            if pct:
                                emit(
                                    "log",
                                    "download",
                                    {
                                        "message": f"[↓] {pct}",
                                        "level": "info",
                                        "mutable": True,
                                    },
                                )

                    audio_path = _core_download_audio(
                        _input,
                        AUDIO_SOURCE_DIR,
                        fmt="mp3",
                        embed_meta=False,
                        progress_hook=_dl_hook,
                    )
                    emit("download_done", "download", {"audio_path": str(audio_path)})

            if cancel_event.is_set():
                return result

            # --- transcription ---
            output_path = (
                TRANSCRIPTIONS_TEXT_DIR / f"transcription_{audio_path.stem}.txt"
            )

            pipeline_start = time()
            if output_path.exists() and not args.reprocess:
                emit(
                    "log",
                    "transcribe",
                    {
                        "message": f"[»] Reusing existing transcription: {output_path.name}",
                        "level": "info",
                    },
                )
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
                    subtitle_formats=("srt", "vtt") if args.export_subtitles else (),
                )
            result.raw_path = output_path
            _subs = _capture.get("subtitle_paths")
            if _subs:
                result.subtitle_paths = [Path(p) for p in _subs]

            # --- transcription summary ---
            elapsed_transcribe = time() - pipeline_start
            flagged_count = _capture.get("flagged_count", 0)
            emit(
                "transcribe_summary",
                "pipeline",
                {
                    "title": meta.get("title", "n/a"),
                    "duration": meta.get("duration", 0),
                    "output_path": str(output_path),
                    "elapsed": elapsed_transcribe,
                    "flagged_count": flagged_count,
                },
            )

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
                profile=args.analysis_profile,
            )
            result.analysis_path = analysis_path
            # Plan 4B: the profile the user chose for this document is a gold
            # label. Record it (best-effort) so the supervised classifier can
            # eventually upgrade the zero-shot suggestion. Never break the run.
            try:
                from src.core.ml.classify import record_label

                record_label(str(output_path), args.analysis_profile)
            except Exception as exc:  # noqa: BLE001 — labelling is non-critical
                logging.debug("[d] Could not record profile label: %s", exc)

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
            "analysis_path": str(result.analysis_path)
            if result.analysis_path
            else None,
            "prompt_path": str(result.prompt_path) if result.prompt_path else None,
            "subtitle_paths": [str(p) for p in result.subtitle_paths]
            if result.subtitle_paths
            else None,
        }
        result.completed = True
        emit("task_done", "pipeline", _done_payload)

    except Exception as exc:
        result.error = str(exc)
        emit("task_error", "pipeline", {"message": str(exc)})
    except SystemExit as exc:
        # sys.exit() from a library — kept as safety net to ensure task_error is emitted.
        _msg = f"Initialization error (code {exc.code}) — check dependencies and configuration."
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
    """Start the pipeline in a background thread and return the thread.

    Detects cancellation (early return without task_done/task_error) and
    emits pipeline_cancelled so the ProgressPanel can reset its state.

    Args:
        args: Pipeline parameters.
        bus: EventBus for thread-safe communication.
        cancel_event: threading.Event for cancellation.

    Returns:
        Started daemon thread.
    """

    def _run() -> None:
        result = run_pipeline(args, bus, cancel_event)
        # Cancellation: no completed and no error → early return via cancel_event
        if not result.completed and result.error is None:
            bus.emit("pipeline_cancelled", "pipeline", {}, module_id="transcription")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
