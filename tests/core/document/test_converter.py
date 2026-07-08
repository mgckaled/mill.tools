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


def test_images_to_pdf_raises_on_empty_list(out_dir):
    from src.core.document.converter import images_to_pdf

    with pytest.raises(ValueError):
        images_to_pdf([], out_dir)


def _exif_oriented_jpeg(tmp_path, size=(60, 40), orientation=6):
    """A landscape JPEG carrying an EXIF Orientation tag (274)."""
    from PIL import Image

    path = tmp_path / "photo.jpg"
    img = Image.new("RGB", size, (10, 20, 30))
    exif = img.getexif()
    exif[274] = orientation
    img.save(path, exif=exif)
    return path


def test_images_to_pdf_applies_exif_transpose(tmp_path, out_dir):
    """A landscape photo with Orientation=6 must land as a portrait page
    (40x60), not sideways (60x40) — same bug family fixed in core/image."""
    from src.core.document.converter import images_to_pdf
    import pymupdf  # type: ignore[import-untyped]

    src = _exif_oriented_jpeg(tmp_path)
    out = images_to_pdf([src], out_dir)

    doc = pymupdf.open(str(out))
    page = doc[0]
    assert (page.rect.width, page.rect.height) == (40, 60)
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
