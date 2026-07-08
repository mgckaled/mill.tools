"""Unit tests for src/core/document/_shared.py."""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def encrypted_pdf(sample_pdf, tmp_path):
    from src.core.document.processor import encrypt_pdf

    return encrypt_pdf(sample_pdf, tmp_path, password="testsecret")


def test_open_pdf_returns_open_document(sample_pdf):
    from src.core.document._shared import open_pdf

    doc = open_pdf(sample_pdf)
    assert doc.page_count == 3
    doc.close()


def test_open_pdf_raises_clear_error_on_password_protected(encrypted_pdf):
    from src.core.document._shared import open_pdf

    with pytest.raises(ValueError, match="protegido por senha"):
        open_pdf(encrypted_pdf)


def test_open_pdf_raised_error_names_the_file(encrypted_pdf):
    from src.core.document._shared import open_pdf

    with pytest.raises(ValueError, match=encrypted_pdf.name):
        open_pdf(encrypted_pdf)
