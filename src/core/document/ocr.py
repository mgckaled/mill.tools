"""OCR for scanned PDFs via pytesseract. Optional extra [ocr] + Tesseract binary.

Hybrid extraction: pages that already carry a text layer are read natively;
image-only (scanned) pages are rasterized and OCR'd. This avoids reprocessing
pages that don't need it and keeps the loop torch-free.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import Callable

from src.core.document._shared import open_pdf
from src.utils import sanitize_filename

# por = Portuguese, eng = English, spa = Spanish. Combine with '+': "por+eng".
LANGS = ("por", "eng", "por+eng", "spa")

SETUP_HINT = (
    "Instale o extra de OCR e o binário do Tesseract: uv sync --extra ocr "
    "(https://github.com/UB-Mannheim/tesseract/wiki)"
)

# Common Windows install locations checked when tesseract isn't on PATH.
_WINDOWS_FALLBACKS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def resolve_tesseract_cmd() -> str | None:
    """Return a usable tesseract executable path, or None if not found.

    Prefers the binary on PATH; falls back to common Windows install dirs so
    the feature works even when the installer didn't add Tesseract to PATH.
    """
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in _WINDOWS_FALLBACKS:
        if candidate.exists():
            return str(candidate)
    return None


def is_available() -> bool:
    """True if pytesseract is importable AND a tesseract binary is resolvable."""
    if resolve_tesseract_cmd() is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def ocr_pdf(
    path: Path,
    output_dir: Path,
    lang: str = "por",
    dpi: int = 300,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[Path, int]:
    """Hybrid extraction: native text per page; OCR fallback for image-only pages.

    For each page: use the embedded text layer if present; otherwise rasterize at
    `dpi` (300 is Tesseract's clean-OCR floor) and run pytesseract. Writes a .txt
    and returns (path, word_count).

    Args:
        path: Source PDF path.
        output_dir: Directory to write the .txt output.
        lang: Tesseract language code(s), e.g. "por", "eng", "por+eng".
        dpi: Rasterization resolution for OCR'd pages (150 or 300).
        progress_cb: Optional callback(current_page, total_pages).

    Returns:
        Tuple of (txt_path, word_count).

    Raises:
        RuntimeError: tesseract binary could not be resolved.
    """
    import pymupdf  # type: ignore[import-untyped]
    import pytesseract
    from PIL import Image

    cmd = resolve_tesseract_cmd()
    if cmd is None:
        raise RuntimeError(
            "Tesseract binary not found on PATH or in standard install dirs."
        )
    pytesseract.pytesseract.tesseract_cmd = cmd

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = open_pdf(path)
    total = doc.page_count
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)
    parts: list[str] = []

    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if not text:  # scanned / image-only page → OCR
            pix = page.get_pixmap(matrix=matrix)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang=lang).strip()
        if text:
            parts.append(f"\n\n--- Página {i + 1} ---\n\n{text}")
        if progress_cb:
            progress_cb(i + 1, total)

    doc.close()
    full_text = "".join(parts).strip()
    word_count = len(full_text.split()) if full_text else 0

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_ocr.txt"
    out_path.write_text(full_text, encoding="utf-8")
    return out_path, word_count
