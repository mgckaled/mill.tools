"""
info.py: PDF metadata extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.document._shared import open_pdf

# get_pdf_info's has_text scan samples only the first N pages — a full scan of
# a 500-page scanned PDF is too slow for what is just preview metadata.
_HAS_TEXT_SAMPLE_PAGES = 20


def render_first_page_png(path: Path, *, zoom: float = 1.0) -> bytes | None:
    """Rasterize the first page of a PDF to PNG bytes (~72dpi * zoom).

    Shared by the Documents viewer (before/after thumbnails) and the Library
    thumbnail dispatch. Returns None when the file cannot be opened or has no
    pages, so callers can fall back to a type icon instead of crashing.

    Args:
        path: Path to a PDF file.
        zoom: Rasterization scale; 1.0 ≈ 72dpi. Use a higher value for crisper
            previews at the cost of size/time.

    Returns:
        PNG bytes for the first page, or None on any failure.
    """
    try:
        import pymupdf  # type: ignore[import-untyped]

        doc = open_pdf(path)
    except Exception:
        return None
    try:
        if doc.page_count == 0:
            return None
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return pix.tobytes("png")
    except Exception:
        return None
    finally:
        doc.close()


@dataclass
class PdfInfo:
    """Metadata extracted from a PDF file."""

    page_count: int
    file_size_bytes: int
    title: str
    author: str
    has_text: bool  # False = scanned PDF (no embedded text)
    first_page_thumb: bytes | None  # PNG bytes at ~72dpi for preview


def get_pdf_info(path: Path) -> PdfInfo:
    """Extract metadata and first-page thumbnail from a PDF.

    `has_text` samples only the first `_HAS_TEXT_SAMPLE_PAGES` pages — a full
    scan is too slow for a 500-page scanned PDF when this is just preview
    metadata. A document is scanned cover-to-cover or not; sampling the front
    is enough to tell native-text PDFs from image-only ones in practice.

    Args:
        path: Path to a PDF file.

    Returns:
        PdfInfo dataclass with page count, metadata and preview thumbnail.
    """
    doc = open_pdf(path)
    try:
        meta = doc.metadata or {}
        page_count = doc.page_count

        has_text = False
        for page in doc[:_HAS_TEXT_SAMPLE_PAGES]:
            if page.get_text().strip():
                has_text = True
                break

        return PdfInfo(
            page_count=page_count,
            file_size_bytes=path.stat().st_size,
            title=meta.get("title", "") or "",
            author=meta.get("author", "") or "",
            has_text=has_text,
            first_page_thumb=render_first_page_png(path),
        )
    finally:
        doc.close()
