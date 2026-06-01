"""Worker do pipeline de áudio rodando em thread separada."""

from __future__ import annotations

import logging
import threading
from time import time
from typing import TYPE_CHECKING

from src.core.audio.converter import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, convert_audio, extract_audio
from src.core.audio.downloader import download_audio
from src.gui.events import LogEventHandler
from src.gui.modules.audio.form_view import AudioArgs
from src.utils import AUDIO_PROCESSED_DIR, AUDIO_SOURCE_DIR

if TYPE_CHECKING:

    from src.gui.events import EventBus

_MODULE_ID = "audio"

logger = logging.getLogger(__name__)


def run_audio_pipeline(
    args: AudioArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
) -> bool:
    """Executa a fila de itens de áudio sequencialmente.

    Emite eventos genéricos (progress_start, progress_update, queue_progress,
    task_done, task_error) além de eventos específicos de áudio (audio_op_start,
    audio_op_done) para o log.

    Args:
        args: Parâmetros do formulário de áudio.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event setado pelo botão Cancelar.

    Returns:
        True se todos os itens concluíram sem erro.
    """

    def emit(type: str, stage: str = "audio", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {}, module_id=_MODULE_ID)

    # Instala LogEventHandler para capturar logs do downloader/converter
    log_handler = LogEventHandler(bus, module_id=_MODULE_ID)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    for _noisy in ("httpx", "httpcore", "yt_dlp", "urllib3"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    output_paths: list[str] = []
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

            if item.kind == "url":
                operation = "download"
                emit("audio_op_start", payload={
                    "operation": operation,
                    "item_name": item_name,
                    "item_idx": idx,
                    "total": total,
                })

                def _ydl_hook(d: dict, _idx=idx, _total=total) -> None:
                    if d.get("status") == "downloading":
                        downloaded = d.get("downloaded_bytes", 0) or 0
                        total_b = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        if total_b > 0:
                            ratio = min(downloaded / total_b, 1.0)
                            emit("progress_update", payload={"current": ratio})

                out_path = download_audio(
                    url=item.value,
                    out_dir=AUDIO_SOURCE_DIR,
                    fmt=args.fmt,
                    quality=args.quality,
                    embed_meta=args.embed_meta,
                    progress_hook=_ydl_hook,
                )

            else:
                from pathlib import Path
                src = Path(item.value)
                suffix = src.suffix.lower()

                if suffix in VIDEO_EXTENSIONS:
                    operation = "extract"
                    emit("audio_op_start", payload={
                        "operation": operation,
                        "item_name": item_name,
                        "item_idx": idx,
                        "total": total,
                    })

                    def _progress_cb(ratio: float) -> None:
                        emit("progress_update", payload={"current": ratio})

                    out_path = extract_audio(
                        video=src,
                        out_dir=AUDIO_PROCESSED_DIR,
                        fmt=args.fmt if args.fmt != "best" else "mp3",
                        progress_cb=_progress_cb,
                    )

                elif suffix in AUDIO_EXTENSIONS:
                    operation = "convert"
                    emit("audio_op_start", payload={
                        "operation": operation,
                        "item_name": item_name,
                        "item_idx": idx,
                        "total": total,
                    })

                    def _progress_cb(ratio: float) -> None:  # type: ignore[no-redef]
                        emit("progress_update", payload={"current": ratio})

                    out_path = convert_audio(
                        src=src,
                        out_dir=AUDIO_PROCESSED_DIR,
                        fmt=args.fmt if args.fmt != "best" else "mp3",
                        bitrate=args.quality if args.quality != "best" else None,
                        progress_cb=_progress_cb,
                    )

                else:
                    emit("task_error", payload={
                        "message": f"Extensão não suportada: {suffix} ({item_name})"
                    })
                    return False

            elapsed = time() - t0
            output_paths.append(str(out_path))
            emit("audio_op_done", payload={
                "output_path": str(out_path),
                "elapsed": f"{elapsed:.1f}s",
                "item_idx": idx,
                "total": total,
            })

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado pelo usuário."})
                return False

        emit("task_done", payload={"output_paths": output_paths})
        return True

    except Exception as exc:
        emit("task_error", payload={"message": str(exc)})
        return False

    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)


def start_audio_pipeline(
    args: AudioArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    on_finish: "callable" = None,
) -> threading.Thread:
    """Inicia o pipeline de áudio em thread daemon.

    Args:
        args: Parâmetros do formulário.
        bus: EventBus compartilhado.
        cancel_event: threading.Event para cancelamento.
        on_finish: Callback opcional chamado ao término (sucesso ou erro).

    Returns:
        Thread iniciada.
    """
    def _run() -> None:
        run_audio_pipeline(args, bus, cancel_event)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _item_label(item) -> str:
    """Retorna label legível para o item (nome do arquivo ou domínio da URL)."""
    from pathlib import Path
    if item.kind == "local":
        return Path(item.value).name
    # Para URL, extrai o domínio como hint
    try:
        from urllib.parse import urlparse
        parsed = urlparse(item.value)
        return parsed.netloc or item.value[:40]
    except Exception:
        return item.value[:40]
