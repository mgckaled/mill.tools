"""Unit tests for src/gui/modules/ai/worker.py — index/answer event emission.

The worker has no Flet dependency: it emits through a fake bus. The RAG core is
mocked at its boundaries (embedder, make_llm) so no Ollama is needed.
install_log_handler=False keeps the root logger untouched.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class _Bus:
    """Captures (type, payload) and ignores stage/module_id."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, type, stage, payload=None, module_id=""):
        self.events.append((type, payload or {}))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def payload_of(self, type: str) -> dict:
        return next(p for t, p in self.events if t == type)


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _make_item(path, *, kind="transcription", mtime=1.0):
    from src.core.library.types import LibraryItem

    return LibraryItem(
        path=path,
        kind=kind,
        category="text",
        size_bytes=path.stat().st_size,
        modified=mtime,
        stem=path.stem,
        suffix=path.suffix.lower(),
    )


@pytest.mark.unit
def test_index_emits_progress_and_done(tmp_path, monkeypatch, mocker):
    import src.core.rag.indexer as indexer
    from src.gui.modules.ai.worker import run_ai_index

    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    mocker.patch("src.core.library.scanner.scan_library", return_value=[_make_item(f)])
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_texts",
        return_value=np.ones((1, 768), dtype=np.float32),
    )

    bus = _Bus()
    ok = run_ai_index(
        bus,
        threading.Event(),
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    assert ok is True
    assert "progress_start" in bus.types()
    assert "index_start" in bus.types()
    assert "index_done" in bus.types()
    assert "task_done" in bus.types()
    assert bus.payload_of("index_done")["n_chunks"] == 1
    assert (rag_dir / "vectors.npz").exists()


@pytest.mark.unit
def test_index_errors_when_embedder_unavailable(mocker):
    from src.gui.modules.ai.worker import run_ai_index

    mocker.patch("src.core.rag.embedder.is_available", return_value=False)

    bus = _Bus()
    ok = run_ai_index(
        bus,
        threading.Event(),
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    assert ok is False
    assert "task_error" in bus.types()
    assert "ollama pull" in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_answer_errors_when_index_empty(tmp_path, monkeypatch):
    import src.core.rag.indexer as indexer
    from src.gui.modules.ai.worker import run_ai_answer

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")

    bus = _Bus()
    ok = run_ai_answer(
        bus,
        threading.Event(),
        query="q?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    assert ok is False
    assert "Índice vazio" in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_answer_emits_answer_done_with_sources(tmp_path, monkeypatch, mocker):
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta
    from src.gui.modules.ai.worker import run_ai_answer

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=768)
    store.add(
        np.ones((1, 768), dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta [1]"))

    bus = _Bus()
    ok = run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    assert ok is True
    assert "answer_start" in bus.types()
    assert "task_done" in bus.types()
    done = bus.payload_of("answer_done")
    assert done["text"] == "resposta [1]"
    assert done["sources"] == ["doc.txt"]
    # Timing fields feed the per-model "typical time" estimate in the view.
    assert done["model_name"] == "qwen7b-custom"
    assert done["elapsed"] >= 0.0


@pytest.mark.unit
def test_index_cancel_emits_error(tmp_path, monkeypatch, mocker):
    import src.core.rag.indexer as indexer
    from src.gui.modules.ai.worker import run_ai_index

    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    mocker.patch("src.core.library.scanner.scan_library", return_value=[_make_item(f)])
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_texts",
        return_value=np.ones((1, 768), dtype=np.float32),
    )

    cancel = threading.Event()
    cancel.set()  # cancel before the first progress callback fires

    bus = _Bus()
    ok = run_ai_index(
        bus, cancel, embed_model="nomic-embed-text", install_log_handler=False
    )

    assert ok is False
    assert "cancelada" in bus.payload_of("task_error")["message"].lower()
