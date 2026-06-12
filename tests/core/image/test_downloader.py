"""Unit tests for src/core/image/downloader.py (urllib mockado)."""
import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def _png_bytes(width: int = 32, height: int = 32) -> bytes:
    """Build a valid PNG image as bytes (no network/IO needed)."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _jpg_bytes(width: int = 32, height: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(0, 0, 255)).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_urlopen(payload: bytes) -> MagicMock:
    """Returns a MagicMock that behaves like urlopen's context manager (reusable)."""
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = payload
    cm.__exit__.return_value = False
    return cm


def test_download_image_saves_png(mocker, tmp_path, out_dir):
    from src.core.image.downloader import download_image

    mocker.patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(_png_bytes()),
    )
    out = download_image("https://example.com/img.png", out_dir)
    assert out.exists()
    assert out.suffix.lower() == ".png"


def test_download_image_uses_url_filename_when_present(mocker, out_dir):
    from src.core.image.downloader import download_image

    mocker.patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(_jpg_bytes()),
    )
    out = download_image("https://example.com/path/banner.jpg", out_dir)
    # URL has a filename with extension → reused verbatim
    assert out.name == "banner.jpg"


def test_download_image_falls_back_to_image_ext_when_url_lacks_filename(mocker, out_dir):
    from src.core.image.downloader import download_image

    mocker.patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(_png_bytes()),
    )
    # URL path "/" — no parsed name; downloader uses _EXT_BY_FORMAT
    out = download_image("https://example.com/", out_dir)
    assert out.name == "image.png"


def test_download_image_avoids_collisions(mocker, out_dir):
    from src.core.image.downloader import download_image

    mocker.patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(_png_bytes()),
    )
    first = download_image("https://example.com/x.png", out_dir)
    second = download_image("https://example.com/x.png", out_dir)
    assert first.name == "x.png"
    assert second.name == "x_1.png"
    assert first != second


def test_download_image_html_content_raises_value_error(mocker, out_dir):
    from src.core.image.downloader import download_image

    html = b"<!DOCTYPE html><html><body>Not an image</body></html>"
    mocker.patch(
        "urllib.request.urlopen",
        return_value=_fake_urlopen(html),
    )
    with pytest.raises(ValueError, match="imagem válida"):
        download_image("https://example.com/page.html", out_dir)


def test_download_image_network_error_raises_value_error(mocker, out_dir):
    from src.core.image.downloader import download_image

    mocker.patch(
        "urllib.request.urlopen",
        side_effect=ConnectionError("simulated network failure"),
    )
    with pytest.raises(ValueError, match="Falha ao baixar"):
        download_image("https://example.com/x.png", out_dir)
