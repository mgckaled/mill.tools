"""Unit tests for src/core/text/reader.py — header-stripped document body."""

from __future__ import annotations

import pytest

from src.core.text.reader import read_document_text

_SEP = "-" * 64


@pytest.mark.unit
def test_reads_plain_file_whole(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# Título\n\nCorpo do texto.", encoding="utf-8")
    assert read_document_text(f) == "# Título\n\nCorpo do texto."


@pytest.mark.unit
def test_strips_transcription_header(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text(
        f"Modelo: medium\nIdioma: pt\n{_SEP}\nEste é o corpo.", encoding="utf-8"
    )
    assert read_document_text(f) == "Este é o corpo."


@pytest.mark.unit
def test_blank_file_yields_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   \n  ", encoding="utf-8")
    assert read_document_text(f) == ""
