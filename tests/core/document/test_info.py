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
