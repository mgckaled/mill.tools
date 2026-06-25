"""Document (PDF) step adapters for the recipe registry."""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_IMAGE,
    KIND_PDF,
    KIND_TEXT,
    StepContext,
    StepSpec,
)


def _doc_merge(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """N PDFs → one merged PDF. Wraps merge_pdfs (consumes the whole input list)."""
    from src.core.document.processor import merge_pdfs
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = merge_pdfs([Path(p) for p in inputs], DOCUMENT_PROCESSED_DIR)
    return [out]


def _doc_split(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → one PDF per page range. Wraps split_pdf."""
    from src.core.document.processor import split_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    return split_pdf(
        Path(inputs[0]), params.get("pages", "all"), DOCUMENT_PROCESSED_DIR
    )


def _doc_compress(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → image-recompressed PDF. Wraps compress_pdf."""
    from src.core.document.processor import compress_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = compress_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        image_quality=params.get("image_quality", 75),
    )
    return [out]


def _doc_rotate(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → rotated PDF. Wraps rotate_pdf."""
    from src.core.document.processor import rotate_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = rotate_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        angle=params.get("angle", 90),
        pages=params.get("pages", "all"),
    )
    return [out]


def _doc_watermark(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → watermarked PDF. Wraps watermark_pdf."""
    from src.core.document.processor import watermark_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = watermark_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        text=params.get("text", "CONFIDENCIAL"),
        opacity=params.get("opacity", 0.3),
        position=params.get("position", "center"),
    )
    return [out]


def _doc_stamp(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → stamped PDF. Wraps stamp_pdf."""
    from src.core.document.processor import stamp_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = stamp_pdf(
        Path(inputs[0]), DOCUMENT_PROCESSED_DIR, text=params.get("text", "RASCUNHO")
    )
    return [out]


def _doc_encrypt(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → AES-256 encrypted PDF. Wraps encrypt_pdf."""
    from src.core.document.processor import encrypt_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = encrypt_pdf(
        Path(inputs[0]), DOCUMENT_PROCESSED_DIR, password=params.get("password", "")
    )
    return [out]


def _doc_extract(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → extracted text .txt. Wraps extract_text (keeps only the path)."""
    from src.core.document.converter import extract_text
    from src.utils import DOCUMENT_PROCESSED_DIR

    out, _wc = extract_text(Path(inputs[0]), DOCUMENT_PROCESSED_DIR)
    return [out]


def _doc_ocr(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """scanned PDF → OCR text .txt. Wraps ocr_pdf (hybrid native + Tesseract)."""
    from src.core.document.ocr import ocr_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out, _wc = ocr_pdf(
        Path(inputs[0]),
        DOCUMENT_PROCESSED_DIR,
        lang=params.get("lang", "por"),
        dpi=params.get("dpi", 300),
        progress_cb=lambda c, t: ctx.emit(
            "progress_update", {"current": c, "total": t}
        ),
    )
    return [out]


def _doc_pdf_to_images(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """PDF → one image per page. Wraps pdf_to_images (writes to image/processed)."""
    from src.core.document.converter import pdf_to_images
    from src.utils import IMAGE_PROCESSED_DIR

    return pdf_to_images(
        Path(inputs[0]),
        IMAGE_PROCESSED_DIR,
        fmt=params.get("fmt", "jpg"),
        dpi=params.get("dpi", 150),
        progress_cb=lambda c, t: ctx.emit(
            "progress_update", {"current": c, "total": t}
        ),
    )


def _doc_images_to_pdf(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """N images → one PDF. Wraps images_to_pdf (consumes the whole input list)."""
    from src.core.document.converter import images_to_pdf
    from src.utils import DOCUMENT_PROCESSED_DIR

    out = images_to_pdf(
        [Path(p) for p in inputs],
        DOCUMENT_PROCESSED_DIR,
        output_name=params.get("output_name", ""),
    )
    return [out]


DOCUMENT_STEPS: dict[str, StepSpec] = {
    "document.merge": StepSpec(
        _doc_merge, frozenset({KIND_PDF}), KIND_PDF, "Mesclar PDFs"
    ),
    "document.split": StepSpec(
        _doc_split, frozenset({KIND_PDF}), KIND_PDF, "Dividir PDF"
    ),
    "document.compress": StepSpec(
        _doc_compress, frozenset({KIND_PDF}), KIND_PDF, "Comprimir PDF"
    ),
    "document.rotate": StepSpec(
        _doc_rotate, frozenset({KIND_PDF}), KIND_PDF, "Girar PDF"
    ),
    "document.watermark": StepSpec(
        _doc_watermark, frozenset({KIND_PDF}), KIND_PDF, "Marca d'água"
    ),
    "document.stamp": StepSpec(
        _doc_stamp, frozenset({KIND_PDF}), KIND_PDF, "Carimbar PDF"
    ),
    "document.encrypt": StepSpec(
        _doc_encrypt, frozenset({KIND_PDF}), KIND_PDF, "Criptografar PDF"
    ),
    "document.extract": StepSpec(
        _doc_extract, frozenset({KIND_PDF}), KIND_TEXT, "Extrair texto"
    ),
    "document.ocr": StepSpec(_doc_ocr, frozenset({KIND_PDF}), KIND_TEXT, "OCR"),
    "document.pdf_to_images": StepSpec(
        _doc_pdf_to_images, frozenset({KIND_PDF}), KIND_IMAGE, "PDF → imagens"
    ),
    "document.images_to_pdf": StepSpec(
        _doc_images_to_pdf, frozenset({KIND_IMAGE}), KIND_PDF, "Imagens → PDF"
    ),
}
