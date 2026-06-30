"""Pure SRT/WebVTT serialization from transcription cues.

Standalone module — no Flet, no faster-whisper, no ffmpeg. 100% deterministic
and reusable by CLI and GUI alike. Consumed by `src.transcriber.transcribe`
when called with a non-empty `subtitle_formats`.

Format reference:
- SubRip (.srt): "HH:MM:SS,mmm" timestamps, blank-line separated blocks.
- WebVTT (.vtt): "WEBVTT" header, "HH:MM:SS.mmm" timestamps, no index.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """One timed caption line.

    Attributes:
        index: 1-based block index (used by SRT, ignored by VTT).
        start: Start time in seconds.
        end: End time in seconds.
        text: Caption text. Surrounding whitespace is stripped at serialization.
    """

    index: int
    start: float
    end: float
    text: str


def _format_ts(seconds: float, *, sep: str) -> str:
    """Format seconds as HH:MM:SS<sep>mmm.

    Args:
        seconds: Time in seconds. Negative values are clamped to 0.
        sep: Separator between seconds and milliseconds — ',' for SRT, '.' for VTT.

    Returns:
        Zero-padded timestamp string.
    """
    if seconds < 0:
        seconds = 0.0
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[SubtitleCue]) -> str:
    """Serialize cues to SubRip (.srt) text.

    Each cue becomes a block: index, "start --> end", text, blank line.
    """
    blocks = []
    for c in cues:
        blocks.append(
            f"{c.index}\n"
            f"{_format_ts(c.start, sep=',')} --> {_format_ts(c.end, sep=',')}\n"
            f"{c.text.strip()}\n"
        )
    return "\n".join(blocks)


def to_vtt(cues: list[SubtitleCue]) -> str:
    """Serialize cues to WebVTT (.vtt) text.

    WebVTT does not require cue indices and uses '.' as the millisecond separator.
    """
    body = []
    for c in cues:
        body.append(
            f"{_format_ts(c.start, sep='.')} --> {_format_ts(c.end, sep='.')}\n"
            f"{c.text.strip()}\n"
        )
    return "WEBVTT\n\n" + "\n".join(body)


_SERIALIZERS = {"srt": to_srt, "vtt": to_vtt}


def write_subtitles(
    cues: list[SubtitleCue],
    out_stem: Path,
    formats: tuple[str, ...] = ("srt",),
) -> list[Path]:
    """Write the requested subtitle files next to out_stem.

    Unknown formats are silently skipped — callers control which formats are valid.

    Args:
        cues: List of SubtitleCue instances.
        out_stem: Output path WITHOUT extension (e.g. /out/transcricao_x).
            The actual files become `<stem>.srt` / `<stem>.vtt`.
        formats: Tuple of format identifiers ("srt", "vtt").

    Returns:
        List of Path objects for files actually written, in input order.
    """
    written: list[Path] = []
    for fmt in formats:
        serializer = _SERIALIZERS.get(fmt)
        if serializer is None:
            continue
        out_path = out_stem.with_suffix(f".{fmt}")
        out_path.write_text(serializer(cues), encoding="utf-8")
        written.append(out_path)
    return written
