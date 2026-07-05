"""Download de imagens via URL (urllib stdlib)."""

from __future__ import annotations

import io
import logging
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from src.core.image._paths import unique_path

logger = logging.getLogger(__name__)

_EXT_BY_FORMAT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "TIFF": ".tiff",
    "BMP": ".bmp",
    "ICO": ".ico",
    "AVIF": ".avif",
}


def download_image(url: str, out_dir: Path, timeout: float = 15.0) -> Path:
    """GET HTTP direto da imagem. Salva em out_dir.

    Valida que é imagem abrindo com Pillow; levanta ValueError com mensagem
    amigável se for HTML/404/não-imagem.

    Args:
        url: URL direta da imagem.
        out_dir: Diretório de destino.
        timeout: Timeout da requisição em segundos.

    Returns:
        Path do arquivo salvo.

    Raises:
        ValueError: Se a URL não retornar uma imagem válida.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mill-tools/1.0 (image-downloader)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:
        raise ValueError(f"Falha ao baixar '{url}': {exc}") from exc

    # Valida que o conteúdo é uma imagem real
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
    except Exception as exc:
        raise ValueError(
            f"URL não contém uma imagem válida (possível HTML/404): {exc}"
        ) from exc

    # Nome do arquivo: tenta extrair da URL, senão usa formato detectado
    parsed_name = Path(urlparse(url).path).name
    if parsed_name and "." in parsed_name:
        name = parsed_name
    else:
        ext = _EXT_BY_FORMAT.get(fmt or "", ".img")
        name = f"image{ext}"

    out_path = unique_path(out_dir, Path(name).stem, Path(name).suffix)
    out_path.write_bytes(data)
    logger.info("[ok] Image downloaded: %s", out_path.name)
    return out_path
