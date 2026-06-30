"""Unit tests for the advanced watermark (core/image/transform.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.core.image.transform import _wm_coords, watermark_image

pytestmark = pytest.mark.unit


def _src(tmp_path: Path) -> Path:
    p = tmp_path / "src.png"
    Image.new("RGB", (400, 300), (40, 40, 40)).save(p)
    return p


def test_9grid_corners_and_center() -> None:
    # 100x50 stamp in a 1000x800 image, margin 10.
    assert _wm_coords(1000, 800, 100, 50, "top-left") == (10, 10)
    assert _wm_coords(1000, 800, 100, 50, "top-right") == (890, 10)
    assert _wm_coords(1000, 800, 100, 50, "bottom-left") == (10, 740)
    assert _wm_coords(1000, 800, 100, 50, "bottom-right") == (890, 740)
    assert _wm_coords(1000, 800, 100, 50, "center") == (450, 375)
    assert _wm_coords(1000, 800, 100, 50, "top-center") == (450, 10)
    assert _wm_coords(1000, 800, 100, 50, "middle-left") == (10, 375)


def test_text_watermark_changes_pixels(tmp_path: Path) -> None:
    src = _src(tmp_path)
    out = watermark_image(
        src,
        tmp_path / "out",
        wm_mode="text",
        text="(c) Me",
        text_color="#ffffff",
        text_size=24,
        wm_path=None,
        position="bottom-right",
        opacity=0.8,
        out_fmt=None,
        quality=90,
    )
    assert out.exists()
    with Image.open(src) as a, Image.open(out) as b:
        assert a.convert("RGB").tobytes() != b.convert("RGB").tobytes()


def test_qr_watermark_runs(tmp_path: Path) -> None:
    src = _src(tmp_path)
    out = watermark_image(
        src,
        tmp_path / "out",
        wm_mode="qr",
        text="https://example.com",
        text_color="#ffffff",
        text_size=24,
        wm_path=None,
        position="top-left",
        opacity=1.0,
        out_fmt=None,
        quality=90,
    )
    assert out.exists()


def test_tile_and_rotation_run(tmp_path: Path) -> None:
    src = _src(tmp_path)
    out = watermark_image(
        src,
        tmp_path / "out",
        wm_mode="text",
        text="x",
        text_color="#ffffff",
        text_size=20,
        wm_path=None,
        position="tile",
        opacity=0.5,
        out_fmt=None,
        quality=90,
        rotation=30,
    )
    assert out.exists()
