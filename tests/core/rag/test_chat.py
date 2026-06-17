"""Unit tests for src/core/rag/chat.py — context building and cited answers.

The LLM is mocked with GenericFakeChatModel (a real Runnable) so `prompt | llm`
works without Ollama, following the analyzer/prompter test pattern.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _chunk(
    source: str,
    text: str,
    idx: int = 0,
    *,
    kind: str = "transcription",
    score: float = 0.9,
):
    from src.core.rag.types import ChunkMeta, RetrievedChunk

    return RetrievedChunk(ChunkMeta(source, kind, 1.0, idx, text), score)


@pytest.mark.unit
def test_build_context_numbers_blocks_and_dedupes_sources():
    from src.core.rag.chat import build_context

    retrieved = [
        _chunk("a.txt", "first", 0),
        _chunk("a.txt", "second", 1),
        _chunk("b.txt", "third", 0),
    ]
    context, sources = build_context(retrieved)

    assert "[1] (a.txt)" in context
    assert "[2] (a.txt)" in context
    assert "[3] (b.txt)" in context
    assert "first" in context and "third" in context
    # Distinct sources, first-seen order.
    assert sources == [Path("a.txt"), Path("b.txt")]


@pytest.mark.unit
def test_build_context_empty_retrieval():
    from src.core.rag.chat import build_context

    context, sources = build_context([])
    assert context == "(sem contexto)"
    assert sources == []


@pytest.mark.unit
def test_answer_returns_text_and_cited_sources(mocker):
    from src.core.rag import chat

    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("A resposta [1]."))
    retrieved = [_chunk("a.txt", "ctx", 0), _chunk("a.txt", "ctx2", 1)]

    result = chat.answer("pergunta?", retrieved, model_name="qwen7b-custom")
    assert result.text == "A resposta [1]."
    assert result.sources == [Path("a.txt")]


@pytest.mark.unit
def test_answer_with_empty_retrieval_still_calls_llm(mocker):
    from src.core.rag import chat

    spy = mocker.patch.object(
        chat, "make_llm", return_value=_fake_llm("Não encontrei.")
    )
    result = chat.answer("pergunta?", [], model_name="qwen7b-custom")

    assert "Não encontrei" in result.text
    assert result.sources == []
    assert spy.called


@pytest.mark.unit
def test_answer_emits_start_and_done_events(mocker):
    from src.core.rag import chat

    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("ok"))
    events: list[tuple[str, str]] = []

    chat.answer(
        "q",
        [_chunk("a.txt", "c")],
        on_event=lambda type, stage, payload: events.append((type, stage)),
    )
    types = [t for t, _ in events]
    assert "answer_start" in types
    assert "answer_done" in types
    assert all(stage == "answer" for _, stage in events)
