"""Unit tests for src/core/subtitles.py."""
import pytest

pytestmark = pytest.mark.unit


def _cue(index: int, start: float, end: float, text: str):
    from src.core.subtitles import SubtitleCue
    return SubtitleCue(index=index, start=start, end=end, text=text)


# ── _format_ts ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("seconds, sep, expected", [
    (0.0,      ",", "00:00:00,000"),
    (0.001,    ",", "00:00:00,001"),
    (1.5,      ",", "00:00:01,500"),
    (59.999,   ",", "00:00:59,999"),
    (60.0,     ",", "00:01:00,000"),
    (3599.999, ",", "00:59:59,999"),
    (3600.0,   ",", "01:00:00,000"),
    (3661.5,   ",", "01:01:01,500"),
    (1.5,      ".", "00:00:01.500"),
    (3600.0,   ".", "01:00:00.000"),
])
def test_format_ts_canonical_cases(seconds, sep, expected):
    from src.core.subtitles import _format_ts
    assert _format_ts(seconds, sep=sep) == expected


def test_format_ts_rounds_milliseconds_correctly():
    """0.9999 s should round UP to 1.000 s, not down."""
    from src.core.subtitles import _format_ts
    assert _format_ts(0.9999, sep=",") == "00:00:01,000"


def test_format_ts_negative_clamps_to_zero():
    from src.core.subtitles import _format_ts
    assert _format_ts(-5.0, sep=",") == "00:00:00,000"


def test_format_ts_sub_millisecond_truncates():
    from src.core.subtitles import _format_ts
    # 0.0004 → round(0.4) = 0
    assert _format_ts(0.0004, sep=",") == "00:00:00,000"


# ── to_srt ───────────────────────────────────────────────────────────────────

def test_to_srt_single_cue():
    from src.core.subtitles import to_srt
    out = to_srt([_cue(1, 0.0, 2.5, "olá mundo")])
    expected = "1\n00:00:00,000 --> 00:00:02,500\nolá mundo\n"
    assert out == expected


def test_to_srt_multiple_cues_blank_line_between():
    from src.core.subtitles import to_srt
    out = to_srt([
        _cue(1, 0.0, 2.0, "primeiro"),
        _cue(2, 2.0, 4.5, "segundo"),
    ])
    expected = (
        "1\n00:00:00,000 --> 00:00:02,000\nprimeiro\n"
        "\n"
        "2\n00:00:02,000 --> 00:00:04,500\nsegundo\n"
    )
    assert out == expected


def test_to_srt_strips_surrounding_whitespace_in_text():
    from src.core.subtitles import to_srt
    out = to_srt([_cue(1, 0.0, 1.0, "  texto com espaço   ")])
    assert "texto com espaço\n" in out
    assert "  texto" not in out  # leading whitespace stripped


def test_to_srt_empty_list_returns_empty_string():
    from src.core.subtitles import to_srt
    assert to_srt([]) == ""


# ── to_vtt ───────────────────────────────────────────────────────────────────

def test_to_vtt_has_webvtt_header():
    from src.core.subtitles import to_vtt
    out = to_vtt([_cue(1, 0.0, 1.0, "hi")])
    assert out.startswith("WEBVTT\n\n")


def test_to_vtt_uses_dot_separator():
    from src.core.subtitles import to_vtt
    out = to_vtt([_cue(1, 1.5, 2.5, "hi")])
    assert "00:00:01.500 --> 00:00:02.500" in out
    assert "," not in out.split("\n")[2]  # second line is the timestamp


def test_to_vtt_does_not_emit_index():
    from src.core.subtitles import to_vtt
    out = to_vtt([
        _cue(1, 0.0, 1.0, "primeiro"),
        _cue(2, 1.0, 2.0, "segundo"),
    ])
    # No bare-line "1" or "2" before timestamps (VTT cues are not indexed)
    lines = out.split("\n")
    timestamp_lines = [i for i, l in enumerate(lines) if "-->" in l]
    for idx in timestamp_lines:
        prev = lines[idx - 1].strip()
        assert prev in ("", "WEBVTT"), f"Unexpected index line before timestamp: {prev!r}"


def test_to_vtt_empty_list_returns_just_header():
    from src.core.subtitles import to_vtt
    assert to_vtt([]) == "WEBVTT\n\n"


# ── write_subtitles ──────────────────────────────────────────────────────────

def test_write_subtitles_srt_only(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.5, "hi")]
    written = write_subtitles(cues, tmp_path / "out", formats=("srt",))
    assert len(written) == 1
    assert written[0].suffix == ".srt"
    assert written[0].exists()
    content = written[0].read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:01,500\nhi\n" in content


def test_write_subtitles_both_formats(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    written = write_subtitles(cues, tmp_path / "out", formats=("srt", "vtt"))
    suffixes = sorted(p.suffix for p in written)
    assert suffixes == [".srt", ".vtt"]


def test_write_subtitles_preserves_input_order(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    written = write_subtitles(cues, tmp_path / "out", formats=("vtt", "srt"))
    # Output order matches input order, not alphabetical
    assert [p.suffix for p in written] == [".vtt", ".srt"]


def test_write_subtitles_unknown_format_silently_skipped(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    written = write_subtitles(cues, tmp_path / "out", formats=("xyz", "srt"))
    assert len(written) == 1
    assert written[0].suffix == ".srt"


def test_write_subtitles_empty_formats_writes_nothing(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    assert write_subtitles(cues, tmp_path / "out", formats=()) == []


def test_write_subtitles_default_format_is_srt(tmp_path):
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    written = write_subtitles(cues, tmp_path / "out")
    assert [p.suffix for p in written] == [".srt"]


def test_write_subtitles_uses_stem_with_suffix(tmp_path):
    """out_stem '<dir>/transcricao_x' → file '<dir>/transcricao_x.srt'."""
    from src.core.subtitles import write_subtitles
    cues = [_cue(1, 0.0, 1.0, "hi")]
    stem = tmp_path / "transcricao_x"
    written = write_subtitles(cues, stem, formats=("srt",))
    assert written[0] == tmp_path / "transcricao_x.srt"


def test_subtitle_cue_is_frozen():
    """SubtitleCue is frozen — attributes cannot be reassigned."""
    from src.core.subtitles import SubtitleCue
    cue = SubtitleCue(index=1, start=0.0, end=1.0, text="hi")
    with pytest.raises((AttributeError, Exception)):
        cue.text = "changed"  # type: ignore[misc]
