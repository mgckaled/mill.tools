"""Operações de manipulação de imagens via Pillow (puro, sem Flet)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from src.core.image.converter import LOSSY_FMTS, _PILLOW_FMT


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _out_path(src: Path, out_dir: Path, out_fmt: str | None) -> Path:
    """Caminho de saída sem colisão. out_fmt=None → usa extensão de src."""
    ext = out_fmt.lower().strip(".") if out_fmt else src.suffix.lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate = out_dir / f"{src.stem}.{ext}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = out_dir / f"{src.stem}_{counter}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def _save(im: Image.Image, path: Path, out_fmt: str | None, quality: int) -> None:
    """Salva im em path replicando a lógica de converter.py."""
    ext = path.suffix.lstrip(".").lower()
    pillow_fmt = _PILLOW_FMT.get(ext, ext.upper())
    if pillow_fmt == "JPEG":
        if im.mode == "P":
            im = im.convert("RGBA")
        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
    kwargs: dict = {}
    if ext in LOSSY_FMTS:
        kwargs["quality"] = max(1, min(95, quality))
    elif pillow_fmt == "PNG":
        kwargs["optimize"] = True
    im.save(path, format=pillow_fmt, **kwargs)


def _hex_rgb(color: str) -> tuple[int, int, int]:
    """'#rrggbb' ou '#rgb' → (r, g, b)."""
    c = color.strip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _ensure_rgb(im: Image.Image) -> Image.Image:
    """Converte para RGB achando alpha sobre branco."""
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    if im.mode != "RGB":
        return im.convert("RGB")
    return im


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

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
    """Redimensiona src. Modos: contain, exact, scale_pct."""
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
) -> Path:
    """Recorta src. Modos: manual, ratio, autotrim."""
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
    """Rotaciona e/ou espelha src."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        if exif_auto:
            im = ImageOps.exif_transpose(im)
        if angle:
            im = im.rotate(-angle, expand=True)  # sentido horário
        if flip_h:
            im = ImageOps.mirror(im)
        if flip_v:
            im = ImageOps.flip(im)
        _save(im, out_path, out_fmt, quality)
    return out_path


def _wm_coords(iw: int, ih: int, ww: int, wh: int, position: str, margin: int = 10) -> tuple[int, int]:
    match position:
        case "top-left":    return margin, margin
        case "top-right":   return iw - ww - margin, margin
        case "bottom-left": return margin, ih - wh - margin
        case "center":      return (iw - ww) // 2, (ih - wh) // 2
        case _:             return iw - ww - margin, ih - wh - margin  # bottom-right


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
) -> Path:
    """Aplica marca d'água de texto ou imagem sobre src."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        base = im.convert("RGBA")
        iw, ih = base.size

        if wm_mode == "text" and text:
            try:
                font = ImageFont.load_default(size=text_size)
            except TypeError:
                font = ImageFont.load_default()
            layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            rgb = _hex_rgb(text_color)
            alpha = int(opacity * 255)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x, y = _wm_coords(iw, ih, tw, th, position)
            draw.text((x, y), text, font=font, fill=(*rgb, alpha))
            base = Image.alpha_composite(base, layer)

        elif wm_mode == "image" and wm_path and wm_path.exists():
            with Image.open(wm_path) as wm:
                max_w = max(1, iw // 4)
                max_h = max(1, ih // 4)
                wm.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                wm = wm.convert("RGBA")
                ww, wh = wm.size
                x, y = _wm_coords(iw, ih, ww, wh, position)
                alpha_val = int(opacity * 255)
                r, g, b, a = wm.split()
                a = a.point(lambda p: int(p * alpha_val / 255))
                wm.putalpha(a)
                base.paste(wm, (x, y), wm)

        _save(base, out_path, out_fmt, quality)
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
    """Adiciona borda sólida em torno de src."""
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
    """Ajusta brilho, contraste, saturação e nitidez de src."""
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


def apply_filter(
    src: Path,
    out_dir: Path,
    *,
    filter_type: str,
    out_fmt: str | None,
    quality: int,
) -> Path:
    """Aplica filtro de imagem: blur, sharpen, autocontrast, equalize, grayscale."""
    out_path = _out_path(src, out_dir, out_fmt)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        match filter_type:
            case "blur":         im = im.filter(ImageFilter.BLUR)
            case "sharpen":      im = im.filter(ImageFilter.SHARPEN)
            case "autocontrast": im = ImageOps.autocontrast(_ensure_rgb(im))
            case "equalize":     im = ImageOps.equalize(_ensure_rgb(im))
            case "grayscale":    im = ImageOps.grayscale(im)
        _save(im, out_path, out_fmt, quality)
    return out_path


def make_favicon(src: Path, out_dir: Path, *, sizes: list[int]) -> Path:
    """Gera .ico com múltiplas resoluções embutidas. Ignora out_fmt."""
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
    """Monta grade de miniaturas (N→1). Arquivos inválidos são ignorados."""
    import logging
    _log = logging.getLogger(__name__)

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
            _log.warning("[!] Ignorando arquivo inválido: %s", s.name)

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
