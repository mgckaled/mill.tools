"""Audio conversion and extraction via ffmpeg with structured progress."""

from __future__ import annotations

import shutil
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
    channels: int | None = None,
    sample_rate: int | None = None,
) -> Path:
    """Converte arquivo de áudio para outro formato via ffmpeg.

    Args:
        src: Arquivo de origem.
        out_dir: Diretório de saída (criado se necessário).
        fmt: Formato alvo ("mp3", "m4a", "wav", "ogg", "opus").
        bitrate: Bitrate em kbps ("320", "128", etc.). None = qualidade padrão.
        progress_cb: Chamado com float 0.0-1.0 durante a conversão.
        channels: Channel count for downmix (1 = mono). None preserves source.
        sample_rate: Target sample rate in Hz (e.g. 16000). None preserves source.

    Returns:
        Path do arquivo convertido.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}.{fmt}"

    same_path = out_path.resolve() == src.resolve()
    has_transform = (
        bool(channels) or bool(sample_rate) or bool(bitrate and bitrate != "best")
    )
    # No-op: same format, same location, nothing to transform → return as-is.
    if same_path and not has_transform:
        return src

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if bitrate and bitrate != "best":
        cmd += ["-b:a", f"{bitrate}k"]
    if channels:
        cmd += ["-ac", str(channels)]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    # ffmpeg cannot read and write the same path in place: when an in-place
    # transform is requested (e.g. mp3→mp3 mono), encode to a temp file and move.
    target = out_path
    tmp: Path | None = None
    if same_path:
        tmp = out_dir / f".tmp_encode_{sanitize_filename(src.stem)}.{fmt}"
        target = tmp
    cmd += ["-progress", "pipe:1", "-nostats", str(target)]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    run_ffmpeg(cmd, target, total_secs=total_secs, progress_cb=progress_cb)
    if tmp is not None:
        shutil.move(str(tmp), str(out_path))
    return out_path


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
