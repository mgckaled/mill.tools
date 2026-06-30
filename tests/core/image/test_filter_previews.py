"""Unit tests for filter preview generation (core/image/filter_previews.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.core.image.filter_previews import generate_filter_previews

pytestmark = pytest.mark.unit

_NAMES = ["blur", "sharpen", "autocontrast", "equalize", "grayscale"]


def _src(tmp_path: Path) -> Path:
    p = tmp_path / "src.png"
    Image.new("RGB", (300, 200), (80, 140, 60)).save(p)
    return p


def test_returns_png_bytes_for_each_filter(tmp_path: Path) -> None:
    previews = generate_filter_previews(_src(tmp_path), _NAMES)
    assert set(previews) == set(_NAMES)
    for data in previews.values():
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_previews_are_downscaled(tmp_path: Path) -> None:
    previews = generate_filter_previews(_src(tmp_path), ["blur"], size=(64, 64))
    import io

    with Image.open(io.BytesIO(previews["blur"])) as im:
        assert im.width <= 64 and im.height <= 64


def test_unknown_filter_passthrough(tmp_path: Path) -> None:
    # apply_filter_im returns the image unchanged for unknown names → still valid PNG.
    previews = generate_filter_previews(_src(tmp_path), ["nope"])
    assert "nope" in previews
