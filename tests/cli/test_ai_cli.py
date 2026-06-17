"""Unit tests for src/cli/ai.py — parser defaults, dispatch and scope helper."""

from __future__ import annotations

import argparse

import numpy as np
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.cli.ai import add_ai_parser


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_ai_parser(sub)
    return parser.parse_args(["ai", *argv])


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _persisted_store(directory, *, source: str = "doc.txt"):
    """Persist a one-row store at `directory` and return it."""
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    store = VectorStore(dim=768)
    store.add(
        np.ones((1, 768), dtype=np.float32),
        [ChunkMeta(source, "transcription", 1.0, 0, "context text")],
    )
    store.persist(directory)
    return store


@pytest.mark.unit
def test_defaults():
    ns = _parse("what did I say about whisper?")
    assert ns.query == "what did I say about whisper?"
    assert ns.k == 6
    assert ns.scope is None
    assert ns.model is None
    assert ns.embed_model is None
    assert ns.reindex is False
    assert callable(ns.func)


@pytest.mark.unit
def test_parses_options():
    ns = _parse(
        "resuma", "--scope", "transcription", "--model", "gemini-2.5-flash", "--k", "8"
    )
    assert ns.scope == "transcription"
    assert ns.model == "gemini-2.5-flash"
    assert ns.k == 8


@pytest.mark.unit
def test_index_query_dispatches_to_build_only(mocker):
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("index")
    ns.func(ns)

    assert build.called
    assert not ask.called


@pytest.mark.unit
def test_question_dispatches_to_ask_only(mocker):
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("what is x?")
    ns.func(ns)

    assert ask.called
    assert not build.called


@pytest.mark.unit
def test_reindex_flag_builds_then_asks(mocker):
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    build = mocker.patch("src.cli.ai._build")
    ask = mocker.patch("src.cli.ai._ask")

    ns = _parse("what is x?", "--reindex")
    ns.func(ns)

    assert build.called
    assert ask.called


@pytest.mark.unit
def test_index_exits_when_embedder_unavailable(mocker, capsys):
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)
    mocker.patch("src.cli.ai._build")

    ns = _parse("index")
    with pytest.raises(SystemExit):
        ns.func(ns)

    assert "ollama pull" in capsys.readouterr().out


@pytest.mark.unit
def test_resolve_scope_existing_file_becomes_absolute(tmp_path):
    from src.cli.ai import _resolve_scope

    f = tmp_path / "x.txt"
    f.write_text("hi", encoding="utf-8")
    assert _resolve_scope(str(f)) == str(f.resolve())


@pytest.mark.unit
def test_resolve_scope_kind_and_none():
    from src.cli.ai import _resolve_scope

    assert _resolve_scope("transcription") == "transcription"
    assert _resolve_scope(None) is None


@pytest.mark.unit
def test_build_scans_embeds_and_persists(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _build
    from src.core.library.types import LibraryItem

    rag_dir = tmp_path / "rag"
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    item = LibraryItem(
        path=f,
        kind="transcription",
        category="text",
        size_bytes=f.stat().st_size,
        modified=1.0,
        stem="a",
        suffix=".txt",
    )
    mocker.patch("src.core.library.scanner.scan_library", return_value=[item])
    mocker.patch(
        "src.core.rag.embedder.embed_texts",
        return_value=np.ones((1, 768), dtype=np.float32),
    )

    _build("nomic-embed-text")

    assert (rag_dir / "vectors.npz").exists()
    assert "Índice atualizado" in capsys.readouterr().out


@pytest.mark.unit
def test_ask_prints_answer_and_sources(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.chat as chat
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir, source="doc.txt")
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)

    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch(
        "src.core.rag.embedder.embed_query",
        return_value=np.ones(768, dtype=np.float32),
    )
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("resposta [1]"))

    _ask(_parse("pergunta?"), "nomic-embed-text")

    out = capsys.readouterr().out
    assert "resposta [1]" in out
    assert "Fontes:" in out
    assert "doc.txt" in out


@pytest.mark.unit
def test_ask_exits_when_index_empty(tmp_path, monkeypatch, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")

    with pytest.raises(SystemExit):
        _ask(_parse("q?"), "nomic-embed-text")
    assert "Índice vazio" in capsys.readouterr().out


@pytest.mark.unit
def test_ask_exits_when_embedder_unavailable(tmp_path, monkeypatch, mocker, capsys):
    import src.core.rag.indexer as indexer
    from src.cli.ai import _ask

    rag_dir = tmp_path / "rag"
    _persisted_store(rag_dir)
    monkeypatch.setattr(indexer, "index_dir", lambda: rag_dir)
    mocker.patch("src.core.rag.embedder.is_available", return_value=False)

    with pytest.raises(SystemExit):
        _ask(_parse("q?"), "nomic-embed-text")
    assert "ollama pull" in capsys.readouterr().out
