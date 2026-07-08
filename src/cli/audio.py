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
        "--denoise-adaptive",
        action="store_true",
        dest="denoise_adaptive",
        help="Use adaptive (non-stationary) noise reduction instead of stationary",
    )
    p.add_argument(
        "--mono",
        action="store_true",
        help="Downmix output to a single (mono) channel",
    )
    p.add_argument(
        "--sample-rate",
        type=int,
        default=None,
        dest="sample_rate",
        choices=[16000, 22050, 44100, 48000],
        metavar="HZ",
        help="Resample output to the given sample rate (e.g. 16000 for Whisper)",
    )
    p.add_argument(
        "--trim-silence",
        action="store_true",
        dest="trim_silence",
        help="Remove leading, trailing and internal silence (ffmpeg silenceremove)",
    )
    p.add_argument(
        "--silence-threshold",
        type=float,
        default=-40.0,
        dest="silence_threshold",
        metavar="DB",
        help="Silence threshold in dBFS for --trim-silence (default -40.0)",
    )
    p.add_argument(
        "--silence-min",
        type=float,
        default=0.5,
        dest="silence_min",
        metavar="SECONDS",
        help="Minimum silence duration to cut for --trim-silence (default 0.5)",
    )
    p.add_argument(
        "--speed",
        type=float,
        default=1.0,
        metavar="FACTOR",
        help="Change speed without pitch shift, e.g. 1.25 (range 0.5-4.0; default 1.0)",
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


def add_audio_viz_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'audio-viz' subcommand (audio → static PNG image)."""
    p = subparsers.add_parser(
        "audio-viz",
        help="Render a static waveform or spectrogram PNG from an audio file",
    )
    p.add_argument("input", help="Local audio or video file")
    p.add_argument(
        "--spectrogram",
        action="store_true",
        help="Render a spectrogram instead of a waveform",
    )
    p.add_argument(
        "--width",
        type=int,
        default=1200,
        metavar="PX",
        help="Image width (default 1200)",
    )
    p.add_argument(
        "--height",
        type=int,
        default=None,
        metavar="PX",
        help="Image height (default 240 waveform / 480 spectrogram)",
    )
    p.set_defaults(func=run_audio_viz_cli)


def run_audio_viz_cli(ns: argparse.Namespace) -> None:
    """Render a waveform/spectrogram PNG from parsed CLI arguments."""
    from pathlib import Path

    from src.core.audio.visualize import render_spectrogram_png, render_waveform_png
    from src.utils import AUDIO_PROCESSED_DIR, check_dependencies

    # Output filenames may contain non-cp1252 characters. Reconfigure only our
    # real stdout; under pytest sys.stdout is a capture wrapper (≠ __stdout__)
    # whose reconfigure would drop the captured output.
    if sys.stdout is sys.__stdout__:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    check_dependencies()

    src = Path(ns.input)
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(1)

    if ns.spectrogram:
        out = render_spectrogram_png(
            src, AUDIO_PROCESSED_DIR, width=ns.width, height=ns.height or 480
        )
    else:
        out = render_waveform_png(
            src, AUDIO_PROCESSED_DIR, width=ns.width, height=ns.height or 240
        )
    print(f"Saved: {out}")


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
        denoise_stationary=not ns.denoise_adaptive,
        trim_silence=ns.trim_silence,
        silence_threshold_db=ns.silence_threshold,
        silence_min_s=ns.silence_min,
        speed_factor=ns.speed,
        normalize=ns.normalize,
        normalize_target_lufs=ns.lufs,
        channels=1 if ns.mono else None,
        sample_rate=ns.sample_rate,
    )

    bus = CLIEventBus()
    cancel = threading.Event()

    success = run_audio_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
