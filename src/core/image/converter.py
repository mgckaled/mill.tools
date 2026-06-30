"""Conversão de imagens via Pillow (formato + qualidade)."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Formatos cujo slider de qualidade faz sentido (com perda)
LOSSY_FMTS: frozenset[str] = frozenset({"jpg", "jpeg", "webp"})

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
    "jpeg": "jpg",  # normaliza para .jpg
    "png": "png",
    "webp": "webp",
    "avif": "avif",
    "tiff": "tiff",
    "bmp": "bmp",
    "gif": "gif",
    "ico": "ico",
}


def convert_image(src: Path, out_dir: Path, fmt: str, quality: int = 90) -> Path:
    """Converte src → out_dir/{stem}.{ext}.

    Args:
        src: Arquivo de origem.
        out_dir: Diretório de saída.
        fmt: Formato alvo (ex.: 'jpg', 'webp', 'png').
        quality: Qualidade 50–100 para formatos lossy (jpg/webp). Ignorado nos demais.

    Returns:
        Path do arquivo convertido.
    """
    fmt_key = fmt.lower().strip(".")
    pillow_fmt = _PILLOW_FMT.get(fmt_key, fmt_key.upper())
    out_ext = _OUT_EXT.get(fmt_key, fmt_key)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _unique_path(out_dir, src.stem, out_ext)

    with Image.open(src) as im:
        # Corrige orientação EXIF (fotos de câmera)
        im = ImageOps.exif_transpose(im)

        # JPEG não suporta canal alpha — achata sobre fundo branco
        if pillow_fmt == "JPEG":
            if im.mode == "P":
                im = im.convert("RGBA")
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")

        save_kwargs: dict = {}
        if fmt_key in LOSSY_FMTS:
            save_kwargs["quality"] = max(1, min(95, quality))
        elif pillow_fmt == "PNG":
            save_kwargs["optimize"] = True

        im.save(out_path, format=pillow_fmt, **save_kwargs)

    logger.info("[✓] Convertido: %s → %s", src.name, out_path.name)
    return out_path


def _unique_path(directory: Path, stem: str, ext: str) -> Path:
    """Retorna path sem colisão, anexando _1, _2… se necessário."""
    candidate = directory / f"{stem}.{ext}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}.{ext}"
        if not candidate.exists():
            return candidate
        counter += 1
