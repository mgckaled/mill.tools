"""Resize, crop, rotate, border, adjust, filter, favicon and contact-sheet ops."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from src.core.image.transform._shared import _ensure_rgb, _hex_rgb, _out_path, _save

logger = logging.getLogger(__name__)


def resize_image(
    src: Path,
    out_dir: Path,
    *,
    resize_mode: str,
    width: int | None,
    height: int | None,
    scale_pct: float,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Resize src. Modes: contain, exact, scale_pct."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        match resize_mode:
            case "scale_pct":
                factor = max(0.01, scale_pct / 100)
                im = ImageOps.scale(im, factor, resample=Image.Resampling.LANCZOS)
            case "contain":
                w = width or im.width
                h = height or im.height
                im = ImageOps.contain(im, (w, h), method=Image.Resampling.LANCZOS)
            case "exact":
                w = width or im.width
                h = height or im.height
                im = im.resize((w, h), resample=Image.Resampling.LANCZOS)
        _save(im, out_path, out_fmt, quality)
    return out_path


def crop_image(
    src: Path,
    out_dir: Path,
    *,
    crop_mode: str,
    left: int,
    top: int,
    crop_width: int,
    crop_height: int,
    ratio: str,
    trim_color: str,
    out_fmt: str | None,
    quality: int,
    focal_x: float = 0.5,
    focal_y: float = 0.5,
) -> Path:
    """Crop src. Modes: manual, ratio, autotrim, focal."""
    from src.core.image.smart_crop import focal_crop_box

    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        match crop_mode:
            case "manual":
                iw, ih = im.size
                x1 = max(0, min(left, iw))
                y1 = max(0, min(top, ih))
                x2 = min(iw, x1 + crop_width) if crop_width > 0 else iw
                y2 = min(ih, y1 + crop_height) if crop_height > 0 else ih
                im = im.crop((x1, y1, x2, y2))
            case "ratio":
                rw, rh = (int(x) for x in ratio.split(":"))
                iw, ih = im.size
                target_h = int(iw * rh / rw)
                target_w = iw
                if target_h > ih:
                    target_h = ih
                    target_w = int(ih * rw / rh)
                im = ImageOps.fit(im, (target_w, target_h), centering=(0.5, 0.5))
            case "autotrim":
                rgb = _hex_rgb(trim_color)
                bg = Image.new("RGB", im.size, rgb)
                diff = ImageChops.difference(_ensure_rgb(im), bg)
                bbox = diff.getbbox()
                if bbox:
                    im = im.crop(bbox)
            case "focal":
                rw, rh = (int(x) for x in ratio.split(":"))
                box = focal_crop_box(im.width, im.height, rw / rh, focal_x, focal_y)
                im = im.crop(box)
        _save(im, out_path, out_fmt, quality)
    return out_path


def rotate_image(
    src: Path,
    out_dir: Path,
    *,
    angle: int,
    flip_h: bool,
    flip_v: bool,
    exif_auto: bool,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Rotate and/or mirror src."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        if exif_auto:
            im = ImageOps.exif_transpose(im)
        if angle:
            im = im.rotate(-angle, expand=True)  # clockwise
        if flip_h:
            im = ImageOps.mirror(im)
        if flip_v:
            im = ImageOps.flip(im)
        _save(im, out_path, out_fmt, quality)
    return out_path


def add_border(
    src: Path,
    out_dir: Path,
    *,
    padding: int,
    color: str,
    fill_alpha: bool,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Add a solid border around src."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if fill_alpha and im.mode in ("RGBA", "LA", "P"):
            if im.mode == "P":
                im = im.convert("RGBA")
            rgb = _hex_rgb(color)
            bg = Image.new("RGB", im.size, rgb)
            if im.mode in ("RGBA", "LA"):
                bg.paste(im, mask=im.split()[-1])
            im = bg
        im = ImageOps.expand(im, border=padding, fill=color)
        _save(im, out_path, out_fmt, quality)
    return out_path


def adjust_image(
    src: Path,
    out_dir: Path,
    *,
    brightness: float,
    contrast: float,
    color: float,
    sharpness: float,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Adjust brightness, contrast, saturation and sharpness of src."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        for Enhancer, val in [
            (ImageEnhance.Brightness, brightness),
            (ImageEnhance.Contrast, contrast),
            (ImageEnhance.Color, color),
            (ImageEnhance.Sharpness, sharpness),
        ]:
            if val != 1.0:
                im = Enhancer(im).enhance(val)
        _save(im, out_path, out_fmt, quality)
    return out_path


def apply_filter_im(im: Image.Image, filter_type: str) -> Image.Image:
    """Apply a named filter to an in-memory image (pure). Reused by previews."""
    match filter_type:
        case "blur":
            return im.filter(ImageFilter.BLUR)
        case "sharpen":
            return im.filter(ImageFilter.SHARPEN)
        case "autocontrast":
            return ImageOps.autocontrast(_ensure_rgb(im))
        case "equalize":
            return ImageOps.equalize(_ensure_rgb(im))
        case "grayscale":
            return ImageOps.grayscale(im)
    return im


def apply_filter(
    src: Path,
    out_dir: Path,
    *,
    filter_type: str,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Apply an image filter: blur, sharpen, autocontrast, equalize, grayscale."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        im = apply_filter_im(im, filter_type)
        _save(im, out_path, out_fmt, quality)
    return out_path


def make_favicon(src: Path, out_dir: Path, *, sizes: list[int]) -> Path:
    """Generate a multi-resolution .ico. Ignores out_fmt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _out_path(src, out_dir, "ico")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        iw, ih = im.size
        valid = [(s, s) for s in sizes if s <= min(iw, ih)]
        if not valid:
            valid = [(min(iw, ih), min(iw, ih))]
        im.save(out_path, format="ICO", sizes=valid)
    return out_path


def make_contact_sheet(
    sources: list[Path],
    out_dir: Path,
    *,
    cols: int,
    thumb_size: int,
    gap: int,
    bg_color: str,
    out_fmt: str,
    quality: int,
) -> Path:
    """Build an N→1 thumbnail grid. Invalid files are ignored."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = out_fmt.lower().strip(".") if out_fmt else "png"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"contact_sheet_{ts}.{ext}"

    valid: list[Path] = []
    for s in sources:
        try:
            with Image.open(s) as _chk:
                _chk.verify()
            valid.append(s)
        except Exception:
            logger.warning("[!] Ignoring invalid file: %s", s.name)

    if not valid:
        raise ValueError("Nenhum arquivo válido para montar a colagem.")

    rows = -(-len(valid) // cols)
    cw = cols * thumb_size + (cols + 1) * gap
    ch = rows * thumb_size + (rows + 1) * gap
    canvas = Image.new("RGB", (cw, ch), bg_color)

    for i, path in enumerate(valid):
        col_i = i % cols
        row_i = i // cols
        x = gap + col_i * (thumb_size + gap)
        y = gap + row_i * (thumb_size + gap)
        try:
            with Image.open(path) as im:
                im = _ensure_rgb(im)
                im.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
                canvas.paste(im, (x, y))
        except Exception:
            pass

    _save(canvas, out_path, out_fmt, quality)
    return out_path
