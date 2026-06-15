"""Typed model for an item stored under the project's output/ tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Logical kinds shown in the Library filter.
KIND_AUDIO = "audio"
KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_DOCUMENT = "document"
KIND_TRANSCRIPTION = "transcription"

# All kinds, in display priority order (mirrors the NavigationRail).
ALL_KINDS: tuple[str, ...] = (
    KIND_AUDIO,
    KIND_VIDEO,
    KIND_IMAGE,
    KIND_TRANSCRIPTION,
    KIND_DOCUMENT,
)


@dataclass(frozen=True, slots=True)
class LibraryItem:
    """A single file produced by any module, plus cheap filesystem metadata.

    `frozen=True` + `slots=True` keeps the item cheap and hashable so it can be
    used as a thumbnail cache key. No thumbnail bytes live here — metadata only.
    """

    path: Path
    kind: str  # one of the KIND_* constants
    category: str  # "source" | "processed" | "text" | "analysis" | "digest"
    size_bytes: int
    modified: float  # st_mtime epoch seconds
    stem: str
    suffix: str  # lowercase, with dot (".mp3")
