"""Lazy thumbnail dispatch for Library items. Reuses existing generators.

Pure core (no Flet): returns PNG/JPEG bytes that the GUI passes straight to
ft.Image, or None to fall back to a type icon. Generation is meant to run in a
single background thread (CPU-bound pymupdf raster / ffmpeg single frame) to
avoid GPU contention — see the Library view's thumbnail worker.
"""

from __future__ import annotations

import logging
import subprocess

from src.core.library.types import (
    KIND_DOCUMENT,
    KIND_VIDEO,
    LibraryItem,
)

_THUMB_PX = 256
_PDF_ZOOM = 1.2  # ~86dpi — a touch crisper than the 72dpi viewer thumb

# Raster suffixes Pillow can open — mirrors the GUI's image-picker allowlist
# (src/gui/modules/image/describe_tab.py), duplicated here since core/ never
# imports gui/. Checked before the kind-based dispatch below so a PNG produced
# by a non-image module (e.g. the Audio waveform/spectrogram, kind "audio")
# still gets a real preview instead of a generic type icon.
_IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".tiff",
    ".tif",
    ".bmp",
    ".gif",
}


def _video_frame(path, *, seek: str = "00:00:01") -> bytes | None:
    """Grab a single scaled frame from a video as JPEG bytes via ffmpeg pipe:1.

    Tries a 1s seek first (frame 0 is often black); falls back to the very
    start for clips shorter than the seek point. Binary mode only — decoding
    ffmpeg output as cp1252 text would corrupt the bytes on Windows.
    """

    def _grab(ss: str) -> bytes | None:
        cmd = [
            "ffmpeg",
            "-ss",
            ss,
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={_THUMB_PX}:-1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
            "-loglevel",
            "quiet",
        ]
        result = subprocess.run(cmd, capture_output=True)
        data = result.stdout
        return data if (result.returncode == 0 and data) else None

    return _grab(seek) or _grab("0")


def thumbnail_for(item: LibraryItem) -> bytes | None:
    """Return preview bytes for an item, or None to fall back to a type icon.

    - any raster suffix (by extension, not kind) → src.core.image.info.thumbnail_bytes
    - document → first page rasterized via pymupdf (hard dep)
    - video    → single frame via ffmpeg (piped, no temp file)
    - audio / transcription with no raster suffix → None (UI shows a type icon)
    """
    try:
        if item.suffix in _IMAGE_SUFFIXES:
            from src.core.image.info import thumbnail_bytes

            return thumbnail_bytes(item.path, max_px=_THUMB_PX)
        if item.kind == KIND_DOCUMENT and item.suffix == ".pdf":
            from src.core.document.info import render_first_page_png

            return render_first_page_png(item.path, zoom=_PDF_ZOOM)
        if item.kind == KIND_VIDEO:
            return _video_frame(item.path)
    except Exception as exc:  # never let a bad file break the grid
        logging.debug("[d] Thumbnail failed for %s: %s", item.path.name, exc)
    return None
