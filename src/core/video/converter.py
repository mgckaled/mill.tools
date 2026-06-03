"""Operações de vídeo via ffmpeg: convert, trim, compress, resize, thumbnail, extract_audio."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.core.video.info import get_video_info

# Codecs disponíveis — sem NVENC (decisão definitiva, CPU-only)
VCODEC_MAP = {
    "copy": ["-c:v", "copy"],
    "h264": ["-c:v", "libx264", "-preset", "medium"],
    "h265": ["-c:v", "libx265", "-preset", "medium"],
    "vp9":  ["-c:v", "libvpx-vp9"],
}
CONTAINER_EXT = {"mp4": "mp4", "mkv": "mkv", "webm": "webm", "avi": "avi"}


def _run_ffmpeg(
    cmd: list[str],
    src: Path,
    out_path: Path,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Executa ffmpeg com progresso estruturado via -progress pipe:1."""
    info = get_video_info(src)
    total_secs = info.duration if progress_cb else None

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    stderr_lines: list[str] = []

    def _drain() -> None:
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())
            if len(stderr_lines) > 100:
                del stderr_lines[:-100]

    threading.Thread(target=_drain, daemon=True).start()

    for line in proc.stdout:
        if line.strip().startswith("out_time_us=") and progress_cb and total_secs:
            try:
                ratio = min(int(line.strip().split("=", 1)[1]) / 1_000_000 / total_secs, 1.0)
                progress_cb(ratio)
            except (ValueError, IndexError):
                pass

    proc.wait()
    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(sem detalhes)"
        raise RuntimeError(f"ffmpeg retornou {proc.returncode}: {tail}")

    if not out_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {out_path}")

    return out_path


def convert_video(
    src: Path,
    out_dir: Path,
    container: str = "mp4",
    vcodec: str = "copy",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Converte container e/ou codec. 'copy' = sem reencoding (rápido)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = CONTAINER_EXT.get(container, "mp4")
    out_path = out_dir / f"{src.stem}_converted.{ext}"
    codec_flags = VCODEC_MAP.get(vcodec, ["-c:v", "copy"])
    cmd = (
        ["ffmpeg", "-y", "-i", str(src)]
        + codec_flags
        + ["-c:a", "copy", "-progress", "pipe:1", "-nostats", str(out_path)]
    )
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def trim_video(
    src: Path,
    out_dir: Path,
    start: str = "",
    end: str = "",
    reenc: bool = False,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Recorta vídeo entre start e end (formato HH:MM:SS ou SS).

    reenc=False usa -c copy (rápido, corte no keyframe mais próximo).
    reenc=True usa libx264 (corte frame-preciso, mais lento).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_trimmed{src.suffix}"

    cmd = ["ffmpeg", "-y"]
    if start:
        cmd += ["-ss", start]
    cmd += ["-i", str(src)]
    if end:
        cmd += ["-to", end]

    if reenc:
        cmd += ["-c:v", "libx264", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]

    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def compress_video(
    src: Path,
    out_dir: Path,
    crf: int = 23,
    preset: str = "medium",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Reencoda com H.264/CRF para reduzir tamanho.

    crf: 18 (alta qualidade) → 28 (alta compressão). Padrão 23.
    preset: ultrafast, fast, medium, slow.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_compressed.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
        "-c:a", "aac", "-b:a", "128k",
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def resize_video(
    src: Path,
    out_dir: Path,
    width: int = 0,
    height: int = 0,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Redimensiona vídeo preservando aspect ratio.

    Passar apenas width ou height: o outro eixo usa -2 (múltiplo de 2 compatível).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_resized.mp4"
    w = width if width else -2
    h = height if height else -2
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={w}:{h}",
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "copy",
        "-progress", "pipe:1", "-nostats",
        str(out_path),
    ]
    return _run_ffmpeg(cmd, src, out_path, progress_cb)


def extract_audio_from_video(
    src: Path,
    out_dir: Path,
    audio_fmt: str = "mp3",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Extrai faixa de áudio do vídeo (bridge para src/core/audio/converter.py)."""
    from src.core.audio.converter import extract_audio
    return extract_audio(src, out_dir, fmt=audio_fmt, progress_cb=progress_cb)


def make_thumbnail(
    src: Path,
    out_dir: Path,
    time: str = "00:00:01",
    fmt: str = "jpg",
) -> Path:
    """Extrai um frame do vídeo como imagem."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src.stem}_thumb.{fmt}"
    cmd = [
        "ffmpeg", "-y",
        "-ss", time,
        "-i", str(src),
        "-vframes", "1",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"Thumbnail falhou para {src.name}")
    return out_path
