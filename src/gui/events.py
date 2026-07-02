"""EventBus, PipelineEvent e LogEventHandler para comunicação worker → UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import flet as ft


@dataclass
class PipelineEvent:
    """Evento emitido pelo worker e recebido pelas views via pubsub."""

    type: str
    stage: str  # "download" | "transcribe" | "format" | "analyze" | "prompt" | "audio"
    payload: dict = field(default_factory=dict)
    module_id: str = ""  # "transcription" | "audio" | "" (legado — passa por todos)


def _is_cancellation(message: str) -> bool:
    """True for the user-initiated cancellation messages emitted across workers.

    Cancelling is a user action, not a system failure — it must not clutter
    the Observatório's Logs tab with an expected event every time someone
    hits Esc.
    """
    return "cancel" in message.lower()


class EventBus:
    """Publica PipelineEvents de forma thread-safe via page.pubsub."""

    def __init__(self, page: ft.Page) -> None:
        self._page = page

    def emit(
        self,
        type: str,
        stage: str,
        payload: dict | None = None,
        module_id: str = "",
    ) -> None:
        payload = payload or {}
        self._page.pubsub.send_all(PipelineEvent(type, stage, payload, module_id))
        if type == "task_error":
            try:
                message = str(payload.get("message", ""))
                if not _is_cancellation(message):
                    from src.core.observatory.logs import log_error

                    log_error(module_id or "?", stage, message)
            except Exception:
                pass


class LogEventHandler(logging.Handler):
    """Captura logs do Python e os repassa ao EventBus como eventos 'log'."""

    # Mensagens que já são cobertas por eventos estruturais — evitar duplicação
    _SUPPRESSED_PREFIXES = (
        "[~] Transcribing",
        "[i] Detected language",
        "[*] Loading model",
        "[i] Fetching video metadata",
        "[»] Audio already exists",
        "[↓] Downloading audio",
        "[*] Formatting:",
        "[*] Format model:",
        "[*] Analyzing:",
        "[*] Model:",
        "[*] Building prompt-ready:",
        "[*] Prompt model:",
        "[~] Formatting chunk",
        "[~] Analyzing chunk",
        "[~] Analyzing single chunk",
        "[~] Condensing chunk",
        "[~] Merging",
        "[~] Translating",
        "[✓] Translation complete",
        "[✓] Formatted in place",
        "[✓] Analysis saved",
        "[✓] Prompt-ready saved",
    )

    def __init__(self, bus: EventBus, module_id: str = "") -> None:
        super().__init__()
        self._bus = bus
        self._module_id = module_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if any(msg.startswith(p) for p in self._SUPPRESSED_PREFIXES):
                return
            self._bus.emit(
                "log",
                "system",
                {"message": msg, "level": record.levelname},
                module_id=self._module_id,
            )
        except Exception:
            self.handleError(record)
