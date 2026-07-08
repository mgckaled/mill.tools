"""
utils.py: Logging setup, path constants and dependency checking.
"""

import logging
import os
import re
import shutil
from pathlib import Path

from tqdm import tqdm

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
AUDIO_SOURCE_DIR = OUTPUT_DIR / "audio" / "source"
AUDIO_PROCESSED_DIR = OUTPUT_DIR / "audio" / "processed"
VIDEO_SOURCE_DIR = OUTPUT_DIR / "video" / "source"
VIDEO_PROCESSED_DIR = OUTPUT_DIR / "video" / "processed"
IMAGE_SOURCE_DIR = OUTPUT_DIR / "image" / "source"
IMAGE_PROCESSED_DIR = OUTPUT_DIR / "image" / "processed"
DOCUMENT_SOURCE_DIR = OUTPUT_DIR / "document" / "source"
DOCUMENT_PROCESSED_DIR = OUTPUT_DIR / "document" / "processed"
TRANSCRIPTIONS_TEXT_DIR = OUTPUT_DIR / "transcriptions" / "text"
TRANSCRIPTIONS_ANALYSIS_DIR = OUTPUT_DIR / "transcriptions" / "analysis"
TRANSCRIPTIONS_DIGEST_DIR = OUTPUT_DIR / "transcriptions" / "digest"
TRANSCRIPTIONS_SUBTITLES_DIR = OUTPUT_DIR / "transcriptions" / "subtitles"
DATA_DIR = OUTPUT_DIR / "data"  # structured-data module (PR9)

_SANITIZE_SEPS = re.compile(r"\s*[｜|·–—]\s*")
_SANITIZE_COLON = re.compile(r"\s*[：:]\s*")
_SANITIZE_INVALID = re.compile(r'[<>"\\/?*\x00-\x1f]')
_SANITIZE_PUNCT = re.compile(r"[!！？]")
_SANITIZE_DASH_SPACE = re.compile(r"\s*-\s*")
_SANITIZE_SPACES = re.compile(r"\s+")
_SANITIZE_MULTI_US = re.compile(r"_+")
_SANITIZE_MULTI_HY = re.compile(r"-+")

# Keeps the stem well under Windows' MAX_PATH (260 chars total) even after the
# output directory prefix and a suffix are added.
_MAX_STEM_LENGTH = 120


def sanitize_filename(name: str) -> str:
    """Convert a title to a clean filename stem (no spaces or problematic chars).

    Rules: section separators (｜ |) → hyphen; ASCII/fullwidth colon → hyphen
    (dropping it outright, as ``:`` alone would, creates an NTFS Alternate
    Data Stream instead of failing loudly); spaces → underscore; remaining
    chars invalid on Windows are removed. Accented characters are preserved
    (NTFS supports them). Result is capped at ``_MAX_STEM_LENGTH`` chars.
    """
    name = _SANITIZE_SEPS.sub("-", name)
    name = _SANITIZE_COLON.sub("-", name)
    name = _SANITIZE_INVALID.sub("", name)
    name = _SANITIZE_PUNCT.sub("", name)
    name = _SANITIZE_DASH_SPACE.sub("-", name.strip())
    name = _SANITIZE_SPACES.sub("_", name)
    name = _SANITIZE_MULTI_US.sub("_", name)
    name = _SANITIZE_MULTI_HY.sub("-", name)
    return name.strip("-_.")[:_MAX_STEM_LENGTH].rstrip("-_.")


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
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.root.setLevel(level)
    logging.root.handlers = [handler]

    for noisy in ("httpx", "httpcore", "faster_whisper", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def check_dependencies() -> None:
    """Verify that required external tools are available on PATH.

    Raises:
        RuntimeError: If yt-dlp or ffmpeg are not found on PATH.
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
        raise RuntimeError(
            f"Missing dependencies: {', '.join(missing)}. Install and add to PATH."
        )
    logging.debug("Dependencies OK: yt-dlp and ffmpeg found.")
