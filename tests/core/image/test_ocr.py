"""Unit tests for image OCR (core/image/ocr.py) with a mocked Tesseract."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from src.core.image import ocr

pytestmark = pytest.mark.unit


def _src(tmp_path: Path) -> Path:
    p = tmp_path / "doc.png"
    Image.new("RGB", (120, 60), (255, 255, 255)).save(p)
    return p


def test_ocr_image_writes_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Fake the tesseract binary resolution and the pytesseract module.
    monkeypatch.setattr(ocr, "resolve_tesseract_cmd", lambda: "tesseract")

    fake = types.ModuleType("pytesseract")
    fake.pytesseract = types.SimpleNamespace(tesseract_cmd="")
    fake.image_to_string = lambda im, lang="por": "  Olá mundo  \n"
    monkeypatch.setitem(sys.modules, "pytesseract", fake)

    out_dir = tmp_path / "out"
    out_path, words = ocr.ocr_image(_src(tmp_path), out_dir, lang="por")

    assert out_path.exists()
    assert out_path.name == "doc_ocr.txt"
    assert out_path.read_text(encoding="utf-8") == "Olá mundo"
    assert words == 2


def test_ocr_image_raises_without_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "resolve_tesseract_cmd", lambda: None)
    with pytest.raises(RuntimeError):
        ocr.ocr_image(_src(tmp_path), tmp_path / "out")
