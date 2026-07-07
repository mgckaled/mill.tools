"""
transcription.py: CLI-specific helpers for the transcribe subcommand.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from src.utils import sanitize_filename


def add_transcribe_args(
    parser: argparse.ArgumentParser, *, include_profile_choices: bool = True
) -> None:
    """Register the transcribe flag set on *parser*.

    Shared by the legacy top-level parser (``main.py::parse_args``) and the
    introspected reference parser (``cli/reference.py``) — single source of
    truth for the "transcribe" flags, so a new one shows up in both
    automatically.

    ``include_profile_choices=False`` skips the lazy LangChain import used to
    validate ``--profile`` in the real CLI: the reference parser only needs
    the flag to exist for NL→CLI generation, not real choice validation.
    """
    parser.add_argument("url", help="YouTube URL or path to local audio file")
    parser.add_argument(
        "--wm",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"],
        help="Whisper model size",
        dest="whisper_model",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code for transcription (e.g. en, pt). Defaults to auto-detection.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=2,
        help="Number of CPU threads to use",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Custom name for the output file (without extension)",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=1,
        help="Beam size for decoding (1 = fastest, 5 = most accurate)",
    )
    parser.add_argument(
        "--format",
        action="store_true",
        help="Add paragraph breaks to the transcription using a local LLM (requires Ollama)",
    )
    parser.add_argument(
        "--fm",
        default="phi4mini-custom",
        help="Ollama model for paragraph formatting",
        dest="format_model",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run structured analysis after transcription (requires Ollama)",
    )
    parser.add_argument(
        "--am",
        default="gemma3-4b-custom",
        help="Ollama model for analysis",
        dest="analyzer_model",
    )
    if include_profile_choices:
        from src.analysis import (
            list_profiles,
        )  # lazy: avoids loading LangChain for other commands

        profile_choices = list_profiles()
    else:
        profile_choices = None
    parser.add_argument(
        "--profile",
        default="default",
        choices=profile_choices,
        help="Analysis profile (schema/prompt). 'default' keeps the legacy video schema.",
    )
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="Generate a condensed prompt-ready version of the transcription (requires Ollama)",
    )
    parser.add_argument(
        "--pm",
        default="gemma3-4b-custom",
        help="Ollama model for prompt-ready condensation",
        dest="prompt_model",
    )
    parser.add_argument(
        "--srt",
        action="store_true",
        help="Export an .srt subtitle file alongside the .txt transcription",
    )
    parser.add_argument(
        "--vtt",
        action="store_true",
        help="Export a .vtt (WebVTT) subtitle file alongside the .txt transcription",
    )
    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Shortcut for --srt --vtt (exports both subtitle formats)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )


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
