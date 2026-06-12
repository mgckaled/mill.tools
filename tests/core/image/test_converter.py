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
