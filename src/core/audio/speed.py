"""Playback speed change without pitch shift via ffmpeg atempo."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe
from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename

_MIN_FACTOR = 0.5
_MAX_FACTOR = 4.0
_ATEMPO_MIN = 0.5
_ATEMPO_MAX = 2.0


def _atempo_chain(factor: float) -> str:
    """Build an atempo filter chain honoring the per-stage 0.5-2.0 limit.

    A single atempo stage only accepts 0.5-2.0; out-of-range factors are split
    into a product of in-range stages (e.g. 3.0 -> "atempo=2.0,atempo=1.5").

    Raises:
        ValueError: factor outside the supported [0.5, 4.0] range.
    """
    if not (_MIN_FACTOR <= factor <= _MAX_FACTOR):
        raise ValueError(
            f"speed factor {factor} out of range [{_MIN_FACTOR}, {_MAX_FACTOR}]"
        )

    stages: list[float] = []
    remaining = factor
    # Peel off maximal in-range stages while the remainder stays above the cap.
    while remaining > _ATEMPO_MAX:
        stages.append(_ATEMPO_MAX)
        remaining /= _ATEMPO_MAX
    while remaining < _ATEMPO_MIN:
        stages.append(_ATEMPO_MIN)
        remaining /= _ATEMPO_MIN
    stages.append(remaining)

    return ",".join(f"atempo={s:g}" for s in stages)


def change_speed(
    src: Path,
    out_dir: Path,
    fmt: str,
    *,
    factor: float,
    bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Change playback speed without altering pitch via ffmpeg atempo.

    Args:
        src: Source audio file (any ffmpeg-readable format).
        out_dir: Output directory (created if needed).
        fmt: Output container/format ("mp3", "wav", ...).
        factor: Speed multiplier (1.25 = 25% faster). Range [0.5, 4.0].
        bitrate: Output bitrate in kbps (e.g. "192"); None keeps default.
        progress_cb: Called with float 0.0-1.0 during processing.

    Returns:
        Path of the retimed file (``<stem>_<factor>x.<fmt>``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{factor:g}".replace(".", "_")
    out_path = out_dir / f"{sanitize_filename(src.stem)}_{tag}x.{fmt}"

    af = _atempo_chain(factor)
    cmd = ["ffmpeg", "-y", "-i", str(src), "-af", af]
    if bitrate and bitrate != "best":
        cmd += ["-b:a", f"{bitrate}k"]
    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    # Output duration shrinks by `factor`; scale the progress denominator so the
    # reported ratio still tracks 0.0-1.0 against the output timeline.
    scaled = total_secs / factor if total_secs else None
    return run_ffmpeg(cmd, out_path, total_secs=scaled, progress_cb=progress_cb)
