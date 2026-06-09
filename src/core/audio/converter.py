"""Audio conversion and extraction via ffmpeg with structured progress."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe
from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename

# Video extensions that trigger extraction (instead of conversion)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
# Audio extensions accepted for conversion
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}


def convert_audio(
    src: Path,
    out_dir: Path,
    fmt: str,
    bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Converte arquivo de áudio para outro formato via ffmpeg.

    Args:
        src: Arquivo de origem.
        out_dir: Diretório de saída (criado se necessário).
        fmt: Formato alvo ("mp3", "m4a", "wav", "ogg", "opus").
        bitrate: Bitrate em kbps ("320", "128", etc.). None = qualidade padrão.
        progress_cb: Chamado com float 0.0-1.0 durante a conversão.

    Returns:
        Path do arquivo convertido.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}.{fmt}"

    # Evita "same as Input #0" quando src já está em out_dir com mesmo formato
    if out_path.resolve() == src.resolve():
        return src

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if bitrate and bitrate != "best":
        cmd += ["-b:a", f"{bitrate}k"]
    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    return run_ffmpeg(cmd, out_path, total_secs=total_secs, progress_cb=progress_cb)


def extract_audio(
    video: Path,
    out_dir: Path,
    fmt: str = "mp3",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Extrai faixa de áudio de vídeo local via ffmpeg.

    Args:
        video: Arquivo de vídeo de origem.
        out_dir: Diretório de saída (criado se necessário).
        fmt: Formato do áudio extraído.
        progress_cb: Chamado com float 0.0-1.0 durante a extração.

    Returns:
        Path do arquivo de áudio extraído.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(video.stem)}_audio.{fmt}"

    cmd = ["ffmpeg", "-y", "-i", str(video), "-vn"]  # -vn: drop video stream
    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]

    total_secs = get_duration_ffprobe(video) if progress_cb else None
    return run_ffmpeg(cmd, out_path, total_secs=total_secs, progress_cb=progress_cb)
