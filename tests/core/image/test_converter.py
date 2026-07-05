"""Testes unitários — src/core/image/converter.py (PIL puro, sem ffmpeg)."""

import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def test_convert_jpg_to_png(session_jpg, out_dir):
    """Conversão JPEG → PNG deve produzir arquivo PNG válido."""
    from src.core.image.converter import convert_image

    out = convert_image(session_jpg, out_dir, fmt="png", quality=85)
    assert out.exists()
    assert out.suffix.lower() == ".png"
    with Image.open(out) as im:
        assert im.format == "PNG"


def test_convert_jpg_to_webp(session_jpg, out_dir):
    """Conversão JPEG → WebP deve produzir arquivo WebP."""
    from src.core.image.converter import convert_image

    out = convert_image(session_jpg, out_dir, fmt="webp", quality=80)
    assert out.exists()
    assert out.suffix.lower() == ".webp"


def test_convert_preserves_dimensions(session_jpg, out_dir):
    """Conversão de formato não deve alterar as dimensões da imagem."""
    from src.core.image.converter import convert_image

    with Image.open(session_jpg) as orig:
        orig_size = orig.size
    out = convert_image(session_jpg, out_dir, fmt="png", quality=85)
    with Image.open(out) as im:
        assert im.size == orig_size


def test_convert_rgba_to_jpg_flattens_alpha(tmp_path, out_dir):
    """PNG RGBA convertido para JPEG deve resultar em imagem RGB (sem canal alpha)."""
    from src.core.image.converter import convert_image

    png = tmp_path / "rgba.png"
    Image.new("RGBA", (50, 50), (255, 0, 0, 128)).save(png)
    out = convert_image(png, out_dir, fmt="jpg", quality=85)
    with Image.open(out) as im:
        assert im.mode == "RGB"


def test_convert_jpg_to_avif(session_jpg, out_dir):
    """Conversão JPEG → AVIF (nativo no Pillow) deve produzir arquivo válido."""
    from src.core.image.converter import convert_image

    out = convert_image(session_jpg, out_dir, fmt="avif", quality=90)
    assert out.exists()
    assert out.suffix.lower() == ".avif"
    with Image.open(out) as im:
        assert im.format == "AVIF"


def test_save_kwargs_jpg_webp_capped_at_95():
    """jpg/webp: quality acima de 95 é clampado (Pillow aceitaria até 100, mas o
    projeto prefere conter o crescimento de arquivo sem ganho visível)."""
    from src.core.image.converter import _save_kwargs

    assert _save_kwargs("jpg", "JPEG", 100) == {"quality": 95}
    assert _save_kwargs("webp", "WEBP", 0) == {"quality": 1}


def test_save_kwargs_avif_uses_full_0_100_range():
    """avif: quality respeita o range nativo do Pillow (0-100), sem o teto de 95."""
    from src.core.image.converter import _save_kwargs

    assert _save_kwargs("avif", "AVIF", 100) == {"quality": 100}
    assert _save_kwargs("avif", "AVIF", 0) == {"quality": 0}


def test_save_kwargs_png_optimizes():
    from src.core.image.converter import _save_kwargs

    assert _save_kwargs("png", "PNG", 90) == {"optimize": True}


def test_save_kwargs_other_format_is_empty():
    from src.core.image.converter import _save_kwargs

    assert _save_kwargs("bmp", "BMP", 90) == {}


def test_ensure_rgb_flattens_rgba_over_white():
    from src.core.image.converter import _ensure_rgb

    im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    out = _ensure_rgb(im)
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (255, 255, 255)


def test_ensure_rgb_passthrough_for_rgb():
    from src.core.image.converter import _ensure_rgb

    im = Image.new("RGB", (10, 10), (1, 2, 3))
    assert _ensure_rgb(im) is im
