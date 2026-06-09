"""
video.py: CLI subcommand for the video pipeline.

Each operation is a nested subcommand:
    download, convert, trim, compress, resize, extract-audio, thumbnail

Usage:
    uv run main.py video download URL [--quality 1080] [--container mp4]
    uv run main.py video convert FILE [--codec h264] [--container mp4]
    uv run main.py video trim FILE --start 0:30 [--end 2:00] [--reenc]
    uv run main.py video compress FILE [--crf 23] [--preset medium]
    uv run main.py video resize FILE [--width 1280] [--height 720]
    uv run main.py video extract-audio FILE [--fmt mp3]
    uv run main.py video thumbnail FILE [--time 00:00:01] [--fmt jpg]
"""
from __future__ import annotations

import argparse
import sys
import threading


def add_video_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'video' subcommand with per-operation sub-subcommands."""
    video_p = subparsers.add_parser(
        "video",
        help="Download, convert, trim, compress, resize video; extract audio or thumbnail",
    )
    video_sub = video_p.add_subparsers(dest="video_op", required=True)

    # ── download ──────────────────────────────────────────────────────────────
    dl = video_sub.add_parser("download", help="Download video from URL via yt-dlp")
    dl.add_argument("url", help="YouTube/yt-dlp URL")
    dl.add_argument("--quality", default="1080", metavar="HEIGHT", help="Max resolution height (default 1080)")
    dl.add_argument("--container", default="mp4", help="Output container format (default mp4)")
    dl.add_argument("--no-meta", action="store_true", dest="no_meta", help="Skip embedding metadata")

    # ── convert ───────────────────────────────────────────────────────────────
    cv = video_sub.add_parser("convert", help="Convert video codec or container")
    cv.add_argument("file", help="Local video file")
    cv.add_argument("--codec", default="copy", help="Video codec: copy, h264, hevc (default copy)")
    cv.add_argument("--container", default="mp4", help="Output container (default mp4)")

    # ── trim ──────────────────────────────────────────────────────────────────
    tr = video_sub.add_parser("trim", help="Trim video to a time range")
    tr.add_argument("file", help="Local video file")
    tr.add_argument("--start", required=True, dest="trim_start", metavar="TIME",
                    help="Start time e.g. '0:30', '00:01:00'")
    tr.add_argument("--end", default="", dest="trim_end", metavar="TIME",
                    help="End time (omit to cut to end)")
    tr.add_argument("--reenc", action="store_true", dest="trim_reenc",
                    help="Re-encode instead of stream-copy (accurate but slower)")

    # ── compress ──────────────────────────────────────────────────────────────
    cp = video_sub.add_parser("compress", help="Compress video with H.264 (CPU, CRF)")
    cp.add_argument("file", help="Local video file")
    cp.add_argument("--crf", type=int, default=23, help="CRF value 18–28; lower=better quality (default 23)")
    cp.add_argument("--preset", default="medium",
                    choices=["ultrafast", "superfast", "veryfast", "faster",
                             "fast", "medium", "slow", "slower", "veryslow"],
                    help="x264 preset (default medium)")

    # ── resize ────────────────────────────────────────────────────────────────
    rs = video_sub.add_parser("resize", help="Resize video (aspect ratio preserved)")
    rs.add_argument("file", help="Local video file")
    rs.add_argument("--width", type=int, default=0, help="Target width px (0 = derive from height)")
    rs.add_argument("--height", type=int, default=0, help="Target height px (0 = derive from width)")

    # ── extract-audio ─────────────────────────────────────────────────────────
    ea = video_sub.add_parser("extract-audio", help="Extract audio track from video")
    ea.add_argument("file", help="Local video file")
    ea.add_argument("--fmt", default="mp3",
                    choices=["mp3", "m4a", "wav", "ogg", "opus"],
                    help="Output audio format (default mp3)")

    # ── thumbnail ─────────────────────────────────────────────────────────────
    th = video_sub.add_parser("thumbnail", help="Extract a frame as an image")
    th.add_argument("file", help="Local video file")
    th.add_argument("--time", default="00:00:01", metavar="TIME",
                    help="Timestamp to capture e.g. '00:00:05' (default 00:00:01)")
    th.add_argument("--fmt", default="jpg", choices=["jpg", "png"],
                    help="Output image format (default jpg)")

    video_p.add_argument(
        "--verbose", action="store_true", help="Enable debug logging",
    )
    video_p.set_defaults(func=run_video_cli)


def run_video_cli(ns: argparse.Namespace) -> None:
    """Execute the video pipeline from parsed CLI arguments.

    Args:
        ns: Parsed argument namespace from add_video_parser.
    """
    from src.cli.bus import CLIEventBus
    from src.core.io_types import InputItem
    from src.core.video.args import VideoArgs
    from src.gui.modules.video.worker import run_video_pipeline
    from src.utils import check_dependencies

    check_dependencies()

    op = ns.video_op

    # Resolve input: URL → kind="url", local file → kind="local"
    if op == "download":
        item = InputItem(kind="url", value=ns.url)
    else:
        from pathlib import Path
        item = InputItem(kind="local", value=str(Path(ns.file).resolve()))

    args = VideoArgs(
        items=[item],
        operation=op if op != "extract-audio" else "extract_audio",
        # download
        resolution=getattr(ns, "quality", "1080"),
        container=getattr(ns, "container", "mp4"),
        embed_meta=not getattr(ns, "no_meta", False),
        # convert
        vcodec=getattr(ns, "codec", "copy"),
        out_container=getattr(ns, "container", "mp4"),
        # trim
        trim_start=getattr(ns, "trim_start", ""),
        trim_end=getattr(ns, "trim_end", ""),
        trim_reenc=getattr(ns, "trim_reenc", False),
        # compress
        crf=getattr(ns, "crf", 23),
        preset=getattr(ns, "preset", "medium"),
        # resize
        resize_width=getattr(ns, "width", 0),
        resize_height=getattr(ns, "height", 0),
        # extract_audio
        audio_fmt=getattr(ns, "fmt", "mp3"),
        # thumbnail
        thumb_time=getattr(ns, "time", "00:00:01"),
        thumb_fmt=getattr(ns, "fmt", "jpg"),
    )

    bus = CLIEventBus()
    cancel = threading.Event()

    success = run_video_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
