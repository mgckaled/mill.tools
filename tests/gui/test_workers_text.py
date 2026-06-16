"""Unit tests for the text-input branch of the transcription worker.

A local .txt/.md skips download + Whisper and runs only the LLM steps on a copy
under transcriptions/text/ (the source is never rewritten in place).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import src.gui.workers as workers
from src.gui.workers import PipelineArgs, run_pipeline


class _Bus:
    """Minimal EventBus stand-in capturing (type, payload) tuples."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, type: str, stage: str, payload: dict, module_id: str | None = None):
        self.events.append((type, payload))


@pytest.fixture
def isolate(monkeypatch, tmp_path: Path):
    """Stub dependency checks and redirect the transcription output dir."""
    monkeypatch.setattr(workers, "check_dependencies", lambda: None)
    monkeypatch.setattr(workers, "TRANSCRIPTIONS_TEXT_DIR", tmp_path / "text")
    return tmp_path


@pytest.mark.unit
def test_text_input_requires_an_analysis(isolate, tmp_path: Path):
    txt = tmp_path / "notes.txt"
    txt.write_text("conteúdo " * 20, encoding="utf-8")

    bus = _Bus()
    result = run_pipeline(PipelineArgs(url=str(txt)), bus, threading.Event())

    assert not result.completed
    assert any(t == "task_error" for t, _ in bus.events)


@pytest.mark.unit
def test_text_input_runs_analyzer_on_a_copy(isolate, tmp_path: Path, monkeypatch):
    txt = tmp_path / "notes.txt"
    original = "conteúdo para análise. " * 20
    txt.write_text(original, encoding="utf-8")

    seen: dict = {}

    def fake_analyze(input_path, model_name=None, transcription=None, on_event=None):
        seen["input_path"] = Path(input_path)
        return tmp_path / "notes.md"

    monkeypatch.setattr(workers.analyzer, "analyze", fake_analyze)

    bus = _Bus()
    result = run_pipeline(
        PipelineArgs(url=str(txt), use_analyze=True, analyzer_model="qwen7b-custom"),
        bus,
        threading.Event(),
    )

    assert result.completed
    assert any(t == "task_done" for t, _ in bus.events)
    # The analyzer ran on the copy under transcriptions/text/, never the source.
    assert seen["input_path"] != txt
    assert seen["input_path"].parent == (tmp_path / "text")
    assert (tmp_path / "text" / "notes.txt").exists()
    assert txt.read_text(encoding="utf-8") == original  # source preserved
