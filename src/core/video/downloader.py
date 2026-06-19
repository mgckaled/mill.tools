"""Download de vídeo via yt-dlp com suporte a progresso."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Callable

import yt_dlp

from src.utils import sanitize_filename

logger = logging.getLogger(__name__)

_RESOLUTIONS = {
    "best": None,
    "2160": 2160,
    "1080": 1080,
    "720": 720,
    "480": 480,
    "360": 360,
}


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
                f"/bestvideo[height<={max_h}]+bestaudio"
                f"/best[height<={max_h}][ext=mp4]/best[height<={max_h}]"
            )
    else:
        if container == "webm":
            fmt = (
                "bestvideo[vcodec^=vp]+bestaudio[acodec^=opus]/bestvideo+bestaudio/best"
            )
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"

    # Não usar FFmpegVideoConvertor: cria .temp.<ext> no diretório de saída que o
    # Windows Defender bloqueia durante o rename → WinError 32. merge_output_format
    # já garante o container correto para downloads com streams separados.
    postprocessors: list[dict] = []
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
        # Download only the single video, never the playlist. A watch URL with a
        # "&list=" param (e.g. a YouTube "RD..." radio mix, which is endless)
        # would otherwise fetch every entry into out_dir.
        "noplaylist": True,
        # Redireciona .temp/.part para %TEMP% do sistema — geralmente excluído do antivírus
        "paths": {"temp": tempfile.gettempdir()},
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    out_path: Path | None = None

    if final_path and Path(final_path[-1]).exists():
        out_path = Path(final_path[-1])
    elif info:
        downloads = info.get("requested_downloads", [])
        if downloads:
            fp = downloads[0].get("filepath", "")
            if fp and Path(fp).exists():
                out_path = Path(fp)

    if out_path is None:
        files = sorted(
            (f for f in out_dir.iterdir() if f.is_file()),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if files:
            out_path = files[0]

    if out_path is None:
        raise FileNotFoundError(
            f"Download concluído mas arquivo não encontrado em: {out_dir}"
        )

    safe_stem = sanitize_filename(out_path.stem)
    if safe_stem and safe_stem != out_path.stem:
        new_path = out_path.with_stem(safe_stem)
        try:
            out_path.rename(new_path)
            out_path = new_path
        except OSError:
            pass  # mantém nome original se o rename falhar

    return out_path
