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
        ("pdf-to-images", ["doc.pdf"]),
        ("images-to-pdf", ["a.jpg"]),
        ("qr", ["data"]),
    ]
    for op, extra in ops_and_args:
        ns = _parse(op, *extra)
        assert callable(ns.func), f"ns.func not callable for op={op}"
