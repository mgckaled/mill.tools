"""EXIF metadata control for the image module (pure Pillow, torch-free).

Applied as an additive post-process on the output file so the 11 transform
functions keep their signatures untouched. Modes: preserve | strip | strip_gps
| inject. "preserve" copies the source EXIF onto the output (transforms drop it
by default); all copying modes clear the Orientation tag because the transforms
already bake orientation into pixels via ``ImageOps.exif_transpose`` — re-writing
it would double-rotate on display.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import ExifTags, Image

logger = logging.getLogger(__name__)

# Formats that can carry an EXIF block on save.
_EXIF_FMTS = frozenset({"jpg", "jpeg", "webp", "tiff", "tif", "png"})

_ORIENTATION = ExifTags.Base.Orientation
_GPS_IFD = ExifTags.IFD.GPSInfo
_INJECT_TAGS = {
    "artist": ExifTags.Base.Artist,
    "copyright": ExifTags.Base.Copyright,
    "description": ExifTags.Base.ImageDescription,
}


def read_summary(path: Path) -> dict:
    """Return a human-readable EXIF dict (skips binary values); adds a GPS flag."""
    summary: dict = {}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            for tag, value in exif.items():
                if isinstance(value, bytes):
                    continue
                name = ExifTags.TAGS.get(tag, str(tag))
                summary[name] = value
            summary["GPS"] = _GPS_IFD in exif
    except Exception as exc:  # pragma: no cover - corrupt/unsupported file
        logger.debug("[d] read_summary failed for %s: %s", path, exc)
    return summary


def _load_src_exif(src: Path) -> "Image.Exif":
    """Load the source EXIF and drop Orientation (pixels are already transposed)."""
    with Image.open(src) as im:
        exif = im.getexif()
    if _ORIENTATION in exif:
        del exif[_ORIENTATION]
    return exif


def _has_entries(exif: "Image.Exif") -> bool:
    """True if the EXIF block holds any tag worth writing."""
    return len(exif) > 0


def resolve_exif(src: Path, mode: str, fields: dict | None) -> "Image.Exif | None":
    """Compute the EXIF block to write on the output for the given mode.

    Returns None when the output should carry no EXIF (mode 'strip').
    """
    if mode == "strip":
        return None
    exif = _load_src_exif(src)
    if mode == "strip_gps":
        if _GPS_IFD in exif:
            del exif[_GPS_IFD]
    elif mode == "inject":
        for key, tag in _INJECT_TAGS.items():
            value = (fields or {}).get(key, "").strip() if fields else ""
            if value:
                exif[tag] = value
    return exif


def apply_to_file(
    out_path: Path, src: Path, mode: str, fields: dict | None = None
) -> None:
    """Post-process the output file to preserve/strip/inject EXIF.

    No-op when there is nothing to change or the format can't carry EXIF.
    Degrades gracefully (logs at debug) on any Pillow error.
    """
    ext = out_path.suffix.lower().lstrip(".")
    if ext not in _EXIF_FMTS:
        return

    if mode == "strip":
        # Transforms don't write EXIF, so the output usually has none already.
        try:
            with Image.open(out_path) as im:
                if not _has_entries(im.getexif()):
                    return
        except Exception:  # pragma: no cover
            return
        exif = None
    else:
        exif = resolve_exif(src, mode, fields)
        if exif is None or not _has_entries(exif):
            return

    try:
        with Image.open(out_path) as im:
            im.load()
            params: dict = {}
            if ext in ("jpg", "jpeg"):
                params["quality"] = (
                    "keep"  # retain quantization tables, no visible re-encode
                )
            if exif is not None:
                params["exif"] = exif
            im.save(out_path, **params)
    except Exception as exc:
        logger.debug("[d] apply_to_file failed for %s: %s", out_path, exc)
