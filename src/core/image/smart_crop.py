"""Focal-point crop geometry (pure, no Pillow/Flet).

Computes a crop box that fits a target aspect ratio while keeping a focal point
(normalized 0..1) as centered as possible — so cropping to a square/portrait
doesn't cut off the subject. Used by ``transform.crop_image`` (mode "focal").
"""

from __future__ import annotations


def focal_crop_box(
    width: int,
    height: int,
    target_ratio: float,
    focal_x: float,
    focal_y: float,
) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) cropping to ``target_ratio`` (w/h).

    The box is the largest rectangle of the target ratio that fits inside the
    image, centered on the focal point and clamped to the image bounds.
    """
    if width <= 0 or height <= 0 or target_ratio <= 0:
        return (0, 0, max(width, 0), max(height, 0))

    current = width / height
    if current > target_ratio:
        # Image is wider than target → limit width.
        new_h = height
        new_w = max(1, round(height * target_ratio))
    else:
        # Image is taller/narrower → limit height.
        new_w = width
        new_h = max(1, round(width / target_ratio))

    fx = min(max(focal_x, 0.0), 1.0)
    fy = min(max(focal_y, 0.0), 1.0)

    left = round(fx * width - new_w / 2)
    top = round(fy * height - new_h / 2)
    left = max(0, min(left, width - new_w))
    top = max(0, min(top, height - new_h))
    return (left, top, left + new_w, top + new_h)
