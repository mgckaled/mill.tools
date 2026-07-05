"""Download de áudio via yt-dlp com suporte a progresso e metadados."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import yt_dlp

from src.core.ytdlp_cookies import cookie_ydl_opts
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)

# Formatos que não suportam thumbnail embutida de forma confiável.
# "best" skips re-encoding, so the final container is whatever yt-dlp's bestaudio
# selection picked — frequently webm, which yt-dlp's EmbedThumbnail postprocessor
# rejects outright (raises, aborting the whole download). Since the final
# extension isn't known ahead of time, cover embedding is skipped for "best".
_NO_COVER_FMTS = {"ogg", "opus", "best"}

# Extensões de thumbnail geradas pelo yt-dlp — ignoradas ao procurar o arquivo de áudio
_THUMB_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def download_audio(
    url: str,
    out_dir: Path,
    fmt: str = "mp3",
    quality: str = "best",
    embed_meta: bool = True,
    progress_hook: Callable[[dict], None] | None = None,
) -> Path:
    """Baixa áudio de URL para out_dir.

    Todo o download e pós-processamento (FFmpegExtractAudio, EmbedThumbnail)
    ocorre num diretório temporário privado para evitar que o Windows Defender
    bloqueie o rename de .temp.<ext> com WinError 32. Só o arquivo final é
    movido para out_dir.

    Args:
        url: URL do YouTube, SoundCloud, etc.
        out_dir: Diretório de saída (criado se necessário).
        fmt: Formato de saída. "best" preserva o codec original sem reencode.
        quality: Bitrate em kbps ("best", "320", "256", "128", "96", "64").
        embed_meta: Embutir metadados e capa (se o formato suportar).
        progress_hook: Chamado com dict yt-dlp (status, downloaded_bytes, total_bytes…).

    Returns:
        Path do arquivo gerado em out_dir.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    postprocessors: list[dict] = []

    if fmt != "best":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt,
                "preferredquality": quality if quality != "best" else "0",
            }
        )

    supports_cover = embed_meta and fmt not in _NO_COVER_FMTS

    if embed_meta:
        postprocessors.append({"key": "FFmpegMetadata"})

    if supports_cover:
        postprocessors.append(
            {"key": "EmbedThumbnail", "already_have_thumbnail": False}
        )
    elif embed_meta:
        logger.info("[i] %s: thumbnail not supported — metadata only", fmt)

    # Diretório temporário privado: FFmpegExtractAudio cria .temp.<ext> no mesmo
    # diretório do arquivo de entrada. Usando %TEMP%, o Defender não escaneia e
    # o rename não falha. Somente o arquivo final é movido para out_dir.
    tmp_dir = Path(tempfile.mkdtemp(prefix="mill_audio_"))

    final_path: list[str] = []

    def _pp_hook(d: dict) -> None:
        if d.get("status") == "finished":
            fp = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
            if fp:
                final_path.append(fp)

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp_dir / "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "postprocessor_hooks": [_pp_hook],
        "progress_hooks": [progress_hook] if progress_hook else [],
        "writethumbnail": supports_cover,
        "nopart": True,
        "overwrites": True,
        # Download only the single video, never the playlist. A watch URL with a
        # "&list=" param (e.g. a YouTube "RD..." radio mix, which is endless)
        # would otherwise fetch every entry. The module handles one item at a time.
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        # yt-dlp has no default read timeout — a stalled connection would hang
        # the whole pipeline indefinitely.
        "socket_timeout": 30,
    }
    # Browser cookies (anti-bot gate) — shared resolver, no-op when disabled.
    ydl_opts.update(cookie_ydl_opts())

    try:
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
                (
                    f
                    for f in tmp_dir.iterdir()
                    if f.is_file() and f.suffix.lower() not in _THUMB_EXTS
                ),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if files:
                out_path = files[0]

        if out_path is None:
            raise FileNotFoundError(
                f"Download concluído mas arquivo não encontrado em: {tmp_dir}"
            )

        # Sanitiza o nome enquanto ainda está em tmp_dir (sem Defender)
        safe_stem = sanitize_filename(out_path.stem)
        if safe_stem and safe_stem != out_path.stem:
            try:
                out_path = out_path.rename(out_path.with_stem(safe_stem))
            except OSError:
                pass

        # Move o arquivo final para out_dir
        dest = out_dir / out_path.name
        shutil.move(str(out_path), str(dest))
        return dest

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
