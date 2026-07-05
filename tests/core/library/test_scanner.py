"""Unit tests for src/core/library/scanner.py — classify, scan, filter, sort."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Scanner module-level constants to redirect at test time. They are bound into
# the scanner namespace at import (`from src.utils import ...`), so isolating
# them means patching them on the scanner module — same pattern as
# settings._CONFIG_FILE in the testing skill.
_ROOT_ATTRS = (
    ("AUDIO_SOURCE_DIR", "audio", "source"),
    ("AUDIO_PROCESSED_DIR", "audio", "processed"),
    ("VIDEO_SOURCE_DIR", "video", "source"),
    ("VIDEO_PROCESSED_DIR", "video", "processed"),
    ("IMAGE_SOURCE_DIR", "image", "source"),
    ("IMAGE_PROCESSED_DIR", "image", "processed"),
    ("DOCUMENT_SOURCE_DIR", "document", "source"),
    ("DOCUMENT_PROCESSED_DIR", "document", "processed"),
    ("TRANSCRIPTIONS_TEXT_DIR", "transcription", "text"),
    ("TRANSCRIPTIONS_ANALYSIS_DIR", "transcription", "analysis"),
    ("TRANSCRIPTIONS_DIGEST_DIR", "transcription", "digest"),
    ("TRANSCRIPTIONS_SUBTITLES_DIR", "transcription", "subtitles"),
    ("DATA_DIR", "data", "processed"),
)


@pytest.fixture
def library_tree(tmp_path: Path, monkeypatch):
    """Build a fake output/ tree under tmp_path and redirect scanner roots.

    Returns a dict attr_name -> directory Path. Directories are created lazily
    by the individual tests so the "missing directory is skipped" path can be
    exercised by simply not creating one.
    """
    import src.core.library.scanner as scanner

    dirs: dict[str, Path] = {}
    for attr, kind, category in _ROOT_ATTRS:
        d = tmp_path / "output" / kind / category
        dirs[attr] = d
        monkeypatch.setattr(scanner, attr, d)
    return dirs


def _touch(path: Path, *, mtime: float | None = None, data: bytes = b"x") -> Path:
    """Create a file (and parents) and optionally pin its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.mark.unit
def test_classify_path_maps_each_root(library_tree):
    from src.core.library.scanner import classify_path

    for attr, kind, category in _ROOT_ATTRS:
        target = _touch(library_tree[attr] / "file.bin")
        assert classify_path(target) == (kind, category)


@pytest.mark.unit
def test_classify_path_outside_output_returns_none(library_tree, tmp_path):
    from src.core.library.scanner import classify_path

    stray = _touch(tmp_path / "elsewhere" / "note.txt")
    assert classify_path(stray) is None


@pytest.mark.unit
def test_scan_library_collects_and_sorts_by_mtime_desc(library_tree):
    from src.core.library.scanner import scan_library

    # Three files across two roots, distinct mtimes (newest = video).
    _touch(library_tree["AUDIO_SOURCE_DIR"] / "old.mp3", mtime=1_000.0)
    _touch(library_tree["AUDIO_PROCESSED_DIR"] / "mid.mp3", mtime=2_000.0)
    _touch(library_tree["VIDEO_SOURCE_DIR"] / "new.mp4", mtime=3_000.0)

    items = scan_library()

    assert len(items) == 3
    assert [it.path.name for it in items] == ["new.mp4", "mid.mp3", "old.mp3"]
    # Metadata is populated from the filesystem.
    newest = items[0]
    assert newest.kind == "video"
    assert newest.category == "source"
    assert newest.suffix == ".mp4"
    assert newest.stem == "new"
    assert newest.size_bytes == 1


@pytest.mark.unit
def test_scan_library_skips_hidden_placeholder_files(library_tree):
    from src.core.library.scanner import scan_library

    root = library_tree["AUDIO_SOURCE_DIR"]
    _touch(root / ".gitkeep")
    _touch(root / ".DS_Store")
    _touch(root / "real.mp3")

    items = scan_library()

    assert [it.path.name for it in items] == ["real.mp3"]


@pytest.mark.unit
def test_scan_library_skips_unreadable_files(library_tree, mocker):
    import pathlib

    from src.core.library.scanner import scan_library

    _touch(library_tree["AUDIO_SOURCE_DIR"] / "broken.mp3")

    # Simulate a TOCTOU race: is_file() succeeds, then the file vanishes before
    # the explicit stat(). Fail stat() only for the target file so the dir
    # exists()/iterdir() calls keep working on the real filesystem.
    real_stat = pathlib.Path.stat

    def _fake_stat(self, *args, **kwargs):
        if self.name == "broken.mp3":
            raise OSError("permission denied")
        return real_stat(self, *args, **kwargs)

    mocker.patch.object(pathlib.Path, "is_file", autospec=True, return_value=True)
    mocker.patch.object(pathlib.Path, "stat", autospec=True, side_effect=_fake_stat)

    # The unreadable file is skipped instead of raising.
    assert scan_library() == []


@pytest.mark.unit
def test_scan_library_skips_missing_dirs_and_subdirs(library_tree):
    from src.core.library.scanner import scan_library

    # Only one root exists; the rest are never created (fresh-install case).
    root = library_tree["IMAGE_PROCESSED_DIR"]
    _touch(root / "pic.png")
    # A nested directory must not be picked up (scan is shallow, files only).
    (root / "nested").mkdir()
    _touch(root / "nested" / "deep.png")

    items = scan_library()

    assert [it.path.name for it in items] == ["pic.png"]


def _item(
    name: str,
    kind: str,
    *,
    mtime: float = 0.0,
    size: int = 0,
    category: str = "processed",
):
    from src.core.library.types import LibraryItem

    p = Path(name)
    return LibraryItem(
        path=p,
        kind=kind,
        category=category,
        size_bytes=size,
        modified=mtime,
        stem=p.stem,
        suffix=p.suffix.lower(),
    )


@pytest.mark.unit
def test_filter_items_by_kind():
    from src.core.library.scanner import filter_items

    items = [_item("a.mp3", "audio"), _item("b.mp4", "video"), _item("c.mp3", "audio")]
    out = filter_items(items, kinds={"audio"})
    assert [it.path.name for it in out] == ["a.mp3", "c.mp3"]


@pytest.mark.unit
def test_filter_items_by_category():
    from src.core.library.scanner import filter_items

    items = [
        _item("dl.mp3", "audio", category="processed"),
        _item("src.mp3", "audio", category="source"),
    ]
    out = filter_items(items, categories={"source"})
    assert [it.path.name for it in out] == ["src.mp3"]


@pytest.mark.unit
def test_filter_items_by_query_is_case_insensitive():
    from src.core.library.scanner import filter_items

    items = [_item("Lecture_Intro.mp3", "audio"), _item("outro.mp3", "audio")]
    out = filter_items(items, query="INTRO")
    assert [it.path.name for it in out] == ["Lecture_Intro.mp3"]


@pytest.mark.unit
def test_filter_items_by_since():
    from src.core.library.scanner import filter_items

    items = [
        _item("old.mp3", "audio", mtime=100.0),
        _item("new.mp3", "audio", mtime=300.0),
    ]
    out = filter_items(items, since=200.0)
    assert [it.path.name for it in out] == ["new.mp3"]


@pytest.mark.unit
def test_filter_items_query_matches_content_tags():
    from src.core.library.scanner import filter_items

    items = [_item("aula01.txt", "transcription"), _item("aula02.txt", "transcription")]
    # aula01 is about inflation; the filename says nothing about it.
    tag_index = {"aula01.txt": ["inflação", "juros"], "aula02.txt": ["bolo", "forno"]}
    out = filter_items(items, query="inflação", tag_index=tag_index)
    assert [it.path.name for it in out] == ["aula01.txt"]


@pytest.mark.unit
def test_filter_items_query_still_matches_name_with_tag_index():
    from src.core.library.scanner import filter_items

    items = [_item("aula01.txt", "transcription"), _item("outro.txt", "transcription")]
    tag_index = {"aula01.txt": ["x"], "outro.txt": ["y"]}
    out = filter_items(items, query="aula", tag_index=tag_index)
    assert [it.path.name for it in out] == ["aula01.txt"]


@pytest.mark.unit
def test_filter_items_combines_predicates():
    from src.core.library.scanner import filter_items

    items = [
        _item("Talk_intro.mp3", "audio", mtime=300.0),
        _item("Talk_intro.mp4", "video", mtime=300.0),
        _item("old_intro.mp3", "audio", mtime=100.0),
    ]
    out = filter_items(items, kinds={"audio"}, query="intro", since=200.0)
    assert [it.path.name for it in out] == ["Talk_intro.mp3"]


@pytest.mark.unit
def test_sort_items_by_name_and_size():
    from src.core.library.scanner import sort_items

    items = [
        _item("b.mp3", "audio", size=30),
        _item("A.mp3", "audio", size=10),
        _item("c.mp3", "audio", size=20),
    ]
    by_name = sort_items(items, by="name", desc=False)
    assert [it.path.name for it in by_name] == ["A.mp3", "b.mp3", "c.mp3"]

    by_size_desc = sort_items(items, by="size", desc=True)
    assert [it.size_bytes for it in by_size_desc] == [30, 20, 10]


@pytest.mark.unit
def test_sort_items_unknown_key_falls_back_to_modified():
    from src.core.library.scanner import sort_items

    items = [_item("a.mp3", "audio", mtime=1.0), _item("b.mp3", "audio", mtime=2.0)]
    out = sort_items(items, by="bogus", desc=True)
    assert [it.path.name for it in out] == ["b.mp3", "a.mp3"]
