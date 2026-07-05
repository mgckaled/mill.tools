"""Audio conversion and extraction via ffmpeg with structured progress."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable

from src.core.audio.info import get_audio_codec_ffprobe, get_duration_ffprobe
from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)

# Video extensions that trigger extraction (instead of conversion)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
# Audio extensions accepted for conversion
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a"}

# Source codecs that can be copied (no re-encode) straight into a given target
# container/fmt without a compatibility mismatch. Deliberately conservative —
# "wav" is excluded because PCM subtype/layout mismatches are more likely to
# bite silently than for these compressed formats.
_COPYABLE_CODECS: dict[str, set[str]] = {
    "m4a": {"aac"},
    "mp3": {"mp3"},
    "opus": {"opus"},
    "ogg": {"opus", "vorbis"},
}


def convert_audio(
    src: Path,
    out_dir: Path,
    fmt: str,
    bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
    channels: int | None = None,
    sample_rate: int | None = None,
) -> Path:
    """Convert an audio file to another format via ffmpeg.

    Args:
        src: Source file.
        out_dir: Output directory (created if needed).
        fmt: Target format ("mp3", "m4a", "wav", "ogg", "opus").
        bitrate: Bitrate in kbps ("320", "128", etc.). None = default quality.
        progress_cb: Called with float 0.0-1.0 during the conversion.
        channels: Channel count for downmix (1 = mono). None preserves source.
        sample_rate: Target sample rate in Hz (e.g. 16000). None preserves source.

    Returns:
        Path of the converted file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}.{fmt}"

    same_path = out_path.resolve() == src.resolve()
    has_transform = (
        bool(channels) or bool(sample_rate) or bool(bitrate and bitrate != "best")
    )
    # No-op: same format, same location, nothing to transform → return as-is.
    if same_path and not has_transform:
        return src

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if bitrate and bitrate != "best":
        cmd += ["-b:a", f"{bitrate}k"]
    if channels:
        cmd += ["-ac", str(channels)]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    # ffmpeg cannot read and write the same path in place: when an in-place
    # transform is requested (e.g. mp3→mp3 mono), encode to a temp file and move.
    target = out_path
    tmp: Path | None = None
    if same_path:
        tmp = out_dir / f".tmp_encode_{sanitize_filename(src.stem)}.{fmt}"
        target = tmp
    cmd += ["-progress", "pipe:1", "-nostats", str(target)]

    total_secs = get_duration_ffprobe(src) if progress_cb else None
    try:
        run_ffmpeg(cmd, target, total_secs=total_secs, progress_cb=progress_cb)
    except Exception:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        raise
    if tmp is not None:
        shutil.move(str(tmp), str(out_path))
    return out_path


def extract_audio(
    video: Path,
    out_dir: Path,
    fmt: str = "mp3",
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Extract the audio track from a local video via ffmpeg.

    Args:
        video: Source video file.
        out_dir: Output directory (created if needed).
        fmt: Format of the extracted audio.
        progress_cb: Called with float 0.0-1.0 during the extraction.

    Returns:
        Path of the extracted audio file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(video.stem)}_audio.{fmt}"

    def _build_cmd(use_copy: bool) -> list[str]:
        cmd = ["ffmpeg", "-y", "-i", str(video), "-vn"]  # -vn: drop video stream
        if use_copy:
            cmd += ["-acodec", "copy"]
        cmd += ["-progress", "pipe:1", "-nostats", str(out_path)]
        return cmd

    total_secs = get_duration_ffprobe(video) if progress_cb else None

    source_codec = get_audio_codec_ffprobe(video)
    if source_codec in _COPYABLE_CODECS.get(fmt, ()):
        try:
            return run_ffmpeg(
                _build_cmd(True),
                out_path,
                total_secs=total_secs,
                progress_cb=progress_cb,
            )
        except RuntimeError:
            logger.warning(
                "codec copy fast path failed for %s (source codec %s, target %s) — "
                "falling back to re-encode",
                video,
                source_codec,
                fmt,
            )

    return run_ffmpeg(
        _build_cmd(False), out_path, total_secs=total_secs, progress_cb=progress_cb
    )
