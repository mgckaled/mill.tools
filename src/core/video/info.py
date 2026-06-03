"""Inspeção de arquivos de vídeo via ffprobe."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    duration: float | None
    width: int | None
    height: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    size_bytes: int


def get_video_info(src: Path) -> VideoInfo:
    """Retorna metadados via ffprobe (streams de vídeo e áudio)."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(src),
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), {})

        fps = None
        r_fps = v.get("r_frame_rate", "")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            fps = float(num) / float(den) if float(den) else None

        return VideoInfo(
            duration=float(fmt.get("duration", 0)) or None,
            width=v.get("width"),
            height=v.get("height"),
            fps=fps,
            vcodec=v.get("codec_name"),
            acodec=a.get("codec_name"),
            size_bytes=int(fmt.get("size", 0)),
        )
    except Exception:
        return VideoInfo(None, None, None, None, None, None, 0)
