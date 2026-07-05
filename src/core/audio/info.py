"""Audio/video file inspection via ffprobe."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_duration_ffprobe(src: Path) -> float | None:
    """Return duration in seconds. None if ffprobe fails or the stream lacks metadata."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            timeout=10,
        )
        return float(result.stdout.decode("utf-8", errors="replace").strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_audio_codec_ffprobe(src: Path) -> str | None:
    """Return the codec_name of the first audio stream (e.g. "aac", "mp3", "opus").

    None if ffprobe fails or the stream lacks metadata.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            timeout=10,
        )
        codec = result.stdout.decode("utf-8", errors="replace").strip()
        return codec or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_sample_rate_ffprobe(src: Path) -> int | None:
    """Return the sample rate (Hz) of the first audio stream.

    None if ffprobe fails or the stream lacks metadata.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            timeout=10,
        )
        return int(result.stdout.decode("utf-8", errors="replace").strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
