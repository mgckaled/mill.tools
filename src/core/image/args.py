"""
args.py: Shared argument types for the image pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.core.io_types import InputItem


@dataclass
class ImageArgs:
    """Image pipeline parameters."""

    items: list[InputItem] = field(default_factory=list)
    operation: str = "convert"

    # convert
    fmt: str = "jpg"
    quality: int = 90

    # output for manipulation (None = preserve original format)
    out_fmt: str | None = None
    out_quality: int = 90

    # resize
    resize_mode: str = "contain"
    resize_width: int | None = None
    resize_height: int | None = None
    resize_scale_pct: float = 100.0

    # crop
    crop_mode: str = "manual"
    crop_left: int = 0
    crop_top: int = 0
    crop_width: int = 0
    crop_height: int = 0
    crop_ratio: str = "1:1"
    crop_trim_color: str = "#ffffff"

    # rotate
    rotate_angle: int = 0
    rotate_flip_h: bool = False
    rotate_flip_v: bool = False
    rotate_exif_auto: bool = False

    # watermark
    wm_mode: str = "text"
    wm_text: str = ""
    wm_text_color: str = "#ffffff"
    wm_text_size: int = 40
    wm_path: Path | None = None
    wm_position: str = "bottom-right"
    wm_opacity: float = 0.5

    # border
    border_padding: int = 20
    border_color: str = "#000000"
    border_fill_alpha: bool = False

    # adjust
    adj_brightness: float = 1.0
    adj_contrast: float = 1.0
    adj_color: float = 1.0
    adj_sharpness: float = 1.0

    # filter
    filter_type: str = "blur"

    # favicon
    favicon_sizes: list[int] = field(default_factory=lambda: [16, 32, 48, 64, 128, 256])

    # contact_sheet
    cs_cols: int = 4
    cs_thumb_size: int = 200
    cs_gap: int = 10
    cs_bg_color: str = "#ffffff"

    # remove_bg
    rembg_model: str = "u2net"

    # describe
    describe_model: str = "moondream-custom"
    describe_prompt: str = ""
