"""Worker for the audio pipeline running in a background thread."""

from __future__ import annotations

import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Callable

from src.core.audio.args import AudioArgs
from src.core.audio.converter import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    convert_audio,
    extract_audio,
)
from src.core.audio.denoiser import (
    denoise as _denoise_audio,
    is_available as _denoise_available,
)
from src.core.audio.downloader import download_audio
from src.core.audio.normalizer import normalize_lufs as _normalize_lufs
from src.gui.modules._pipeline_runner import (
    fmt_ydl_progress,
    item_label,
    run_queue_pipeline,
    start_pipeline,
)
from src.gui.modules.audio import pipeline_log
from src.utils import AUDIO_PROCESSED_DIR, AUDIO_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "audio"


def run_audio_pipeline(
    args: AudioArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    *,
    install_log_handler: bool = True,
) -> bool:
    """Execute the audio item queue sequentially.

    Emits generic events (progress_start, progress_update, queue_progress,
    task_done, task_error) plus audio-specific events (audio_op_start,
    audio_op_done) for the log panel.

    Args:
        args: Audio form parameters.
        bus: Shared application EventBus.
        cancel_event: threading.Event set by the Cancel button.
        install_log_handler: When False, skips LogEventHandler installation
            (use False in CLI to avoid duplicating TqdmLoggingHandler output).

    Returns:
        True if all items completed without error.
    """
    return run_queue_pipeline(
        items=args.items,
        bus=bus,
        module_id=_MODULE_ID,
        default_stage="audio",
        cancel_event=cancel_event,
        process_item=_make_process_item(args),
        install_log_handler=install_log_handler,
    )


def _make_process_item(args: AudioArgs) -> Callable:
    """Return a process_item closure capturing the pipeline args."""

    def _process_item(
        emit: Callable,
        item,
        idx: int,
        total: int,
        cancel_event: threading.Event,
    ) -> str:
        item_name = item_label(item)
        t0 = time()

        if item.kind == "url":
            operation = "download"
            emit(
                "audio_op_start",
                payload={
                    "operation": operation,
                    "item_name": item_name,
                    "item_idx": idx,
                    "total": total,
                },
            )

            def _ydl_hook(d: dict) -> None:
                if d.get("status") == "downloading":
                    downloaded = d.get("downloaded_bytes", 0) or 0
                    total_b = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    if total_b > 0:
                        emit(
                            "progress_update",
                            payload={"current": min(downloaded / total_b, 1.0)},
                        )
                    line = fmt_ydl_progress(d)
                    if line:
                        emit("log", payload={"message": line, "mutable": True})

            out_path = download_audio(
                url=item.value,
                out_dir=AUDIO_SOURCE_DIR,
                fmt=args.fmt,
                quality=args.quality,
                embed_meta=args.embed_meta,
                progress_hook=_ydl_hook,
            )

        else:
            src = Path(item.value)
            suffix = src.suffix.lower()

            if suffix in VIDEO_EXTENSIONS:
                operation = "extract"
            elif suffix in AUDIO_EXTENSIONS:
                operation = "convert"
            else:
                raise ValueError(f"Unsupported extension: {suffix} ({item_name})")

            emit(
                "audio_op_start",
                payload={
                    "operation": operation,
                    "item_name": item_name,
                    "item_idx": idx,
                    "total": total,
                },
            )

            def _progress_cb(ratio: float) -> None:
                emit("progress_update", payload={"current": ratio})
                if ratio > 0:
                    emit(
                        "log",
                        payload={
                            "message": pipeline_log.fmt_ffmpeg_progress(ratio),
                            "mutable": True,
                        },
                    )

            if operation == "extract":
                out_path = extract_audio(
                    video=src,
                    out_dir=AUDIO_PROCESSED_DIR,
                    fmt=args.fmt if args.fmt != "best" else "mp3",
                    progress_cb=_progress_cb,
                )
            else:
                out_path = convert_audio(
                    src=src,
                    out_dir=AUDIO_PROCESSED_DIR,
                    fmt=args.fmt if args.fmt != "best" else "mp3",
                    bitrate=args.quality if args.quality != "best" else None,
                    progress_cb=_progress_cb,
                )

        original_src_size = out_path.stat().st_size

        # ── Post: Denoise ────────────────────────────────────────────────
        if args.denoise:
            if not _denoise_available():
                emit(
                    "log",
                    payload={
                        "message": "[!] noisereduce not installed — skipping denoise."
                    },
                )
            else:
                emit(
                    "audio_op_start",
                    payload={
                        "operation": "denoise",
                        "item_name": out_path.name,
                        "item_idx": idx,
                        "total": total,
                    },
                )
                emit(
                    "log",
                    payload={"message": pipeline_log.fmt_denoise_start(out_path.name)},
                )
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_denoise_detail(
                            stationary=args.denoise_stationary
                        )
                    },
                )
                out_path = _denoise_audio(
                    out_path, AUDIO_PROCESSED_DIR, stationary=args.denoise_stationary
                )

        # ── Post: Normalize ──────────────────────────────────────────────
        if args.normalize:
            emit(
                "audio_op_start",
                payload={
                    "operation": "normalize",
                    "item_name": out_path.name,
                    "item_idx": idx,
                    "total": total,
                },
            )
            emit(
                "log",
                payload={"message": pipeline_log.fmt_normalize_start(out_path.name)},
            )
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_normalize_detail(
                        args.normalize_target_lufs
                    )
                },
            )

            def _norm_cb(ratio: float) -> None:
                emit("progress_update", payload={"current": ratio})
                if ratio > 0:
                    emit(
                        "log",
                        payload={
                            "message": pipeline_log.fmt_ffmpeg_progress(ratio),
                            "mutable": True,
                        },
                    )

            out_path, stats = _normalize_lufs(
                out_path, AUDIO_PROCESSED_DIR, args.normalize_target_lufs, _norm_cb
            )

            if stats:
                emit(
                    "log",
                    payload={"message": pipeline_log.fmt_normalize_measured(stats)},
                )
            else:
                emit("log", payload={"message": pipeline_log.fmt_normalize_fallback()})

        # ── Post: final encode (fixes denoise .wav output + applies mono/sr) ──
        # target_fmt mirrors the base operation; "best" keeps the current suffix.
        target_fmt = (
            args.fmt if args.fmt != "best" else out_path.suffix.lstrip(".").lower()
        )
        needs_fmt_change = out_path.suffix.lstrip(".").lower() != target_fmt.lower()
        needs_resample = bool(args.channels) or bool(args.sample_rate)
        if needs_fmt_change or needs_resample:
            emit(
                "audio_op_start",
                payload={
                    "operation": "encode",
                    "item_name": out_path.name,
                    "item_idx": idx,
                    "total": total,
                },
            )
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_encode_start(out_path.name, target_fmt)
                },
            )
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_encode_detail(
                        args.channels, args.sample_rate
                    )
                },
            )

            def _encode_cb(ratio: float) -> None:
                emit("progress_update", payload={"current": ratio})

            out_path = convert_audio(
                src=out_path,
                out_dir=AUDIO_PROCESSED_DIR,
                fmt=target_fmt,
                bitrate=args.quality if args.quality != "best" else None,
                channels=args.channels,
                sample_rate=args.sample_rate,
                progress_cb=_encode_cb,
            )

        elapsed = time() - t0
        emit(
            "audio_op_done",
            payload={
                "output_path": str(out_path),
                "elapsed": f"{elapsed:.1f}s",
                "item_idx": idx,
                "total": total,
                "src_size_bytes": original_src_size,
                "out_size_bytes": out_path.stat().st_size,
            },
        )
        return str(out_path)

    return _process_item


def start_audio_pipeline(
    args: AudioArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch the audio pipeline in a daemon thread.

    Args:
        args: Form parameters.
        bus: Shared EventBus.
        cancel_event: threading.Event for cancellation.
        on_finish: Optional callback called on completion (success or error).

    Returns:
        Started daemon thread.
    """
    return start_pipeline(run_audio_pipeline, args, bus, cancel_event, on_finish)
