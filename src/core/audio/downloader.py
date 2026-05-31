"""Download de áudio via yt-dlp com suporte a progresso e metadados."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yt_dlp

logger = logging.getLogger(__name__)

# Formatos que não suportam thumbnail embutida de forma confiável
_NO_COVER_FMTS = {"ogg", "opus"}


def download_audio(
    url: str,
    out_dir: Path,
    fmt: str = "mp3",
    quality: str = "best",
    embed_meta: bool = True,
    progress_hook: Callable[[dict], None] | None = None,
) -> Path:
    """Baixa áudio de URL para out_dir.

    Args:
        url: URL do YouTube, SoundCloud, etc.
        out_dir: Diretório de saída (criado se necessário).
        fmt: Formato de saída. "best" preserva o codec original sem reencode.
        quality: Bitrate em kbps ("best", "320", "256", "128", "96", "64").
        embed_meta: Embutir metadados e capa (se o formato suportar).
        progress_hook: Chamado com dict yt-dlp (status, downloaded_bytes, total_bytes…).

    Returns:
        Path do arquivo gerado.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    postprocessors: list[dict] = []

    if fmt != "best":
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            "preferredquality": quality if quality != "best" else "0",
        })

    supports_cover = embed_meta and fmt not in _NO_COVER_FMTS

    if embed_meta:
        postprocessors.append({"key": "FFmpegMetadata"})

    if supports_cover:
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    elif embed_meta:
        logger.info("[i] %s: thumbnail não suportada — só metadados embutidos", fmt)

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "progress_hooks": [progress_hook] if progress_hook else [],
        "writethumbnail": supports_cover,
        "quiet": True,
        "no_warnings": True,
    }

    final_path: list[str] = []

    def _pp_hook(d: dict) -> None:
        if d.get("status") == "finished":
            fp = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
            if fp:
                final_path.append(fp)

    ydl_opts["postprocessor_hooks"] = [_pp_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Tenta obter o caminho final do postprocessor hook
    if final_path and Path(final_path[-1]).exists():
        return Path(final_path[-1])

    # Fallback: info dict
    if info:
        downloads = info.get("requested_downloads", [])
        if downloads:
            fp = downloads[0].get("filepath", "")
            if fp and Path(fp).exists():
                return Path(fp)

    # Último recurso: arquivo mais recente em out_dir
    files = sorted(
        (f for f in out_dir.iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if files:
        return files[0]

    raise FileNotFoundError(f"Download concluído mas arquivo não encontrado em: {out_dir}")
