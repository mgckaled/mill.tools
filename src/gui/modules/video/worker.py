"""Worker do pipeline de vídeo rodando em thread separada."""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

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
from src.gui.events import LogEventHandler
from src.gui.modules.video import pipeline_log
from src.gui.modules.video.form_view import VideoArgs
from src.utils import VIDEO_PROCESSED_DIR, VIDEO_SOURCE_DIR

if TYPE_CHECKING:
    from src.gui.events import EventBus

_MODULE_ID = "video"

logger = logging.getLogger(__name__)


def run_video_pipeline(
    args: VideoArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
) -> bool:
    """Executa a fila de itens de vídeo sequencialmente.

    Args:
        args: Parâmetros do formulário de vídeo.
        bus: EventBus compartilhado da aplicação.
        cancel_event: threading.Event setado pelo botão Cancelar.

    Returns:
        True se todos os itens concluíram sem erro.
    """

    def emit(type: str, stage: str = "video", payload: dict | None = None) -> None:
        bus.emit(type, stage, payload or {}, module_id=_MODULE_ID)

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
                "total_items":  total,
                "item_name":    item_name,
            })

            # URL → forçar download; local → operação escolhida
            effective_op = "download" if item.kind == "url" else args.operation

            if effective_op == "download" and item.kind != "url":
                emit("task_error", payload={
                    "message": f"Operação 'download' requer URL, não arquivo local: {item_name}"
                })
                return False

            if effective_op != "download" and item.kind == "url":
                emit("task_error", payload={
                    "message": f"Arquivo local esperado para '{effective_op}': {item_name}"
                })
                return False

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
                        line = _fmt_ydl_progress(d)
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
                            emit("task_error", payload={
                                "message": (
                                    f"[!] Arquivo sem faixa de áudio: {item_name}\n"
                                    "[i] Arquivos .webm de stream de vídeo puro (ex.: f313.webm) "
                                    "não contêm áudio. Use o arquivo mesclado completo."
                                )
                            })
                            return False
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
                        emit("task_error", payload={"message": f"Operação desconhecida: {effective_op}"})
                        return False

            elapsed = time() - t0
            src_size = Path(item.value).stat().st_size if item.kind == "local" and Path(item.value).exists() else 0
            output_paths.append(str(out_path))

            emit("video_op_done", payload={
                "output_path":    str(out_path),
                "elapsed":        f"{elapsed:.1f}s",
                "item_idx":       idx,
                "total":          total,
                "src_size_bytes": src_size,
                "out_size_bytes": out_path.stat().st_size,
            })

            if cancel_event.is_set():
                emit("task_error", payload={"message": "Cancelado pelo usuário."})
                return False

        emit("task_done", payload={"output_paths": output_paths})
        return True

    except Exception as exc:
        msg = str(exc)
        if "WinError 32" in msg or "being used by another process" in msg:
            msg += (
                "\n[i] Arquivo bloqueado pelo antivírus durante o rename. "
                "Aguarde alguns segundos e tente novamente, ou adicione a pasta "
                "output/ às exclusões do Windows Defender."
            )
        emit("task_error", payload={"message": msg})
        return False

    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)


def start_video_pipeline(
    args: VideoArgs,
    bus: "EventBus",
    cancel_event: threading.Event,
    on_finish: "callable" = None,
) -> threading.Thread:
    """Inicia o pipeline de vídeo em thread daemon.

    Args:
        args: Parâmetros do formulário.
        bus: EventBus compartilhado.
        cancel_event: threading.Event para cancelamento.
        on_finish: Callback opcional chamado ao término.

    Returns:
        Thread iniciada.
    """
    def _run() -> None:
        run_video_pipeline(args, bus, cancel_event)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


_ANSI_ESC = re.compile(r'\x1b\[[0-9;]*m')


def _strip_ansi(s: str) -> str:
    return _ANSI_ESC.sub('', s).strip()


def _fmt_ydl_progress(d: dict) -> str:
    """Formata a linha de progresso do yt-dlp para exibição no log."""
    pct   = _strip_ansi(d.get("_percent_str") or "")
    total = _strip_ansi(d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str") or "")
    speed = _strip_ansi(d.get("_speed_str") or "")
    eta   = _strip_ansi(d.get("_eta_str") or "")
    parts: list[str] = []
    if pct:
        parts.append(pct)
    if total:
        parts.append(f"de {total}")
    if speed and speed not in ("Unknown B/s", "N/A"):
        parts.append(speed)
    if eta and eta not in ("Unknown", "N/A"):
        parts.append(f"ETA {eta}")
    return f"[d] {' | '.join(parts)}" if parts else ""


def _item_label(item) -> str:
    """Retorna label legível para o item (nome do arquivo ou domínio da URL)."""
    if item.kind == "local":
        return Path(item.value).name
    try:
        from urllib.parse import urlparse
        parsed = urlparse(item.value)
        return parsed.netloc or item.value[:40]
    except Exception:
        return item.value[:40]
