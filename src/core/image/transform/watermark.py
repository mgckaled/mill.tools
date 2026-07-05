"""Text/image/QR watermarking — 9-grid placement, tiling and rotation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from src.core.image.transform._shared import _hex_rgb, _out_path, _save


def _wm_coords(
    iw: int, ih: int, ww: int, wh: int, position: str, margin: int = 10
) -> tuple[int, int]:
    """9-grid placement from a position name like 'top-left'/'center'/'bottom-right'."""
    if "left" in position:
        x = margin
    elif "right" in position:
        x = iw - ww - margin
    else:
        x = (iw - ww) // 2
    if "top" in position:
        y = margin
    elif "bottom" in position:
        y = ih - wh - margin
    else:
        y = (ih - wh) // 2
    return x, y


def _qr_rgba(data: str) -> Image.Image:
    """Build an RGBA QR code image in memory (mirrors core/document/qr settings)."""
    import qrcode  # type: ignore[import-untyped]

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGBA")


def _build_wm_stamp(
    wm_mode: str,
    text: str,
    text_color: str,
    text_size: int,
    wm_path: Path | None,
    opacity: float,
    base_size: tuple[int, int],
) -> Image.Image | None:
    """Render the watermark content (text/image/qr) as a tight RGBA stamp."""
    iw, ih = base_size
    alpha = int(opacity * 255)

    if wm_mode == "text":
        if not text:
            return None
        try:
            font = ImageFont.load_default(size=text_size)
        except TypeError:
            font = ImageFont.load_default()
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bbox = probe.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        stamp = Image.new("RGBA", (max(1, tw + 4), max(1, th + 4)), (0, 0, 0, 0))
        ImageDraw.Draw(stamp).text(
            (2 - bbox[0], 2 - bbox[1]),
            text,
            font=font,
            fill=(*_hex_rgb(text_color), alpha),
        )
        return stamp

    logo: Image.Image | None = None
    if wm_mode == "qr":
        if not text:
            return None
        logo = _qr_rgba(text)
    elif wm_path and wm_path.exists():
        with Image.open(wm_path) as wm:
            logo = wm.convert("RGBA")
    if logo is None:
        return None

    logo.thumbnail((max(1, iw // 4), max(1, ih // 4)), Image.Resampling.LANCZOS)
    r, g, b, a = logo.split()
    a = a.point(lambda p: int(p * alpha / 255))
    logo.putalpha(a)
    return logo


def _tile_watermark(base: Image.Image, stamp: Image.Image) -> Image.Image:
    """Repeat the stamp across the whole image with spacing."""
    iw, ih = base.size
    sw, sh = stamp.size
    gap_x = sw + max(sw // 2, 20)
    gap_y = sh + max(sh // 2, 20)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    y = 0
    while y < ih:
        x = 0
        while x < iw:
            layer.alpha_composite(stamp, (x, y))
            x += gap_x
        y += gap_y
    return Image.alpha_composite(base, layer)


def watermark_image(
    src: Path,
    out_dir: Path,
    *,
    wm_mode: str,
    text: str,
    text_color: str,
    text_size: int,
    wm_path: Path | None,
    position: str,
    opacity: float,
    out_fmt: str | None,
    quality: int,
    rotation: int = 0,
) -> Path:
    """Apply a text, image or QR watermark; 9-grid, tiling and rotation."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        base = im.convert("RGBA")
        iw, ih = base.size

        stamp = _build_wm_stamp(
            wm_mode, text, text_color, text_size, wm_path, opacity, (iw, ih)
        )
        if stamp is not None:
            if rotation:
                stamp = stamp.rotate(
                    rotation, expand=True, resample=Image.Resampling.BICUBIC
                )
            if position == "tile":
                base = _tile_watermark(base, stamp)
            else:
                sw, sh = stamp.size
                x, y = _wm_coords(iw, ih, sw, sh, position)
                base.alpha_composite(stamp, (x, y))

        _save(base, out_path, out_fmt, quality)
    return out_path
