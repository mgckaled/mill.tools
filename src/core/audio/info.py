"""Inspeção de arquivos de áudio/vídeo via ffprobe."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_duration_ffprobe(src: Path) -> float | None:
    """Retorna duração em segundos. None se ffprobe falhar ou stream sem metadata."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(src),
            ],
            capture_output=True,
            timeout=10,
        )
        return float(result.stdout.decode('utf-8', errors='replace').strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
