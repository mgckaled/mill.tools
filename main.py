"""
yt-transcriber: Transcribe YouTube videos using faster-whisper.

Usage:
    uv run yt-transcriber <YOUTUBE_URL> [options]

Examples:
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --wm medium
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --language pt
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --format
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --analyze
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --format --analyze
    uv run yt-transcriber https://www.youtube.com/watch?v=ovabeVoWrA0 --format --fm phi4-mini --analyze --am qwen7b-custom
"""

import argparse
import logging

from src.transcriber import print_summary, transcribe
from src.utils import (
    AUDIOS_DIR,
    TRANSCRIPTIONS_RAW_DIR,
    check_dependencies,
    download_audio,
    extract_video_id,
    fetch_metadata,
    setup_logging,
    validate_url,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Namespace with url, whisper_model, language, threads, beam_size,
        output_name, format, format_model, analyze, analyzer_model and verbose fields.
    """
    parser = argparse.ArgumentParser(
        description="Transcribe a YouTube video to plain text using faster-whisper.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("url", help="YouTube video URL")
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
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: validate inputs, fetch metadata, download audio, and transcribe."""
    args = parse_args()

    setup_logging(args.verbose)
    check_dependencies()
    validate_url(args.url)

    video_id = extract_video_id(args.url)
    audio_path = AUDIOS_DIR / f"{video_id}.mp3"

    TRANSCRIPTIONS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_stem = args.output_name or f"transcricao_{video_id}"
    output_path = TRANSCRIPTIONS_RAW_DIR / f"{output_stem}.txt"

    logging.debug("Video ID slug: %s", video_id)
    logging.debug("Audio path: %s", audio_path)
    logging.debug("Output path: %s", output_path)

    meta = fetch_metadata(args.url)
    download_audio(args.url, audio_path)

    elapsed = transcribe(
        audio_path,
        output_path,
        meta,
        args.url,
        args.whisper_model,
        args.language,
        args.threads,
        args.beam_size,
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


if __name__ == "__main__":
    main()
