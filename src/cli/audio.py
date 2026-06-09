"""
audio.py: CLI subcommand for the audio pipeline.

Supports URL download, local video extraction and local audio conversion.
Operation is auto-detected from the input type.

Usage:
    uv run main.py audio URL [--fmt mp3] [--quality 320] [--no-meta]
    uv run main.py audio audio.wav [--fmt mp3] [--denoise] [--normalize]
    uv run main.py audio video.mp4 [--fmt mp3]
"""
from __future__ import annotations

import argparse
import sys
import threading


def add_audio_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'audio' subcommand with its arguments."""
    p = subparsers.add_parser(
        "audio",
        help="Download, convert or extract audio (operation auto-detected from input)",
    )
    p.add_argument(
        "input",
        help="YouTube/yt-dlp URL, local video file or local audio file",
    )
    p.add_argument(
        "--fmt",
        default="mp3",
        choices=["mp3", "m4a", "wav", "ogg", "opus", "best"],
        help="Output audio format (default mp3; 'best' skips re-encoding for URL downloads)",
    )
    p.add_argument(
        "--quality",
        default="best",
        metavar="BITRATE",
        help="Audio bitrate e.g. '320', '192', '128', or 'best' (default best)",
    )
    p.add_argument(
        "--no-meta",
        action="store_true",
        dest="no_meta",
        help="Skip embedding cover art and metadata tags",
    )
    p.add_argument(
        "--denoise",
        action="store_true",
        help="Apply spectral gating noise reduction after the main operation",
    )
    p.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize loudness to EBU R128 target after the main operation",
    )
    p.add_argument(
        "--lufs",
        type=float,
        default=-14.0,
        metavar="TARGET",
        help="Target LUFS for --normalize (default -14.0)",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    p.set_defaults(func=run_audio_cli)


def run_audio_cli(ns: argparse.Namespace) -> None:
    """Execute the audio pipeline from parsed CLI arguments.

    Args:
        ns: Parsed argument namespace from add_audio_parser.
    """
    from src.cli.bus import CLIEventBus
    from src.cli.transcription import resolve_input
    from src.core.audio.args import AudioArgs
    from src.core.io_types import InputItem
    from src.gui.modules.audio.worker import run_audio_pipeline
    from src.utils import check_dependencies

    check_dependencies()

    kind, value = resolve_input(ns.input)

    args = AudioArgs(
        items=[InputItem(kind=kind, value=value)],
        fmt=ns.fmt,
        quality=ns.quality,
        embed_meta=not ns.no_meta,
        denoise=ns.denoise,
        normalize=ns.normalize,
        normalize_target_lufs=ns.lufs,
    )

    bus = CLIEventBus()
    cancel = threading.Event()

    success = run_audio_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
