"""Download de vídeo via yt-dlp com suporte a progresso."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Callable

import yt_dlp

logger = logging.getLogger(__name__)

_RESOLUTIONS = {"best": None, "2160": 2160, "1080": 1080, "720": 720, "480": 480, "360": 360}


def download_video(
    url: str,
    out_dir: Path,
    resolution: str = "1080",
    container: str = "mp4",
    embed_meta: bool = True,
    progress_hook: Callable[[dict], None] | None = None,
) -> Path:
    """Baixa vídeo de URL para out_dir.

    Args:
        url: URL do YouTube, etc.
        out_dir: Diretório de saída.
        resolution: Resolução máxima ("best", "2160", "1080", "720", "480", "360").
        container: Container de saída ("mp4", "mkv", "webm").
        embed_meta: Embutir metadados.
        progress_hook: Chamado com dict yt-dlp durante o download.

    Returns:
        Path do arquivo baixado.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    max_h = _RESOLUTIONS.get(resolution)
    if max_h:
        if container == "webm":
            fmt = (
                f"bestvideo[height<={max_h}][vcodec^=vp]+bestaudio[acodec^=opus]"
                f"/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]"
            )
        else:
            fmt = (
                f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={max_h}]+bestaudio/best[height<={max_h}]"
            )
    else:
        if container == "webm":
            fmt = "bestvideo[vcodec^=vp]+bestaudio[acodec^=opus]/bestvideo+bestaudio/best"
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    postprocessors: list[dict] = []
    if container == "mp4":
        postprocessors.append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})
    # WebM: merge_output_format já cuida do container com streams VP9+Opus nativos;
    # FFmpegVideoConvertor criaria .temp.webm → WinError 32 (rename bloqueado pelo SO)
    if embed_meta:
        postprocessors.append({"key": "FFmpegMetadata"})

    final_path: list[str] = []

    def _pp_hook(d: dict) -> None:
        if d.get("status") == "finished":
            fp = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
            if fp:
                final_path.append(fp)

    ydl_opts = {
        "format": fmt,
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "postprocessor_hooks": [_pp_hook],
        "progress_hooks": [progress_hook] if progress_hook else [],
        "merge_output_format": container,
        "nopart": True,
        "overwrites": True,
        # Redireciona .temp/.part para %TEMP% do sistema — geralmente excluído do antivírus
        "paths": {"temp": tempfile.gettempdir()},
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if final_path and Path(final_path[-1]).exists():
        return Path(final_path[-1])

    if info:
        downloads = info.get("requested_downloads", [])
        if downloads:
            fp = downloads[0].get("filepath", "")
            if fp and Path(fp).exists():
                return Path(fp)

    files = sorted(
        (f for f in out_dir.iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if files:
        return files[0]

    raise FileNotFoundError(f"Download concluído mas arquivo não encontrado em: {out_dir}")
