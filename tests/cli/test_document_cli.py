"""Unit tests for src/cli/document.py."""

import argparse

import pytest

pytestmark = pytest.mark.unit


def _parse(*argv: str) -> argparse.Namespace:
    """Isolated parser helper — never touches sys.argv."""
    from src.cli.document import add_document_parser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_document_parser(sub)
    return parser.parse_args(["document", *argv])


def test_merge_defaults():
    ns = _parse("merge", "a.pdf", "b.pdf")
    assert ns.document_op == "merge"
    assert ns.files == ["a.pdf", "b.pdf"]


def test_merge_accepts_multiple_files():
    ns = _parse("merge", "a.pdf", "b.pdf", "c.pdf")
    assert len(ns.files) == 3


def test_split_pages_flag():
    ns = _parse("split", "doc.pdf", "--pages", "1-3")
    assert ns.document_op == "split"
    assert ns.pages == "1-3"


def test_compress_image_quality_flag():
    ns = _parse("compress", "doc.pdf", "--image-quality", "60")
    assert ns.image_quality == 60


def test_rotate_angle_flag():
    ns = _parse("rotate", "doc.pdf", "--angle", "180")
    assert ns.angle == 180


def test_watermark_text_flag():
    ns = _parse("watermark", "doc.pdf", "--text", "CONF.")
    assert ns.text == "CONF."


def test_watermark_opacity_flag():
    ns = _parse("watermark", "doc.pdf", "--text", "X", "--opacity", "0.5")
    assert ns.opacity == pytest.approx(0.5)


def test_stamp_text_flag():
    ns = _parse("stamp", "doc.pdf", "--text", "PAGO")
    assert ns.text == "PAGO"


def test_encrypt_password_flag():
    ns = _parse("encrypt", "doc.pdf", "--password", "senha")
    assert ns.password == "senha"


def test_extract_defaults():
    ns = _parse("extract", "doc.pdf")
    assert ns.document_op == "extract"
    assert ns.file == "doc.pdf"


def test_qr_url_input():
    ns = _parse("qr", "https://example.com")
    assert ns.document_op == "qr"
    assert ns.data == "https://example.com"


def test_pdf_to_images_fmt_flag():
    ns = _parse("pdf-to-images", "doc.pdf", "--fmt", "png")
    assert ns.fmt == "png"


def test_ocr_defaults():
    ns = _parse("ocr", "scanned.pdf")
    assert ns.document_op == "ocr"
    assert ns.file == "scanned.pdf"
    assert ns.ocr_lang == "por"
    assert ns.ocr_dpi == 300


def test_ocr_lang_and_dpi_flags():
    ns = _parse("ocr", "scanned.pdf", "--lang", "por+eng", "--dpi", "150")
    assert ns.ocr_lang == "por+eng"
    assert ns.ocr_dpi == 150


def test_func_callable_for_all_ops():
    ops_and_args = [
        ("merge", ["a.pdf"]),
        ("split", ["doc.pdf"]),
        ("compress", ["doc.pdf"]),
        ("rotate", ["doc.pdf"]),
        ("watermark", ["doc.pdf", "--text", "W"]),
        ("stamp", ["doc.pdf"]),
        ("encrypt", ["doc.pdf", "--password", "x"]),
        ("extract", ["doc.pdf"]),
        ("ocr", ["doc.pdf"]),
        ("pdf-to-images", ["doc.pdf"]),
        ("images-to-pdf", ["a.jpg"]),
        ("qr", ["data"]),
    ]
    for op, extra in ops_and_args:
        ns = _parse(op, *extra)
        assert callable(ns.func), f"ns.func not callable for op={op}"


def test_run_document_cli_merge_dispatches_to_pipeline(mocker, tmp_path):
    """document merge a.pdf b.pdf → DocumentArgs with operation='merge' and 2 input_paths."""
    mocker.patch("src.utils.setup_logging")
    mock_pipeline = mocker.patch(
        "src.gui.modules.document.worker.run_document_pipeline",
        return_value=True,
    )
    ns = _parse("merge", "a.pdf", "b.pdf")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "merge"
    assert len(args.input_paths) == 2


def test_run_document_cli_pdf_to_images_normalises_op(mocker):
    """'pdf-to-images' (kebab) becomes 'pdf_to_images' (snake) in DocumentArgs."""
    mocker.patch("src.utils.setup_logging")
    mock_pipeline = mocker.patch(
        "src.gui.modules.document.worker.run_document_pipeline",
        return_value=True,
    )
    ns = _parse("pdf-to-images", "doc.pdf", "--fmt", "png", "--dpi", "150")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "pdf_to_images"
    assert args.image_fmt == "png"
    assert args.dpi == 150


def test_run_document_cli_ocr_dispatches(mocker):
    """document ocr FILE --lang --dpi → DocumentArgs with operation='ocr' + ocr_*."""
    mocker.patch("src.utils.setup_logging")
    mock_pipeline = mocker.patch(
        "src.gui.modules.document.worker.run_document_pipeline",
        return_value=True,
    )
    ns = _parse("ocr", "scanned.pdf", "--lang", "por+eng", "--dpi", "150")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "ocr"
    assert len(args.input_paths) == 1
    assert args.ocr_lang == "por+eng"
    assert args.ocr_dpi == 150


def test_run_document_cli_qr_has_no_input_paths(mocker):
    """document qr DATA → DocumentArgs with input_paths=[] and qr_data filled."""
    mocker.patch("src.utils.setup_logging")
    mock_pipeline = mocker.patch(
        "src.gui.modules.document.worker.run_document_pipeline",
        return_value=True,
    )
    ns = _parse("qr", "https://example.com")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "qr"
    assert args.input_paths == []
    assert args.qr_data == "https://example.com"
