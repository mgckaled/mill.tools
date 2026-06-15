"""Unit tests for src/core/document/info.py."""

import pytest

pytestmark = pytest.mark.unit


def test_get_pdf_info_returns_dataclass(sample_pdf):
    from src.core.document.info import PdfInfo, get_pdf_info

    info = get_pdf_info(sample_pdf)
    assert isinstance(info, PdfInfo)


def test_get_pdf_info_page_count(sample_pdf):
    from src.core.document.info import get_pdf_info

    info = get_pdf_info(sample_pdf)
    assert info.page_count == 3


def test_get_pdf_info_file_size(sample_pdf):
    from src.core.document.info import get_pdf_info

    info = get_pdf_info(sample_pdf)
    assert info.file_size_bytes > 0


def test_get_pdf_info_has_text_true(sample_pdf):
    from src.core.document.info import get_pdf_info

    info = get_pdf_info(sample_pdf)
    assert info.has_text is True


def test_get_pdf_info_has_text_false(sample_pdf_with_images):
    from src.core.document.info import get_pdf_info

    info = get_pdf_info(sample_pdf_with_images)
    assert info.has_text is False


def test_render_first_page_png_returns_bytes(sample_pdf):
    from src.core.document.info import render_first_page_png

    data = render_first_page_png(sample_pdf)
    assert isinstance(data, bytes) and len(data) > 0


def test_render_first_page_png_zoom_grows_output(sample_pdf):
    from src.core.document.info import render_first_page_png

    small = render_first_page_png(sample_pdf, zoom=1.0)
    big = render_first_page_png(sample_pdf, zoom=2.0)
    assert len(big) > len(small)


def test_render_first_page_png_corrupted_returns_none(tmp_path):
    from src.core.document.info import render_first_page_png

    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    assert render_first_page_png(bad) is None


def test_render_first_page_png_zero_pages_returns_none(mocker):
    # A real on-disk PDF can never have zero pages (pymupdf refuses to save
    # one), so the defensive page_count==0 guard is covered with a fake doc.
    import sys
    from pathlib import Path
    from unittest.mock import MagicMock

    from src.core.document.info import render_first_page_png

    fake_doc = MagicMock()
    fake_doc.page_count = 0
    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = fake_doc
    mocker.patch.dict(sys.modules, {"pymupdf": fake_pymupdf})

    assert render_first_page_png(Path("ghost.pdf")) is None
    fake_doc.close.assert_called_once()
