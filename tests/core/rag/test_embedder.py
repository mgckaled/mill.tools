"""Unit tests for src/core/rag/embedder.py — availability and embedding shape.

OllamaEmbeddings is never instantiated for real here: the langchain_ollama
module is replaced with a fake so the tests run without Ollama.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def isolate_model_timing_store(tmp_path, monkeypatch):
    """embed_texts/embed_query call the real record_timing() — redirect its
    store so running this file never touches the developer's real
    ~/.mill-tools/model_timings.json (same isolation pattern already used for
    gui.settings/activity._store_path in tests/gui/modules/observatory/)."""
    import src.core.observatory.model_timing as model_timing

    path = tmp_path / ".mill-tools" / "model_timings.json"
    monkeypatch.setattr(model_timing, "_store_path", lambda: path)
    return path


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
def test_is_available_pings_with_short_timeout_not_embed_timeout(mocker):
    """A stalled Ollama service must fail the availability check fast — it
    should never wait on EMBED_TIMEOUT (300s), sized for real requests."""
    from src.core.rag import embedder

    module = _fake_ollama_module(query_vec=[0.1] * 4)
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    embedder.is_available()

    _args, kwargs = module.OllamaEmbeddings.call_args
    assert kwargs["client_kwargs"]["timeout"] == embedder.AVAILABILITY_TIMEOUT
    assert embedder.AVAILABILITY_TIMEOUT < embedder.EMBED_TIMEOUT


@pytest.mark.unit
def test_is_available_use_cache_reuses_recent_ping(mocker, monkeypatch):
    """PLANO_CORRECOES_RAG_ML_2, Fase 2.2: use_cache=True must not re-ping
    Ollama within AVAILABILITY_CACHE_TTL — the hot path (one call per
    question) shouldn't cost a round trip every time."""
    from src.core.rag import embedder

    monkeypatch.setattr(embedder, "_availability_cache", {})
    module = _fake_ollama_module(query_vec=[0.1] * 4)
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    assert embedder.is_available(use_cache=True) is True
    assert embedder.is_available(use_cache=True) is True
    assert module.OllamaEmbeddings.call_count == 1


@pytest.mark.unit
def test_is_available_without_cache_pings_every_call(mocker, monkeypatch):
    from src.core.rag import embedder

    monkeypatch.setattr(embedder, "_availability_cache", {})
    module = _fake_ollama_module(query_vec=[0.1] * 4)
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    embedder.is_available()
    embedder.is_available()
    assert module.OllamaEmbeddings.call_count == 2


@pytest.mark.unit
def test_is_available_cache_expires_after_ttl(mocker, monkeypatch):
    from src.core.rag import embedder

    monkeypatch.setattr(embedder, "_availability_cache", {})
    module = _fake_ollama_module(query_vec=[0.1] * 4)
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    fake_now = [1000.0]
    monkeypatch.setattr(embedder.time, "monotonic", lambda: fake_now[0])

    embedder.is_available(use_cache=True)
    fake_now[0] += embedder.AVAILABILITY_CACHE_TTL + 1
    embedder.is_available(use_cache=True)

    assert module.OllamaEmbeddings.call_count == 2


@pytest.mark.unit
def test_is_available_cache_keyed_by_model(mocker, monkeypatch):
    from src.core.rag import embedder

    monkeypatch.setattr(embedder, "_availability_cache", {})
    module = _fake_ollama_module(query_vec=[0.1] * 4)
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    embedder.is_available("model-a", use_cache=True)
    embedder.is_available("model-b", use_cache=True)
    assert module.OllamaEmbeddings.call_count == 2

    # Re-requesting either one within the TTL is a cache hit.
    embedder.is_available("model-a", use_cache=True)
    embedder.is_available("model-b", use_cache=True)
    assert module.OllamaEmbeddings.call_count == 2


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


@pytest.mark.unit
def test_embed_texts_records_one_timing_entry_for_the_whole_call(
    mocker, isolate_model_timing_store
):
    """Sub-batches share one aggregated timing entry (not one each) — logging
    per sub-batch would rewrite the whole model_timings.json log dozens of
    times for a single large document (plan item [O2])."""
    from src.core.observatory.model_timing import load_timings
    from src.core.rag import embedder

    module = _fake_ollama_module(doc_vec=[1, 2, 3])
    mocker.patch.dict(sys.modules, {"langchain_ollama": module})

    embedder.embed_texts(
        ["a", "b", "c", "d", "e"], model="nomic-embed-custom", batch_size=2
    )

    entries = load_timings(isolate_model_timing_store)
    assert len(entries) == 1  # 5 texts at batch_size 2 -> 3 sub-batches, 1 entry
    assert entries[0].domain == "embed"
    assert entries[0].model == "nomic-embed-custom"
    assert entries[0].elapsed >= 0


@pytest.mark.unit
def test_embed_query_records_one_timing_entry(mocker, isolate_model_timing_store):
    from src.core.observatory.model_timing import load_timings
    from src.core.rag import embedder

    mocker.patch.dict(
        sys.modules, {"langchain_ollama": _fake_ollama_module(query_vec=[1, 2, 3, 4])}
    )

    embedder.embed_query("hello", model="nomic-embed-custom")

    entries = load_timings(isolate_model_timing_store)
    assert len(entries) == 1
    assert entries[0].domain == "embed"
    assert entries[0].model == "nomic-embed-custom"


@pytest.mark.unit
def test_embed_texts_empty_records_no_timing(mocker, isolate_model_timing_store):
    from src.core.observatory.model_timing import load_timings
    from src.core.rag import embedder

    mocker.patch.dict(sys.modules, {"langchain_ollama": _fake_ollama_module()})

    embedder.embed_texts([])

    assert load_timings(isolate_model_timing_store) == []
