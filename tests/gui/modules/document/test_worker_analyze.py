"""Unit tests for the Documents 'analyze' worker accepting a text file.

A .txt/.md is analyzed as-is (no PDF rasterize/extract), and the reported output
path is the one analyzer.analyze() actually returns.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import src.gui.modules.document.worker as docworker
from src.core.document.args import DocumentArgs


@pytest.mark.unit
def test_run_analyze_text_skips_pdf_extraction(tmp_path: Path, monkeypatch):
    txt = tmp_path / "extract.txt"
    txt.write_text("palavra " * 50, encoding="utf-8")
    md = tmp_path / "extract.md"
    md.write_text("# análise", encoding="utf-8")

    seen: dict = {}

    def fake_analyze(
        input_path,
        model_name=None,
        transcription=None,
        on_event=None,
        profile="default",
    ):
        seen["input_path"] = Path(input_path)
        seen["profile"] = profile
        return md

    # The worker imports analyze lazily (from src.analyzer import analyze).
    monkeypatch.setattr("src.analyzer.analyze", fake_analyze)
    # Guard: a PDF-only helper must not be reached on the text branch.
    monkeypatch.setattr(
        "src.core.document.info.get_pdf_info",
        lambda *a, **k: pytest.fail("get_pdf_info called on a text file"),
    )

    events: list[tuple[str, dict]] = []

    def emit(type: str, payload: dict | None = None) -> None:
        events.append((type, payload or {}))

    args = DocumentArgs(
        input_paths=[txt],
        operation="analyze",
        analyze_model="qwen7b-custom",
        analyze_profile="scientific",
    )
    ok = docworker._run_analyze(args, emit, threading.Event())

    assert ok
    types = [t for t, _ in events]
    assert "task_done" in types
    assert seen["input_path"] == txt  # analyzed the .txt directly
    assert seen["profile"] == "scientific"  # profile threaded through
    start = next(p for t, p in events if t == "document_op_start")
    assert start["page_count"] == 0
    done = next(p for t, p in events if t == "document_op_done")
    assert done["output_path"] == str(md)  # real returned path, not a guess
