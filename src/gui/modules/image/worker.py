"""Worker do pipeline de imagens rodando em thread separada."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from src.core.image.converter import convert_image
from src.core.image.downloader import download_image
from src.core.image.info import thumbnail_bytes
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
    Erro por item não trava a fila — pipeline continua.

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

    output_paths: list[str] = []
    failed_count = 0
    total = len(args.items)

    try:
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
                # ── Download (URL) ────────────────────────────────────────────
                if item.kind == "url":
                    emit("image_op_start", payload={
                        "operation": "download",
                        "item_name": item_name,
                    })
                    src = download_image(item.value, IMAGE_SOURCE_DIR)
                    input_thumb = _make_thumb(src)
                    emit("image_op_start", payload={
                        "operation": "convert",
                        "item_name": src.name,
                        "thumb": input_thumb,
                    })
                else:
                    src = Path(item.value)
                    input_thumb = _make_thumb(src)
                    emit("image_op_start", payload={
                        "operation": "convert",
                        "item_name": item_name,
                        "thumb": input_thumb,
                    })

                # ── Conversão ─────────────────────────────────────────────────
                out_path = convert_image(src, IMAGE_PROCESSED_DIR, args.fmt, args.quality)
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
                continue  # fila continua

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
