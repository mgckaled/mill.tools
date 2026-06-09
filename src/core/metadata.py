"""
metadata.py: Shared metadata helpers for the transcription pipeline.
"""

import logging
from datetime import datetime

import yt_dlp


def fetch_metadata(url: str) -> dict:
    """Fetch video metadata from a URL without downloading the media.

    Args:
        url: Video URL (YouTube, SoundCloud, etc.).

    Returns:
        Dictionary containing raw metadata fields from yt-dlp.
    """
    logging.info("[i] Fetching video metadata...")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        meta = ydl.extract_info(url, download=False)
    logging.debug(
        "[d] Metadata: title=%r | channel=%s | duration=%ss",
        meta.get("title"), meta.get("uploader"), meta.get("duration"),
    )
    return meta


def format_duration(seconds: int) -> str:
    """Format a duration in seconds to HH:MM:SS string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string.
    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def format_metadata(meta: dict, url: str, detected_language: str | None = None) -> str:
    """Format selected metadata fields as a plain text header.

    Args:
        meta: Raw metadata dictionary returned by yt-dlp.
        url: Original URL.
        detected_language: Language detected by Whisper (optional).

    Returns:
        A formatted multi-line string ready to be written to the output file.
    """
    raw_date = meta.get("upload_date", "")
    upload_date = (
        datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
        if raw_date else "n/a"
    )

    duration = format_duration(int(meta.get("duration", 0)))
    tags = ", ".join(meta.get("tags", []) or []) or "n/a"
    language = detected_language or "n/a"

    lines = [
        f"title:        {meta.get('title', 'n/a')}",
        f"channel:      {meta.get('uploader', 'n/a')}",
        f"upload_date:  {upload_date}",
        f"duration:     {duration}",
        f"language:     {language}",
        f"tags:         {tags}",
        f"url:          {url}",
        "",
        "-" * 64,
        "",
    ]
    return "\n".join(lines)
