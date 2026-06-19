"""Worker for the document pipeline running in a background thread."""

from __future__ import annotations

import logging
import threading
from time import time
from typing import TYPE_CHECKING, Callable

from src.core.document.args import DocumentArgs
from src.gui.modules._pipeline_runner import (
    _LogScope,
    make_emitter,
)
from src.gui.modules.document import pipeline_log
from src.utils import DOCUMENT_PROCESSED_DIR, DOCUMENT_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "document"

logger = logging.getLogger(__name__)


def run_document_pipeline(
    args: DocumentArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    *,
    install_log_handler: bool = True,
) -> bool:
    """Execute the document pipeline for the given operation.

    Args:
        args: Document form parameters.
        bus: Shared application EventBus.
        cancel_event: threading.Event set by the Cancel button.
        install_log_handler: When False, skips LogEventHandler installation.

    Returns:
        True on success, False on failure or cancellation.
    """
    from contextlib import nullcontext

    emit = make_emitter(bus, _MODULE_ID, "document")
    ctx = _LogScope(bus, _MODULE_ID) if install_log_handler else nullcontext()

    with ctx:
        try:
            emit("progress_start")
            op = args.operation

            DOCUMENT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            DOCUMENT_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

            if op == "qr":
                return _run_qr(args, emit)

            if op == "merge":
                return _run_merge(args, emit)

            if op == "images_to_pdf":
                return _run_images_to_pdf(args, emit)

            if op == "split":
                return _run_split(args, emit)

            if op == "pdf_to_images":
                return _run_pdf_to_images(args, emit, cancel_event)

            if op == "extract":
                return _run_extract(args, emit)

            if op == "ocr":
                return _run_ocr(args, emit)

            if op == "analyze":
                return _run_analyze(args, emit, cancel_event)

            # Single-file operations: compress, rotate, watermark, stamp, encrypt
            return _run_single(args, emit)

        except Exception as exc:
            logger.exception("[!] Document pipeline error: %s", exc)
            emit("task_error", payload={"message": str(exc)})
            return False


# ─── Operation handlers ────────────────────────────────────────────────────────


def _run_qr(args: DocumentArgs, emit: Callable) -> bool:
    from src.core.document.qr import generate_qr

    t0 = time()
    emit(
        "document_op_start",
        payload={
            "operation": "qr",
            "item_name": args.qr_data[:40] or "QR code",
            "item_idx": 1,
            "total": 1,
            "page_count": 0,
        },
    )
    emit(
        "log",
        payload={
            "message": pipeline_log.fmt_qr_detail(
                args.qr_data[:40],
                args.qr_size,
            )
        },
    )
    out = generate_qr(
        args.qr_data, DOCUMENT_PROCESSED_DIR, size=args.qr_size, fmt=args.qr_fmt
    )
    elapsed = f"{time() - t0:.1f}s"
    emit(
        "document_op_done",
        payload={
            "operation": "qr",
            "output_path": str(out),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": 0,
            "out_size_bytes": out.stat().st_size,
            "extra_stats": {"qr_data_preview": args.qr_data[:40]},
        },
    )
    emit("task_done", payload={"output_paths": [str(out)], "failed_count": 0})
    return True


def _run_merge(args: DocumentArgs, emit: Callable) -> bool:
    from src.core.document.processor import merge_pdfs
    from src.core.document.info import get_pdf_info

    t0 = time()
    paths = args.input_paths
    total_pages = 0
    for p in paths:
        try:
            info = get_pdf_info(p)
            total_pages += info.page_count
            emit(
                "log",
                payload={"message": f"[*] Lendo {p.name} · {info.page_count} pág."},
            )
        except Exception:
            pass
    emit(
        "document_op_start",
        payload={
            "operation": "merge",
            "item_name": f"{len(paths)} arquivos",
            "item_idx": 1,
            "total": 1,
            "page_count": total_pages,
        },
    )
    emit(
        "log",
        payload={"message": pipeline_log.fmt_merge_detail(len(paths), total_pages)},
    )
    emit("log", payload={"message": "[~] Unindo documentos…"})
    out = merge_pdfs(paths, DOCUMENT_PROCESSED_DIR)
    elapsed = f"{time() - t0:.1f}s"
    try:
        out_info = get_pdf_info(out)
        out_pages = out_info.page_count
    except Exception:
        out_pages = total_pages
    emit(
        "document_op_done",
        payload={
            "operation": "merge",
            "output_path": str(out),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": sum(p.stat().st_size for p in paths),
            "out_size_bytes": out.stat().st_size,
            "extra_stats": {"page_total": out_pages, "file_count": len(paths)},
        },
    )
    emit("task_done", payload={"output_paths": [str(out)], "failed_count": 0})
    return True


def _run_split(args: DocumentArgs, emit: Callable) -> bool:
    from src.core.document.processor import split_pdf
    from src.core.document.info import get_pdf_info

    path = args.input_paths[0]
    t0 = time()
    info = get_pdf_info(path)
    spec = args.pages or "all"
    emit(
        "document_op_start",
        payload={
            "operation": "split",
            "item_name": path.name,
            "item_idx": 1,
            "total": 1,
            "page_count": info.page_count,
        },
    )
    emit(
        "log",
        payload={
            "message": pipeline_log.fmt_split_detail(
                path.name,
                info.page_count,
                spec,
            )
        },
    )
    parts = split_pdf(path, spec, DOCUMENT_PROCESSED_DIR)
    elapsed = f"{time() - t0:.1f}s"
    page_counts = []
    for p in parts:
        try:
            page_counts.append(get_pdf_info(p).page_count)
        except Exception:
            page_counts.append(0)
    emit(
        "document_op_done",
        payload={
            "operation": "split",
            "output_path": str(parts[0]) if parts else "",
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": path.stat().st_size,
            "out_size_bytes": sum(p.stat().st_size for p in parts),
            "extra_stats": {
                "output_files": [p.name for p in parts],
                "page_counts": page_counts,
            },
        },
    )
    emit(
        "task_done",
        payload={"output_paths": [str(p) for p in parts], "failed_count": 0},
    )
    return True


def _run_pdf_to_images(
    args: DocumentArgs,
    emit: Callable,
    cancel_event: threading.Event,
) -> bool:
    from src.core.document.converter import pdf_to_images
    from src.core.document.info import get_pdf_info

    path = args.input_paths[0]
    t0 = time()
    info = get_pdf_info(path)
    emit(
        "document_op_start",
        payload={
            "operation": "pdf_to_images",
            "item_name": path.name,
            "item_idx": 1,
            "total": 1,
            "page_count": info.page_count,
        },
    )
    emit("log", payload={"message": f"[i] {path.name} · {info.page_count} páginas"})

    def _progress(current: int, total: int) -> None:
        emit(
            "log",
            payload={
                "message": pipeline_log.fmt_pdf_to_images_progress(current, total),
                "mutable": True,
            },
        )

    imgs = pdf_to_images(
        path,
        DOCUMENT_PROCESSED_DIR,
        fmt=args.image_fmt,
        dpi=args.dpi,
        progress_cb=_progress,
    )
    elapsed = f"{time() - t0:.1f}s"
    resolution = ""
    if imgs:
        try:
            from PIL import Image as PILImage

            with PILImage.open(imgs[0]) as im:
                resolution = f"{im.size[0]}×{im.size[1]}"
        except Exception:
            pass
    emit(
        "document_op_done",
        payload={
            "operation": "pdf_to_images",
            "output_path": str(imgs[0]) if imgs else "",
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": path.stat().st_size,
            "out_size_bytes": sum(p.stat().st_size for p in imgs),
            "extra_stats": {"image_count": len(imgs), "resolution": resolution},
        },
    )
    emit(
        "task_done", payload={"output_paths": [str(p) for p in imgs], "failed_count": 0}
    )
    return True


def _run_images_to_pdf(args: DocumentArgs, emit: Callable) -> bool:
    from src.core.document.converter import images_to_pdf

    paths = args.input_paths
    t0 = time()
    total = len(paths)
    emit(
        "document_op_start",
        payload={
            "operation": "images_to_pdf",
            "item_name": f"{total} imagens",
            "item_idx": 1,
            "total": 1,
            "page_count": total,
        },
    )
    emit("log", payload={"message": f"[i] {total} imagens selecionadas"})
    for i, p in enumerate(paths, 1):
        emit(
            "log",
            payload={
                "message": pipeline_log.fmt_images_to_pdf_progress(p.name, i, total),
                "mutable": True,
            },
        )
    out = images_to_pdf(paths, DOCUMENT_PROCESSED_DIR, output_name=args.output_name)
    elapsed = f"{time() - t0:.1f}s"
    emit(
        "document_op_done",
        payload={
            "operation": "images_to_pdf",
            "output_path": str(out),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": sum(p.stat().st_size for p in paths),
            "out_size_bytes": out.stat().st_size,
            "extra_stats": {},
        },
    )
    emit("task_done", payload={"output_paths": [str(out)], "failed_count": 0})
    return True


def _run_extract(args: DocumentArgs, emit: Callable) -> bool:
    from src.core.document.converter import extract_text
    from src.core.document.info import get_pdf_info

    path = args.input_paths[0]
    t0 = time()
    info = get_pdf_info(path)
    emit(
        "document_op_start",
        payload={
            "operation": "extract",
            "item_name": path.name,
            "item_idx": 1,
            "total": 1,
            "page_count": info.page_count,
        },
    )
    emit(
        "log",
        payload={
            "message": pipeline_log.fmt_extract_detail(path.name, info.page_count)
        },
    )
    txt_path, word_count = extract_text(path, DOCUMENT_PROCESSED_DIR)
    elapsed = f"{time() - t0:.1f}s"
    emit(
        "log",
        payload={"message": f"[»] {info.page_count} páginas · ~{word_count} palavras"},
    )
    if word_count >= 50:
        emit(
            "log",
            payload={
                "message": '[i] Clique em "Analisar com IA" para processar o conteúdo'
            },
        )
    emit(
        "document_op_done",
        payload={
            "operation": "extract",
            "output_path": str(txt_path),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": path.stat().st_size,
            "out_size_bytes": txt_path.stat().st_size,
            "extra_stats": {"word_count": word_count},
        },
    )
    emit("task_done", payload={"output_paths": [str(txt_path)], "failed_count": 0})
    return True


def _run_ocr(args: DocumentArgs, emit: Callable) -> bool:
    """OCR a (possibly scanned) PDF to text — hybrid native/Tesseract per page."""
    from src.core.document import ocr
    from src.core.document.info import get_pdf_info

    path = args.input_paths[0]
    t0 = time()
    info = get_pdf_info(path)
    emit(
        "document_op_start",
        payload={
            "operation": "ocr",
            "item_name": path.name,
            "item_idx": 1,
            "total": 1,
            "page_count": info.page_count,
        },
    )
    emit(
        "log",
        payload={
            "message": pipeline_log.fmt_ocr_detail(
                path.name,
                info.page_count,
                args.ocr_lang,
                args.ocr_dpi,
            )
        },
    )

    def _progress(current: int, total: int) -> None:
        emit(
            "log",
            payload={
                "message": pipeline_log.fmt_ocr_progress(current, total),
                "mutable": True,
            },
        )

    txt_path, word_count = ocr.ocr_pdf(
        path,
        DOCUMENT_PROCESSED_DIR,
        lang=args.ocr_lang,
        dpi=args.ocr_dpi,
        progress_cb=_progress,
    )
    elapsed = f"{time() - t0:.1f}s"
    emit(
        "log",
        payload={"message": f"[»] {info.page_count} páginas · ~{word_count} palavras"},
    )
    if word_count >= 50:
        emit(
            "log",
            payload={
                "message": '[i] Clique em "Analisar com IA" para processar o conteúdo'
            },
        )
    emit(
        "document_op_done",
        payload={
            "operation": "ocr",
            "output_path": str(txt_path),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": path.stat().st_size,
            "out_size_bytes": txt_path.stat().st_size,
            "extra_stats": {"word_count": word_count},
        },
    )
    emit("task_done", payload={"output_paths": [str(txt_path)], "failed_count": 0})
    return True


def _run_analyze(
    args: DocumentArgs,
    emit: Callable,
    cancel_event: threading.Event,
) -> bool:
    """Analyze a document or text file — reuses src/analyzer.py.

    PDFs are rasterized to text first; a .txt/.md is analyzed as-is (the
    analyzer reads any text file, with or without a metadata header).
    """
    path = args.input_paths[0]
    t0 = time()
    is_text = path.suffix.lower() in {".txt", ".md"}

    if is_text:
        emit(
            "document_op_start",
            payload={
                "operation": "analyze",
                "item_name": path.name,
                "item_idx": 1,
                "total": 1,
                "page_count": 0,
            },
        )
        emit("log", payload={"message": f"[i] {path.name} · arquivo de texto"})
        txt_path = path
        word_count = len(path.read_text(encoding="utf-8", errors="replace").split())
    else:
        from src.core.document.converter import extract_text
        from src.core.document.info import get_pdf_info

        info = get_pdf_info(path)
        emit(
            "document_op_start",
            payload={
                "operation": "analyze",
                "item_name": path.name,
                "item_idx": 1,
                "total": 1,
                "page_count": info.page_count,
            },
        )
        emit("log", payload={"message": f"[i] {path.name} · {info.page_count} páginas"})
        emit("log", payload={"message": "[*] Extraindo texto do documento…"})
        txt_path, word_count = extract_text(path, DOCUMENT_PROCESSED_DIR)

    emit("log", payload={"message": f"[»] ~{word_count} palavras"})
    emit("log", payload={"message": f"[*] Carregando modelo {args.analyze_model}…"})
    from src.analyzer import analyze  # lazy import

    # analyze() writes to transcriptions/analysis/ and returns the .md path —
    # use it directly (do not guess a path under output/document/).
    analysis_path = analyze(
        txt_path, model_name=args.analyze_model, profile=args.analyze_profile
    )
    elapsed = f"{time() - t0:.1f}s"
    emit(
        "document_op_done",
        payload={
            "operation": "analyze",
            "output_path": str(analysis_path),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": path.stat().st_size,
            "out_size_bytes": analysis_path.stat().st_size
            if analysis_path.exists()
            else 0,
            "extra_stats": {},
        },
    )
    emit("task_done", payload={"output_paths": [str(analysis_path)], "failed_count": 0})
    return True


def _run_single(args: DocumentArgs, emit: Callable) -> bool:
    """Handle compress, rotate, watermark, stamp, encrypt (single-file ops)."""
    from src.core.document import processor
    from src.core.document.info import get_pdf_info

    path = args.input_paths[0]
    op = args.operation
    t0 = time()
    info = get_pdf_info(path)
    emit(
        "document_op_start",
        payload={
            "operation": op,
            "item_name": path.name,
            "item_idx": 1,
            "total": 1,
            "page_count": info.page_count,
        },
    )

    src_mb = path.stat().st_size / 1_048_576

    # Emit detail line
    match op:
        case "compress":
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_compress_detail(
                        path.name,
                        info.page_count,
                        src_mb,
                        args.image_quality,
                    )
                },
            )
            out = processor.compress_pdf(
                path, DOCUMENT_PROCESSED_DIR, args.image_quality
            )
        case "rotate":
            pages_desc = (
                "todas as páginas"
                if args.rotate_pages == "all"
                else f"páginas {args.rotate_pages}"
            )
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_rotate_detail(
                        path.name,
                        info.page_count,
                        pages_desc,
                        args.angle,
                    )
                },
            )
            out = processor.rotate_pdf(
                path, DOCUMENT_PROCESSED_DIR, args.angle, args.rotate_pages
            )
        case "watermark":
            pct = int(args.watermark_opacity * 100)
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_watermark_detail(
                        path.name,
                        info.page_count,
                        args.watermark_text,
                        pct,
                    )
                },
            )
            out = processor.watermark_pdf(
                path,
                DOCUMENT_PROCESSED_DIR,
                args.watermark_text,
                args.watermark_opacity,
                args.watermark_position,
            )
        case "stamp":
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_stamp_detail(
                        path.name,
                        info.page_count,
                        args.stamp_text,
                    )
                },
            )
            out = processor.stamp_pdf(path, DOCUMENT_PROCESSED_DIR, args.stamp_text)
        case "encrypt":
            emit(
                "log",
                payload={
                    "message": pipeline_log.fmt_encrypt_detail(
                        path.name,
                        info.page_count,
                        src_mb,
                    )
                },
            )
            out = processor.encrypt_pdf(path, DOCUMENT_PROCESSED_DIR, args.password)
        case _:
            raise ValueError(f"Unknown operation: {op}")

    elapsed = f"{time() - t0:.1f}s"
    src_bytes = path.stat().st_size
    out_bytes = out.stat().st_size

    extra_stats: dict = {}
    if op == "compress" and src_bytes > 0:
        reduction = (1 - out_bytes / src_bytes) * 100
        extra_stats["size_reduction_pct"] = round(reduction, 1)

    emit(
        "document_op_done",
        payload={
            "operation": op,
            "output_path": str(out),
            "elapsed": elapsed,
            "item_idx": 1,
            "total": 1,
            "src_size_bytes": src_bytes,
            "out_size_bytes": out_bytes,
            "extra_stats": extra_stats,
        },
    )
    emit("task_done", payload={"output_paths": [str(out)], "failed_count": 0})
    return True


def start_document_pipeline(
    args: DocumentArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> threading.Thread:
    """Launch the document pipeline in a daemon thread.

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
            run_document_pipeline(args, bus, cancel_event)
        finally:
            pipeline_running[0] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
