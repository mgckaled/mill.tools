"""Unit tests for EXIF metadata control (core/image/exif.py)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import ExifTags, Image

from src.core.image import exif

pytestmark = pytest.mark.unit


def _jpg_with_exif(path: Path) -> Path:
    """Create a JPEG carrying Artist, Orientation and a GPS sub-IFD."""
    im = Image.new("RGB", (32, 24), (120, 60, 30))
    ex = im.getexif()
    ex[ExifTags.Base.Artist] = "Alice"
    ex[ExifTags.Base.Orientation] = 6
    ex[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N"}
    im.save(path, format="JPEG", exif=ex)
    return path


def _summary(path: Path) -> dict:
    return exif.read_summary(path)


def test_read_summary_detects_artist_and_gps(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    summary = _summary(src)
    assert summary.get("Artist") == "Alice"
    assert summary.get("GPS") is True


def test_resolve_strip_returns_none(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    assert exif.resolve_exif(src, "strip", None) is None


def test_resolve_drops_orientation(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    resolved = exif.resolve_exif(src, "preserve", None)
    assert ExifTags.Base.Orientation not in resolved


def test_apply_strip_removes_all_metadata(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    shutil.copy2(src, out)
    exif.apply_to_file(out, src, "strip", None)
    summary = _summary(out)
    assert "Artist" not in summary
    assert summary.get("GPS") is False


def test_apply_strip_gps_keeps_artist(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    shutil.copy2(src, out)
    exif.apply_to_file(out, src, "strip_gps", None)
    summary = _summary(out)
    assert summary.get("Artist") == "Alice"
    assert summary.get("GPS") is False


def test_apply_inject_writes_copyright(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    shutil.copy2(src, out)
    exif.apply_to_file(
        out, src, "inject", {"copyright": "(c) Me", "artist": "", "description": ""}
    )
    summary = _summary(out)
    assert summary.get("Copyright") == "(c) Me"
    assert summary.get("Artist") == "Alice"


def test_apply_noop_on_format_without_exif(tmp_path: Path) -> None:
    """A .bmp can't carry EXIF — apply_to_file is a graceful no-op (no crash)."""
    src = _jpg_with_exif(tmp_path / "src.jpg")
    out = tmp_path / "out.bmp"
    Image.new("RGB", (8, 8), (0, 0, 0)).save(out, format="BMP")
    exif.apply_to_file(out, src, "strip", None)  # must not raise
    assert out.exists()


def test_inject_orientation_not_rewritten(tmp_path: Path) -> None:
    src = _jpg_with_exif(tmp_path / "src.jpg")
    out = tmp_path / "out.jpg"
    shutil.copy2(src, out)
    exif.apply_to_file(
        out, src, "inject", {"artist": "Bob", "copyright": "", "description": ""}
    )
    assert "Orientation" not in _summary(out)
