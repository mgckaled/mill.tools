"""
args.py: Shared argument types for the audio pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.io_types import InputItem


@dataclass
class AudioArgs:
    """Audio pipeline parameters."""

    items: list[InputItem] = field(default_factory=list)
    fmt: str = "mp3"
    quality: str = "best"
    embed_meta: bool = True
    denoise: bool = False
    denoise_stationary: bool = True
    trim_silence: bool = False
    silence_threshold_db: float = -40.0
    silence_min_s: float = 0.5
    speed_factor: float = 1.0  # 1.0 = disabled
    normalize: bool = False
    normalize_target_lufs: float = -14.0
    channels: int | None = None  # 1 = mono; None preserves source
    sample_rate: int | None = None  # e.g. 16000; None preserves source
