"""Tests for src/core/document/ocr.py.

Unit tests mock pytesseract (the [ocr] extra) so they run without the package,
exercising the hybrid native-text/OCR logic. One integration test runs real
Tesseract end-to-end and skips gracefully when the binary is absent.
"""

import sys
from unittest.mock import MagicMock

import pytest


# ─── resolve_tesseract_cmd ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_resolve_prefers_path(mocker):
    from src.core.document import ocr

    mocker.patch(
        "src.core.document.ocr.shutil.which", return_value="/usr/bin/tesseract"
    )
    assert ocr.resolve_tesseract_cmd() == "/usr/bin/tesseract"


@pytest.mark.unit
def test_resolve_falls_back_to_windows_dir(mocker, tmp_path):
    from src.core.document import ocr

    mocker.patch("src.core.document.ocr.shutil.which", return_value=None)
    fake_exe = tmp_path / "tesseract.exe"
    fake_exe.write_bytes(b"")
    mocker.patch("src.core.document.ocr._WINDOWS_FALLBACKS", (fake_exe,))
    assert ocr.resolve_tesseract_cmd() == str(fake_exe)


@pytest.mark.unit
def test_resolve_none_when_missing(mocker):
    from src.core.document import ocr

    mocker.patch("src.core.document.ocr.shutil.which", return_value=None)
    mocker.patch("src.core.document.ocr._WINDOWS_FALLBACKS", ())
    assert ocr.resolve_tesseract_cmd() is None


# ─── is_available ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_is_available_false_without_binary(mocker):
    from src.core.document import ocr

    mocker.patch("src.core.document.ocr.shutil.which", return_value=None)
    mocker.patch("src.core.document.ocr._WINDOWS_FALLBACKS", ())
    assert ocr.is_available() is False


@pytest.mark.unit
def test_is_available_false_without_pytesseract(mocker):
    from src.core.document import ocr

    mocker.patch(
        "src.core.document.ocr.shutil.which", return_value="/usr/bin/tesseract"
    )
    mocker.patch.dict(sys.modules, {"pytesseract": None})  # import → ImportError
    assert ocr.is_available() is False


@pytest.mark.unit
def test_is_available_true_with_binary_and_pytesseract(mocker):
    from src.core.document import ocr

    mocker.patch(
        "src.core.document.ocr.shutil.which", return_value="/usr/bin/tesseract"
    )
    mocker.patch.dict(sys.modules, {"pytesseract": MagicMock()})
    assert ocr.is_available() is True


# ─── ocr_pdf ────────────────────────────────────────────────────────────────────


def _patch_tesseract(mocker, ocr_text="texto reconhecido"):
    """Mock the pytesseract module and resolve a fake binary path."""
    fake = MagicMock()
    fake.image_to_string.return_value = ocr_text
    mocker.patch.dict(sys.modules, {"pytesseract": fake})
    mocker.patch(
        "src.core.document.ocr.resolve_tesseract_cmd", return_value="tesseract"
    )
    return fake


@pytest.mark.unit
def test_ocr_pdf_uses_native_text_when_present(sample_pdf, out_dir, mocker):
    """Pages with a text layer are read natively — Tesseract is not invoked."""
    from src.core.document import ocr

    fake = _patch_tesseract(mocker)
    out_path, word_count = ocr.ocr_pdf(sample_pdf, out_dir, lang="por")
    assert out_path.exists()
    assert out_path.name.endswith("_ocr.txt")
    assert word_count > 0
    assert "Page 1" in out_path.read_text(encoding="utf-8")
    fake.image_to_string.assert_not_called()


@pytest.mark.unit
def test_ocr_pdf_falls_back_to_ocr_on_image_page(
    sample_pdf_with_images, out_dir, mocker
):
    """Image-only pages (no text layer) are rasterized and OCR'd."""
    from src.core.document import ocr

    fake = _patch_tesseract(mocker, ocr_text="reconhecido via ocr")
    out_path, word_count = ocr.ocr_pdf(
        sample_pdf_with_images, out_dir, lang="eng", dpi=150
    )
    assert out_path.exists()
    fake.image_to_string.assert_called()
    body = out_path.read_text(encoding="utf-8")
    assert "reconhecido via ocr" in body
    # word_count includes the per-page header ("--- Página 1 ---") like extract_text
    assert word_count >= 3


@pytest.mark.unit
def test_ocr_pdf_calls_progress_cb_per_page(sample_pdf, out_dir, mocker):
    from src.core.document import ocr

    _patch_tesseract(mocker)
    calls: list[tuple[int, int]] = []
    ocr.ocr_pdf(sample_pdf, out_dir, progress_cb=lambda c, t: calls.append((c, t)))
    assert calls == [(1, 3), (2, 3), (3, 3)]


@pytest.mark.unit
def test_ocr_pdf_raises_when_binary_unresolved(sample_pdf, out_dir, mocker):
    from src.core.document import ocr

    mocker.patch.dict(sys.modules, {"pytesseract": MagicMock()})
    mocker.patch("src.core.document.ocr.resolve_tesseract_cmd", return_value=None)
    with pytest.raises(RuntimeError, match="Tesseract"):
        ocr.ocr_pdf(sample_pdf, out_dir)


# ─── integration (real Tesseract) ───────────────────────────────────────────────


@pytest.mark.integration
def test_ocr_pdf_real_tesseract_reads_rendered_text(out_dir, tmp_path):
    """End-to-end: render text to an image-only PDF and OCR it with real Tesseract."""
    from src.core.document import ocr

    if not ocr.is_available():
        pytest.skip("Tesseract não disponível no PATH/locais padrão")

    import pymupdf
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (640, 200), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=48)
    draw.text((20, 70), "HELLO OCR WORLD", fill="black", font=font)
    png = tmp_path / "rendered.png"
    img.save(png)

    doc = pymupdf.open()
    page = doc.new_page(width=640, height=200)
    page.insert_image(pymupdf.Rect(0, 0, 640, 200), filename=str(png))
    pdf = tmp_path / "scan.pdf"
    doc.save(str(pdf))
    doc.close()

    out_path, word_count = ocr.ocr_pdf(pdf, out_dir, lang="eng", dpi=300)
    text = out_path.read_text(encoding="utf-8").upper()
    assert word_count > 0
    assert "HELLO" in text or "WORLD" in text or "OCR" in text
