"""
args.py: Shared argument types for the video pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.io_types import InputItem


@dataclass
class VideoArgs:
    """Video pipeline parameters."""

    items: list[InputItem] = field(default_factory=list)
    operation: str = "download"

    # Download
    resolution: str = "1080"
    container: str = "mp4"
    embed_meta: bool = True

    # Convert
    vcodec: str = "copy"
    out_container: str = "mp4"

    # Trim
    trim_start: str = ""
    trim_end: str = ""
    trim_reenc: bool = False

    # Compress
    crf: int = 23
    preset: str = "medium"

    # Resize
    resize_width: int = 0
    resize_height: int = 0

    # Extract audio
    audio_fmt: str = "mp3"

    # Thumbnail
    thumb_time: str = "00:00:01"
    thumb_fmt: str = "jpg"
