"""Generate small filter previews for the GUI grid (pure, off-thread friendly).

Reuses ``transform.apply_filter_im`` so the preview matches the real output.
Returns ``{filter_name: png_bytes}`` from a downscaled copy of the source —
cheap enough to run for every filter on a background thread.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from src.core.image.transform import apply_filter_im


def generate_filter_previews(
    src: Path,
    names: list[str],
    size: tuple[int, int] = (120, 120),
) -> dict[str, bytes]:
    """Return PNG bytes for each named filter applied to a thumbnail of ``src``."""
    previews: dict[str, bytes] = {}
    with Image.open(src) as im0:
        base = ImageOps.exif_transpose(im0)
        base = base.copy()
        base.thumbnail(size, Image.Resampling.LANCZOS)
    for name in names:
        try:
            res = apply_filter_im(base.copy(), name)
            if res.mode not in ("RGB", "L"):
                res = res.convert("RGB")
            buf = io.BytesIO()
            res.save(buf, format="PNG")
            previews[name] = buf.getvalue()
        except Exception:
            continue
    return previews
