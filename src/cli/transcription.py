"""
transcription.py: CLI-specific helpers for the transcribe subcommand.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.utils import sanitize_filename


def build_output_stem(meta: dict, custom_name: str | None = None) -> str:
    """Build a filesystem-safe stem for the transcription output file.

    Uses the sanitised video title by default. Falls back to a timestamp
    slug when the title is absent or yields an empty string after sanitisation.

    Args:
        meta: Metadata dict (at minimum expects 'title').
        custom_name: User-supplied override (also sanitised).

    Returns:
        A clean stem string suitable for use in a filename.
    """
    if custom_name:
        stem = sanitize_filename(custom_name)
        return stem or custom_name
    title = meta.get("title", "")
    if title:
        stem = sanitize_filename(title)
        if stem:
            return stem
    return f"transcription_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def resolve_input(value: str) -> tuple[str, str]:
    """Determine whether *value* is a local file path or a remote URL.

    Args:
        value: CLI positional argument (URL or file path).

    Returns:
        Tuple of (kind, resolved_value) where kind is 'local' or 'url'.
        resolved_value is the absolute path string for local files, or the
        original string for URLs.
    """
    path = Path(value)
    if path.is_file():
        return ("local", str(path.resolve()))
    return ("url", value)
