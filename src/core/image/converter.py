"""Image conversion via Pillow (format + quality)."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps

from src.core.image._paths import unique_path

logger = logging.getLogger(__name__)

# Lossy formats whose quality slider makes sense, capped at 95 (Pillow accepts
# up to 100, but past 95 the file size grows fast for a barely-visible gain).
LOSSY_FMTS: frozenset[str] = frozenset({"jpg", "jpeg", "webp"})
# Also quality-aware, but honoring Pillow's full 0-100 AVIF range instead of
# the 95 cap above — AVIF doesn't have the same "95+ is pointless" behavior.
_FULL_RANGE_QUALITY_FMTS: frozenset[str] = frozenset({"avif"})

_PILLOW_FMT: dict[str, str] = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
    "tiff": "TIFF",
    "bmp": "BMP",
    "gif": "GIF",
    "ico": "ICO",
}

_OUT_EXT: dict[str, str] = {
    "jpg": "jpg",
    "jpeg": "jpg",  # normalize to .jpg
    "png": "png",
    "webp": "webp",
    "avif": "avif",
    "tiff": "tiff",
    "bmp": "bmp",
    "gif": "gif",
    "ico": "ico",
}


def convert_image(src: Path, out_dir: Path, fmt: str, quality: int = 90) -> Path:
    """Convert src → out_dir/{stem}.{ext}.

    Args:
        src: Source file.
        out_dir: Output directory.
        fmt: Target format (e.g. 'jpg', 'webp', 'png').
        quality: Quality for lossy formats — 1-95 for jpg/webp, 1-100 for avif
            (each format's own valid range in Pillow). Ignored otherwise.

    Returns:
        Path of the converted file.
    """
    fmt_key = fmt.lower().strip(".")
    pillow_fmt = _PILLOW_FMT.get(fmt_key, fmt_key.upper())
    out_ext = _OUT_EXT.get(fmt_key, fmt_key)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = unique_path(out_dir, src.stem, out_ext)

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # fix camera EXIF orientation

        if pillow_fmt == "JPEG":
            im = _ensure_rgb(im)  # JPEG can't carry an alpha channel

        im.save(
            out_path, format=pillow_fmt, **_save_kwargs(fmt_key, pillow_fmt, quality)
        )

    logger.info("[ok] Converted: %s -> %s", src.name, out_path.name)
    return out_path


def _ensure_rgb(im: Image.Image) -> Image.Image:
    """Flatten palette/alpha modes to opaque RGB over a white background.

    Shared by convert_image's JPEG branch and transform.py's _save/
    apply_filter_im/make_contact_sheet — JPEG can't carry alpha, and
    autocontrast/equalize/canvas-paste all need a plain RGB source.
    """
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    if im.mode != "RGB":
        return im.convert("RGB")
    return im


def _save_kwargs(fmt_key: str, pillow_fmt: str, quality: int) -> dict:
    """Pillow save() kwargs for a format: quality clamp, or PNG optimize."""
    if fmt_key in LOSSY_FMTS:
        return {"quality": max(1, min(95, quality))}
    if fmt_key in _FULL_RANGE_QUALITY_FMTS:
        return {"quality": max(0, min(100, quality))}
    if pillow_fmt == "PNG":
        return {"optimize": True}
    return {}
