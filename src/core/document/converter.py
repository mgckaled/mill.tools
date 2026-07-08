"""
converter.py: PDF format conversion — pdf_to_images, images_to_pdf, extract_text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.core.document._shared import open_pdf
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
    doc = open_pdf(path)
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

    Each image becomes one page, sized to fit the image dimensions. Camera
    EXIF orientation is applied before insertion so portrait photos taken
    with a phone don't end up sideways. Images are decoded and inserted one
    at a time (pymupdf pages) rather than held in memory all at once, so
    peak memory use stays bounded to a single image regardless of how many
    photos are combined.

    Args:
        paths: Ordered list of image paths (JPEG, PNG, etc.).
        output_dir: Directory to write the output PDF.
        output_name: Stem for the output file; defaults to "images_combined".

    Returns:
        Path to the generated PDF.

    Raises:
        ValueError: If no images are provided.
    """
    import io

    import pymupdf  # type: ignore[import-untyped]
    from PIL import Image as PILImage
    from PIL import ImageOps

    if not paths:
        raise ValueError("No valid images provided.")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(output_name) if output_name else "images_combined"
    out_path = output_dir / f"{stem}.pdf"

    doc = pymupdf.open()
    for p in paths:
        with PILImage.open(p) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
            width, height = img.size
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_bytes = buf.getvalue()

        page = doc.new_page(width=width, height=height)
        page.insert_image(pymupdf.Rect(0, 0, width, height), stream=image_bytes)

    doc.save(str(out_path))
    doc.close()
    return out_path


def extract_text(path: Path, output_dir: Path) -> tuple[Path, int]:
    """Extract all text from a PDF and save it to a .txt file.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the .txt output.

    Returns:
        Tuple of (txt_path, word_count).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = open_pdf(path)
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
