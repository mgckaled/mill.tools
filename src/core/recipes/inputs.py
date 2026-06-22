"""Map a raw input (URL or local file) to a recipe payload kind.

``resolve_input`` (``src/cli/transcription.py``) and the GUI ``InputSource`` both
classify an input only as ``"url"`` vs ``"local"``. Recipes need the *logical*
kind (audio/video/pdf/...) so the first step can be validated. This pure helper —
shared by the CLI and the GUI — derives it from the file extension.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_AUDIO,
    KIND_DATA,
    KIND_IMAGE,
    KIND_PDF,
    KIND_TEXT,
    KIND_URL,
    KIND_VIDEO,
)

_AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}
_VIDEO_EXT = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
_IMAGE_EXT = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".tiff",
    ".bmp",
    ".gif",
    ".ico",
}
_TEXT_EXT = {".txt", ".md"}
_DATA_EXT = {".csv", ".tsv", ".json", ".ndjson", ".jsonl", ".parquet", ".pq", ".xlsx"}


def kind_for(kind: str, value: str) -> str:
    """Resolve the recipe payload kind for a ``resolve_input()`` result.

    Args:
        kind: ``resolve_input``'s classification — ``"url"`` or ``"local"``.
        value: The URL or local file path.

    Returns:
        ``KIND_URL`` for URLs, or one of audio/video/image/pdf/text for files.

    Raises:
        ValueError: When the local file extension is not supported by recipes.
    """
    if kind == "url":
        return KIND_URL
    ext = Path(value).suffix.lower()
    if ext in _AUDIO_EXT:
        return KIND_AUDIO
    if ext in _VIDEO_EXT:
        return KIND_VIDEO
    if ext in _IMAGE_EXT:
        return KIND_IMAGE
    if ext == ".pdf":
        return KIND_PDF
    if ext in _TEXT_EXT:
        return KIND_TEXT
    if ext in _DATA_EXT:
        return KIND_DATA
    raise ValueError(f"Tipo de arquivo não suportado em receitas: {ext or value}")
