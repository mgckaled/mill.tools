"""Silence removal via ffmpeg silenceremove (leading, trailing and internal)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe
from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename


def build_filtergraph(
    threshold_db: float, min_silence_s: float, keep_silence_s: float
) -> str:
    """Build the silenceremove filtergraph string (pure, testable).

    Trims silence at the start, end and middle. A negative ``stop_periods``
    makes the filter restart after each non-silent run, which removes internal
    gaps as well (validated against the ffmpeg docs).
    """
    th = f"{threshold_db}dB"
    return (
        "silenceremove="
        f"start_periods=1:start_silence=0:start_threshold={th}:"
        f"stop_periods=-1:stop_duration={min_silence_s}:"
        f"stop_threshold={th}:stop_silence={keep_silence_s}"
    )


def remove_silence(
    src: Path,
    out_dir: Path,
    fmt: str,
    *,
    threshold_db: float = -40.0,
    min_silence_s: float = 0.5,
    keep_silence_s: float = 0.1,
    bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Remove leading, trailing and internal silence via ffmpeg silenceremove.

    Args:
        src: Source audio file (any ffmpeg-readable format).
        out_dir: Output directory (created if needed).
        fmt: Output container/format ("mp3", "wav", ...).
        threshold_db: Level below which audio counts as silence (dBFS).
        min_silence_s: Minimum silence duration to cut (seconds).
        keep_silence_s: Silence padding kept around kept segments (seconds).
        bitrate: Output bitrate in kbps (e.g. "192"); None keeps default.
        progress_cb: Called with float 0.0-1.0 during processing.

    Returns:
        Path of the silence-trimmed file (``<stem>_nosilence.<fmt>``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}_nosilence.{fmt}"

    af = build_filtergraph(threshold_db, min_silence_s, keep_silence_s)
    cmd = ["ffmpeg", "-y", "-i", str(src), "-af", af]
    if bitrate and bitrate != "best":
        cmd += ["-b:a", f"{bitrate}k"]
    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    return run_ffmpeg(cmd, out_path, total_secs=total_secs, progress_cb=progress_cb)
