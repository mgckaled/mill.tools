"""
converter.py: PDF format conversion — pdf_to_images, images_to_pdf, extract_text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.utils import sanitize_filename


def pdf_to_images(
    path: Path,
    output_dir: Path,
    fmt: str = "jpg",
    dpi: int = 150,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """Rasterize each page of a PDF into an image file.

    Args:
        path: Source PDF path.
        output_dir: Directory to write output images.
        fmt: Output format — "jpg" or "png".
        dpi: Resolution in dots per inch (72, 96, 150, 300).
        progress_cb: Optional callback(current_page, total_pages) for progress updates.

    Returns:
        Ordered list of paths to the generated image files.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    total = doc.page_count
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)
    stem = sanitize_filename(path.stem)
    ext = "jpg" if fmt.lower() == "jpg" else "png"
    out_paths: list[Path] = []

    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix)
        if ext == "jpg" and pix.alpha:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
        out_path = output_dir / f"{stem}_p{i + 1:03d}.{ext}"
        pix.save(str(out_path))
        out_paths.append(out_path)
        if progress_cb:
            progress_cb(i + 1, total)

    doc.close()
    return out_paths


def images_to_pdf(
    paths: list[Path],
    output_dir: Path,
    output_name: str = "",
) -> Path:
    """Combine a list of images into a single PDF.

    Each image becomes one page, sized to fit the image dimensions.

    Args:
        paths: Ordered list of image paths (JPEG, PNG, etc.).
        output_dir: Directory to write the output PDF.
        output_name: Stem for the output file; defaults to "images_combined".

    Returns:
        Path to the generated PDF.
    """
    from PIL import Image as PILImage

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(output_name) if output_name else "images_combined"
    out_path = output_dir / f"{stem}.pdf"

    images = []
    for p in paths:
        img = PILImage.open(p).convert("RGB")
        images.append(img)

    if not images:
        raise ValueError("No valid images provided.")

    first = images[0]
    rest = images[1:] if len(images) > 1 else []
    first.save(
        str(out_path),
        format="PDF",
        save_all=True,
        append_images=rest,
    )
    return out_path


def extract_text(path: Path, output_dir: Path) -> tuple[Path, int]:
    """Extract all text from a PDF and save it to a .txt file.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the .txt output.

    Returns:
        Tuple of (txt_path, word_count).
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    parts: list[str] = []

    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            parts.append(f"\n\n--- Página {i + 1} ---\n\n{text.strip()}")

    doc.close()
    full_text = "".join(parts).strip()
    word_count = len(full_text.split()) if full_text else 0

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_text.txt"
    out_path.write_text(full_text, encoding="utf-8")
    return out_path, word_count
