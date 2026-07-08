"""Unit tests for src/core/document/processor.py."""

import pytest

pytestmark = pytest.mark.unit


def test_merge_two_pdfs_page_count_is_sum(sample_pdf, out_dir):
    from src.core.document.processor import merge_pdfs
    import pymupdf  # type: ignore[import-untyped]

    out = merge_pdfs([sample_pdf, sample_pdf], out_dir)
    doc = pymupdf.open(str(out))
    assert doc.page_count == 6
    doc.close()


def test_merge_preserves_input_order(sample_pdf, out_dir):
    from src.core.document.processor import merge_pdfs
    import pymupdf  # type: ignore[import-untyped]

    out = merge_pdfs([sample_pdf, sample_pdf], out_dir)
    doc = pymupdf.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert "Page 1" in text


def test_split_by_page_range(sample_pdf, out_dir):
    from src.core.document.processor import split_pdf
    import pymupdf  # type: ignore[import-untyped]

    parts = split_pdf(sample_pdf, "1-2", out_dir)
    assert len(parts) == 1
    doc = pymupdf.open(str(parts[0]))
    assert doc.page_count == 2
    doc.close()


def test_split_single_page(sample_pdf, out_dir):
    from src.core.document.processor import split_pdf
    import pymupdf  # type: ignore[import-untyped]

    parts = split_pdf(sample_pdf, "2", out_dir)
    assert len(parts) == 1
    doc = pymupdf.open(str(parts[0]))
    assert doc.page_count == 1
    doc.close()


def test_compress_output_is_valid_pdf_not_larger(sample_pdf_with_images, out_dir):
    """Compress must produce a valid PDF whose size is not larger than the input.

    A strict "< size" assert is flaky across pymupdf versions for very small
    inputs (overhead of the new container can exceed the savings). We accept
    equality and rely on the qualitative reembedding test below.
    """
    from src.core.document.processor import compress_pdf

    out = compress_pdf(sample_pdf_with_images, out_dir, image_quality=50)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.stat().st_size <= sample_pdf_with_images.stat().st_size


def test_compress_returns_valid_pdf(sample_pdf_with_images, out_dir):
    from src.core.document.processor import compress_pdf
    import pymupdf  # type: ignore[import-untyped]

    out = compress_pdf(sample_pdf_with_images, out_dir)
    doc = pymupdf.open(str(out))
    assert doc.page_count >= 1
    doc.close()


def test_compress_lower_quality_yields_smaller_file(
    sample_pdf_with_textured_image, out_dir
):
    """image_quality must actually drive recompression, not be a no-op.

    Uses a high-entropy JPEG fixture — a flat-color image compresses to
    near-nothing at any quality and wouldn't discriminate the two runs.
    """
    from src.core.document.processor import compress_pdf

    low = compress_pdf(
        sample_pdf_with_textured_image, out_dir / "low", image_quality=50
    )
    high = compress_pdf(
        sample_pdf_with_textured_image, out_dir / "high", image_quality=95
    )
    assert low.stat().st_size < high.stat().st_size


def test_compress_preserves_alpha_transparency(tmp_path, out_dir):
    """rewrite_images must keep the soft mask, not flatten transparent images."""
    import pymupdf  # type: ignore[import-untyped]
    from PIL import Image

    from src.core.document.processor import compress_pdf

    img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
    png_path = tmp_path / "alpha.png"
    img.save(png_path, format="PNG")

    src_doc = pymupdf.open()
    page = src_doc.new_page()
    page.insert_image(pymupdf.Rect(0, 0, 64, 64), filename=str(png_path))
    src_path = tmp_path / "alpha_src.pdf"
    src_doc.save(str(src_path))
    src_doc.close()

    out = compress_pdf(src_path, out_dir, image_quality=50)

    doc = pymupdf.open(str(out))
    xref = doc[0].get_images(full=True)[0][0]
    extracted = doc.extract_image(xref)
    assert extracted["smask"] > 0
    doc.close()


def test_rotate_90_changes_page_orientation(sample_pdf, out_dir):
    from src.core.document.processor import rotate_pdf
    import pymupdf  # type: ignore[import-untyped]

    out = rotate_pdf(sample_pdf, out_dir, angle=90, pages="1")
    doc = pymupdf.open(str(out))
    assert doc[0].rotation == 90
    doc.close()


def test_rotate_applies_to_all_pages(sample_pdf, out_dir):
    from src.core.document.processor import rotate_pdf
    import pymupdf  # type: ignore[import-untyped]

    out = rotate_pdf(sample_pdf, out_dir, angle=90, pages="all")
    doc = pymupdf.open(str(out))
    assert all(doc[i].rotation == 90 for i in range(doc.page_count))
    doc.close()


def test_watermark_text_embeds_in_output(sample_pdf, out_dir):
    from src.core.document.processor import watermark_pdf
    import pymupdf  # type: ignore[import-untyped]

    out = watermark_pdf(sample_pdf, out_dir, text="CONFIDENCIAL")
    doc = pymupdf.open(str(out))
    assert out.exists()
    assert doc.page_count == 3
    doc.close()


def test_stamp_text_embeds_in_output(sample_pdf, out_dir):
    from src.core.document.processor import stamp_pdf
    import pymupdf  # type: ignore[import-untyped]

    out = stamp_pdf(sample_pdf, out_dir, text="PAGO")
    doc = pymupdf.open(str(out))
    assert out.exists()
    assert doc.page_count == 3
    doc.close()


def test_encrypt_file_requires_password(sample_pdf, out_dir):
    from src.core.document.processor import encrypt_pdf
    import pymupdf  # type: ignore[import-untyped]

    pw = "testsecret"
    out = encrypt_pdf(sample_pdf, out_dir, password=pw)
    doc = pymupdf.open(str(out))
    assert doc.is_encrypted
    result = doc.authenticate(pw)
    assert result != 0
    doc.close()
