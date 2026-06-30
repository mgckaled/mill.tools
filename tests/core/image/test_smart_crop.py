"""Unit tests for focal-point crop geometry (core/image/smart_crop.py)."""

from __future__ import annotations

import pytest

from src.core.image.smart_crop import focal_crop_box

pytestmark = pytest.mark.unit


def _wh(box: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = box
    return right - left, bottom - top


def test_square_from_landscape_centered() -> None:
    box = focal_crop_box(2000, 1000, 1.0, 0.5, 0.5)
    w, h = _wh(box)
    assert w == h == 1000
    # centered horizontally: left = (2000-1000)/2
    assert box[0] == 500


def test_target_ratio_respected() -> None:
    # 16:9 target from a tall image limits height.
    box = focal_crop_box(1000, 2000, 16 / 9, 0.5, 0.5)
    w, h = _wh(box)
    assert w == 1000
    assert abs(w / h - 16 / 9) < 0.02


def test_focal_left_clamps_to_bounds() -> None:
    box = focal_crop_box(2000, 1000, 1.0, 0.0, 0.5)
    # focal at far left → box hugs the left edge.
    assert box[0] == 0
    assert _wh(box) == (1000, 1000)


def test_focal_right_clamps_to_bounds() -> None:
    box = focal_crop_box(2000, 1000, 1.0, 1.0, 0.5)
    assert box[2] == 2000  # right edge
    assert _wh(box) == (1000, 1000)


def test_box_inside_image() -> None:
    box = focal_crop_box(1234, 567, 3 / 2, 0.3, 0.8)
    left, top, right, bottom = box
    assert 0 <= left < right <= 1234
    assert 0 <= top < bottom <= 567


def test_degenerate_inputs() -> None:
    assert focal_crop_box(0, 0, 1.0, 0.5, 0.5) == (0, 0, 0, 0)
