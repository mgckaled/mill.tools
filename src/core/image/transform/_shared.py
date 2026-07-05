"""Private IO/format helpers shared by ops.py and watermark.py."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.core.image._paths import unique_path
from src.core.image.converter import _ensure_rgb as _ensure_rgb
from src.core.image.converter import _PILLOW_FMT, _save_kwargs


def _out_path(src: Path, out_dir: Path, out_fmt: str | None) -> Path:
    """Output path with no collision. out_fmt=None → reuse src's extension."""
    ext = out_fmt.lower().strip(".") if out_fmt else src.suffix.lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    out_dir.mkdir(parents=True, exist_ok=True)
    return unique_path(out_dir, src.stem, ext)


def _save(im: Image.Image, path: Path, out_fmt: str | None, quality: int) -> None:
    """Save im to path, flattening alpha for JPEG and applying converter's
    quality/optimize rules (single source of truth for both, see converter.py)."""
    ext = path.suffix.lstrip(".").lower()
    pillow_fmt = _PILLOW_FMT.get(ext, ext.upper())
    if pillow_fmt == "JPEG":
        im = _ensure_rgb(im)
    im.save(path, format=pillow_fmt, **_save_kwargs(ext, pillow_fmt, quality))


def _hex_rgb(color: str) -> tuple[int, int, int]:
    """'#rrggbb' or '#rgb' → (r, g, b)."""
    c = color.strip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
