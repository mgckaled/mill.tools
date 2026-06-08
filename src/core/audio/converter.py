"""Conversão e extração de áudio via ffmpeg com progresso estruturado."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable

from src.core.audio.info import get_duration_ffprobe
from src.utils import sanitize_filename

# Extensões de vídeo que disparam extração (em vez de conversão)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
# Extensões de áudio aceitas para conversão
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}


def _run_ffmpeg_with_progress(
    cmd: list[str],
    src: Path,
    out_path: Path,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Executa ffmpeg com progresso estruturado via -progress pipe:1.

    Lê out_time_us do stdout para calcular razão current/total.
    Cai para barra indeterminada (sem chamar progress_cb) se a duração for desconhecida.
    """
    total_secs = get_duration_ffprobe(src) if progress_cb else None

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stderr_lines: list[str] = []

    def _drain_stderr() -> None:
        for raw in process.stderr:
            stderr_lines.append(raw.decode('utf-8', errors='replace').rstrip())
            if len(stderr_lines) > 100:
                del stderr_lines[:-100]

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # Lê progresso estruturado de stdout (out_time_us=, progress=end, …)
    for raw in process.stdout:
        line = raw.decode('utf-8', errors='replace').strip()
        if line.startswith("out_time_us=") and progress_cb and total_secs:
            try:
                current_us = int(line.split("=", 1)[1])
                current_secs = current_us / 1_000_000
                ratio = min(current_secs / total_secs, 1.0)
                progress_cb(ratio)
            except (ValueError, IndexError):
                pass

    process.wait()
    stderr_thread.join(timeout=2)

    if process.returncode != 0:
        last_err = "\n".join(stderr_lines[-10:]) if stderr_lines else "(sem detalhes)"
        raise RuntimeError(f"ffmpeg retornou {process.returncode}: {last_err}")

    if not out_path.exists():
        raise FileNotFoundError(f"ffmpeg concluiu mas arquivo não encontrado: {out_path}")

    return out_path


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

    return _run_ffmpeg_with_progress(cmd, src, out_path, progress_cb)


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

    cmd = ["ffmpeg", "-y", "-i", str(video), "-vn"]  # -vn: sem stream de vídeo
    cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]

    return _run_ffmpeg_with_progress(cmd, video, out_path, progress_cb)
