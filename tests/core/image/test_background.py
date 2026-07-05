"""Unit tests for src/core/image/background.py (rembg mockado, sem [ai-image])."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
from PIL import Image

pytestmark = pytest.mark.unit


def _fake_rembg(mocker) -> MagicMock:
    """Patch the lazy `import rembg` with an identity pass-through remove().

    remove() just adds an alpha channel (RGBA) without cutting anything out —
    enough to exercise replace_background's own logic (exif_transpose, mode
    dispatch, save) without the real rembg/onnxruntime model.
    """
    fake = MagicMock()
    fake.remove.side_effect = lambda im, session=None: im.convert("RGBA")
    mocker.patch.dict(sys.modules, {"rembg": fake})
    return fake


def _exif_oriented_jpeg(tmp_path, size=(60, 40), orientation=6):
    """A landscape JPEG carrying an EXIF Orientation tag (274)."""
    path = tmp_path / "photo.jpg"
    img = Image.new("RGB", size, (10, 20, 30))
    exif = img.getexif()
    exif[274] = orientation
    img.save(path, exif=exif)
    return path


def test_replace_background_applies_exif_transpose(tmp_path, mocker):
    """A landscape photo with Orientation=6 must come out transposed (40x60),
    not raw (60x40) — matches the other 11 transforms, all of which already
    call ImageOps.exif_transpose before processing."""
    from src.core.image.background import replace_background

    _fake_rembg(mocker)
    src = _exif_oriented_jpeg(tmp_path)

    out = replace_background(
        src, tmp_path / "out", session=None, bg_mode="color", bg_color="#ffffff"
    )

    with Image.open(out) as im:
        assert im.size == (40, 60)


def test_replace_background_image_mode_missing_bg_image_logs_warning(
    tmp_path, mocker, caplog
):
    """bg_mode='image' without a valid bg_image falls back to solid color, but
    must log a warning instead of silently doing something the user didn't ask for."""
    from src.core.image.background import replace_background

    _fake_rembg(mocker)
    src = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 40), (0, 0, 0)).save(src)

    with caplog.at_level("WARNING"):
        out = replace_background(
            src,
            tmp_path / "out",
            session=None,
            bg_mode="image",
            bg_image=None,
            bg_color="#ff0000",
        )

    assert out.exists()
    assert "bg_mode='image'" in caplog.text
