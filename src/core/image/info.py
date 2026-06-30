"""Informações e miniatura de imagens via Pillow."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image


def image_info(path: Path) -> dict:
    """Retorna {'width','height','format','mode','size_bytes'} via Pillow (lazy open)."""
    with Image.open(path) as im:
        return {
            "width": im.width,
            "height": im.height,
            "format": im.format or path.suffix.lstrip(".").upper(),
            "mode": im.mode,
            "size_bytes": path.stat().st_size,
        }


def thumbnail_bytes(path: Path, max_px: int = 600, fmt: str = "PNG") -> bytes:
    """Miniatura para o visor — Image.thumbnail() + salva em buffer. NUNCA full-res."""
    with Image.open(path) as im:
        im = im.copy()
        im.thumbnail((max_px, max_px))
        if fmt == "JPEG" and im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format=fmt)
        return buf.getvalue()
