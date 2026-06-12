"""Unit tests for main.py — transcribe parser and subtitle helpers."""
import argparse

import pytest

pytestmark = pytest.mark.unit


def _parse(*argv: str) -> argparse.Namespace:
    """Run main.parse_args with isolated sys.argv."""
    import sys
    import main as main_mod
    original = sys.argv
    sys.argv = ["main.py", *argv]
    try:
        return main_mod.parse_args()
    finally:
        sys.argv = original


# ── _subtitle_formats_from_args ──────────────────────────────────────────────

def test_subtitle_formats_no_flags_returns_empty():
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc")
    assert _subtitle_formats_from_args(ns) == ()


def test_subtitle_formats_srt_only():
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc", "--srt")
    assert _subtitle_formats_from_args(ns) == ("srt",)


def test_subtitle_formats_vtt_only():
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc", "--vtt")
    assert _subtitle_formats_from_args(ns) == ("vtt",)


def test_subtitle_formats_srt_and_vtt():
    """Combining both individual flags yields ordered ('srt', 'vtt')."""
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc", "--srt", "--vtt")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


def test_subtitle_formats_subtitles_shortcut_expands_to_both():
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc", "--subtitles")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


def test_subtitle_formats_subtitles_takes_priority_over_individual():
    """When --subtitles is set, individual flags are subsumed (same result)."""
    from main import _subtitle_formats_from_args
    ns = _parse("https://youtu.be/abc", "--subtitles", "--srt")
    assert _subtitle_formats_from_args(ns) == ("srt", "vtt")


# ── parser defaults ──────────────────────────────────────────────────────────

def test_parse_args_subtitle_flags_default_false():
    ns = _parse("https://youtu.be/abc")
    assert ns.srt is False
    assert ns.vtt is False
    assert ns.subtitles is False


def test_parse_args_subtitle_flags_true_when_passed():
    ns = _parse("https://youtu.be/abc", "--srt", "--vtt")
    assert ns.srt is True
    assert ns.vtt is True


def test_parse_args_other_existing_flags_unchanged_by_subtitle_addition():
    """Sanity: --format and --analyze still parse correctly."""
    ns = _parse("https://youtu.be/abc", "--format", "--analyze", "--srt")
    assert ns.format is True
    assert ns.analyze is True
    assert ns.srt is True
