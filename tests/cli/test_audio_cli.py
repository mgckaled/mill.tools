"""Tests for CLI audio subcommand argument parsing."""
import argparse

import pytest

from src.cli.audio import add_audio_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(sub)
    return parser.parse_args(["audio", *argv])


@pytest.mark.unit
def test_audio_url_defaults():
    ns = _parse("https://youtu.be/abc123")
    assert ns.input == "https://youtu.be/abc123"
    assert ns.fmt == "mp3"
    assert ns.quality == "best"
    assert ns.no_meta is False
    assert ns.denoise is False
    assert ns.normalize is False
    assert ns.lufs == -14.0


@pytest.mark.unit
def test_audio_local_file_custom_fmt():
    ns = _parse("audio.wav", "--fmt", "ogg", "--quality", "192")
    assert ns.input == "audio.wav"
    assert ns.fmt == "ogg"
    assert ns.quality == "192"


@pytest.mark.unit
def test_audio_denoise_normalize():
    ns = _parse("video.mp4", "--denoise", "--normalize", "--lufs", "-23")
    assert ns.denoise is True
    assert ns.normalize is True
    assert ns.lufs == -23.0


@pytest.mark.unit
def test_audio_no_meta():
    ns = _parse("https://example.com/song", "--no-meta")
    assert ns.no_meta is True


@pytest.mark.unit
def test_audio_func_is_callable():
    ns = _parse("https://youtu.be/abc")
    assert callable(ns.func)
