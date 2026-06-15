"""
document.py: CLI subcommand for the document pipeline.

Each operation is a nested subcommand.

Usage:
    uv run main.py document merge a.pdf b.pdf c.pdf
    uv run main.py document split doc.pdf --pages "1-3,5"
    uv run main.py document compress doc.pdf --image-quality 60
    uv run main.py document rotate doc.pdf --angle 90 --pages "1,3"
    uv run main.py document watermark doc.pdf --text "CONFIDENCIAL" --opacity 0.3
    uv run main.py document stamp doc.pdf --text "PAGO"
    uv run main.py document encrypt doc.pdf --password "senha"
    uv run main.py document extract doc.pdf
    uv run main.py document ocr scanned.pdf --lang por --dpi 300
    uv run main.py document pdf-to-images doc.pdf --fmt jpg --dpi 150
    uv run main.py document images-to-pdf *.jpg --name "album"
    uv run main.py document qr "https://example.com" --size 300 --fmt png
"""

from __future__ import annotations

import argparse
import sys
import threading


def add_document_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'document' subcommand with per-operation sub-subcommands."""
    doc_p = subparsers.add_parser(
        "document",
        help="PDF manipulation — merge, split, compress, rotate, watermark, stamp, encrypt, convert, QR",
    )
    doc_sub = doc_p.add_subparsers(dest="document_op", required=True)
    doc_p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    doc_p.set_defaults(func=run_document_cli)

    _add_merge(doc_sub)
    _add_split(doc_sub)
    _add_compress(doc_sub)
    _add_rotate(doc_sub)
    _add_watermark(doc_sub)
    _add_stamp(doc_sub)
    _add_encrypt(doc_sub)
    _add_extract(doc_sub)
    _add_ocr(doc_sub)
    _add_pdf_to_images(doc_sub)
    _add_images_to_pdf(doc_sub)
    _add_qr(doc_sub)


# ── Sub-subcommand definitions ─────────────────────────────────────────────────


def _add_merge(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("merge", help="Merge multiple PDFs into one")
    p.add_argument("files", nargs="+", help="PDF files to merge in order")


def _add_split(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("split", help="Split a PDF into multiple files")
    p.add_argument("file", help="PDF file to split")
    p.add_argument(
        "--pages",
        default="",
        help='Page range spec, e.g. "1-3,5,8-" (1-indexed, inclusive)',
    )


def _add_compress(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("compress", help="Compress embedded images in a PDF")
    p.add_argument("file", help="PDF file to compress")
    p.add_argument(
        "--image-quality",
        type=int,
        default=75,
        dest="image_quality",
        metavar="Q",
        help="JPEG quality for recompressed images 50–95 (default 75)",
    )


def _add_rotate(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("rotate", help="Rotate pages in a PDF")
    p.add_argument("file", help="PDF file")
    p.add_argument(
        "--angle",
        type=int,
        default=90,
        choices=[90, 180, 270],
        help="Rotation angle in degrees CW (default 90)",
    )
    p.add_argument(
        "--pages",
        default="all",
        help='Pages to rotate: "all" or range like "1,3,5" (default all)',
    )


def _add_watermark(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("watermark", help="Add diagonal text watermark to a PDF")
    p.add_argument("file", help="PDF file")
    p.add_argument("--text", default="", help="Watermark text")
    p.add_argument(
        "--opacity",
        type=float,
        default=0.3,
        help="Text opacity 0.1–0.9 (default 0.3)",
    )
    p.add_argument(
        "--position",
        default="center",
        choices=["center", "top", "bottom"],
        help="Vertical anchor (default center)",
    )


def _add_stamp(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("stamp", help="Add a bold centered stamp to a PDF")
    p.add_argument("file", help="PDF file")
    p.add_argument(
        "--text",
        default="RASCUNHO",
        help="Stamp text (default RASCUNHO)",
    )


def _add_encrypt(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("encrypt", help="Protect a PDF with AES-256 password")
    p.add_argument("file", help="PDF file")
    p.add_argument("--password", default="", help="Password to set")


def _add_extract(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("extract", help="Extract all text from a PDF to .txt")
    p.add_argument("file", help="PDF file")


def _add_ocr(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "ocr", help="OCR a scanned PDF to text (hybrid native/Tesseract)"
    )
    p.add_argument("file", help="PDF file")
    p.add_argument(
        "--lang",
        default="por",
        dest="ocr_lang",
        help="Tesseract language(s): por, eng, por+eng, spa (default por)",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=300,
        dest="ocr_dpi",
        choices=[150, 300],
        help="Rasterization DPI for OCR'd pages (default 300)",
    )


def _add_pdf_to_images(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pdf-to-images", help="Rasterize each PDF page to an image")
    p.add_argument("file", help="PDF file")
    p.add_argument(
        "--fmt",
        default="jpg",
        choices=["jpg", "png"],
        help="Output image format (default jpg)",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=150,
        choices=[72, 96, 150, 300],
        help="Resolution in DPI (default 150)",
    )


def _add_images_to_pdf(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("images-to-pdf", help="Combine images into a single PDF")
    p.add_argument("files", nargs="+", help="Image files to combine in order")
    p.add_argument(
        "--name",
        default="",
        dest="output_name",
        help="Output PDF stem (default images_combined)",
    )


def _add_qr(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("qr", help="Generate a QR code image")
    p.add_argument("data", help="Content to encode (URL or text)")
    p.add_argument(
        "--size",
        type=int,
        default=300,
        help="Approximate output size in pixels (default 300)",
    )
    p.add_argument(
        "--fmt",
        default="png",
        choices=["png", "jpg"],
        help="Output format (default png)",
    )


# ── Runner ─────────────────────────────────────────────────────────────────────


def run_document_cli(ns: argparse.Namespace) -> None:
    """Execute the document pipeline from parsed CLI arguments.

    Args:
        ns: Parsed argument namespace from add_document_parser.
    """
    from pathlib import Path

    from src.cli.bus import CLIEventBus
    from src.core.document.args import DocumentArgs
    from src.gui.modules.document.worker import run_document_pipeline
    from src.utils import setup_logging

    setup_logging(getattr(ns, "verbose", False))

    op = ns.document_op

    # Build input_paths
    if op in ("merge", "images-to-pdf"):
        input_paths = [Path(f) for f in ns.files]
    elif op == "qr":
        input_paths = []
    else:
        input_paths = [Path(ns.file)]

    # Normalise operation name (kebab → snake)
    op_norm = op.replace("-", "_")

    args = DocumentArgs(
        input_paths=input_paths,
        operation=op_norm,
        # split
        pages=getattr(ns, "pages", ""),
        # compress
        image_quality=getattr(ns, "image_quality", 75),
        # rotate
        angle=getattr(ns, "angle", 90),
        rotate_pages=getattr(ns, "pages", "all") if op == "rotate" else "all",
        # watermark
        watermark_text=getattr(ns, "text", ""),
        watermark_opacity=getattr(ns, "opacity", 0.3),
        watermark_position=getattr(ns, "position", "center"),
        # stamp
        stamp_text=getattr(ns, "text", "RASCUNHO") if op == "stamp" else "RASCUNHO",
        # encrypt
        password=getattr(ns, "password", ""),
        # pdf_to_images
        image_fmt=getattr(ns, "fmt", "jpg") if op == "pdf-to-images" else "jpg",
        dpi=getattr(ns, "dpi", 150),
        # images_to_pdf
        output_name=getattr(ns, "output_name", ""),
        # qr
        qr_data=getattr(ns, "data", ""),
        qr_size=getattr(ns, "size", 300),
        qr_fmt=getattr(ns, "fmt", "png") if op == "qr" else "png",
        # ocr
        ocr_lang=getattr(ns, "ocr_lang", "por"),
        ocr_dpi=getattr(ns, "ocr_dpi", 300),
    )

    bus = CLIEventBus()
    cancel = threading.Event()

    success = run_document_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
