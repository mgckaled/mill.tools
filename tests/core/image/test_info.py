"""Testes unitários — src/core/image/info.py (PIL puro, sem ffmpeg)."""

import io

import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def test_image_info_returns_dict(session_jpg):
    """image_info deve retornar dict com campos de dimensão corretos."""
    from src.core.image.info import image_info

    info = image_info(session_jpg)
    assert isinstance(info, dict)
    assert "width" in info
    assert "height" in info
    assert info["width"] == 640
    assert info["height"] == 480


def test_image_info_format_field(session_jpg):
    """Campo 'format' deve indicar JPEG."""
    from src.core.image.info import image_info

    info = image_info(session_jpg)
    assert info.get("format", "").upper() in ("JPEG", "JPG")


def test_thumbnail_bytes_returns_bytes(session_jpg):
    """thumbnail_bytes deve retornar bytes não vazios."""
    from src.core.image.info import thumbnail_bytes

    result = thumbnail_bytes(session_jpg, max_px=64)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_thumbnail_bytes_is_valid_image(session_jpg):
    """Bytes retornados devem ser uma imagem PNG válida com dimensões reduzidas."""
    from src.core.image.info import thumbnail_bytes

    data = thumbnail_bytes(session_jpg, max_px=64)
    with Image.open(io.BytesIO(data)) as thumb:
        assert thumb.width <= 64
        assert thumb.height <= 64
