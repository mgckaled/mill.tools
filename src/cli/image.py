"""
image.py: CLI subcommand for the image pipeline.

Each operation is a nested subcommand.

Usage:
    uv run main.py image convert FILE [--fmt webp] [--quality 85]
    uv run main.py image resize FILE [--width 1920] [--mode contain]
    uv run main.py image crop FILE [--mode ratio] [--ratio 16:9]
    uv run main.py image rotate FILE [--angle 90] [--flip-h] [--flip-v]
    uv run main.py image watermark FILE --text "© 2025" [--position bottom-right]
    uv run main.py image border FILE [--padding 20] [--color #000000]
    uv run main.py image adjust FILE [--brightness 1.2] [--contrast 1.1]
    uv run main.py image filter FILE [--type blur]
    uv run main.py image favicon FILE [--sizes 16,32,48,64,128,256]
    uv run main.py image contact-sheet FILES... [--cols 4] [--thumb 200]
    uv run main.py image remove-bg FILE [--model u2net]
    uv run main.py image describe FILE [--model moondream-custom] [--preset short]
"""

from __future__ import annotations

import argparse
import sys
import threading

_FMT_CHOICES = ["jpg", "png", "webp", "avif", "tiff", "bmp", "gif", "ico"]
_FMT_OUT_CHOICES = ["preserve"] + _FMT_CHOICES


def add_image_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'image' subcommand with per-operation sub-subcommands."""
    img_p = subparsers.add_parser(
        "image",
        help="Convert, resize, crop, rotate, watermark, adjust, filter, favicon, "
        "contact sheet, remove background or describe images",
    )
    img_sub = img_p.add_subparsers(dest="image_op", required=True)

    def _out_fmt_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--out-fmt",
            default="preserve",
            choices=_FMT_OUT_CHOICES,
            dest="out_fmt",
            help="Output format (default: preserve original)",
        )
        p.add_argument(
            "--out-quality",
            type=int,
            default=90,
            dest="out_quality",
            metavar="Q",
            help="Quality for lossy formats (default 90)",
        )

    # ── convert ───────────────────────────────────────────────────────────────
    cv = img_sub.add_parser("convert", help="Convert image format")
    cv.add_argument("file", help="Image file or URL")
    cv.add_argument(
        "--fmt", default="jpg", choices=_FMT_CHOICES, help="Target format (default jpg)"
    )
    cv.add_argument(
        "--quality",
        type=int,
        default=90,
        metavar="Q",
        help="Quality for lossy formats: 1-95 for jpg/webp, 1-100 for avif (default 90)",
    )

    # ── resize ────────────────────────────────────────────────────────────────
    rs = img_sub.add_parser("resize", help="Resize image")
    rs.add_argument("file", help="Image file or URL")
    rs.add_argument(
        "--mode",
        default="contain",
        choices=["contain", "exact", "scale_pct"],
        help="Resize mode: contain (fit), exact (force), scale_pct (percentage; default contain)",
    )
    rs.add_argument("--width", type=int, default=0, help="Target width px")
    rs.add_argument("--height", type=int, default=0, help="Target height px")
    rs.add_argument(
        "--scale",
        type=float,
        default=100.0,
        dest="scale_pct",
        help="Scale percentage for --mode scale_pct (default 100)",
    )
    _out_fmt_arg(rs)

    # ── crop ──────────────────────────────────────────────────────────────────
    cr = img_sub.add_parser("crop", help="Crop image")
    cr.add_argument("file", help="Image file or URL")
    cr.add_argument(
        "--mode",
        default="manual",
        choices=["manual", "ratio", "autotrim", "focal"],
        help="Crop mode (default manual). focal = smart crop to --ratio around a focal point",
    )
    cr.add_argument("--left", type=int, default=0)
    cr.add_argument("--top", type=int, default=0)
    cr.add_argument("--crop-width", type=int, default=0, dest="crop_width")
    cr.add_argument("--crop-height", type=int, default=0, dest="crop_height")
    cr.add_argument(
        "--ratio",
        default="1:1",
        help="Aspect ratio for --mode ratio/focal (default 1:1)",
    )
    cr.add_argument(
        "--focal-x",
        type=float,
        default=0.5,
        dest="focal_x",
        help="Focal point X 0.0–1.0 for --mode focal (default 0.5)",
    )
    cr.add_argument(
        "--focal-y",
        type=float,
        default=0.5,
        dest="focal_y",
        help="Focal point Y 0.0–1.0 for --mode focal (default 0.5)",
    )
    cr.add_argument(
        "--trim-color",
        default="#ffffff",
        dest="trim_color",
        help="Background color to trim for autotrim (default #ffffff)",
    )
    _out_fmt_arg(cr)

    # ── rotate ────────────────────────────────────────────────────────────────
    ro = img_sub.add_parser("rotate", help="Rotate or flip image")
    ro.add_argument("file", help="Image file or URL")
    ro.add_argument(
        "--angle",
        type=int,
        default=0,
        choices=[0, 90, 180, 270],
        help="Rotation angle in degrees CW (default 0)",
    )
    ro.add_argument(
        "--flip-h", action="store_true", dest="flip_h", help="Mirror horizontally"
    )
    ro.add_argument(
        "--flip-v", action="store_true", dest="flip_v", help="Mirror vertically"
    )
    ro.add_argument(
        "--exif",
        action="store_true",
        dest="exif_auto",
        help="Auto-correct EXIF orientation",
    )
    _out_fmt_arg(ro)

    # ── watermark ─────────────────────────────────────────────────────────────
    wm = img_sub.add_parser("watermark", help="Add text, image or QR watermark")
    wm.add_argument("file", help="Image file or URL")
    wm.add_argument(
        "--mode",
        default="text",
        choices=["text", "image", "qr"],
        dest="wm_mode",
        help="Watermark mode (default text). qr/text use --text; image uses --image",
    )
    wm.add_argument("--text", default="", help="Watermark text or QR payload")
    wm.add_argument(
        "--image", default="", dest="wm_image", help="Logo image path for --mode image"
    )
    wm.add_argument(
        "--color",
        default="#ffffff",
        dest="wm_color",
        help="Text color hex (default #ffffff)",
    )
    wm.add_argument(
        "--size", type=int, default=40, dest="wm_size", help="Font size (default 40)"
    )
    wm.add_argument(
        "--position",
        default="bottom-right",
        choices=[
            "top-left",
            "top-center",
            "top-right",
            "middle-left",
            "center",
            "middle-right",
            "bottom-left",
            "bottom-center",
            "bottom-right",
            "tile",
        ],
        help="Watermark position or 'tile' (default bottom-right)",
    )
    wm.add_argument(
        "--opacity", type=float, default=0.5, help="Opacity 0.0–1.0 (default 0.5)"
    )
    wm.add_argument(
        "--rotation", type=int, default=0, help="Rotation in degrees (default 0)"
    )
    _out_fmt_arg(wm)

    # ── border ────────────────────────────────────────────────────────────────
    bd = img_sub.add_parser("border", help="Add border/padding to image")
    bd.add_argument("file", help="Image file or URL")
    bd.add_argument(
        "--padding", type=int, default=20, help="Border thickness px (default 20)"
    )
    bd.add_argument(
        "--color",
        default="#000000",
        dest="border_color",
        help="Border color hex (default #000000)",
    )
    bd.add_argument(
        "--fill-alpha",
        action="store_true",
        dest="fill_alpha",
        help="Fill transparent areas with border color",
    )
    _out_fmt_arg(bd)

    # ── adjust ────────────────────────────────────────────────────────────────
    aj = img_sub.add_parser(
        "adjust", help="Adjust brightness, contrast, saturation, sharpness"
    )
    aj.add_argument("file", help="Image file or URL")
    aj.add_argument(
        "--brightness", type=float, default=1.0, help="Brightness 0.1–2.0 (default 1.0)"
    )
    aj.add_argument(
        "--contrast", type=float, default=1.0, help="Contrast 0.1–2.0 (default 1.0)"
    )
    aj.add_argument(
        "--saturation",
        type=float,
        default=1.0,
        dest="saturation",
        help="Color saturation 0.1–2.0 (default 1.0)",
    )
    aj.add_argument(
        "--sharpness", type=float, default=1.0, help="Sharpness 0.1–2.0 (default 1.0)"
    )
    _out_fmt_arg(aj)

    # ── filter ────────────────────────────────────────────────────────────────
    fl = img_sub.add_parser("filter", help="Apply image filter")
    fl.add_argument("file", help="Image file or URL")
    fl.add_argument(
        "--type",
        default="blur",
        choices=["blur", "sharpen", "autocontrast", "equalize", "grayscale"],
        dest="filter_type",
        help="Filter type (default blur)",
    )
    _out_fmt_arg(fl)

    # ── favicon ───────────────────────────────────────────────────────────────
    fv = img_sub.add_parser("favicon", help="Generate multi-resolution .ico favicon")
    fv.add_argument("file", help="Image file or URL")
    fv.add_argument(
        "--sizes",
        default="16,32,48,64,128,256",
        help="Comma-separated sizes in px (default 16,32,48,64,128,256)",
    )

    # ── contact-sheet ─────────────────────────────────────────────────────────
    cs = img_sub.add_parser(
        "contact-sheet", help="Combine multiple images into a contact sheet"
    )
    cs.add_argument("files", nargs="+", help="Image files or URLs")
    cs.add_argument("--cols", type=int, default=4, help="Number of columns (default 4)")
    cs.add_argument(
        "--thumb",
        type=int,
        default=200,
        dest="thumb_size",
        help="Thumbnail size px (default 200)",
    )
    cs.add_argument(
        "--gap", type=int, default=10, help="Gap between images px (default 10)"
    )
    cs.add_argument(
        "--bg-color",
        default="#ffffff",
        dest="bg_color",
        help="Background color hex (default #ffffff)",
    )
    cs.add_argument(
        "--out-fmt",
        default="png",
        choices=_FMT_CHOICES,
        dest="out_fmt",
        help="Output format (default png)",
    )
    cs.add_argument("--out-quality", type=int, default=90, dest="out_quality")

    # ── remove-bg ─────────────────────────────────────────────────────────────
    rb = img_sub.add_parser(
        "remove-bg", help="Remove image background (requires [ai-image] extra)"
    )
    rb.add_argument("file", help="Image file or URL")
    rb.add_argument(
        "--model",
        default="u2net",
        choices=["u2net", "u2netp", "silueta", "isnet-general-use", "u2net_human_seg"],
        help="rembg model (default u2net)",
    )
    rb.add_argument(
        "--bg-mode",
        default="transparent",
        choices=["transparent", "color", "blur", "image"],
        dest="bg_mode",
        help="Background after cutout (default transparent)",
    )
    rb.add_argument(
        "--bg-color",
        default="#ffffff",
        dest="bg_color",
        help="Solid background color for --bg-mode color (default #ffffff)",
    )
    rb.add_argument(
        "--bg-blur",
        type=int,
        default=15,
        dest="bg_blur",
        help="Blur radius for --bg-mode blur (default 15)",
    )
    rb.add_argument(
        "--bg-image",
        default="",
        dest="bg_image",
        help="Background image path for --bg-mode image",
    )

    # ── describe ──────────────────────────────────────────────────────────────
    dc = img_sub.add_parser(
        "describe",
        help="Describe image via a vision model (Ollama local or Gemini/GLM cloud)",
    )
    dc.add_argument("file", help="Image file or URL")
    dc.add_argument(
        "--model",
        default="moondream-custom",
        choices=[
            "moondream-custom",
            "gemma3-4b-custom",
            "llava:7b",
            "minicpm-v",
            "glm-4.6v-flash",
            "gemini-2.5-flash",
        ],
        help=(
            "Vision model (default moondream-custom; glm-4.6v-flash/gemini-2.5-flash "
            "are cloud opt-ins)"
        ),
    )
    dc.add_argument(
        "--preset",
        default="detailed",
        choices=["detailed", "short", "technical", "text", "objects", "narrative"],
        help="Preset prompt (ignored if --prompt is set); default: detailed",
    )
    dc.add_argument("--prompt", default="", help="Custom prompt (overrides --preset)")

    # ── exif ──────────────────────────────────────────────────────────────────
    ex = img_sub.add_parser("exif", help="Read or edit EXIF metadata")
    ex.add_argument("file", help="Image file")
    ex.add_argument("--show", action="store_true", help="Print EXIF summary and exit")
    ex.add_argument("--strip", action="store_true", help="Remove all metadata")
    ex.add_argument(
        "--strip-gps", action="store_true", dest="strip_gps", help="Remove GPS only"
    )
    ex.add_argument("--artist", default="", help="Inject Artist tag")
    ex.add_argument(
        "--copyright", default="", dest="copyright_", help="Inject Copyright tag"
    )
    ex.add_argument("--description", default="", help="Inject ImageDescription tag")
    ex.add_argument(
        "--out", default="", help="Output path (default: <stem>_exif<ext> beside input)"
    )

    # ── ocr ───────────────────────────────────────────────────────────────────
    oc = img_sub.add_parser("ocr", help="Extract text from an image via Tesseract")
    oc.add_argument("file", help="Image file or URL")
    oc.add_argument(
        "--lang",
        default="por",
        choices=["por", "eng", "por+eng", "spa"],
        help="OCR language (default por)",
    )

    img_p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    img_p.set_defaults(func=run_image_cli)


def run_image_cli(ns: argparse.Namespace) -> None:
    """Execute the image pipeline from parsed CLI arguments.

    Args:
        ns: Parsed argument namespace from add_image_parser.
    """
    from pathlib import Path

    from src.cli.bus import CLIEventBus
    from src.cli.transcription import resolve_input
    from src.core.image.args import ImageArgs
    from src.core.image.describe import DESCRIBE_PRESETS
    from src.core.io_types import InputItem
    from src.gui.modules.image.worker import run_image_pipeline
    from src.utils import check_dependencies

    op = ns.image_op

    # EXIF is a direct metadata read/write — no ffmpeg/yt-dlp, no pipeline.
    if op == "exif":
        _run_exif_cli(ns)
        return

    check_dependencies()

    # contact-sheet accepts multiple files
    if op == "contact-sheet":
        items = []
        for f in ns.files:
            kind, value = resolve_input(f)
            items.append(InputItem(kind=kind, value=value))
    else:
        kind, value = resolve_input(ns.file)
        items = [InputItem(kind=kind, value=value)]

    # Parse favicon sizes
    favicon_sizes = [16, 32, 48, 64, 128, 256]
    if op == "favicon" and getattr(ns, "sizes", None):
        try:
            favicon_sizes = [int(s.strip()) for s in ns.sizes.split(",") if s.strip()]
        except ValueError:
            pass

    # Resolve "preserve" out_fmt
    raw_out_fmt = getattr(ns, "out_fmt", "preserve")
    out_fmt: str | None = None if raw_out_fmt == "preserve" else raw_out_fmt

    args = ImageArgs(
        items=items,
        operation=op.replace("-", "_"),
        # convert
        fmt=getattr(ns, "fmt", "jpg"),
        quality=getattr(ns, "quality", 90),
        # output
        out_fmt=out_fmt,
        out_quality=getattr(ns, "out_quality", 90),
        # resize
        resize_mode=getattr(ns, "mode", "contain"),
        resize_width=getattr(ns, "width", 0) or None,
        resize_height=getattr(ns, "height", 0) or None,
        resize_scale_pct=getattr(ns, "scale_pct", 100.0),
        # crop
        crop_mode=getattr(ns, "mode", "manual"),
        crop_left=getattr(ns, "left", 0),
        crop_top=getattr(ns, "top", 0),
        crop_width=getattr(ns, "crop_width", 0),
        crop_height=getattr(ns, "crop_height", 0),
        crop_ratio=getattr(ns, "ratio", "1:1"),
        crop_trim_color=getattr(ns, "trim_color", "#ffffff"),
        crop_focal_x=getattr(ns, "focal_x", 0.5),
        crop_focal_y=getattr(ns, "focal_y", 0.5),
        # rotate
        rotate_angle=getattr(ns, "angle", 0),
        rotate_flip_h=getattr(ns, "flip_h", False),
        rotate_flip_v=getattr(ns, "flip_v", False),
        rotate_exif_auto=getattr(ns, "exif_auto", False),
        # watermark
        wm_mode=getattr(ns, "wm_mode", "text"),
        wm_text=getattr(ns, "text", ""),
        wm_text_color=getattr(ns, "wm_color", "#ffffff"),
        wm_text_size=getattr(ns, "wm_size", 40),
        wm_path=(Path(ns.wm_image) if getattr(ns, "wm_image", "") else None),
        wm_position=getattr(ns, "position", "bottom-right"),
        wm_opacity=getattr(ns, "opacity", 0.5),
        wm_rotation=getattr(ns, "rotation", 0),
        # border
        border_padding=getattr(ns, "padding", 20),
        border_color=getattr(ns, "border_color", "#000000"),
        border_fill_alpha=getattr(ns, "fill_alpha", False),
        # adjust
        adj_brightness=getattr(ns, "brightness", 1.0),
        adj_contrast=getattr(ns, "contrast", 1.0),
        adj_color=getattr(ns, "saturation", 1.0),
        adj_sharpness=getattr(ns, "sharpness", 1.0),
        # filter
        filter_type=getattr(ns, "filter_type", "blur"),
        # favicon
        favicon_sizes=favicon_sizes,
        # contact_sheet
        cs_cols=getattr(ns, "cols", 4),
        cs_thumb_size=getattr(ns, "thumb_size", 200),
        cs_gap=getattr(ns, "gap", 10),
        cs_bg_color=getattr(ns, "bg_color", "#ffffff"),
        # remove_bg
        rembg_model=getattr(ns, "model", "u2net"),
        rembg_bg_mode=getattr(ns, "bg_mode", "transparent"),
        rembg_bg_color=getattr(ns, "bg_color", "#ffffff"),
        rembg_bg_blur=getattr(ns, "bg_blur", 15),
        rembg_bg_image=(Path(ns.bg_image) if getattr(ns, "bg_image", "") else None),
        # describe
        describe_model=getattr(ns, "model", "moondream-custom"),
        describe_prompt=(
            getattr(ns, "prompt", "")
            or DESCRIBE_PRESETS.get(getattr(ns, "preset", "detailed"), "")
        ),
        # ocr
        ocr_lang=getattr(ns, "lang", "por"),
    )

    bus = CLIEventBus()
    cancel = threading.Event()

    success = run_image_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)


def _run_exif_cli(ns: argparse.Namespace) -> None:
    """Read (--show) or write EXIF metadata to a copy of the input image."""
    import shutil
    from pathlib import Path

    from src.core.image.exif import apply_to_file, read_summary

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # filenames/values may be non-cp1252
    except Exception:
        pass

    src = Path(ns.file)
    if not src.exists():
        print(f"[!] File not found: {src}")
        sys.exit(1)

    # Pick the write mode from flags; absence of any mutating flag → show summary.
    if ns.strip:
        mode = "strip"
    elif ns.strip_gps:
        mode = "strip_gps"
    elif ns.artist or ns.copyright_ or ns.description:
        mode = "inject"
    else:
        mode = "show"

    if ns.show or mode == "show":
        summary = read_summary(src)
        if not summary:
            print("[i] No EXIF metadata found.")
            return
        for key, value in summary.items():
            print(f"{key}: {value}")
        return

    out = Path(ns.out) if ns.out else src.with_name(f"{src.stem}_exif{src.suffix}")
    shutil.copy2(src, out)
    apply_to_file(
        out,
        src,
        mode,
        {
            "artist": ns.artist,
            "copyright": ns.copyright_,
            "description": ns.description,
        },
    )
    print(f"[✓] EXIF ({mode}) -> {out}")
