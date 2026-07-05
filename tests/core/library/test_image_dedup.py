"""Unit tests for src/core/library/image_dedup.py — dHash near-duplicate groups."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


def _gradient(tmp_path, name, angle_offset=0):
    """A left-to-right gradient; `angle_offset` nudges the pixels a little so a
    lightly re-encoded/perturbed copy can be simulated without a new file format."""
    arr = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (64, 1))
    if angle_offset:
        arr = np.clip(arr.astype(int) + angle_offset, 0, 255).astype(np.uint8)
    path = tmp_path / name
    Image.fromarray(arr, mode="L").convert("RGB").save(path)
    return path


def _checkerboard(tmp_path, name):
    xs, ys = np.meshgrid(np.arange(64), np.arange(64))
    arr = (((xs // 8) + (ys // 8)) % 2 * 255).astype(np.uint8)
    path = tmp_path / name
    Image.fromarray(arr, mode="L").convert("RGB").save(path)
    return path


@pytest.mark.unit
def test_empty_and_single_image_return_no_groups(tmp_path):
    from src.core.library.image_dedup import near_duplicate_images

    assert near_duplicate_images([]) == []
    assert near_duplicate_images([_gradient(tmp_path, "a.png")]) == []


@pytest.mark.unit
def test_near_identical_images_form_a_group(tmp_path):
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png")
    b = _gradient(tmp_path, "b.png", angle_offset=5)  # lightly perturbed copy
    unrelated = _checkerboard(tmp_path, "c.png")

    groups = near_duplicate_images([a, b, unrelated])

    assert len(groups) == 1
    assert set(groups[0].paths) == {a, b}


@pytest.mark.unit
def test_distinct_images_do_not_group(tmp_path):
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png")
    b = _checkerboard(tmp_path, "b.png")

    assert near_duplicate_images([a, b], max_distance=0) == []


@pytest.mark.unit
def test_max_distance_zero_still_groups_byte_identical_content(tmp_path):
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png")
    b = _gradient(tmp_path, "b.png")  # identical content, different file

    groups = near_duplicate_images([a, b], max_distance=0)
    assert len(groups) == 1
    assert groups[0].max_distance == 0


@pytest.mark.unit
def test_max_images_guard_skips_large_batches(tmp_path, caplog):
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png")
    b = _gradient(tmp_path, "b.png")

    with caplog.at_level("WARNING"):
        result = near_duplicate_images([a, b], max_images=1)

    assert result == []
    assert "skipped" in caplog.text


@pytest.mark.unit
def test_corrupted_image_is_skipped_not_fatal(tmp_path, caplog):
    """One unreadable image must not abort the whole batch — the rest still group."""
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png")
    b = _gradient(tmp_path, "b.png", angle_offset=5)
    corrupt = tmp_path / "broken.png"
    corrupt.write_bytes(b"not a real image")

    with caplog.at_level("WARNING"):
        groups = near_duplicate_images([a, b, corrupt])

    assert len(groups) == 1
    assert set(groups[0].paths) == {a, b}
    assert "Skipping unreadable image" in caplog.text


@pytest.mark.unit
def test_transitive_chain_forms_one_component(tmp_path):
    """A~B and B~C (but A and C themselves over the threshold) still merge into
    one group via the shared B — same transitivity ml.dedup.near_duplicates has."""
    from src.core.library.image_dedup import near_duplicate_images

    a = _gradient(tmp_path, "a.png", angle_offset=0)
    b = _gradient(tmp_path, "b.png", angle_offset=6)
    c = _gradient(tmp_path, "c.png", angle_offset=12)

    groups = near_duplicate_images([a, b, c], max_distance=10)

    assert len(groups) == 1
    assert set(groups[0].paths) == {a, b, c}
