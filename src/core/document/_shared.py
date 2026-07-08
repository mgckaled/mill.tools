"""Private PDF-open helper shared by processor.py, converter.py, info.py and ocr.py."""

from __future__ import annotations

from pathlib import Path


def open_pdf(path: Path):
    """Open a PDF with pymupdf, raising a clear error if it needs a password.

    Centralizes the `needs_pass` check so every operation in this package
    surfaces the same actionable message instead of a raw pymupdf error deep
    in a save()/get_text() call.

    Args:
        path: Path to a PDF file.

    Returns:
        An open pymupdf.Document.

    Raises:
        ValueError: If the PDF is password-protected.
    """
    import pymupdf  # type: ignore[import-untyped]

    doc = pymupdf.open(str(path))
    if doc.needs_pass:
        doc.close()
        raise ValueError(
            f"'{path.name}' está protegido por senha — remova a proteção antes de processá-lo."
        )
    return doc
