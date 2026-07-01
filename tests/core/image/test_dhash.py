"""Unit tests for src/core/image/dhash.py — difference hash + Hamming distance."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


def _solid(tmp_path, color, name="solid.png"):
    path = tmp_path / name
    Image.new("RGB", (64, 64), color).save(path)
    return path


def _gradient(tmp_path, name="grad.png"):
    """A left-to-right gradient — has real horizontal structure for dHash to read."""
    path = tmp_path / name
    arr = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (64, 1))
    Image.fromarray(arr, mode="L").convert("RGB").save(path)
    return path


def _checkerboard(tmp_path, name="checker.png"):
    path = tmp_path / name
    xs, ys = np.meshgrid(np.arange(64), np.arange(64))
    arr = (((xs // 8) + (ys // 8)) % 2 * 255).astype(np.uint8)
    Image.fromarray(arr, mode="L").convert("RGB").save(path)
    return path


@pytest.mark.unit
def test_dhash_identical_content_has_zero_distance(tmp_path):
    from src.core.image.dhash import dhash, hamming_distance

    a = _gradient(tmp_path, "a.png")
    b = _gradient(tmp_path, "b.png")  # same content, different file
    assert hamming_distance(dhash(a), dhash(b)) == 0


@pytest.mark.unit
def test_dhash_solid_colors_share_the_all_zero_hash(tmp_path):
    """Known dHash limitation, not a bug: it only encodes left-right gradient,
    so two solid colors with no internal structure hash identically."""
    from src.core.image.dhash import dhash, hamming_distance

    black = _solid(tmp_path, (0, 0, 0), "black.png")
    white = _solid(tmp_path, (255, 255, 255), "white.png")
    assert hamming_distance(dhash(black), dhash(white)) == 0


@pytest.mark.unit
def test_dhash_distinguishes_structured_images(tmp_path):
    from src.core.image.dhash import dhash, hamming_distance

    checker = _checkerboard(tmp_path)
    black = _solid(tmp_path, (0, 0, 0))
    assert hamming_distance(dhash(checker), dhash(black)) > 0


@pytest.mark.unit
def test_dhash_shape_matches_hash_size(tmp_path):
    from src.core.image.dhash import dhash

    path = _gradient(tmp_path)
    assert dhash(path, hash_size=8).shape == (64,)
    assert dhash(path, hash_size=4).shape == (16,)


@pytest.mark.unit
def test_hamming_distance_counts_differing_bits():
    from src.core.image.dhash import hamming_distance

    a = np.array([True, True, False, False])
    b = np.array([True, False, False, True])
    assert hamming_distance(a, b) == 2
