"""Worker do pipeline de imagens rodando em thread separada."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Callable

from src.core.image.converter import convert_image
from src.core.image.downloader import download_image
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
from src.gui.events import LogEventHandler
from src.gui.modules.image.form_view import ImageArgs
from src.utils import IMAGE_PROCESSED_DIR, IMAGE_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "image"

logger = logging.getLogger(__name__)


def run_image_pipeline(
    args: ImageArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
) -> bool:
    """Executa a fila de itens de imagem sequencialmente.

    Emite eventos genéricos (progress_start, queue_progress, task_done, task_error)
    e eventos específicos (image_op_start, image_op_done, image_op_error).
    Erro por item não trava a fila. contact_sheet é tratado antes do loop principal.

    Args:
        args: Parâmetros do formulário de imagens.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event setado pelo botão Cancelar.

    Returns:
        True se ao menos um item completou sem erro.
    """

    def emit(type: str, stage: str = "image", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {}, module_id=_MODULE_ID)

    log_handler = LogEventHandler(bus, module_id=_MODULE_ID)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.INFO)

    try:
        # contact_sheet é N→1: tratamento especial fora do loop
        if args.operation == "contact_sheet":
            return _run_contact_sheet(args, cancel_event, emit)

        output_paths: list[str] = []
        failed_count = 0
        total = len(args.items)

        emit("progress_start")

        for idx, item in enumerate(args.items, start=1):
            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado pelo usuário."})
                return False

            item_name = _item_label(item)
            emit("queue_progress", payload={
                "current_item": idx,
                "total_items": total,
                "item_name": item_name,
            })

            t0 = time()

            try:
                # ── Resolve src (download se URL) ─────────────────────────
                if item.kind == "url":
                    emit("image_op_start", payload={
                        "operation": "download",
                        "item_name": item_name,
                        "item_idx": idx,
                        "total_items": total,
                    })
                    src = download_image(item.value, IMAGE_SOURCE_DIR)
                else:
                    src = Path(item.value)

                input_thumb = _make_thumb(src)

                # ── Dispatch por operação ─────────────────────────────────
                op = args.operation
                emit("image_op_start", payload={
                    "operation": op,
                    "item_name": src.name,
                    "thumb": input_thumb,
                    "item_idx": idx,
                    "total_items": total,
                })

                match op:
                    case "convert":
                        out_path = convert_image(
                            src, IMAGE_PROCESSED_DIR, args.fmt, args.quality
                        )
                    case "resize":
                        out_path = resize_image(
                            src, IMAGE_PROCESSED_DIR,
                            resize_mode=args.resize_mode,
                            width=args.resize_width,
                            height=args.resize_height,
                            scale_pct=args.resize_scale_pct,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "crop":
                        out_path = crop_image(
                            src, IMAGE_PROCESSED_DIR,
                            crop_mode=args.crop_mode,
                            left=args.crop_left,
                            top=args.crop_top,
                            crop_width=args.crop_width,
                            crop_height=args.crop_height,
                            ratio=args.crop_ratio,
                            trim_color=args.crop_trim_color,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "rotate":
                        out_path = rotate_image(
                            src, IMAGE_PROCESSED_DIR,
                            angle=args.rotate_angle,
                            flip_h=args.rotate_flip_h,
                            flip_v=args.rotate_flip_v,
                            exif_auto=args.rotate_exif_auto,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "watermark":
                        out_path = watermark_image(
                            src, IMAGE_PROCESSED_DIR,
                            wm_mode=args.wm_mode,
                            text=args.wm_text,
                            text_color=args.wm_text_color,
                            text_size=args.wm_text_size,
                            wm_path=args.wm_path,
                            position=args.wm_position,
                            opacity=args.wm_opacity,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "border":
                        out_path = add_border(
                            src, IMAGE_PROCESSED_DIR,
                            padding=args.border_padding,
                            color=args.border_color,
                            fill_alpha=args.border_fill_alpha,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "adjust":
                        out_path = adjust_image(
                            src, IMAGE_PROCESSED_DIR,
                            brightness=args.adj_brightness,
                            contrast=args.adj_contrast,
                            color=args.adj_color,
                            sharpness=args.adj_sharpness,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "filter":
                        out_path = apply_filter(
                            src, IMAGE_PROCESSED_DIR,
                            filter_type=args.filter_type,
                            out_fmt=args.out_fmt,
                            quality=args.out_quality,
                        )
                    case "favicon":
                        out_path = make_favicon(
                            src, IMAGE_PROCESSED_DIR,
                            sizes=args.favicon_sizes,
                        )
                    case _:
                        raise ValueError(f"Operação desconhecida: {op}")

                output_thumb = _make_thumb(out_path)
                elapsed = time() - t0
                output_paths.append(str(out_path))

                emit("image_op_done", payload={
                    "output_path": str(out_path),
                    "thumb": output_thumb,
                    "elapsed": f"{elapsed:.1f}s",
                    "item_idx": idx,
                    "total_items": total,
                    "src_size_bytes": src.stat().st_size,
                    "out_size_bytes": out_path.stat().st_size,
                })

            except Exception as exc:
                failed_count += 1
                logger.warning("[!] Erro em '%s': %s", item_name, exc)
                emit("image_op_error", payload={
                    "item_name": item_name,
                    "message": str(exc),
                })
                continue

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado pelo usuário."})
                return False

        emit("task_done", payload={
            "output_paths": output_paths,
            "failed_count": failed_count,
        })
        return len(output_paths) > 0

    except Exception as exc:
        emit("task_error", payload={"message": str(exc)})
        return False

    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)


def _run_contact_sheet(
    args: ImageArgs,
    cancel_event: threading.Event,
    emit: Callable,
) -> bool:
    """Resolve todos os itens e monta contact sheet (N→1)."""
    emit("progress_start")
    sources: list[Path] = []
    total = len(args.items)

    for idx, item in enumerate(args.items, 1):
        if cancel_event.is_set():
            emit("task_error", payload={"message": "Cancelado."})
            return False

        emit("queue_progress", payload={
            "current_item": idx,
            "total_items": total,
            "item_name": _item_label(item),
        })
        try:
            if item.kind == "url":
                src = download_image(item.value, IMAGE_SOURCE_DIR)
            else:
                src = Path(item.value)
            sources.append(src)
        except Exception as exc:
            emit("image_op_error", payload={
                "item_name": _item_label(item),
                "message": str(exc),
            })

    if not sources:
        emit("task_error", payload={"message": "Nenhum item válido para a colagem."})
        return False

    emit("image_op_start", payload={
        "operation": "contact_sheet",
        "item_name": "colagem",
        "thumb": None,
        "item_idx": 1,
        "total_items": 1,
    })
    try:
        t0 = time()
        out_path = make_contact_sheet(
            sources, IMAGE_PROCESSED_DIR,
            cols=args.cs_cols,
            thumb_size=args.cs_thumb_size,
            gap=args.cs_gap,
            bg_color=args.cs_bg_color,
            out_fmt=args.out_fmt or "png",
            quality=args.out_quality,
        )
        thumb = _make_thumb(out_path)
        emit("image_op_done", payload={
            "output_path": str(out_path),
            "thumb": thumb,
            "elapsed": f"{time() - t0:.1f}s",
            "item_idx": 1,
            "total_items": 1,
            "src_size_bytes": 0,
            "out_size_bytes": out_path.stat().st_size,
        })
        emit("task_done", payload={"output_paths": [str(out_path)], "failed_count": 0})
        return True
    except Exception as exc:
        emit("task_error", payload={"message": str(exc)})
        return False


def start_image_pipeline(
    args: ImageArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    pipeline_running: list[bool],
) -> threading.Thread:
    """Inicia o pipeline de imagens em thread daemon.

    Args:
        args: Parâmetros do formulário.
        bus: EventBus compartilhado.
        cancel_event: threading.Event para cancelamento.
        pipeline_running: Lista [bool] compartilhada com app.py; resetada em finally.

    Returns:
        Thread iniciada.
    """
    def _run() -> None:
        try:
            run_image_pipeline(args, bus, cancel_event)
        finally:
            pipeline_running[0] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _item_label(item) -> str:
    """Rótulo legível para o item (nome do arquivo ou domínio da URL)."""
    if item.kind == "local":
        return Path(item.value).name
    try:
        from urllib.parse import urlparse
        parsed = urlparse(item.value)
        return parsed.netloc or item.value[:40]
    except Exception:
        return item.value[:40]


def _make_thumb(path: Path) -> bytes | None:
    """Gera miniatura para o visor; retorna None em caso de falha."""
    try:
        return thumbnail_bytes(path, max_px=600)
    except Exception:
        return None
