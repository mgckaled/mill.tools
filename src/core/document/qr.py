"""
qr.py: QR code generation.
"""
from __future__ import annotations

from pathlib import Path

from src.utils import sanitize_filename


def generate_qr(
    data: str,
    output_dir: Path,
    size: int = 300,
    fmt: str = "png",
) -> Path:
    """Generate a QR code image from the given data string.

    The box_size is calculated so that the final image is approximately
    `size` pixels wide (including the 4-module quiet zone border).

    Args:
        data: String to encode (URL, plain text, etc.).
        output_dir: Directory to write the output image.
        size: Approximate output image width/height in pixels.
        fmt: Output format — "png" or "jpg".

    Returns:
        Path to the generated QR code image.
    """
    import qrcode  # type: ignore[import-untyped]

    output_dir.mkdir(parents=True, exist_ok=True)

    # Estimate modules count: version 1 = 21 modules; each +1 version adds 4.
    # We use fit=True so qrcode picks the minimum version; approximate with version 3.
    estimated_modules = 21 + 4 * 2 + 8  # version ~3 plus quiet zone
    box_size = max(1, size // estimated_modules)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    stem = sanitize_filename(data[:30]) or "qr"
    ext = "jpg" if fmt.lower() == "jpg" else "png"
    out_path = output_dir / f"qr_{stem}.{ext}"

    if ext == "jpg":
        img = img.convert("RGB")
    img.save(str(out_path))
    return out_path
