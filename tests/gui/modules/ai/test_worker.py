"""Unit tests for src/gui/modules/ai/worker.py — Conversa + Comandos CLI event
emission.

The worker has no Flet dependency: it emits through a fake bus. The RAG core is
mocked at its boundaries (embedder, make_llm) so no Ollama is needed.
install_log_handler=False keeps the root logger untouched.

The reindex flow's tests moved to
tests/gui/modules/observatory/test_index_worker.py (Fase 0b,
PLANO_NL2CLI_HUB_IA.md) alongside the worker itself.

run_ai_command's tests mock ``to_command``/``build_reference``/
``validate_command`` at their source modules (the same "patch where it's
imported from — a lazy ``from X import Y`` inside the function still resolves
Y off the (patched) module at call time" pattern used for ``chat.make_llm``
above) — nl2cli's own generation logic is already covered by
tests/core/text/test_nl2cli.py; these tests only cover the worker's glue
(gate, event payloads, activity log).
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
    # Query vector == stored vector → cosine ~1.0 → corpus covers it.
    assert done["low_confidence"] is False


@pytest.mark.unit
def test_answer_flags_low_confidence_out_of_corpus(tmp_path, monkeypatch, mocker):
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

    # Query vector orthogonal to the stored all-ones vector → cosine ~0 < 0.35.
    q = np.zeros(768, dtype=np.float32)
    q[0] = 1.0
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=q)
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta"))

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="algo fora do acervo?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    done = bus.payload_of("answer_done")
    assert done["low_confidence"] is True
    assert done["best_score"] < 0.35
    # The warning is also surfaced as a log line.
    assert any("não cobre" in p.get("message", "") for _, p in bus.events)


@pytest.mark.unit
def test_answer_checks_embedder_availability_with_cache(tmp_path, monkeypatch, mocker):
    """PLANO_CORRECOES_RAG_ML_2, Fase 2.2: the hot Conversa path must opt into
    the embedder's short-TTL availability cache instead of pinging Ollama on
    every question."""
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta
    from src.gui.modules.ai.worker import run_ai_answer

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=8)
    store.add(
        np.ones((1, 8), dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    is_available_mock = mocker.patch(
        "src.core.rag.embedder.is_available", return_value=True
    )
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta"))

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    is_available_mock.assert_called_once_with("nomic-embed-text", use_cache=True)


@pytest.mark.unit
def test_answer_low_confidence_uses_max_dense_score_not_first_hit(
    tmp_path, monkeypatch, mocker
):
    """PLANO_CORRECOES_RAG_ML_2, Fase 1.1: `hits` is ordered by the fused RRF
    ranking, not by dense cosine — the first hit can have a low dense score
    while a later hit scores well above the threshold. `low_confidence` must
    reflect the *max* dense score across hits, not `hits[0].score`."""
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    import src.core.rag.retriever as retriever
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta, RetrievedChunk
    from src.gui.modules.ai.worker import run_ai_answer

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=8)
    store.add(
        np.ones((1, 8), dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    # RRF put the low-scoring chunk first (e.g. a lexical-only match) and the
    # high-scoring one second — a fusion order that differs from dense order.
    hits = [
        RetrievedChunk(ChunkMeta("a.txt", "transcription", 1.0, 0, "a"), 0.10),
        RetrievedChunk(ChunkMeta("b.txt", "transcription", 1.0, 0, "b"), 0.90),
    ]
    mocker.patch.object(retriever, "retrieve", return_value=hits)
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta"))

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    done = bus.payload_of("answer_done")
    assert done["best_score"] == pytest.approx(0.90)
    assert done["low_confidence"] is False


@pytest.mark.unit
def test_answer_cancelled_between_retrieve_and_answer(tmp_path, monkeypatch, mocker):
    """PLANO_CORRECOES_RAG_ML_2, Fase 2.3: cancel_event is checked once, right
    after retrieve — a cancel there must skip the (expensive) answer call."""
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    import src.core.rag.retriever as retriever
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta, RetrievedChunk
    from src.gui.modules.ai.worker import run_ai_answer

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=8)
    store.add(
        np.ones((1, 8), dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    hits = [RetrievedChunk(ChunkMeta("a.txt", "transcription", 1.0, 0, "a"), 0.9)]
    mocker.patch.object(retriever, "retrieve", return_value=hits)
    answer_mock = mocker.patch.object(chat, "answer")

    cancel_event = threading.Event()
    cancel_event.set()

    bus = _Bus()
    ok = run_ai_answer(
        bus,
        cancel_event,
        query="pergunta?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        install_log_handler=False,
    )

    assert ok is False
    assert "Cancelado" in bus.payload_of("task_error")["message"]
    answer_mock.assert_not_called()


# ── conversation history / query condensation (Fase 2, PLANO_CONVERSA_
# MULTITURNO.md) ──────────────────────────────────────────────────────────────


def _store_with_one_chunk(tmp_path, monkeypatch, *, dim: int = 8):
    import src.core.rag.indexer as indexer
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    rag_dir = tmp_path / "rag"
    store = VectorStore(dim=dim)
    store.add(
        np.ones((1, dim), dtype=np.float32),
        [ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx")],
    )
    store.persist(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    return rag_dir


@pytest.mark.unit
def test_answer_skips_condensation_when_history_is_empty(tmp_path, monkeypatch, mocker):
    import src.core.rag.chat as chat
    import src.core.rag.condense as condense
    from src.gui.modules.ai.worker import run_ai_answer

    _store_with_one_chunk(tmp_path, monkeypatch)
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta"))
    condense_mock = mocker.patch.object(condense, "condense_query")

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        history=None,
        install_log_handler=False,
    )

    condense_mock.assert_not_called()
    assert "condense_start" not in bus.types()
    done = bus.payload_of("answer_done")
    assert done["search_query"] == done["query"] == "pergunta?"


@pytest.mark.unit
def test_answer_condenses_query_when_history_present(tmp_path, monkeypatch, mocker):
    import src.core.rag.chat as chat
    import src.core.rag.condense as condense
    from src.gui.modules.ai.worker import run_ai_answer

    _store_with_one_chunk(tmp_path, monkeypatch)
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta [1]"))
    condense_mock = mocker.patch.object(
        condense, "condense_query", return_value="pergunta reescrita standalone"
    )

    bus = _Bus()
    ok = run_ai_answer(
        bus,
        threading.Event(),
        query="e sobre isso?",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        history=[("pergunta anterior", "resposta anterior", ["doc.txt"])],
        install_log_handler=False,
    )

    assert ok is True
    assert "condense_start" in bus.types()
    done = bus.payload_of("answer_done")
    assert done["query"] == "e sobre isso?"
    assert done["search_query"] == "pergunta reescrita standalone"

    # Turn tuples are converted to condense.Turn right before the one call
    # that needs them — sources become a tuple, ready for _fmt_history.
    condense_mock.assert_called_once()
    called_question, called_history = condense_mock.call_args[0]
    assert called_question == "e sobre isso?"
    assert called_history[0].question == "pergunta anterior"
    assert called_history[0].answer == "resposta anterior"
    assert called_history[0].sources == ("doc.txt",)

    # The log line announcing the rewrite is only emitted when it actually
    # differs from what the user typed.
    assert any("reformulada" in p.get("message", "") for _, p in bus.events)


@pytest.mark.unit
def test_answer_skips_condensed_log_line_when_rewrite_matches_original(
    tmp_path, monkeypatch, mocker
):
    import src.core.rag.chat as chat
    import src.core.rag.condense as condense
    from src.gui.modules.ai.worker import run_ai_answer

    _store_with_one_chunk(tmp_path, monkeypatch)
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta"))
    mocker.patch.object(condense, "condense_query", return_value="pergunta original")

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta original",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        history=[("q_anterior", "a_anterior", [])],
        install_log_handler=False,
    )

    assert "condense_start" in bus.types()
    assert not any("reformulada" in p.get("message", "") for _, p in bus.events)


@pytest.mark.unit
def test_answer_uses_condensed_query_for_retrieve_and_answer(
    tmp_path, monkeypatch, mocker
):
    """The condensed query — not the raw one — must reach both retrieve() and
    answer(), since it's the one reformulation feeding both uses (Fase 1.3)."""
    from pathlib import Path

    import src.core.rag.chat as chat
    import src.core.rag.condense as condense
    import src.core.rag.retriever as retriever
    from src.core.rag.types import AnswerResult, ChunkMeta, RetrievedChunk
    from src.gui.modules.ai.worker import run_ai_answer

    _store_with_one_chunk(tmp_path, monkeypatch)
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.embedder.embed_query", return_value=np.ones(8))
    mocker.patch.object(condense, "condense_query", return_value="pergunta reescrita")
    retrieve_mock = mocker.patch.object(
        retriever,
        "retrieve",
        return_value=[
            RetrievedChunk(ChunkMeta("doc.txt", "transcription", 1.0, 0, "ctx"), 0.9)
        ],
    )
    answer_mock = mocker.patch.object(
        chat, "answer", return_value=AnswerResult(text="ok", sources=[Path("doc.txt")])
    )

    bus = _Bus()
    run_ai_answer(
        bus,
        threading.Event(),
        query="pergunta original",
        scope=None,
        model_name="qwen7b-custom",
        embed_model="nomic-embed-text",
        history=[("q_anterior", "a_anterior", ["doc.txt"])],
        install_log_handler=False,
    )

    assert retrieve_mock.call_args[0][0] == "pergunta reescrita"
    assert answer_mock.call_args[0][0] == "pergunta reescrita"


# ── run_ai_command (Fase 3) ──────────────────────────────────────────────────


@pytest.mark.unit
def test_command_emits_progress_and_done(mocker):
    from src.gui.modules.ai.worker import run_ai_command

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=("uv run main.py ai index", "Reconstrói o índice."),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    bus = _Bus()
    ok = run_ai_command(
        bus,
        threading.Event(),
        query="reindexa o acervo",
        model_name="qwen7b-custom",
        install_log_handler=False,
    )

    assert ok is True
    assert "progress_start" in bus.types()
    assert "command_start" in bus.types()
    assert "task_done" in bus.types()
    done = bus.payload_of("command_done")
    assert done["command"] == "uv run main.py ai index"
    assert done["explanation"] == "Reconstrói o índice."
    assert done["model_name"] == "qwen7b-custom"
    assert done["elapsed"] >= 0.0
    log_mock.assert_called_once_with("rag", "nl2cli", "uv run main.py ai index")


@pytest.mark.unit
def test_command_errors_when_ollama_unreachable_for_local_model(mocker):
    from src.gui.modules.ai.worker import run_ai_command

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=False),
    )
    to_command_mock = mocker.patch("src.core.text.nl2cli.to_command")

    bus = _Bus()
    ok = run_ai_command(
        bus,
        threading.Event(),
        query="reindexa o acervo",
        model_name="qwen7b-custom",
        install_log_handler=False,
    )

    assert ok is False
    assert "ollama serve" in bus.payload_of("task_error")["message"]
    to_command_mock.assert_not_called()


@pytest.mark.unit
def test_command_skips_ollama_gate_for_cloud_model(mocker):
    from src.gui.modules.ai.worker import run_ai_command

    inventory_mock = mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=False),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=("uv run main.py ai index", "ok"),
    )
    mocker.patch("src.core.observatory.activity.log_activity")

    bus = _Bus()
    ok = run_ai_command(
        bus,
        threading.Event(),
        query="reindexa o acervo",
        model_name="gemini-2.5-flash",
        install_log_handler=False,
    )

    assert ok is True
    inventory_mock.assert_not_called()


@pytest.mark.unit
def test_command_reports_refusal_as_success_without_logging_activity(mocker):
    from src.gui.modules.ai.worker import run_ai_command

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        return_value=("", "Isso não é uma tarefa da CLI."),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    bus = _Bus()
    ok = run_ai_command(
        bus,
        threading.Event(),
        query="qual a previsão do tempo?",
        model_name="qwen7b-custom",
        install_log_handler=False,
    )

    assert ok is True
    done = bus.payload_of("command_done")
    assert done["command"] == ""
    log_mock.assert_called_once_with("rag", "nl2cli", "(fora de escopo)")


@pytest.mark.unit
def test_command_error_surfaces_nl2cli_error_as_task_error(mocker):
    from src.core.text.nl2cli import NL2CLIError
    from src.gui.modules.ai.worker import run_ai_command

    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=mocker.MagicMock(reachable=True),
    )
    mocker.patch("src.cli.reference.build_reference", return_value="REFERÊNCIA")
    mocker.patch(
        "src.core.text.nl2cli.to_command",
        side_effect=NL2CLIError("não consegui gerar um comando válido"),
    )

    bus = _Bus()
    ok = run_ai_command(
        bus,
        threading.Event(),
        query="reindexa o acervo",
        model_name="qwen7b-custom",
        install_log_handler=False,
    )

    assert ok is False
    assert "não consegui gerar" in bus.payload_of("task_error")["message"]
