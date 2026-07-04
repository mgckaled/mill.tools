"""Unit tests for src/core/io_atomic.py — atomic single/group file writes."""

from __future__ import annotations

import pytest

from src.core.io_atomic import atomic_write_bytes, atomic_write_text, write_group


@pytest.mark.unit
def test_atomic_write_text_creates_file_with_content(tmp_path):
    path = tmp_path / "sub" / "out.json"
    atomic_write_text(path, '{"a": 1}')
    assert path.read_text(encoding="utf-8") == '{"a": 1}'


@pytest.mark.unit
def test_atomic_write_text_overwrites_existing_file(tmp_path):
    path = tmp_path / "out.json"
    path.write_text("old", encoding="utf-8")
    atomic_write_text(path, "new")
    assert path.read_text(encoding="utf-8") == "new"


@pytest.mark.unit
def test_atomic_write_bytes_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "c.bin"
    atomic_write_bytes(path, b"\x00\x01\x02")
    assert path.read_bytes() == b"\x00\x01\x02"


@pytest.mark.unit
def test_atomic_write_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "out.json"
    atomic_write_text(path, "content")
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


@pytest.mark.unit
def test_replace_retries_on_permission_error_then_succeeds(tmp_path, mocker):
    import os

    from src.core import io_atomic

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("locked")
        return real_replace(src, dst)

    mocker.patch("src.core.io_atomic.os.replace", side_effect=flaky_replace)
    mocker.patch("src.core.io_atomic.time.sleep")  # skip real delay in the test

    path = tmp_path / "out.json"
    io_atomic.atomic_write_text(path, "ok", retries=5, retry_delay=0.01)

    assert path.read_text(encoding="utf-8") == "ok"
    assert calls["n"] == 3


@pytest.mark.unit
def test_replace_raises_after_exhausting_retries(tmp_path, mocker):
    from src.core import io_atomic

    mocker.patch(
        "src.core.io_atomic.os.replace",
        side_effect=PermissionError("locked forever"),
    )
    mocker.patch("src.core.io_atomic.time.sleep")

    path = tmp_path / "out.json"
    with pytest.raises(PermissionError):
        io_atomic.atomic_write_text(path, "x", retries=2, retry_delay=0.01)


@pytest.mark.unit
def test_replace_with_retry_leaves_no_tmp_file_after_exhausting_retries(
    tmp_path, mocker
):
    from src.core import io_atomic

    mocker.patch(
        "src.core.io_atomic.os.replace",
        side_effect=PermissionError("locked forever"),
    )
    mocker.patch("src.core.io_atomic.time.sleep")

    path = tmp_path / "out.json"
    with pytest.raises(PermissionError):
        io_atomic.atomic_write_text(path, "x", retries=1, retry_delay=0.01)

    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.unit
def test_write_group_writes_all_files_atomically(tmp_path):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "sub" / "b.bin"
    write_group([(p1, b'{"x": 1}'), (p2, b"\x01\x02")])

    assert p1.read_bytes() == b'{"x": 1}'
    assert p2.read_bytes() == b"\x01\x02"
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.unit
def test_write_group_leaves_targets_untouched_if_staging_fails(tmp_path, mocker):
    from src.core import io_atomic

    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    p1.write_text("old-a", encoding="utf-8")
    p2.write_text("old-b", encoding="utf-8")

    real_stage_temp = io_atomic._stage_temp
    calls = {"n": 0}

    def flaky_stage(path, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_stage_temp(path, data)

    mocker.patch("src.core.io_atomic._stage_temp", side_effect=flaky_stage)

    with pytest.raises(OSError):
        io_atomic.write_group([(p1, b"new-a"), (p2, b"new-b")])

    assert p1.read_text(encoding="utf-8") == "old-a"
    assert p2.read_text(encoding="utf-8") == "old-b"
    assert list(tmp_path.rglob("*.tmp")) == []
