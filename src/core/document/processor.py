"""
processor.py: PDF manipulation — merge, split, compress, rotate, watermark, stamp, encrypt.
"""

from __future__ import annotations

from pathlib import Path

from src.utils import sanitize_filename


def _parse_page_ranges(spec: str, total: int) -> list[int]:
    """Convert human-readable page spec to 0-based pymupdf indices.

    Spec format (1-indexed, inclusive):
        "1-3"      → [0, 1, 2]
        "1-3,5"    → [0, 1, 2, 4]
        "8-"       → [7, 8, ..., total-1]
        "all"      → [0, 1, ..., total-1]
        "2"        → [1]

    Args:
        spec: Page range specification string.
        total: Total page count of the document.

    Returns:
        Sorted list of 0-based page indices.

    Raises:
        ValueError: If a page number is out of range or the spec is malformed.
    """
    if spec.strip().lower() == "all" or not spec.strip():
        return list(range(total))

    indices: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            dash_idx = part.index("-")
            start_str = part[:dash_idx].strip()
            end_str = part[dash_idx + 1 :].strip()
            start = int(start_str) if start_str else 1
            end = int(end_str) if end_str else total
            if start < 1 or end > total or start > end:
                raise ValueError(
                    f"Page range '{part}' is out of bounds for a {total}-page document."
                )
            indices.extend(range(start - 1, end))
        else:
            n = int(part)
            if n < 1 or n > total:
                raise ValueError(
                    f"Page {n} is out of bounds for a {total}-page document."
                )
            indices.append(n - 1)

    return sorted(set(indices))


def merge_pdfs(paths: list[Path], output_dir: Path) -> Path:
    """Merge multiple PDFs into a single file.

    Args:
        paths: Ordered list of PDF paths to merge.
        output_dir: Directory to write the merged file.

    Returns:
        Path to the merged PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    merged = pymupdf.open()
    for p in paths:
        src = pymupdf.open(str(p))
        merged.insert_pdf(src)
        src.close()

    stems = "_".join(sanitize_filename(p.stem)[:20] for p in paths[:3])
    out_path = output_dir / f"merged_{stems}.pdf"
    merged.save(str(out_path))
    merged.close()
    return out_path


def split_pdf(path: Path, pages: str, output_dir: Path) -> list[Path]:
    """Split a PDF by extracting the specified pages into separate files.

    Each contiguous range becomes one output file. Non-contiguous pages
    each become their own file.

    Args:
        path: Source PDF path.
        pages: Page range spec (e.g. "1-3,5,8-").
        output_dir: Directory to write the split files.

    Returns:
        List of paths to the generated PDF files.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    total = doc.page_count
    indices = _parse_page_ranges(pages, total)

    # Group consecutive indices into ranges
    ranges: list[list[int]] = []
    current: list[int] = []
    for idx in indices:
        if not current or idx == current[-1] + 1:
            current.append(idx)
        else:
            ranges.append(current)
            current = [idx]
    if current:
        ranges.append(current)

    stem = sanitize_filename(path.stem)
    out_paths: list[Path] = []
    for rng in ranges:
        sub = pymupdf.open()
        sub.insert_pdf(doc, from_page=rng[0], to_page=rng[-1])
        if len(rng) == 1:
            label = f"p{rng[0] + 1}"
        else:
            label = f"p{rng[0] + 1}-{rng[-1] + 1}"
        out_path = output_dir / f"{stem}_{label}.pdf"
        sub.save(str(out_path))
        sub.close()
        out_paths.append(out_path)

    doc.close()
    return out_paths


def compress_pdf(path: Path, output_dir: Path, image_quality: int = 75) -> Path:
    """Recompress embedded images in a PDF to reduce file size.

    Uses pymupdf's native `Document.rewrite_images`, which recompresses
    lossy and lossless images as JPEG at the target quality while keeping
    any soft mask (alpha/transparency) as a separate object — transparent
    images are not flattened.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the compressed file.
        image_quality: JPEG quality for recompressed images (50–95).

    Returns:
        Path to the compressed PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    doc.rewrite_images(quality=image_quality)

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_compressed.pdf"
    doc.save(
        str(out_path),
        garbage=4,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
    )
    doc.close()
    return out_path


def rotate_pdf(
    path: Path,
    output_dir: Path,
    angle: int = 90,
    pages: str = "all",
) -> Path:
    """Rotate pages of a PDF by the given angle.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the rotated file.
        angle: Rotation angle in degrees (90, 180 or 270).
        pages: Page range spec; "all" rotates every page.

    Returns:
        Path to the rotated PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))
    indices = _parse_page_ranges(pages, doc.page_count)

    for i in indices:
        page = doc[i]
        page.set_rotation((page.rotation + angle) % 360)

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_rotated{angle}.pdf"
    doc.save(str(out_path))
    doc.close()
    return out_path


def watermark_pdf(
    path: Path,
    output_dir: Path,
    text: str,
    opacity: float = 0.3,
    position: str = "center",
) -> Path:
    """Add a diagonal text watermark to every page of a PDF.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the watermarked file.
        text: Watermark text string.
        opacity: Text opacity (0.1–0.9).
        position: Vertical anchor — "top", "center" or "bottom".

    Returns:
        Path to the watermarked PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))

    import math

    for page in doc:
        rect = page.rect
        if position == "top":
            y_frac = 0.25
        elif position == "bottom":
            y_frac = 0.75
        else:
            y_frac = 0.5

        # Use a TextWriter with a rotation matrix for diagonal (45°) watermark
        tw = pymupdf.TextWriter(rect, opacity=opacity)
        font = pymupdf.Font("helv")
        tw.append(
            pymupdf.Point(rect.width * 0.10, rect.height * y_frac),
            text,
            font=font,
            fontsize=48,
        )
        # Build 45-degree rotation matrix around the text insertion point
        angle_rad = math.radians(45)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        pivot = pymupdf.Point(rect.width / 2, rect.height / 2)
        rot_matrix = pymupdf.Matrix(cos_a, sin_a, -sin_a, cos_a, 0, 0)
        tw.write_text(page, color=(0.5, 0.5, 0.5), morph=(pivot, rot_matrix))

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_watermark.pdf"
    doc.save(str(out_path))
    doc.close()
    return out_path


def stamp_pdf(path: Path, output_dir: Path, text: str) -> Path:
    """Add a bold centered stamp on every page of a PDF.

    Unlike watermark_pdf, the stamp uses full opacity, a large bold font
    and a contrasting box for a physical-stamp visual.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the stamped file.
        text: Stamp text (e.g. "PAGO", "RASCUNHO", "CONFIDENCIAL").

    Returns:
        Path to the stamped PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))

    for page in doc:
        rect = page.rect
        fontsize = 64
        text_width = pymupdf.get_text_length(text, fontname="helv", fontsize=fontsize)
        x = (rect.width - text_width) / 2
        y = rect.height / 2

        # Draw a light background rect for contrast
        box = pymupdf.Rect(x - 10, y - fontsize - 4, x + text_width + 10, y + 8)
        page.draw_rect(box, color=(0.85, 0.85, 0.85), fill=(0.95, 0.95, 0.95))

        page.insert_text(
            pymupdf.Point(x, y),
            text,
            fontsize=fontsize,
            fontname="helv",
            color=(0.7, 0.0, 0.0),
        )

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_stamp.pdf"
    doc.save(str(out_path))
    doc.close()
    return out_path


def encrypt_pdf(path: Path, output_dir: Path, password: str) -> Path:
    """Encrypt a PDF with AES-256 user and owner password.

    Args:
        path: Source PDF path.
        output_dir: Directory to write the encrypted file.
        password: Password to protect the document (used as both user and owner pw).

    Returns:
        Path to the encrypted PDF.
    """
    import pymupdf  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(path))

    stem = sanitize_filename(path.stem)
    out_path = output_dir / f"{stem}_encrypted.pdf"
    perm = int(
        pymupdf.PDF_PERM_ACCESSIBILITY
        | pymupdf.PDF_PERM_PRINT
        | pymupdf.PDF_PERM_COPY
        | pymupdf.PDF_PERM_ANNOTATE
    )
    doc.save(
        str(out_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw=password,
        user_pw=password,
        permissions=perm,
    )
    doc.close()
    return out_path
