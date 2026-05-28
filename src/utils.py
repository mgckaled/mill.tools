"""
utils.py: Logging setup, validation, metadata handling and audio download.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yt_dlp
from tqdm import tqdm

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIOS_DIR = PROJECT_ROOT / "audios"
TRANSCRIPTIONS_RAW_DIR = PROJECT_ROOT / "transcriptions" / "raw"
TRANSCRIPTIONS_ANALYSIS_DIR = PROJECT_ROOT / "transcriptions" / "analysis"
YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[A-Za-z0-9_-]{11}"
)
DOWNLOAD_TIMEOUT = 300  # seconds


class TqdmLoggingHandler(logging.Handler):
    """Logging handler that writes through tqdm to avoid progress bar conflicts."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except RuntimeError:
            self.handleError(record)


def setup_logging(verbose: bool) -> None:
    """Configure logging level based on verbosity flag.

    Uses a tqdm-aware handler so log messages don't break the progress bar.
    Third-party loggers (httpx, faster_whisper, huggingface_hub) are capped at
    WARNING to avoid cluttering the output with internal library messages.

    Args:
        verbose: If True, sets level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = TqdmLoggingHandler()
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.root.setLevel(level)
    logging.root.handlers = [handler]

    for noisy in ("httpx", "httpcore", "faster_whisper", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def check_dependencies() -> None:
    """Verify that required external tools are available on PATH.

    Checks for yt-dlp and ffmpeg. Exits with a clear message if either
    is missing.
    """
    missing = [tool for tool in ("yt-dlp", "ffmpeg") if not shutil.which(tool)]
    if missing:
        for tool in missing:
            logging.error(
                "'%s' not found. Install it and make sure it's on your PATH.\n"
                "  yt-dlp:  https://github.com/yt-dlp/yt-dlp\n"
                "  ffmpeg:  https://ffmpeg.org/download.html",
                tool,
            )
        sys.exit(1)
    logging.debug("Dependencies OK: yt-dlp and ffmpeg found.")


def validate_url(url: str) -> None:
    """Validate that the provided URL is a recognizable YouTube URL.

    Args:
        url: The URL string to validate.

    Raises:
        SystemExit: If the URL does not match the expected YouTube pattern.
    """
    if not YOUTUBE_URL_PATTERN.match(url):
        logging.error(
            "Invalid YouTube URL: '%s'\n"
            "Expected formats:\n"
            "  https://www.youtube.com/watch?v=VIDEO_ID\n"
            "  https://youtu.be/VIDEO_ID",
            url,
        )
        sys.exit(1)
    logging.debug("URL validated: %s", url)


def extract_video_id(url: str) -> str:
    """Extract a 6-character alphanumeric slug from the YouTube URL.

    Takes the first 6 alphanumeric characters from the video ID
    (e.g. 'ovabeV' from '?v=ovabeVoWrA0').

    Args:
        url: A valid YouTube URL.

    Returns:
        A 6-character alphanumeric string derived from the video ID.
    """
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]+)", url)
    source = match.group(1) if match else re.sub(r"[^A-Za-z0-9]", "", url)
    return re.sub(r"[^A-Za-z0-9]", "", source)[:6]


def fetch_metadata(url: str) -> dict:
    """Fetch video metadata from YouTube without downloading the media.

    Args:
        url: YouTube video URL.

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
        url: Original YouTube URL.
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


def download_audio(url: str, audio_path: Path) -> None:
    """Download audio from a YouTube URL using yt-dlp.

    Skips download if the audio file already exists. Enforces a timeout
    to prevent hanging on slow or unavailable resources.

    Args:
        url: YouTube video URL.
        audio_path: Destination path for the downloaded MP3 file.

    Raises:
        SystemExit: If yt-dlp returns a non-zero exit code or times out.
    """
    if audio_path.exists():
        logging.info(
            "[»] Audio already exists, skipping download: %s", audio_path)
        return

    AUDIOS_DIR.mkdir(exist_ok=True)
    logging.info("[↓] Downloading audio from: %s", url)

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "-o", str(audio_path),
                "--no-playlist",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=DOWNLOAD_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logging.error(
            "Download timed out after %ds. "
            "Check your internet connection or try again later.",
            DOWNLOAD_TIMEOUT,
        )
        sys.exit(1)

    if result.returncode != 0:
        logging.error("yt-dlp error:\n%s", result.stderr.strip())
        sys.exit(1)

    logging.info("[✓] Audio downloaded successfully.")
    size_mb = audio_path.stat().st_size / (1024 * 1024)
    logging.debug("[d] Audio file size: %.1f MB | path: %s", size_mb, audio_path)
