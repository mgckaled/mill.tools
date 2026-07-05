"""Loudness normalization via ffmpeg loudnorm (EBU R128 / ITU-R BS.1770-4)."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe, get_sample_rate_ffprobe
from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)

_TARGET_TP = -1.0  # Max True Peak (dBFS)
_TARGET_LRA = 11.0  # Target Loudness Range
_MEASURE_TIMEOUT_S = 1800  # 30 min — generous enough to not police slowness


def normalize_lufs(
    src: Path,
    out_dir: Path,
    target_lufs: float = -14.0,
    progress_cb: Callable[[float], None] | None = None,
) -> tuple[Path, dict | None]:
    """Normalize integrated loudness to target_lufs (EBU R128, two passes).

    Args:
        src: Input file (any ffmpeg-readable format).
        out_dir: Output directory.
        target_lufs: Target in LUFS (e.g. -14.0 streaming, -23.0 broadcast).
        progress_cb: Called with float 0.0-1.0 during the second pass.

    Returns:
        Tuple (out_path, stats_dict | None).
        stats_dict holds the measured values (input_i, input_tp, input_lra…).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}_normalized{src.suffix}"

    # Pass 1: measurement
    measure_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        (
            f"loudnorm=I={target_lufs}:TP={_TARGET_TP}"
            f":LRA={_TARGET_LRA}:print_format=json"
        ),
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(measure_cmd, capture_output=True, timeout=_MEASURE_TIMEOUT_S)
    stats = (
        _parse_loudnorm_json(r.stderr.decode("utf-8", errors="replace"))
        if r.returncode == 0
        else None
    )

    # Pass 2: apply
    source_sample_rate: int | None = None
    if stats:
        af = (
            f"loudnorm=I={target_lufs}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
            f":measured_I={stats['input_i']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            f":linear=true"
        )
    else:
        reason = (
            f"measurement pass exited with code {r.returncode}"
            if r.returncode != 0
            else "measurement pass produced no parsable loudnorm stats"
        )
        logger.warning(
            "%s for %s — falling back to dynamic loudnorm mode, which upsamples "
            "the output to 192 kHz (per ffmpeg docs); forcing source sample rate "
            "to limit the side effect",
            reason,
            src,
        )
        af = f"loudnorm=I={target_lufs}:TP={_TARGET_TP}:LRA={_TARGET_LRA}"
        source_sample_rate = get_sample_rate_ffprobe(src)

    apply_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        af,
    ]
    if source_sample_rate:
        apply_cmd += ["-ar", str(source_sample_rate)]
    apply_cmd += [
        "-progress",
        "pipe:1",
        "-nostats",
        str(out_path),
    ]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    run_ffmpeg(apply_cmd, out_path, total_secs=total_secs, progress_cb=progress_cb)

    return out_path, stats


_REQUIRED_STATS_KEYS = {
    "input_i",
    "input_tp",
    "input_lra",
    "input_thresh",
    "target_offset",
}


def _parse_loudnorm_json(stderr: str) -> dict | None:
    """Extract the loudnorm stats JSON block from ffmpeg's stderr.

    Returns None if the block is missing, malformed, or lacks any of the keys
    the second pass reads directly (a partial block would otherwise surface as
    a bare KeyError deep in the af= string build).
    """
    lines = stderr.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "{"), None)
    if start is None:
        return None
    end = next(
        (i for i, ln in enumerate(lines[start:], start) if ln.strip() == "}"), None
    )
    if end is None:
        return None
    try:
        data = json.loads("\n".join(lines[start : end + 1]))
    except json.JSONDecodeError:
        return None
    if not _REQUIRED_STATS_KEYS.issubset(data.keys()):
        return None
    return data
