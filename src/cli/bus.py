"""
bus.py: CLI adapter that maps PipelineEvents to tqdm + logging output.

Provides CLIEventBus as a drop-in replacement for the GUI EventBus when
running pipeline workers from the command line.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING

from tqdm import tqdm

if TYPE_CHECKING:
    pass

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*m")

logger = logging.getLogger(__name__)


def _strip(s: str) -> str:
    return _ANSI_ESC.sub("", s).strip()


class CLIEventBus:
    """Adapts PipelineEvents to tqdm progress bar and logging output.

    Workers call bus.emit(type, stage, payload, module_id) exactly as they do
    with the GUI EventBus. The CLI bus translates each event type to the
    appropriate terminal output.

    A single tqdm bar is created on progress_start and closed on task_done /
    task_error. mutable=True log lines overwrite the previous line via tqdm.write.
    """

    def __init__(self) -> None:
        self._bar: tqdm | None = None
        self._last_mutable: bool = False

    # ── Public interface (mirrors gui/events.py EventBus.emit) ───────────────

    def emit(
        self,
        type: str,
        stage: str = "",
        payload: dict | None = None,
        module_id: str = "",
    ) -> None:
        """Dispatch a pipeline event to the terminal."""
        p = payload or {}
        handler = self._HANDLERS.get(type)
        if handler:
            handler(self, p)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_progress_start(self, p: dict) -> None:
        if self._bar is not None:
            self._bar.close()
        self._bar = tqdm(
            total=100,
            unit="%",
            bar_format="{l_bar}{bar}| {n:.0f}%{postfix}",
            leave=True,
        )
        self._last_mutable = False

    def _on_progress_update(self, p: dict) -> None:
        if self._bar is not None:
            ratio = float(p.get("current", 0))
            self._bar.n = round(ratio * 100)
            self._bar.refresh()

    def _on_queue_progress(self, p: dict) -> None:
        cur = p.get("current_item", "?")
        tot = p.get("total_items", "?")
        name = _strip(str(p.get("item_name", "")))
        tqdm.write(f"[{cur}/{tot}] {name}")
        self._last_mutable = False

    def _on_log(self, p: dict) -> None:
        msg = _strip(str(p.get("message", "")))
        if not msg:
            return
        mutable = bool(p.get("mutable", False))
        if mutable:
            # Overwrite the current line
            sys.stdout.write(f"\r{msg}")
            sys.stdout.flush()
        else:
            if self._last_mutable:
                sys.stdout.write("\n")
                sys.stdout.flush()
            tqdm.write(msg)
        self._last_mutable = mutable

    def _on_task_done(self, p: dict) -> None:
        if self._last_mutable:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_mutable = False
        if self._bar is not None:
            self._bar.n = 100
            self._bar.refresh()
            self._bar.close()
            self._bar = None
        paths = p.get("output_paths") or p.get("output_path")
        if isinstance(paths, list):
            for path in paths:
                tqdm.write(f"[✓] {path}")
        elif paths:
            tqdm.write(f"[✓] {paths}")

    def _on_task_error(self, p: dict) -> None:
        if self._last_mutable:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_mutable = False
        if self._bar is not None:
            self._bar.close()
            self._bar = None
        msg = _strip(str(p.get("message", "Unknown error")))
        logger.error("[✗] %s", msg)

    def _on_op_start(self, p: dict) -> None:
        op = p.get("operation", "")
        name = _strip(str(p.get("item_name", "")))
        idx = p.get("item_idx", "")
        tot = p.get("total", p.get("total_items", ""))
        tqdm.write(f"  → {op}: {name}" + (f" ({idx}/{tot})" if idx else ""))
        self._last_mutable = False

    def _on_op_done(self, p: dict) -> None:
        elapsed = p.get("elapsed", "")
        src = p.get("src_size_bytes", 0)
        out = p.get("out_size_bytes", 0)
        parts = [f"done in {elapsed}"]
        if src and out:
            parts.append(f"{src // 1024} KB → {out // 1024} KB")
        tqdm.write(f"  ✓ {' | '.join(parts)}")
        self._last_mutable = False

    # Map event types to handler methods
    _HANDLERS: dict = {
        "progress_start": _on_progress_start,
        "progress_update": _on_progress_update,
        "queue_progress": _on_queue_progress,
        "log": _on_log,
        "task_done": _on_task_done,
        "task_error": _on_task_error,
        # Module-specific op events
        "audio_op_start": _on_op_start,
        "audio_op_done": _on_op_done,
        "video_op_start": _on_op_start,
        "video_op_done": _on_op_done,
        "image_op_start": _on_op_start,
        "image_op_done": _on_op_done,
        "video_op_error": _on_task_error,
        "image_op_error": _on_task_error,
    }
