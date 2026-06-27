"""Unit tests for the `library` CLI subcommand (parser + runner)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pytest

from src.cli.library import add_library_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_library_parser(sub)
    return parser.parse_args(["library", *argv])


def _item(name: str, kind: str, *, size: int = 1024, mtime: float = 0.0):
    from src.core.library.types import LibraryItem

    p = Path(name)
    return LibraryItem(
        path=p,
        kind=kind,
        category="processed",
        size_bytes=size,
        modified=mtime,
        stem=p.stem,
        suffix=p.suffix.lower(),
    )


@pytest.mark.unit
def test_list_defaults():
    ns = _parse("list")
    assert ns.library_op == "list"
    assert ns.kind is None
    assert ns.sort == "modified"
    assert ns.since is None
    assert callable(ns.func)


@pytest.mark.unit
def test_list_flags():
    ns = _parse("list", "--kind", "video", "--since", "7d", "--sort", "size")
    assert ns.kind == "video"
    assert ns.since == "7d"
    assert ns.sort == "size"


@pytest.mark.unit
def test_parse_since_units():
    from src.cli.library import _parse_since

    assert _parse_since(None) is None
    now = time.time()
    assert abs(_parse_since("24h") - (now - 86400)) < 5
    assert abs(_parse_since("30m") - (now - 1800)) < 5
    assert abs(_parse_since("2d") - (now - 2 * 86400)) < 5
    # A bare number is read as days.
    assert abs(_parse_since("3") - (now - 3 * 86400)) < 5


@pytest.mark.unit
def test_parse_since_invalid_raises():
    from src.cli.library import _parse_since

    with pytest.raises(ValueError):
        _parse_since("soon")


@pytest.mark.unit
def test_run_library_cli_prints_table(mocker, capsys):
    mocker.patch(
        "src.cli.library.scan_library",
        return_value=[_item("a/song.mp3", "audio"), _item("b/clip.mp4", "video")],
    )
    ns = _parse("list")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "song.mp3" in out
    assert "clip.mp4" in out
    assert "2 file(s)." in out


@pytest.mark.unit
def test_run_library_cli_filters_by_kind(mocker, capsys):
    mocker.patch(
        "src.cli.library.scan_library",
        return_value=[_item("a/song.mp3", "audio"), _item("b/clip.mp4", "video")],
    )
    ns = _parse("list", "--kind", "audio")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "song.mp3" in out
    assert "clip.mp4" not in out


@pytest.mark.unit
def test_run_library_cli_empty(mocker, capsys):
    mocker.patch("src.cli.library.scan_library", return_value=[])
    ns = _parse("list")
    ns.func(ns)
    assert "No files found" in capsys.readouterr().out


@pytest.mark.unit
def test_stats_parser_defaults():
    ns = _parse("stats")
    assert ns.library_op == "stats"
    assert ns.top == 10
    assert callable(ns.func)


@pytest.mark.unit
def test_stats_runner_prints_dashboard(mocker, capsys):
    items = [
        _item("a/song.mp3", "audio", size=500, mtime=10.0),
        _item("b/clip.mp4", "video", size=9000, mtime=20.0),
    ]
    mocker.patch("src.cli.library.scan_library", return_value=items)
    ns = _parse("stats")
    ns.func(ns)
    out = capsys.readouterr().out
    assert "Biblioteca" in out
    assert "por tipo" in out
    assert "maiores" in out
    assert "crescimento por mês" in out
    assert "clip.mp4" in out  # largest


@pytest.mark.unit
def test_stats_runner_empty(mocker, capsys):
    mocker.patch("src.cli.library.scan_library", return_value=[])
    ns = _parse("stats")
    ns.func(ns)
    assert "No files found" in capsys.readouterr().out
