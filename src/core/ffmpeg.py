"""Shared ffmpeg runner used by audio and video pipelines."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable


def run_ffmpeg(
    cmd: list[str],
    out_path: Path,
    *,
    total_secs: float | None = None,
    progress_cb: Callable[[float], None] | None = None,
    stderr_tail: int = 100,
) -> Path:
    """Run ffmpeg in binary mode with structured progress via -progress pipe:1.

    Reads out_time_us= from stdout and calls progress_cb(ratio 0.0–1.0) if
    total_secs is provided. Stderr is drained in a background thread (capped at
    stderr_tail lines) so it never blocks the stdout reader.

    Raises:
        RuntimeError: ffmpeg exited with non-zero returncode; message includes
            the last 10 lines of stderr.
        FileNotFoundError: ffmpeg succeeded (returncode 0) but out_path is absent.

    Returns:
        out_path on success.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr_lines: list[str] = []

    def _drain() -> None:
        for raw in proc.stderr:
            stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())
            if len(stderr_lines) > stderr_tail:
                del stderr_lines[:-stderr_tail]

    stderr_thread = threading.Thread(target=_drain, daemon=True)
    stderr_thread.start()

    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").strip()
        if line.startswith("out_time_us=") and progress_cb and total_secs:
            try:
                ratio = min(int(line.split("=", 1)[1]) / 1_000_000 / total_secs, 1.0)
                progress_cb(ratio)
            except (ValueError, IndexError):
                pass

    proc.wait()
    stderr_thread.join(timeout=2)

    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(no details)"
        raise RuntimeError(f"ffmpeg returned {proc.returncode}: {tail}")

    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg finished but output not found: {out_path}")

    return out_path
