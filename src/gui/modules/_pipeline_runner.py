"""
_pipeline_runner.py: Shared scaffolding for audio/video/image pipeline workers.
"""

from __future__ import annotations

import contextlib
import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from src.gui.events import EventBus

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*m")
_NOISY_LOGGERS = ("httpx", "httpcore", "yt_dlp", "urllib3")


def strip_ansi(s: str) -> str:
    """Strip ANSI escape codes and surrounding whitespace."""
    return _ANSI_ESC.sub("", s).strip()


def fmt_ydl_progress(d: dict) -> str:
    """Format a yt-dlp progress dict as a mutable log line (pct | de total | speed | ETA)."""
    pct = strip_ansi(d.get("_percent_str") or "")
    total = strip_ansi(
        d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str") or ""
    )
    speed = strip_ansi(d.get("_speed_str") or "")
    eta = strip_ansi(d.get("_eta_str") or "")
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


def item_label(item) -> str:
    """Return a human-readable label: filename for local items, netloc for URLs."""
    if item.kind == "local":
        return Path(item.value).name
    try:
        parsed = urlparse(item.value)
        return parsed.netloc or item.value[:40]
    except Exception:
        return item.value[:40]


def make_emitter(bus: "EventBus", module_id: str, default_stage: str) -> Callable:
    """Return an emit helper bound to a specific bus, module and default stage."""

    def emit(type: str, stage: str | None = None, payload: dict | None = None) -> None:
        bus.emit(type, stage or default_stage, payload or {}, module_id=module_id)

    return emit


class _LogScope:
    """Context manager: install/remove a LogEventHandler for the pipeline duration.

    Always removes the handler in __exit__, even on exception, preventing
    handler accumulation across re-entrant pipeline runs.
    """

    def __init__(self, bus: "EventBus", module_id: str) -> None:
        from src.gui.events import LogEventHandler

        self._handler = LogEventHandler(bus, module_id=module_id)
        self._handler.setLevel(logging.INFO)
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._root = logging.getLogger()
        self._original_level = self._root.level

    def __enter__(self) -> "_LogScope":
        self._root.addHandler(self._handler)
        self._root.setLevel(logging.INFO)
        for noisy in _NOISY_LOGGERS:
            logging.getLogger(noisy).setLevel(logging.WARNING)
        return self

    def __exit__(self, *_exc) -> None:
        self._root.removeHandler(self._handler)
        self._root.setLevel(self._original_level)


def run_queue_pipeline(
    *,
    items: list,
    bus: "EventBus",
    module_id: str,
    default_stage: str,
    cancel_event: threading.Event,
    process_item: Callable,
    stop_on_error: bool = True,
    error_event: str = "task_error",
    install_log_handler: bool = True,
) -> bool:
    """Generic sequential queue runner for module pipelines.

    For each item: checks cancel_event, emits queue_progress, calls
    process_item and collects the returned output_path string. Emits
    progress_start at the start and task_done at the end.

    process_item(emit, item, idx, total, cancel_event) -> str (output_path)
        Receives the bound emit helper; raises on item error.

    When stop_on_error=False, per-item exceptions are caught and error_event
    is emitted; the loop continues. task_done includes failed_count. Returns
    True if ≥1 item succeeded.

    When stop_on_error=True (default), the first exception aborts the pipeline
    and emits task_error. Returns False.

    install_log_handler=False skips the internal _LogScope — use when the
    caller already manages a LogScope (image worker short-circuit paths, CLI).
    """
    emit = make_emitter(bus, module_id, default_stage)
    total = len(items)
    output_paths: list[str] = []
    failed_count = 0

    _scope: contextlib.AbstractContextManager = (
        _LogScope(bus, module_id) if install_log_handler else contextlib.nullcontext()
    )

    with _scope:
        try:
            emit("progress_start")

            for idx, item in enumerate(items, start=1):
                if cancel_event.is_set():
                    emit("task_error", payload={"message": "Cancelado pelo usuário."})
                    return False

                emit(
                    "queue_progress",
                    payload={
                        "current_item": idx,
                        "total_items": total,
                        "item_name": item_label(item),
                    },
                )

                if stop_on_error:
                    out = process_item(emit, item, idx, total, cancel_event)
                    output_paths.append(out)
                else:
                    try:
                        out = process_item(emit, item, idx, total, cancel_event)
                        output_paths.append(out)
                    except Exception as exc:
                        failed_count += 1
                        logging.getLogger(__name__).warning(
                            "[!] Error on '%s': %s", item_label(item), exc
                        )
                        emit(
                            error_event,
                            payload={
                                "item_name": item_label(item),
                                "message": str(exc),
                            },
                        )
                        continue

                if cancel_event.is_set():
                    emit("task_error", payload={"message": "Cancelado pelo usuário."})
                    return False

            done_payload: dict = {"output_paths": output_paths}
            if not stop_on_error:
                done_payload["failed_count"] = failed_count
            emit("task_done", payload=done_payload)

            return True if stop_on_error else len(output_paths) > 0

        except Exception as exc:
            emit("task_error", payload={"message": str(exc)})
            return False


def start_pipeline(
    run_fn: Callable,
    args,
    bus: "EventBus",
    cancel_event: threading.Event,
    on_finish: Callable | None = None,
) -> threading.Thread:
    """Launch run_fn(args, bus, cancel_event) in a daemon thread.

    Calls on_finish() after completion regardless of success or error.
    """

    def _run() -> None:
        run_fn(args, bus, cancel_event)
        if on_finish:
            on_finish()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
