"""Worker for the video pipeline running in a background thread."""

from __future__ import annotations

import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Callable

from src.core.video.args import VideoArgs
from src.core.video.converter import (
    compress_video,
    convert_video,
    extract_audio_from_video,
    make_thumbnail,
    resize_video,
    trim_video,
)
from src.core.video.downloader import download_video
from src.core.video.info import get_video_info
from src.gui.modules._pipeline_runner import (
    fmt_ydl_progress,
    item_label,
    run_queue_pipeline,
    start_pipeline,
)
from src.gui.modules.video import pipeline_log
from src.utils import VIDEO_PROCESSED_DIR, VIDEO_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "video"


def run_video_pipeline(
    args: VideoArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    *,
    install_log_handler: bool = True,
) -> bool:
    """Execute the video item queue sequentially.

    Args:
        args: Video form parameters.
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
        default_stage="video",
        cancel_event=cancel_event,
        process_item=_make_process_item(args),
        install_log_handler=install_log_handler,
    )


def _make_process_item(args: VideoArgs) -> Callable:
    """Return a process_item closure capturing the pipeline args."""

    def _process_item(
        emit: Callable,
        item,
        idx: int,
        total: int,
        cancel_event: threading.Event,
    ) -> str:
        item_name = item_label(item)

        # URL → always download; local → use chosen operation
        effective_op = "download" if item.kind == "url" else args.operation

        if effective_op == "download" and item.kind != "url":
            raise ValueError(f"Operation 'download' requires a URL: {item_name}")
        if effective_op != "download" and item.kind == "url":
            raise ValueError(f"Local file expected for '{effective_op}': {item_name}")

        emit("video_op_start", payload={
            "operation": effective_op,
            "item_name": item_name,
            "item_idx":  idx,
            "total":     total,
        })

        t0 = time()

        def _progress_cb(ratio: float) -> None:
            emit("progress_update", payload={"current": ratio})

        if effective_op == "download":
            emit("log", payload={"message": pipeline_log.fmt_download_detail(
                args.resolution, args.container
            )})

            def _ydl_hook(d: dict) -> None:
                if d.get("status") == "downloading":
                    downloaded = d.get("downloaded_bytes", 0) or 0
                    total_b = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    if total_b > 0:
                        emit("progress_update", payload={"current": min(downloaded / total_b, 1.0)})
                    line = fmt_ydl_progress(d)
                    if line:
                        emit("log", payload={"message": line, "mutable": True})

            out_path = download_video(
                url=item.value,
                out_dir=VIDEO_SOURCE_DIR,
                resolution=args.resolution,
                container=args.container,
                embed_meta=args.embed_meta,
                progress_hook=_ydl_hook,
            )
            info = get_video_info(out_path)
            emit("log", payload={"message": pipeline_log.fmt_video_info(info)})

        else:
            src = Path(item.value)
            info = get_video_info(src)
            emit("log", payload={"message": pipeline_log.fmt_video_info(info)})

            try:
                match effective_op:
                    case "convert":
                        emit("log", payload={"message": pipeline_log.fmt_convert_detail(
                            args.vcodec, args.out_container
                        )})
                        out_path = convert_video(
                            src, VIDEO_PROCESSED_DIR,
                            container=args.out_container,
                            vcodec=args.vcodec,
                            progress_cb=_progress_cb,
                        )

                    case "trim":
                        emit("log", payload={"message": pipeline_log.fmt_trim_detail(
                            args.trim_start, args.trim_end, args.trim_reenc
                        )})
                        out_path = trim_video(
                            src, VIDEO_PROCESSED_DIR,
                            start=args.trim_start,
                            end=args.trim_end,
                            reenc=args.trim_reenc,
                            progress_cb=_progress_cb,
                        )

                    case "compress":
                        emit("log", payload={"message": pipeline_log.fmt_compress_detail(
                            args.crf, args.preset
                        )})
                        out_path = compress_video(
                            src, VIDEO_PROCESSED_DIR,
                            crf=args.crf,
                            preset=args.preset,
                            progress_cb=_progress_cb,
                        )

                    case "resize":
                        emit("log", payload={"message": pipeline_log.fmt_resize_detail(
                            args.resize_width, args.resize_height
                        )})
                        out_path = resize_video(
                            src, VIDEO_PROCESSED_DIR,
                            width=args.resize_width,
                            height=args.resize_height,
                            progress_cb=_progress_cb,
                        )

                    case "extract_audio":
                        if not info.acodec:
                            raise ValueError(
                                f"[!] No audio track in: {item_name}\n"
                                "[i] Video-only .webm streams (e.g. f313.webm) contain no audio. "
                                "Use the merged full file instead."
                            )
                        emit("log", payload={"message": pipeline_log.fmt_extract_audio_detail(
                            args.audio_fmt
                        )})
                        out_path = extract_audio_from_video(
                            src, VIDEO_PROCESSED_DIR,
                            audio_fmt=args.audio_fmt,
                            progress_cb=_progress_cb,
                        )

                    case "thumbnail":
                        emit("log", payload={"message": pipeline_log.fmt_thumbnail_detail(
                            args.thumb_time, args.thumb_fmt
                        )})
                        out_path = make_thumbnail(
                            src, VIDEO_PROCESSED_DIR,
                            time=args.thumb_time,
                            fmt=args.thumb_fmt,
                        )

                    case _:
                        raise ValueError(f"Unknown operation: {effective_op}")

            except Exception as exc:
                # Enrich Windows file-lock errors with actionable guidance
                msg = str(exc)
                if "WinError 32" in msg or "being used by another process" in msg:
                    msg += (
                        "\n[i] File locked by antivirus during rename. "
                        "Wait a few seconds and retry, or add the output/ folder "
                        "to Windows Defender exclusions."
                    )
                raise RuntimeError(msg) from exc

        elapsed = time() - t0
        src_size = (
            Path(item.value).stat().st_size
            if item.kind == "local" and Path(item.value).exists() else 0
        )
        emit("video_op_done", payload={
            "output_path":    str(out_path),
            "elapsed":        f"{elapsed:.1f}s",
            "item_idx":       idx,
            "total":          total,
            "src_size_bytes": src_size,
            "out_size_bytes": out_path.stat().st_size,
        })
        return str(out_path)

    return _process_item


def start_video_pipeline(
    args: VideoArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch the video pipeline in a daemon thread.

    Args:
        args: Form parameters.
        bus: Shared EventBus.
        cancel_event: threading.Event for cancellation.
        on_finish: Optional callback called on completion (success or error).

    Returns:
        Started daemon thread.
    """
    return start_pipeline(run_video_pipeline, args, bus, cancel_event, on_finish)
