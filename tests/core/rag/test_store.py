"""Unit tests for src/core/rag/store.py — cosine search, drop, persist/load."""

from __future__ import annotations

import numpy as np
import pytest


def _meta(source: str, idx: int = 0, *, kind: str = "transcription", text: str = "x"):
    from src.core.rag.types import ChunkMeta

    return ChunkMeta(source_path=source, kind=kind, mtime=1.0, chunk_idx=idx, text=text)


@pytest.mark.unit
def test_add_and_len():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    assert len(store) == 0
    store.add(
        np.eye(3, dtype=np.float32), [_meta("a", 0), _meta("a", 1), _meta("a", 2)]
    )
    assert len(store) == 3
    assert store.vectors.shape == (3, 3)


@pytest.mark.unit
def test_add_rejects_length_mismatch():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    with pytest.raises(ValueError):
        store.add(np.eye(3, dtype=np.float32), [_meta("a", 0)])


@pytest.mark.unit
def test_add_empty_is_noop():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.empty((0, 3), dtype=np.float32), [])
    assert len(store) == 0


@pytest.mark.unit
def test_search_ranks_identical_above_orthogonal():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32),
        [_meta("x", 0), _meta("y", 1), _meta("z", 2)],
    )
    hits = store.search(np.array([1, 0, 0], dtype=np.float32), k=3)

    assert hits[0].meta.source_path == "x"
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)
    # Orthogonal vectors score ~0.
    assert hits[1].score == pytest.approx(0.0, abs=1e-5)
    assert hits[2].score == pytest.approx(0.0, abs=1e-5)


@pytest.mark.unit
def test_search_respects_k():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32), [_meta("a", i) for i in range(3)])
    assert len(store.search(np.array([1, 0, 0], dtype=np.float32), k=2)) == 2


@pytest.mark.unit
def test_search_empty_store_returns_empty():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    assert store.search(np.array([1, 0, 0], dtype=np.float32)) == []


@pytest.mark.unit
def test_search_caches_normalized_vectors():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32), [_meta("a", i) for i in range(3)])
    assert store._normalized is None

    store.search(np.array([1, 0, 0], dtype=np.float32))
    cached = store._normalized
    assert cached is not None

    store.search(np.array([0, 1, 0], dtype=np.float32))
    assert store._normalized is cached  # same array instance — not recomputed


@pytest.mark.unit
def test_add_invalidates_normalized_cache():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32)[:2], [_meta("a", i) for i in range(2)])
    store.search(np.array([1, 0, 0], dtype=np.float32))
    assert store._normalized is not None

    store.add(np.eye(3, dtype=np.float32)[2:], [_meta("a", 2)])
    assert store._normalized is None


@pytest.mark.unit
def test_drop_source_invalidates_normalized_cache():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32),
        [_meta("keep", 0), _meta("gone", 1), _meta("keep", 2)],
    )
    store.search(np.array([1, 0, 0], dtype=np.float32))
    assert store._normalized is not None

    store.drop_source("gone")
    assert store._normalized is None


@pytest.mark.unit
def test_search_mask_restricts_candidates_before_ranking():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.array([[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0]], dtype=np.float32),
        [_meta("a", 0), _meta("b", 0), _meta("c", 0)],
    )
    mask = np.array([False, False, True])  # only "c" is a valid candidate
    hits = store.search(np.array([1, 0, 0], dtype=np.float32), k=3, mask=mask)
    assert [h.meta.source_path for h in hits] == ["c"]


@pytest.mark.unit
def test_search_mask_returns_fewer_than_k_when_scope_is_small():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32), [_meta("a", 0), _meta("b", 0), _meta("c", 0)]
    )
    mask = np.array([True, False, False])
    hits = store.search(np.array([1, 0, 0], dtype=np.float32), k=3, mask=mask)
    assert len(hits) == 1
    assert hits[0].meta.source_path == "a"


@pytest.mark.unit
def test_search_mask_all_false_returns_empty():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32)[:1], [_meta("a", 0)])
    mask = np.array([False])
    assert store.search(np.array([1, 0, 0], dtype=np.float32), mask=mask) == []


@pytest.mark.unit
def test_drop_source_removes_only_matching_chunks():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32),
        [_meta("keep", 0), _meta("gone", 0), _meta("keep", 1)],
    )
    store.drop_source("gone")

    assert len(store) == 2
    assert {m.source_path for m in store.meta} == {"keep"}
    assert store.vectors.shape == (2, 3)


@pytest.mark.unit
def test_drop_source_unknown_is_noop():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32)[:1], [_meta("a", 0)])
    store.drop_source("missing")
    assert len(store) == 1


@pytest.mark.unit
def test_drop_all_sources_leaves_empty_matrix():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32)[:1], [_meta("a", 0)])
    store.drop_source("a")
    assert len(store) == 0
    assert store.vectors.shape == (0, 3)


@pytest.mark.unit
def test_persist_and_load_round_trip(tmp_path):
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32),
        [
            _meta("a.txt", 0, text="hello"),
            _meta("b.txt", 1, kind="document", text="world"),
        ],
    )
    store.persist(tmp_path)

    loaded = VectorStore.load(tmp_path, dim=3)
    assert len(loaded) == 2
    np.testing.assert_allclose(loaded.vectors, store.vectors, rtol=1e-6)
    assert loaded.meta[0].source_path == "a.txt"
    assert loaded.meta[0].text == "hello"
    assert loaded.meta[1].kind == "document"


@pytest.mark.unit
def test_load_missing_dir_returns_empty_store(tmp_path):
    from src.core.rag.store import VectorStore

    loaded = VectorStore.load(tmp_path / "does-not-exist", dim=3)
    assert len(loaded) == 0
