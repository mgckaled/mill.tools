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
    normalize: bool = False
    normalize_target_lufs: float = -14.0
    channels: int | None = None  # 1 = mono; None preserves source
    sample_rate: int | None = None  # e.g. 16000; None preserves source
