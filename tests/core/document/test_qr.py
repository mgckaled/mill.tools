"""Unit tests for src/core/document/qr.py."""

import pytest

pytestmark = pytest.mark.unit


def test_generate_qr_creates_image_file(out_dir):
    from src.core.document.qr import generate_qr

    out = generate_qr("hello world", out_dir)
    assert out.exists()
    assert out.stat().st_size > 100


def test_generate_qr_png_format(out_dir):
    from src.core.document.qr import generate_qr

    out = generate_qr("test", out_dir, fmt="png")
    assert out.suffix == ".png"


def test_generate_qr_respects_size_parameter(out_dir):
    from src.core.document.qr import generate_qr
    from PIL import Image

    out = generate_qr("https://example.com", out_dir, size=300, fmt="png")
    with Image.open(out) as img:
        w, h = img.size
    # Allow ±20% of the requested size
    assert 180 <= w <= 420
    assert 180 <= h <= 420


def test_generate_qr_url_input(out_dir):
    from src.core.document.qr import generate_qr

    out = generate_qr("https://example.com/path?q=1", out_dir, fmt="png")
    assert out.exists()


def test_generate_qr_plain_text_input(out_dir):
    from src.core.document.qr import generate_qr

    out = generate_qr("Texto simples para QR code", out_dir, fmt="png")
    assert out.exists()
