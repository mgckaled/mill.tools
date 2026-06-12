"""
mill.tools CLI — multimodal pipeline.

Usage:
    uv run main.py <URL>                                        # basic transcription
    uv run main.py transcribe <URL>                            # explicit transcribe subcommand
    uv run main.py transcribe <URL> --format --analyze         # full transcription pipeline
    uv run main.py transcribe <URL> --srt                      # also export .srt subtitle file
    uv run main.py transcribe <URL> --subtitles                # exports .srt + .vtt
    uv run main.py transcribe /path/to/audio.mp3               # local file
    uv run main.py transcribe <URL> --am gemini-2.5-flash      # analysis via Gemini
    uv run -m src output/transcriptions/text/<file>.txt        # standalone analysis

    uv run main.py audio URL [--fmt mp3] [--quality 320]       # audio download/convert
    uv run main.py video download URL [--quality 1080]         # video download
    uv run main.py video convert FILE [--codec h264]           # video convert
    uv run main.py image convert FILE [--fmt webp]             # image convert
"""

import argparse
import logging
import re
import sys
from pathlib import Path

from tqdm import tqdm

from src.cli.transcription import build_output_stem, resolve_input
from src.core.audio.downloader import download_audio as _core_download_audio
from src.core.metadata import fetch_metadata
from src.transcriber import print_summary, transcribe
from src.utils import (
    AUDIO_SOURCE_DIR,
    TRANSCRIPTIONS_TEXT_DIR,
    check_dependencies,
    setup_logging,
)

_ANSI_ESC = re.compile(r"\x1b\[[0-9;]*m")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Namespace with url, whisper_model, language, threads, beam_size,
        output_name, format, format_model, analyze, analyzer_model,
        prompt, prompt_model and verbose fields.
    """
    parser = argparse.ArgumentParser(
        description="Transcribe a YouTube video or local audio file using faster-whisper.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("url", help="YouTube URL or path to local audio file")
    parser.add_argument(
        "--wm",
        default="small",
        choices=["tiny", "base", "small", "medium",
                 "large-v3-turbo", "large-v3"],
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
        default="qwen7b-custom",
        help="Ollama model for analysis",
        dest="analyzer_model",
    )
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="Generate a condensed prompt-ready version of the transcription (requires Ollama)",
    )
    parser.add_argument(
        "--pm",
        default="qwen7b-custom",
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
    return parser.parse_args()


def _subtitle_formats_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Resolve the subtitle_formats tuple from CLI flags.

    --subtitles is shorthand for --srt + --vtt. Individual --srt / --vtt
    flags compose freely. Returns () when no subtitle export was requested.
    """
    if getattr(args, "subtitles", False):
        return ("srt", "vtt")
    fmts: list[str] = []
    if getattr(args, "srt", False):
        fmts.append("srt")
    if getattr(args, "vtt", False):
        fmts.append("vtt")
    return tuple(fmts)


_NON_TRANSCRIBE_CMDS = frozenset({"audio", "video", "image", "document"})


def _dispatch_other(cmd: str) -> None:
    """Dispatch audio / video / image subcommands to their CLI modules."""
    from src.cli.audio import add_audio_parser
    from src.cli.document import add_document_parser
    from src.cli.image import add_image_parser
    from src.cli.video import add_video_parser

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="mill.tools — audio, video, image and document processing",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(subparsers)
    add_video_parser(subparsers)
    add_image_parser(subparsers)
    add_document_parser(subparsers)

    ns = parser.parse_args(sys.argv[1:])
    setup_logging(getattr(ns, "verbose", False))
    try:
        ns.func(ns)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        logging.error("%s", exc)
        sys.exit(1)


def main() -> None:
    """Entry point: dispatch to the correct pipeline based on the first argument."""
    # Dispatch audio / video / image to their dedicated CLI modules.
    if len(sys.argv) > 1 and sys.argv[1] in _NON_TRANSCRIBE_CMDS:
        _dispatch_other(sys.argv[1])
        return

    # Transparent "transcribe" subcommand for forward compatibility.
    # Allows both "main.py <URL>" (legacy) and "main.py transcribe <URL>".
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe":
        sys.argv.pop(1)

    args = parse_args()
    setup_logging(args.verbose)

    try:
        check_dependencies()

        kind, value = resolve_input(args.url)

        TRANSCRIPTIONS_TEXT_DIR.mkdir(parents=True, exist_ok=True)

        if kind == "file":
            audio_path = Path(value)
            meta: dict = {"title": audio_path.stem, "duration": 0}
        else:
            meta = fetch_metadata(value)
            _stem = build_output_stem(meta)
            audio_path = AUDIO_SOURCE_DIR / f"{_stem}.mp3"
            AUDIO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

            if not audio_path.exists():
                logging.info("[↓] Downloading audio from: %s", value)

                def _hook(d: dict) -> None:
                    if d.get("status") == "downloading":
                        pct = _ANSI_ESC.sub("", d.get("_percent_str", "")).strip()
                        speed = _ANSI_ESC.sub("", d.get("_speed_str", "")).strip()
                        eta = _ANSI_ESC.sub("", d.get("_eta_str", "")).strip()
                        if pct:
                            tqdm.write(f"\r  ↓ {pct} — {speed}  ETA {eta}", end="")
                    elif d.get("status") == "finished":
                        tqdm.write("")

                audio_path = _core_download_audio(
                    value, AUDIO_SOURCE_DIR, fmt="mp3",
                    embed_meta=False, progress_hook=_hook,
                )
                logging.info("[✓] Audio downloaded: %s", audio_path.name)

        output_stem = build_output_stem(meta, args.output_name)
        output_path = TRANSCRIPTIONS_TEXT_DIR / f"{output_stem}.txt"

        logging.debug("Audio path: %s", audio_path)
        logging.debug("Output path: %s", output_path)

        elapsed = transcribe(
            audio_path,
            output_path,
            meta,
            value,
            args.whisper_model,
            args.language,
            args.threads,
            args.beam_size,
            subtitle_formats=_subtitle_formats_from_args(args),
        )

        if elapsed is not None:
            logging.info("[✓] Transcription saved to: %s", output_path)
            print_summary(meta, output_path, elapsed)

        formatted_body = None
        if args.format:
            from src.formatter import format_transcription  # lazy import
            formatted_body = format_transcription(output_path, model_name=args.format_model)

        if args.analyze:
            from src.analyzer import analyze  # lazy import — only loads LangChain when needed
            analyze(output_path, model_name=args.analyzer_model, transcription=formatted_body)

        if args.prompt:
            from src.prompter import build_prompt_ready  # lazy import
            build_prompt_ready(output_path, model_name=args.prompt_model)

    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        logging.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
