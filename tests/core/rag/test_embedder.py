"""Unit tests for src/core/rag/embedder.py — availability and embedding shape.

OllamaEmbeddings is never instantiated for real here: the langchain_ollama
module is replaced with a fake so the tests run without Ollama.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest


def _fake_ollama_module(*, query_vec=None, doc_vec=None, raises=None) -> MagicMock:
    """Build a fake `langchain_ollama` module exposing OllamaEmbeddings.

    embed_documents returns one copy of ``doc_vec`` per input text (via
    side_effect) so it behaves correctly when called once per sub-batch.
    """
    embeddings = MagicMock()
    if raises is not None:
        embeddings.embed_query.side_effect = raises
    else:
        embeddings.embed_query.return_value = query_vec or [0.0] * 4
    dv = list(doc_vec) if doc_vec is not None else [0.0] * 4
    embeddings.embed_documents.side_effect = lambda batch: [list(dv) for _ in batch]

    module = MagicMock()
    module.OllamaEmbeddings.return_value = embeddings
    return module


@pytest.mark.unit
def test_is_available_true_when_model_answers(mocker):
    from src.core.rag import embedder

    mocker.patch.dict(
        sys.modules, {"langchain_ollama": _fake_ollama_module(query_vec=[0.1] * 4)}
    )
    assert embedder.is_available() is True


@pytest.mark.unit
def test_is_available_false_when_query_raises(mocker):
    from src.core.rag import embedder

    mocker.patch.dict(
        sys.modules,
        {"langchain_ollama": _fake_ollama_module(raises=RuntimeError("ollama down"))},
    )
    assert embedder.is_available() is False


@pytest.mark.unit
def test_is_available_false_when_package_missing(mocker):
    from src.core.rag import embedder

    # Force the import inside is_available to fail.
    mocker.patch.dict(sys.modules, {"langchain_ollama": None})
    assert embedder.is_available() is False


@pytest.mark.unit
def test_embed_texts_returns_float32_matrix(mocker):
    from src.core.rag import embedder

    mocker.patch.dict(
        sys.modules, {"langchain_ollama": _fake_ollama_module(doc_vec=[1, 2, 3])}
    )
    arr = embedder.embed_texts(["a", "b"])
    assert arr.shape == (2, 3)
    assert arr.dtype == np.float32


@pytest.mark.unit
def test_embed_texts_splits_into_sub_batches(mocker):
    from src.core.rag import embedder

    module = _fake_ollama_module(doc_vec=[1, 2, 3])
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    seen: list[tuple[int, int]] = []
    arr = embedder.embed_texts(
        ["a", "b", "c", "d", "e"],
        batch_size=2,
        progress_cb=lambda d, t: seen.append((d, t)),
    )

    # 5 texts at batch_size 2 → 3 requests, but a single result matrix of 5 rows.
    emb = module.OllamaEmbeddings.return_value
    assert emb.embed_documents.call_count == 3
    assert arr.shape == (5, 3)
    # One client is reused across batches (model stays loaded).
    assert module.OllamaEmbeddings.call_count == 1
    # Progress is reported per batch, capped at the total.
    assert seen == [(2, 5), (4, 5), (5, 5)]


@pytest.mark.unit
def test_embed_texts_empty_returns_empty_matrix(mocker):
    from src.core.rag import embedder

    module = _fake_ollama_module()
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    arr = embedder.embed_texts([])
    assert arr.shape == (0, embedder.EMBED_DIM)
    # No client built, no request sent for an empty input.
    assert module.OllamaEmbeddings.call_count == 0


@pytest.mark.unit
def test_embed_query_returns_vector(mocker):
    from src.core.rag import embedder

    mocker.patch.dict(
        sys.modules, {"langchain_ollama": _fake_ollama_module(query_vec=[1, 2, 3, 4])}
    )
    vec = embedder.embed_query("hello")
    assert vec.shape == (4,)
    assert vec.dtype == np.float32


@pytest.mark.unit
def test_check_dim_warns_on_unexpected_width(caplog):
    import logging

    from src.core.rag import embedder

    with caplog.at_level(logging.WARNING):
        embedder._check_dim(np.zeros((2, 8192), dtype=np.float32))
    assert any("Unexpected embedding dim" in r.message for r in caplog.records)


@pytest.mark.unit
def test_check_dim_silent_on_expected_width(caplog):
    import logging

    from src.core.rag import embedder

    with caplog.at_level(logging.WARNING):
        embedder._check_dim(np.zeros((2, embedder.EMBED_DIM), dtype=np.float32))
    assert not caplog.records
