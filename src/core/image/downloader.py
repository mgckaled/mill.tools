"""Image download via URL (urllib stdlib)."""

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

# A single image should never be this large — caps memory use against a
# misbehaving/malicious server (whole response is read into RAM below).
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def download_image(url: str, out_dir: Path, timeout: float = 15.0) -> Path:
    """Direct HTTP GET of the image. Saves it into out_dir.

    Validates that the content is an image by opening it with Pillow; raises
    ValueError with a friendly message if it's HTML/404/not an image.

    Args:
        url: Direct image URL.
        out_dir: Destination directory.
        timeout: Request timeout in seconds.

    Returns:
        Path of the saved file.

    Raises:
        ValueError: If the URL doesn't return a valid image, or the image
            exceeds ``_MAX_DOWNLOAD_BYTES``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mill-tools/1.0 (image-downloader)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > _MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"Imagem em '{url}' excede o limite de "
                    f"{_MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB "
                    f"(Content-Length={content_length})"
                )
            data = resp.read(_MAX_DOWNLOAD_BYTES + 1)
            if len(data) > _MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"Imagem em '{url}' excede o limite de "
                    f"{_MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB"
                )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Falha ao baixar '{url}': {exc}") from exc

    # Validate that the content is a real image
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
    except Exception as exc:
        raise ValueError(
            f"URL não contém uma imagem válida (possível HTML/404): {exc}"
        ) from exc

    # Filename: try extracting it from the URL, else use the detected format
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
