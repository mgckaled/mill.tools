"""Unit tests for src/core/image/_paths.py — shared unique-path helper."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_unique_path_no_collision_returns_plain_name(tmp_path):
    from src.core.image._paths import unique_path

    out = unique_path(tmp_path, "photo", "jpg")
    assert out == tmp_path / "photo.jpg"


def test_unique_path_appends_counter_on_collision(tmp_path):
    from src.core.image._paths import unique_path

    (tmp_path / "photo.jpg").touch()
    out = unique_path(tmp_path, "photo", "jpg")
    assert out == tmp_path / "photo_1.jpg"

    (tmp_path / "photo_1.jpg").touch()
    out2 = unique_path(tmp_path, "photo", "jpg")
    assert out2 == tmp_path / "photo_2.jpg"


def test_unique_path_accepts_ext_with_or_without_dot(tmp_path):
    from src.core.image._paths import unique_path

    assert unique_path(tmp_path, "a", "png") == tmp_path / "a.png"
    assert unique_path(tmp_path, "b", ".png") == tmp_path / "b.png"


def test_unique_path_sanitizes_stem(tmp_path):
    """Windows-invalid characters in stem must not reach the filesystem raw."""
    from src.core.image._paths import unique_path

    out = unique_path(tmp_path, "bad<name>?", "jpg")
    assert "<" not in out.name
    assert ">" not in out.name
    assert "?" not in out.name
