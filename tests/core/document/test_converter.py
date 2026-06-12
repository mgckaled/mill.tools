"""Unit tests for src/core/document/converter.py."""
import pytest

pytestmark = pytest.mark.unit


def test_pdf_to_images_page_count_matches(sample_pdf, out_dir):
    from src.core.document.converter import pdf_to_images
    imgs = pdf_to_images(sample_pdf, out_dir)
    assert len(imgs) == 3


def test_pdf_to_images_output_jpg(sample_pdf, out_dir):
    from src.core.document.converter import pdf_to_images
    imgs = pdf_to_images(sample_pdf, out_dir, fmt="jpg")
    assert all(p.suffix == ".jpg" for p in imgs)


def test_pdf_to_images_output_png(sample_pdf, out_dir):
    from src.core.document.converter import pdf_to_images
    imgs = pdf_to_images(sample_pdf, out_dir, fmt="png")
    assert all(p.suffix == ".png" for p in imgs)


def test_images_to_pdf_creates_file(session_jpg, out_dir):
    from src.core.document.converter import images_to_pdf
    out = images_to_pdf([session_jpg, session_jpg, session_jpg], out_dir)
    assert out.exists()
    assert out.suffix == ".pdf"


def test_images_to_pdf_page_count_matches_inputs(session_jpg, out_dir):
    from src.core.document.converter import images_to_pdf
    import pymupdf  # type: ignore[import-untyped]
    out = images_to_pdf([session_jpg, session_jpg, session_jpg], out_dir)
    doc = pymupdf.open(str(out))
    assert doc.page_count == 3
    doc.close()


def test_extract_text_returns_nonempty_string(sample_pdf, out_dir):
    from src.core.document.converter import extract_text
    txt_path, word_count = extract_text(sample_pdf, out_dir)
    content = txt_path.read_text(encoding="utf-8")
    assert "Page 1" in content
    assert word_count > 0


def test_extract_text_returns_empty_for_image_only_pdf(sample_pdf_with_images, out_dir):
    from src.core.document.converter import extract_text
    _txt_path, word_count = extract_text(sample_pdf_with_images, out_dir)
    assert word_count == 0
