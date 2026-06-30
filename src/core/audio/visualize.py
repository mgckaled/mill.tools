"""Static audio visualizations (waveform / spectrogram) via ffmpeg.

Both filters are single-image ("pic") variants that emit one PNG frame. The
output is written to a file (not piped) and reused via run_ffmpeg, so it lands
in output/audio/ and gets indexed by the Library like any other artifact.
"""

from __future__ import annotations

from pathlib import Path

from src.core.ffmpeg import run_ffmpeg
from src.utils import sanitize_filename


def render_waveform_png(
    src: Path,
    out_dir: Path,
    *,
    width: int = 1200,
    height: int = 240,
    color: str = "#F4A63C",
) -> Path:
    """Render a static waveform PNG via ffmpeg showwavespic.

    Args:
        src: Source audio/video file (any ffmpeg-readable format).
        out_dir: Output directory (created if needed).
        width: Image width in pixels.
        height: Image height in pixels.
        color: Waveform color (hex ``#RRGGBB`` or ffmpeg color name).

    Returns:
        Path of the generated PNG (``<stem>_waveform.png``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}_waveform.png"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-filter_complex",
        f"showwavespic=s={width}x{height}:colors={color}",
        "-frames:v",
        "1",
        str(out_path),
    ]
    return run_ffmpeg(cmd, out_path)


def render_spectrogram_png(
    src: Path,
    out_dir: Path,
    *,
    width: int = 1200,
    height: int = 480,
    mode: str = "combined",
) -> Path:
    """Render a static spectrogram PNG via ffmpeg showspectrumpic.

    Args:
        src: Source audio/video file (any ffmpeg-readable format).
        out_dir: Output directory (created if needed).
        width: Image width in pixels.
        height: Image height in pixels.
        mode: Channel display mode ("combined" or "separate").

    Returns:
        Path of the generated PNG (``<stem>_spectrogram.png``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sanitize_filename(src.stem)}_spectrogram.png"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-filter_complex",
        f"showspectrumpic=s={width}x{height}:mode={mode}",
        "-frames:v",
        "1",
        str(out_path),
    ]
    return run_ffmpeg(cmd, out_path)
