"""OCR for images via pytesseract (extra [ocr] + Tesseract binary).

Reuses the Tesseract resolution and gate from ``core/document/ocr`` so the
binary is found the same way (PATH or standard Windows dirs). Writes a
``<stem>_ocr.txt`` that the Library lists and the RAG can index.
"""

from __future__ import annotations

from pathlib import Path

from src.core.document.ocr import LANGS, is_available, resolve_tesseract_cmd
from src.utils import sanitize_filename

__all__ = ["is_available", "LANGS", "ocr_image"]


def ocr_image(src: Path, output_dir: Path, lang: str = "por") -> tuple[Path, int]:
    """Run OCR on an image and write the extracted text to ``<stem>_ocr.txt``.

    Args:
        src: Source image (JPEG, PNG, etc.).
        output_dir: Directory to write the .txt output.
        lang: Tesseract language code(s), e.g. "por", "eng", "por+eng".

    Returns:
        Tuple of (txt_path, word_count).

    Raises:
        RuntimeError: tesseract binary could not be resolved.
    """
    import pytesseract
    from PIL import Image, ImageOps

    cmd = resolve_tesseract_cmd()
    if cmd is None:
        raise RuntimeError(
            "Tesseract binary not found on PATH or in standard install dirs."
        )
    pytesseract.pytesseract.tesseract_cmd = cmd

    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        text = pytesseract.image_to_string(im, lang=lang).strip()

    word_count = len(text.split()) if text else 0
    out_path = output_dir / f"{sanitize_filename(src.stem)}_ocr.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path, word_count
