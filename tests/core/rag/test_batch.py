"""Unit tests for src/core/rag/batch.py — distinct sources and per-doc batch."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

_W = 8


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _store(rows):
    """rows: list of (vector, source_path, kind)."""
    from src.core.rag.store import VectorStore
    from src.core.rag.types import ChunkMeta

    store = VectorStore(dim=_W)
    vecs = np.array([v for v, _, _ in rows], dtype=np.float32)
    metas = [
        ChunkMeta(src, kind, 1.0, i, f"text {i}")
        for i, (_, src, kind) in enumerate(rows)
    ]
    store.add(vecs, metas)
    return store


@pytest.mark.unit
def test_distinct_sources_dedupes_in_first_seen_order():
    from src.core.rag.batch import distinct_sources

    store = _store(
        [
            ([1, 0, 0, 0, 0, 0, 0, 0], "a.txt", "transcription"),
            ([0, 1, 0, 0, 0, 0, 0, 0], "a.txt", "transcription"),
            ([0, 0, 1, 0, 0, 0, 0, 0], "b.txt", "document"),
        ]
    )
    assert distinct_sources(store) == ["a.txt", "b.txt"]


@pytest.mark.unit
def test_distinct_sources_filters_by_kind():
    from src.core.rag.batch import distinct_sources

    store = _store(
        [
            ([1, 0, 0, 0, 0, 0, 0, 0], "a.txt", "transcription"),
            ([0, 1, 0, 0, 0, 0, 0, 0], "b.txt", "document"),
        ]
    )
    assert distinct_sources(store, kind="document") == ["b.txt"]


@pytest.mark.unit
def test_run_batch_one_answer_per_source(mocker):
    import src.core.rag.chat as chat
    from src.core.rag.batch import run_batch

    store = _store(
        [
            ([1, 0, 0, 0, 0, 0, 0, 0], "a.txt", "transcription"),
            ([0, 1, 0, 0, 0, 0, 0, 0], "b.txt", "document"),
        ]
    )
    mocker.patch.object(chat, "make_llm", return_value=_fake_llm("R-a", "R-b"))

    calls: list[tuple[int, int]] = []
    results = run_batch(
        "resuma",
        store,
        lambda _q: np.ones(_W, dtype=np.float32),
        sources=["a.txt", "b.txt"],
        progress_cb=lambda c, t: calls.append((c, t)),
    )

    assert [r.source_path for r in results] == ["a.txt", "b.txt"]
    assert results[0].answer.text == "R-a"
    assert results[1].answer.text == "R-b"
    # Each answer is scoped to its own document.
    assert results[0].answer.sources == [Path("a.txt")]
    assert calls == [(1, 2), (2, 2)]


@pytest.mark.unit
def test_run_batch_empty_sources_returns_empty(mocker):
    import src.core.rag.chat as chat
    from src.core.rag.batch import run_batch

    spy = mocker.patch.object(chat, "make_llm")
    out = run_batch(
        "resuma", _store([]), lambda _q: np.ones(_W, dtype=np.float32), sources=[]
    )
    assert out == []
    assert not spy.called
