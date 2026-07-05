"""Unit tests for src/core/observatory/disk_usage.py — ~/.mill-tools/ scanner."""

from __future__ import annotations

import pytest

from src.core.observatory.disk_usage import disk_usage, mill_tools_dir, total_bytes


@pytest.mark.unit
def test_disk_usage_missing_directory_returns_empty(tmp_path):
    assert disk_usage(directory=tmp_path / "does-not-exist") == ()


@pytest.mark.unit
def test_disk_usage_lists_files_and_directories(tmp_path):
    (tmp_path / "ml_activity.json").write_bytes(b"x" * 10)
    (tmp_path / "config.json").write_bytes(b"x" * 5)
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "vectors.npz").write_bytes(b"x" * 100)
    (rag_dir / "meta.json").write_bytes(b"x" * 20)

    entries = disk_usage(directory=tmp_path)
    by_name = {e.name: e for e in entries}

    assert by_name["ml_activity.json"].size_bytes == 10
    assert by_name["ml_activity.json"].is_dir is False
    assert by_name["ml_activity.json"].children == ()
    assert by_name["rag"].size_bytes == 120  # summed from children
    assert by_name["rag"].is_dir is True

    rag_children = {c.name: c for c in by_name["rag"].children}
    assert rag_children["vectors.npz"].size_bytes == 100
    assert rag_children["meta.json"].size_bytes == 20


@pytest.mark.unit
def test_disk_usage_nests_grandchildren_too(tmp_path):
    nested_dir = tmp_path / "ml" / "sub"
    nested_dir.mkdir(parents=True)
    (nested_dir / "model.npz").write_bytes(b"x" * 50)

    entries = disk_usage(directory=tmp_path)
    ml_entry = next(e for e in entries if e.name == "ml")
    assert ml_entry.size_bytes == 50
    sub_entry = ml_entry.children[0]
    assert sub_entry.name == "sub"
    assert sub_entry.is_dir is True
    assert sub_entry.children[0].name == "model.npz"


@pytest.mark.unit
def test_disk_usage_sorts_largest_first(tmp_path):
    (tmp_path / "small.json").write_bytes(b"x" * 5)
    (tmp_path / "big.json").write_bytes(b"x" * 500)

    entries = disk_usage(directory=tmp_path)
    assert [e.name for e in entries] == ["big.json", "small.json"]


@pytest.mark.unit
def test_disk_usage_ignores_unreadable_entries(tmp_path, mocker):
    from pathlib import Path

    (tmp_path / "bad.json").write_bytes(b"x")
    (tmp_path / "ok.json").write_bytes(b"x" * 5)

    real_stat = Path.stat

    def _fake_stat(self, *args, **kwargs):
        if self.name == "bad.json":
            raise OSError("gone")
        return real_stat(self, *args, **kwargs)

    mocker.patch("pathlib.Path.stat", _fake_stat)

    entries = disk_usage(directory=tmp_path)
    assert [e.name for e in entries] == ["ok.json"]


@pytest.mark.unit
def test_disk_usage_does_not_follow_a_symlink_cycle(tmp_path):
    # A directory symlink pointing back to an ancestor would recurse forever
    # (RecursionError, not an OSError) if followed like a real directory.
    (tmp_path / "real.json").write_bytes(b"x" * 5)
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this platform/user")

    entries = disk_usage(directory=tmp_path)
    by_name = {e.name: e for e in entries}
    assert by_name["loop"].is_dir is False  # never recursed into
    assert by_name["loop"].children == ()


@pytest.mark.unit
def test_total_bytes_sums_every_entry(tmp_path):
    (tmp_path / "a.json").write_bytes(b"x" * 10)
    (tmp_path / "b.json").write_bytes(b"x" * 20)

    entries = disk_usage(directory=tmp_path)
    assert total_bytes(entries) == 30


@pytest.mark.unit
def test_mill_tools_dir_matches_settings_convention():
    from pathlib import Path

    assert mill_tools_dir() == Path.home() / ".mill-tools"
