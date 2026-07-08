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
def test_add_rejects_width_mismatch_on_empty_store():
    """Ollama #10176: a misconfigured embed model can return 8192-dim vectors
    instead of the expected width. On a fresh (empty) store there is no prior
    row for np.vstack to reject against — add() must catch it itself instead
    of silently corrupting self.dim vs. self.vectors."""
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=768)
    with pytest.raises(ValueError, match="768"):
        store.add(np.zeros((2, 8192), dtype=np.float32), [_meta("a", 0), _meta("a", 1)])
    assert len(store) == 0


@pytest.mark.unit
def test_add_width_mismatch_on_non_empty_store_still_raises():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32), [_meta("a", 0), _meta("a", 1), _meta("a", 2)]
    )
    with pytest.raises(ValueError):
        store.add(np.zeros((1, 8), dtype=np.float32), [_meta("b", 0)])


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
def test_dense_scores_matches_search_ranking():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.eye(3, dtype=np.float32), [_meta("a", i) for i in range(3)])
    scores = store.dense_scores(np.array([1, 0, 0], dtype=np.float32))
    assert scores[0] == pytest.approx(1.0, abs=1e-5)
    assert scores[1] == pytest.approx(0.0, abs=1e-5)


@pytest.mark.unit
def test_bm25_scores_ranks_lexical_match_highest():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32),
        [
            _meta("a", 0, text="artigo quinto da constituicao"),
            _meta("b", 0, text="completely unrelated cooking content"),
            _meta("c", 0, text="more unrelated filler text here"),
        ],
    )
    scores = store.bm25_scores("artigo quinto")
    assert np.argmax(scores) == 0


@pytest.mark.unit
def test_bm25_scores_empty_store_returns_empty():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    assert store.bm25_scores("query").shape == (0,)


@pytest.mark.unit
def test_bm25_scores_caches_index():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32), [_meta("a", i, text=f"doc {i}") for i in range(3)]
    )
    assert store._bm25 is None

    store.bm25_scores("doc")
    cached = store._bm25
    assert cached is not None

    store.bm25_scores("doc")
    assert store._bm25 is cached  # same object — not rebuilt


@pytest.mark.unit
def test_add_invalidates_bm25_cache():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32)[:2],
        [_meta("a", i, text=f"doc {i}") for i in range(2)],
    )
    store.bm25_scores("doc")
    assert store._bm25 is not None

    store.add(np.eye(3, dtype=np.float32)[2:], [_meta("a", 2, text="doc 2")])
    assert store._bm25 is None


@pytest.mark.unit
def test_drop_source_invalidates_bm25_cache():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32),
        [
            _meta("keep", 0, text="alpha"),
            _meta("gone", 1, text="beta"),
            _meta("keep", 2, text="gamma"),
        ],
    )
    store.bm25_scores("alpha")
    assert store._bm25 is not None

    store.drop_source("gone")
    assert store._bm25 is None


@pytest.mark.unit
def test_bm25_scores_mask_marks_excluded_rows_as_infinite():
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.eye(3, dtype=np.float32),
        [
            _meta("a", 0, text="artigo quinto"),
            _meta("b", 0, text="artigo sexto"),
            _meta("c", 0, text="unrelated"),
        ],
    )
    mask = np.array([False, True, True])
    scores = store.bm25_scores("artigo", mask=mask)
    assert not np.isfinite(scores[0])
    assert np.isfinite(scores[1])


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


@pytest.mark.unit
def test_load_tolerates_corrupt_npz(tmp_path, caplog):
    """PLANO_CORRECOES_RAG_ML_2, Fase 2.1: a truncated/malformed vectors.npz
    must degrade to an empty store + warning, not raise zipfile.BadZipFile."""
    from src.core.rag.store import VectorStore

    (tmp_path / "vectors.npz").write_bytes(b"PK\x03\x04" + b"garbage" * 5)
    (tmp_path / "meta.json").write_text("[]", encoding="utf-8")

    with caplog.at_level("WARNING"):
        loaded = VectorStore.load(tmp_path, dim=3)

    assert len(loaded) == 0
    assert "Malformed index" in caplog.text


@pytest.mark.unit
def test_load_tolerates_corrupt_meta_json(tmp_path, caplog):
    """A truncated/invalid meta.json (json.JSONDecodeError, a ValueError
    subclass) must degrade the same way as a corrupt npz."""
    from src.core.rag.store import VectorStore

    np.savez_compressed(tmp_path / "vectors.npz", vectors=np.zeros((1, 3)))
    (tmp_path / "meta.json").write_text("{not valid json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        loaded = VectorStore.load(tmp_path, dim=3)

    assert len(loaded) == 0
    assert "Malformed index" in caplog.text


@pytest.mark.unit
def test_persist_leaves_no_tmp_file_behind(tmp_path):
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), [_meta("a.txt")])
    store.persist(tmp_path)

    assert list(tmp_path.glob("*.tmp")) == []
    assert (tmp_path / "vectors.npz").exists()
    assert (tmp_path / "meta.json").exists()
    assert (tmp_path / "index_info.json").exists()


@pytest.mark.unit
def test_load_tolerates_vectors_without_meta_sidecar(tmp_path, caplog):
    from src.core.rag.store import VectorStore

    # Simulate an interrupted/tampered persist: vectors.npz without its
    # meta.json sidecar.
    np.savez_compressed(tmp_path / "vectors.npz", vectors=np.zeros((1, 3)))

    with caplog.at_level("WARNING"):
        loaded = VectorStore.load(tmp_path, dim=3)

    assert len(loaded) == 0
    assert "meta.json sidecar" in caplog.text
