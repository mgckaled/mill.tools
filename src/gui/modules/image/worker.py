"""Worker for the image pipeline running in a background thread."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Callable

from src.core.image.args import ImageArgs
from src.core.image.background import create_session, is_available, replace_background
from src.core.image.converter import convert_image
from src.core.image.describe import describe_image, save_description
from src.core.image.downloader import download_image
from src.core.image.exif import apply_to_file as apply_exif
from src.core.image.info import thumbnail_bytes
from src.core.image.transform import (
    add_border,
    adjust_image,
    apply_filter,
    crop_image,
    make_contact_sheet,
    make_favicon,
    resize_image,
    rotate_image,
    watermark_image,
)
from src.gui.modules._pipeline_runner import (
    _LogScope,
    item_label,
    make_emitter,
    run_queue_pipeline,
)
from src.gui.modules.image import pipeline_log
from src.utils import IMAGE_PROCESSED_DIR, IMAGE_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "image"

logger = logging.getLogger(__name__)


def run_image_pipeline(
    args: ImageArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    *,
    install_log_handler: bool = True,
) -> bool:
    """Execute the image item queue sequentially.

    contact_sheet, remove_bg and describe are handled by dedicated functions
    before the main loop. The standard operation loop uses run_queue_pipeline
    with stop_on_error=False (per-item errors don't abort the queue).

    Args:
        args: Image form parameters.
        bus: Shared application EventBus.
        cancel_event: threading.Event set by the Cancel button.
        install_log_handler: When False, skips LogEventHandler installation
            (use False in CLI to avoid duplicating TqdmLoggingHandler output).

    Returns:
        True if at least one item completed without error.
    """
    emit = make_emitter(bus, _MODULE_ID, "image")

    # Short-circuit modes run under their own LogScope
    if args.operation == "contact_sheet":
        return _run_contact_sheet(
            args, cancel_event, emit, bus, install_log_handler=install_log_handler
        )
    if args.operation == "remove_bg":
        return _run_batch_rembg(
            args, cancel_event, emit, bus, install_log_handler=install_log_handler
        )
    if args.operation == "describe":
        return _run_batch_describe(
            args, cancel_event, emit, bus, install_log_handler=install_log_handler
        )
    if args.operation == "ocr":
        return _run_batch_ocr(
            args, cancel_event, emit, bus, install_log_handler=install_log_handler
        )

    # Standard ops: run_queue_pipeline manages its own LogScope
    return run_queue_pipeline(
        items=args.items,
        bus=bus,
        module_id=_MODULE_ID,
        default_stage="image",
        cancel_event=cancel_event,
        process_item=_make_process_item(args),
        stop_on_error=False,
        error_event="image_op_error",
        install_log_handler=install_log_handler,
    )


def _make_process_item(args: ImageArgs) -> Callable:
    """Return a process_item closure capturing the pipeline args."""

    def _process_item(
        emit: Callable,
        item,
        idx: int,
        total: int,
        cancel_event: threading.Event,
    ) -> str:
        t0 = time()

        # ── Resolve source (download if URL) ─────────────────────────────
        if item.kind == "url":
            emit(
                "image_op_start",
                payload={
                    "operation": "download",
                    "item_name": item_label(item),
                    "item_idx": idx,
                    "total_items": total,
                },
            )
            src = download_image(item.value, IMAGE_SOURCE_DIR)
        else:
            src = Path(item.value)

        input_thumb = _make_thumb(src)

        # ── Dispatch by operation ─────────────────────────────────────────
        op = args.operation
        emit(
            "image_op_start",
            payload={
                "operation": op,
                "item_name": src.name,
                "thumb": input_thumb,
                "item_idx": idx,
                "total_items": total,
            },
        )

        meta = _try_read_meta(src)
        _w = _h = 0
        _mode = "?"
        _src_fmt: str | None = None
        if meta:
            _w, _h, _mode, _src_fmt = meta
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_image_info(
                        src.name,
                        _w,
                        _h,
                        _mode,
                        src.stat().st_size,
                    )
                },
            )

        match op:
            case "convert":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_convert_detail(_src_fmt, args.fmt)
                    },
                )
                out_path = convert_image(
                    src, IMAGE_PROCESSED_DIR, args.fmt, args.quality
                )

            case "resize":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_resize_detail(
                            args.resize_mode,
                            _w,
                            _h,
                            args.resize_width,
                            args.resize_height,
                            args.resize_scale_pct,
                        )
                    },
                )
                out_path = resize_image(
                    src,
                    IMAGE_PROCESSED_DIR,
                    resize_mode=args.resize_mode,
                    width=args.resize_width,
                    height=args.resize_height,
                    scale_pct=args.resize_scale_pct,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                )

            case "crop":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_crop_detail(
                            args.crop_mode,
                            args.crop_left,
                            args.crop_top,
                            args.crop_width,
                            args.crop_height,
                            args.crop_ratio,
                            args.crop_trim_color,
                        )
                    },
                )
                out_path = crop_image(
                    src,
                    IMAGE_PROCESSED_DIR,
                    crop_mode=args.crop_mode,
                    left=args.crop_left,
                    top=args.crop_top,
                    crop_width=args.crop_width,
                    crop_height=args.crop_height,
                    ratio=args.crop_ratio,
                    trim_color=args.crop_trim_color,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                    focal_x=args.crop_focal_x,
                    focal_y=args.crop_focal_y,
                )

            case "rotate":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_rotate_detail(
                            args.rotate_angle,
                            args.rotate_flip_h,
                            args.rotate_flip_v,
                            args.rotate_exif_auto,
                        )
                    },
                )
                out_path = rotate_image(
                    src,
                    IMAGE_PROCESSED_DIR,
                    angle=args.rotate_angle,
                    flip_h=args.rotate_flip_h,
                    flip_v=args.rotate_flip_v,
                    exif_auto=args.rotate_exif_auto,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                )

            case "watermark":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_watermark_detail(
                            args.wm_mode,
                            args.wm_position,
                            args.wm_opacity,
                        )
                    },
                )
                out_path = watermark_image(
                    src,
                    IMAGE_PROCESSED_DIR,
                    wm_mode=args.wm_mode,
                    text=args.wm_text,
                    text_color=args.wm_text_color,
                    text_size=args.wm_text_size,
                    wm_path=args.wm_path,
                    position=args.wm_position,
                    opacity=args.wm_opacity,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                    rotation=args.wm_rotation,
                )

            case "border":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_border_detail(
                            args.border_padding,
                            args.border_color,
                            args.border_fill_alpha,
                        )
                    },
                )
                out_path = add_border(
                    src,
                    IMAGE_PROCESSED_DIR,
                    padding=args.border_padding,
                    color=args.border_color,
                    fill_alpha=args.border_fill_alpha,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                )

            case "adjust":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_adjust_detail(
                            args.adj_brightness,
                            args.adj_contrast,
                            args.adj_color,
                            args.adj_sharpness,
                        )
                    },
                )
                out_path = adjust_image(
                    src,
                    IMAGE_PROCESSED_DIR,
                    brightness=args.adj_brightness,
                    contrast=args.adj_contrast,
                    color=args.adj_color,
                    sharpness=args.adj_sharpness,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                )

            case "filter":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_filter_detail(args.filter_type)
                    },
                )
                out_path = apply_filter(
                    src,
                    IMAGE_PROCESSED_DIR,
                    filter_type=args.filter_type,
                    out_fmt=args.out_fmt,
                    quality=args.out_quality,
                )

            case "favicon":
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_favicon_detail(args.favicon_sizes)
                    },
                )
                out_path = make_favicon(
                    src, IMAGE_PROCESSED_DIR, sizes=args.favicon_sizes
                )

            case _:
                raise ValueError(f"Unknown operation: {op}")

        # EXIF post-process (no-op for formats that can't carry EXIF, e.g. .ico).
        apply_exif(
            out_path,
            src,
            args.exif_mode,
            {
                "artist": args.exif_artist,
                "copyright": args.exif_copyright,
                "description": args.exif_description,
            },
        )
        if args.exif_mode != "preserve":
            emit(
                "log",
                payload={"message": pipeline_log.fmt_exif_detail(args.exif_mode)},
            )

        output_thumb = _make_thumb(out_path)
        out_meta = _try_read_meta(out_path)
        emit(
            "image_op_done",
            payload={
                "output_path": str(out_path),
                "thumb": output_thumb,
                "elapsed": f"{time() - t0:.1f}s",
                "item_idx": idx,
                "total_items": total,
                "src_size_bytes": src.stat().st_size,
                "out_size_bytes": out_path.stat().st_size,
                "src_w": _w,
                "src_h": _h,
                "src_fmt": _src_fmt,
                "out_w": out_meta[0] if out_meta else 0,
                "out_h": out_meta[1] if out_meta else 0,
                "out_mode": out_meta[2] if out_meta else "?",
                "out_fmt": out_meta[3] if out_meta else None,
            },
        )
        return str(out_path)

    return _process_item


def _run_contact_sheet(
    args: ImageArgs,
    cancel_event: threading.Event,
    emit: Callable,
    bus: "EventBus",
    *,
    install_log_handler: bool = True,
) -> bool:
    """Resolve all items and build a contact sheet (N→1)."""
    from contextlib import nullcontext

    ctx = _LogScope(bus, _MODULE_ID) if install_log_handler else nullcontext()
    with ctx:
        emit("progress_start")
        sources: list[Path] = []
        total = len(args.items)

        for idx, item in enumerate(args.items, 1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

            emit(
                "queue_progress",
                payload={
                    "current_item": idx,
                    "total_items": total,
                    "item_name": item_label(item),
                },
            )
            try:
                src = (
                    download_image(item.value, IMAGE_SOURCE_DIR)
                    if item.kind == "url"
                    else Path(item.value)
                )
                sources.append(src)
            except Exception as exc:
                emit(
                    "image_op_error",
                    payload={
                        "item_name": item_label(item),
                        "message": str(exc),
                    },
                )

        if not sources:
            emit(
                "task_error", payload={"message": "Nenhum item válido para a colagem."}
            )
            return False

        emit(
            "image_op_start",
            payload={
                "operation": "contact_sheet",
                "item_name": f"{len(sources)} imagens",
                "thumb": None,
                "item_idx": 1,
                "total_items": 1,
            },
        )
        emit(
            "log",
            payload={
                "message": pipeline_log.fmt_cs_detail(
                    len(sources),
                    args.cs_cols,
                    args.cs_thumb_size,
                    args.cs_gap,
                    args.cs_bg_color,
                )
            },
        )
        try:
            t0 = time()
            out_path = make_contact_sheet(
                sources,
                IMAGE_PROCESSED_DIR,
                cols=args.cs_cols,
                thumb_size=args.cs_thumb_size,
                gap=args.cs_gap,
                bg_color=args.cs_bg_color,
                out_fmt=args.out_fmt or "png",
                quality=args.out_quality,
            )
            cs_meta = _try_read_meta(out_path)
            emit(
                "image_op_done",
                payload={
                    "output_path": str(out_path),
                    "thumb": _make_thumb(out_path),
                    "elapsed": f"{time() - t0:.1f}s",
                    "item_idx": 1,
                    "total_items": 1,
                    "src_size_bytes": 0,
                    "out_size_bytes": out_path.stat().st_size,
                    "out_w": cs_meta[0] if cs_meta else 0,
                    "out_h": cs_meta[1] if cs_meta else 0,
                    "out_mode": cs_meta[2] if cs_meta else "?",
                    "out_fmt": cs_meta[3] if cs_meta else None,
                },
            )
            emit(
                "task_done",
                payload={"output_paths": [str(out_path)], "failed_count": 0},
            )
            return True
        except Exception as exc:
            emit("task_error", payload={"message": str(exc)})
            return False


def _run_batch_rembg(
    args: ImageArgs,
    cancel_event: threading.Event,
    emit: Callable,
    bus: "EventBus",
    *,
    install_log_handler: bool = True,
) -> bool:
    """Remove background from each item via rembg (CPU/ONNX)."""
    if not is_available():
        emit(
            "task_error",
            payload={
                "message": "Extra [ai-image] not installed. Run: uv sync --extra ai-image"
            },
        )
        return False

    emit("log", payload={"message": pipeline_log.fmt_rembg_loading(args.rembg_model)})
    try:
        session = create_session(args.rembg_model)
    except Exception as exc:
        emit("task_error", payload={"message": f"Failed to load rembg model: {exc}"})
        return False
    emit("log", payload={"message": pipeline_log.fmt_rembg_loaded(args.rembg_model)})

    from contextlib import nullcontext

    ctx = _LogScope(bus, _MODULE_ID) if install_log_handler else nullcontext()
    with ctx:
        emit("progress_start")
        output_paths: list[str] = []
        failed_count = 0
        total = len(args.items)

        for idx, item in enumerate(args.items, 1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

            item_name = item_label(item)
            emit(
                "queue_progress",
                payload={
                    "current_item": idx,
                    "total_items": total,
                    "item_name": item_name,
                },
            )
            t0 = time()

            try:
                if item.kind == "url":
                    emit(
                        "image_op_start",
                        payload={
                            "operation": "download",
                            "item_name": item_name,
                            "item_idx": idx,
                            "total_items": total,
                        },
                    )
                    src = download_image(item.value, IMAGE_SOURCE_DIR)
                else:
                    src = Path(item.value)

                input_thumb = _make_thumb(src)
                emit(
                    "image_op_start",
                    payload={
                        "operation": "remove_bg",
                        "item_name": src.name,
                        "thumb": input_thumb,
                        "item_idx": idx,
                        "total_items": total,
                    },
                )

                meta = _try_read_meta(src)
                if meta:
                    emit(
                        "log",
                        payload={
                            "message": pipeline_log.fmt_image_info(
                                src.name,
                                meta[0],
                                meta[1],
                                meta[2],
                                src.stat().st_size,
                            )
                        },
                    )
                emit(
                    "log",
                    payload={"message": pipeline_log.fmt_rembg_inferring(src.name)},
                )

                out_path = replace_background(
                    src,
                    IMAGE_PROCESSED_DIR,
                    session,
                    bg_mode=args.rembg_bg_mode,
                    bg_color=args.rembg_bg_color,
                    bg_blur=args.rembg_bg_blur,
                    bg_image=args.rembg_bg_image,
                )
                apply_exif(
                    out_path,
                    src,
                    args.exif_mode,
                    {
                        "artist": args.exif_artist,
                        "copyright": args.exif_copyright,
                        "description": args.exif_description,
                    },
                )
                output_paths.append(str(out_path))
                out_meta = _try_read_meta(out_path)
                emit(
                    "image_op_done",
                    payload={
                        "output_path": str(out_path),
                        "thumb": _make_thumb(out_path),
                        "elapsed": f"{time() - t0:.1f}s",
                        "item_idx": idx,
                        "total_items": total,
                        "src_size_bytes": src.stat().st_size,
                        "out_size_bytes": out_path.stat().st_size,
                        "src_w": meta[0] if meta else 0,
                        "src_h": meta[1] if meta else 0,
                        "src_fmt": meta[3] if meta else None,
                        "out_w": out_meta[0] if out_meta else 0,
                        "out_h": out_meta[1] if out_meta else 0,
                        "out_mode": out_meta[2] if out_meta else "?",
                        "out_fmt": out_meta[3] if out_meta else None,
                    },
                )

            except Exception as exc:
                failed_count += 1
                logger.warning("[!] Error on '%s': %s", item_name, exc)
                emit(
                    "image_op_error",
                    payload={"item_name": item_name, "message": str(exc)},
                )

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

        emit(
            "task_done",
            payload={"output_paths": output_paths, "failed_count": failed_count},
        )
        return len(output_paths) > 0


def _run_batch_describe(
    args: ImageArgs,
    cancel_event: threading.Event,
    emit: Callable,
    bus: "EventBus",
    *,
    install_log_handler: bool = True,
) -> bool:
    """Describe each image via Ollama vision and save .txt output."""
    from contextlib import nullcontext

    ctx = _LogScope(bus, _MODULE_ID) if install_log_handler else nullcontext()
    with ctx:
        emit("progress_start")
        output_paths: list[str] = []
        failed_count = 0
        total = len(args.items)

        for idx, item in enumerate(args.items, 1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

            item_name = item_label(item)
            emit(
                "queue_progress",
                payload={
                    "current_item": idx,
                    "total_items": total,
                    "item_name": item_name,
                },
            )
            t0 = time()

            try:
                src = (
                    Path(item.value)
                    if item.kind == "local"
                    else download_image(item.value, IMAGE_SOURCE_DIR)
                )
                input_thumb = _make_thumb(src)
                emit(
                    "image_op_start",
                    payload={
                        "operation": "describe",
                        "item_name": src.name,
                        "thumb": input_thumb,
                        "item_idx": idx,
                        "total_items": total,
                    },
                )

                meta = _try_read_meta(src)
                if meta:
                    emit(
                        "log",
                        payload={
                            "message": pipeline_log.fmt_image_info(
                                src.name,
                                meta[0],
                                meta[1],
                                meta[2],
                                src.stat().st_size,
                            )
                        },
                    )
                emit(
                    "log",
                    payload={
                        "message": pipeline_log.fmt_describe_header(
                            args.describe_model,
                            args.describe_prompt,
                        )
                    },
                )
                emit("log", payload={"message": pipeline_log.fmt_describe_sep_open()})

                text = describe_image(
                    src, model=args.describe_model, prompt=args.describe_prompt
                )
                out_path = save_description(src, IMAGE_PROCESSED_DIR, text)
                output_paths.append(str(out_path))

                for line in text.splitlines():
                    if line.strip():
                        emit("log", payload={"message": line})

                emit("log", payload={"message": pipeline_log.fmt_describe_sep_close()})
                emit(
                    "image_op_done",
                    payload={
                        "output_path": str(out_path),
                        "thumb": None,
                        "elapsed": f"{time() - t0:.1f}s",
                        "item_idx": idx,
                        "total_items": total,
                        "src_size_bytes": src.stat().st_size,
                        "out_size_bytes": out_path.stat().st_size,
                    },
                )

            except Exception as exc:
                failed_count += 1
                logger.warning("[!] Error on '%s': %s", item_name, exc)
                emit(
                    "image_op_error",
                    payload={"item_name": item_name, "message": str(exc)},
                )

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

        emit(
            "task_done",
            payload={"output_paths": output_paths, "failed_count": failed_count},
        )
        return len(output_paths) > 0


def _run_batch_ocr(
    args: ImageArgs,
    cancel_event: threading.Event,
    emit: Callable,
    bus: "EventBus",
    *,
    install_log_handler: bool = True,
) -> bool:
    """Extract text from each image via Tesseract and save a .txt output."""
    from contextlib import nullcontext

    from src.core.image.ocr import is_available, ocr_image

    if not is_available():
        emit(
            "task_error",
            payload={
                "message": "Tesseract não encontrado. Instale o extra [ocr] e o binário."
            },
        )
        return False

    ctx = _LogScope(bus, _MODULE_ID) if install_log_handler else nullcontext()
    with ctx:
        emit("progress_start")
        output_paths: list[str] = []
        failed_count = 0
        total = len(args.items)

        for idx, item in enumerate(args.items, 1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

            item_name = item_label(item)
            emit(
                "queue_progress",
                payload={
                    "current_item": idx,
                    "total_items": total,
                    "item_name": item_name,
                },
            )
            t0 = time()

            try:
                src = (
                    Path(item.value)
                    if item.kind == "local"
                    else download_image(item.value, IMAGE_SOURCE_DIR)
                )
                emit(
                    "image_op_start",
                    payload={
                        "operation": "ocr",
                        "item_name": src.name,
                        "thumb": _make_thumb(src),
                        "item_idx": idx,
                        "total_items": total,
                    },
                )
                emit(
                    "log", payload={"message": f"[~] OCR ({args.ocr_lang}): {src.name}"}
                )

                out_path, words = ocr_image(
                    src, IMAGE_PROCESSED_DIR, lang=args.ocr_lang
                )
                output_paths.append(str(out_path))
                emit("log", payload={"message": f"[i] {words} palavra(s) extraída(s)."})
                emit(
                    "image_op_done",
                    payload={
                        "output_path": str(out_path),
                        "thumb": None,
                        "elapsed": f"{time() - t0:.1f}s",
                        "item_idx": idx,
                        "total_items": total,
                        "src_size_bytes": src.stat().st_size,
                        "out_size_bytes": out_path.stat().st_size,
                    },
                )

            except Exception as exc:
                failed_count += 1
                logger.warning("[!] Error on '%s': %s", item_name, exc)
                emit(
                    "image_op_error",
                    payload={"item_name": item_name, "message": str(exc)},
                )

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado."})
                return False

        emit(
            "task_done",
            payload={"output_paths": output_paths, "failed_count": failed_count},
        )
        return len(output_paths) > 0


def start_image_pipeline(
    args: ImageArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> threading.Thread:
    """Launch the image pipeline in a daemon thread.

    Args:
        args: Form parameters.
        bus: Shared EventBus.
        cancel_event: threading.Event for cancellation.
        pipeline_running: Shared [bool] with app.py; reset to False in finally.

    Returns:
        Started daemon thread.
    """

    def _run() -> None:
        try:
            run_image_pipeline(args, bus, cancel_event)
        finally:
            pipeline_running[0] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _make_thumb(path: Path) -> bytes | None:
    """Generate a preview thumbnail; returns None on failure."""
    try:
        return thumbnail_bytes(path, max_px=600)
    except Exception:
        return None


def _try_read_meta(path: Path) -> tuple[int, int, str, str | None] | None:
    """Read width, height, mode and format from the image header without decoding pixels."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size[0], im.size[1], im.mode, im.format
    except Exception:
        return None
