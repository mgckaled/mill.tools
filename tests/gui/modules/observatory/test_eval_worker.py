"""Unit tests for src/gui/modules/observatory/eval_worker.py — the eval flow.

The worker has no Flet dependency: it emits through a fake bus. The RAG core is
mocked at its boundaries (embedder) so no Ollama is needed.
install_log_handler=False keeps the root logger untouched.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest


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


def _persist_store(directory, *, source="aula.txt", scheme=None):
    from src.core.rag.indexer import CURRENT_EMBED_SCHEME
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    store = VectorStore(dim=768)
    store.add(
        np.ones((1, 768), dtype=np.float32),
        [ChunkMeta(source, "transcription", 1.0, 0, "context text")],
    )
    store.persist(
        directory,
        embed_model="nomic-embed-custom",
        embed_scheme=scheme or CURRENT_EMBED_SCHEME,
    )


def _seed_covered(eval_path, *, question="o que diz a aula?", expected=("aula.txt",)):
    import src.core.rag.eval as eval_mod

    eval_mod.save_eval_data(
        eval_mod.EvalData(
            golden=(eval_mod.GoldenQuestion(question, expected=expected),), runs=()
        ),
        eval_path,
    )


def _run(bus, cancel=None):
    from src.gui.modules.observatory.eval_worker import run_eval_pipeline

    return run_eval_pipeline(
        bus,
        cancel or threading.Event(),
        embed_model="nomic-embed-custom",
        install_log_handler=False,
    )


@pytest.mark.unit
def test_eval_emits_progress_and_done(tmp_path, monkeypatch, mocker):
    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    rag_dir = tmp_path / "rag"
    _persist_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    eval_path = tmp_path / "rag_eval.json"
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: eval_path)
    _seed_covered(eval_path)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    bus = _Bus()
    ok = _run(bus)

    assert ok is True
    assert "progress_start" in bus.types()
    assert "eval_start" in bus.types()
    assert "eval_progress" in bus.types()
    assert "eval_done" in bus.types()
    assert "task_done" in bus.types()
    assert bus.payload_of("eval_start")["total"] == 1
    assert bus.payload_of("eval_done")["hit_rate"] == pytest.approx(1.0)
    # the run was recorded and the activity logged
    assert len(eval_mod.load_eval_data(eval_path).runs) == 1
    assert log_mock.call_args.args[1] == "rag_eval"


@pytest.mark.unit
def test_eval_errors_when_embedder_unavailable(tmp_path, monkeypatch, mocker):
    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    rag_dir = tmp_path / "rag"
    _persist_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: tmp_path / "rag_eval.json")
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)

    bus = _Bus()
    ok = _run(bus)

    assert ok is False
    assert "ollama pull" in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_eval_errors_on_empty_index(tmp_path, monkeypatch):
    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: tmp_path / "rag_eval.json")

    bus = _Bus()
    ok = _run(bus)

    assert ok is False
    assert "vazio" in bus.payload_of("task_error")["message"].lower()


@pytest.mark.unit
def test_eval_errors_on_stale_scheme(tmp_path, monkeypatch):
    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    rag_dir = tmp_path / "rag"
    _persist_store(rag_dir, scheme="esquema-antigo")  # != CURRENT → stale
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: tmp_path / "rag_eval.json")

    bus = _Bus()
    ok = _run(bus)

    assert ok is False
    assert "esquema antigo" in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_eval_errors_on_empty_golden(tmp_path, monkeypatch):
    import json

    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    rag_dir = tmp_path / "rag"
    _persist_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    eval_path = tmp_path / "rag_eval.json"
    eval_path.write_text(json.dumps({"golden": [], "runs": []}), encoding="utf-8")
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: eval_path)

    bus = _Bus()
    ok = _run(bus)

    assert ok is False
    assert "Golden set vazio" in bus.payload_of("task_error")["message"]


@pytest.mark.unit
def test_eval_cancel_emits_error(tmp_path, monkeypatch, mocker):
    import src.core.rag.eval as eval_mod
    import src.core.rag.indexer as indexer

    rag_dir = tmp_path / "rag"
    _persist_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    eval_path = tmp_path / "rag_eval.json"
    monkeypatch.setattr(eval_mod, "eval_store_path", lambda: eval_path)
    _seed_covered(eval_path)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    mocker.patch("src.core.observatory.activity.log_activity")

    cancel = threading.Event()
    cancel.set()  # cancel before the first progress callback fires

    bus = _Bus()
    ok = _run(bus, cancel)

    assert ok is False
    assert "cancelada" in bus.payload_of("task_error")["message"].lower()
