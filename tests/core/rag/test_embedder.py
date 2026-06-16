"""Unit tests for src/core/rag/embedder.py — availability and embedding shape.

OllamaEmbeddings is never instantiated for real here: the langchain_ollama
module is replaced with a fake so the tests run without Ollama.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest


def _fake_ollama_module(*, query_vec=None, doc_vecs=None, raises=None) -> MagicMock:
    """Build a fake `langchain_ollama` module exposing OllamaEmbeddings."""
    embeddings = MagicMock()
    if raises is not None:
        embeddings.embed_query.side_effect = raises
    else:
        embeddings.embed_query.return_value = query_vec or [0.0] * 4
    embeddings.embed_documents.return_value = doc_vecs or [[0.0] * 4]

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
        sys.modules,
        {"langchain_ollama": _fake_ollama_module(doc_vecs=[[1, 2, 3], [4, 5, 6]])},
    )
    arr = embedder.embed_texts(["a", "b"])
    assert arr.shape == (2, 3)
    assert arr.dtype == np.float32


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
