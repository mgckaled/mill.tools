"""
args.py: Shared argument types for the document pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentArgs:
    """Document pipeline parameters."""

    # --- input / output ---
    input_paths: list[Path] = field(default_factory=list)
    operation: str = "merge"
    output_dir: Path = Path("output/document/processed")

    # --- split ---
    pages: str = ""  # e.g. "1-3,5,8-"  (1-indexed, inclusive)

    # --- compress ---
    image_quality: int = 75  # 50–95

    # --- rotate ---
    angle: int = 90  # 90 | 180 | 270
    rotate_pages: str = "all"  # "all" or "1,3,5"

    # --- watermark ---
    watermark_text: str = ""
    watermark_opacity: float = 0.3  # 0.1–0.9
    watermark_position: str = "center"  # center | top | bottom

    # --- stamp ---
    stamp_text: str = "RASCUNHO"  # PAGO | RASCUNHO | CONFIDENCIAL | custom

    # --- encrypt ---
    password: str = ""

    # --- pdf_to_images ---
    image_fmt: str = "jpg"  # jpg | png
    dpi: int = 150  # 72 | 96 | 150 | 300

    # --- images_to_pdf ---
    output_name: str = ""

    # --- qr ---
    qr_data: str = ""
    qr_size: int = 300  # px
    qr_fmt: str = "png"  # png | jpg

    # --- analyze ---
    analyze_model: str = "qwen7b-custom"  # qwen7b-custom | gemini-2.5-flash

    # --- ocr ---
    ocr_lang: str = "por"  # por | eng | por+eng | spa
    ocr_dpi: int = 300  # 150 | 300
