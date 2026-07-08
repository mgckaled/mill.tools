"""Unit tests for src/core/rag/stats.py — index summary + pure formatters."""

from __future__ import annotations

import time

import numpy as np
import pytest


def _meta(source: str, idx: int, *, kind: str = "transcription", text: str = "x"):
    from src.core.rag.types import ChunkMeta

    return ChunkMeta(
        source_path=source, kind=kind, mtime=100.0, chunk_idx=idx, text=text
    )


def _persist_store(
    tmp_path, *, embed_model="nomic-embed-custom", embed_scheme="test-scheme"
):
    """Persist a 3-dim store: doc 'a.txt' (2 chunks) + 'b.txt' (1 chunk, document)."""
    from src.core.rag.store import VectorStore

    store = VectorStore(dim=3)
    store.add(
        np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32),
        [
            _meta("a.txt", 0, text="hello"),
            _meta("a.txt", 1, text="world!"),
            _meta("b.txt", 0, kind="document", text="doc"),
        ],
    )
    store.persist(tmp_path, embed_model=embed_model, embed_scheme=embed_scheme)
    return store


# ---------------------------------------------------------------------------
# index_stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_index_stats_counts_and_dim(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    stats = index_stats(tmp_path)

    assert stats.n_docs == 2
    assert stats.n_chunks == 3
    assert stats.dim == 3
    assert stats.embed_model == "nomic-embed-custom"
    assert stats.embed_scheme == "test-scheme"
    assert stats.disk_bytes > 0
    assert stats.updated_at is not None


@pytest.mark.unit
def test_index_stats_per_doc_ordering_and_aggregation(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    stats = index_stats(tmp_path)

    # Heaviest document first (a.txt has 2 chunks, b.txt has 1).
    assert [d.source_path for d in stats.per_doc] == ["a.txt", "b.txt"]
    a = stats.per_doc[0]
    assert a.n_chunks == 2
    assert a.kind == "transcription"
    assert a.char_total == len("hello") + len("world!")
    assert a.mtime == 100.0
    b = stats.per_doc[1]
    assert b.kind == "document"
    assert b.n_chunks == 1


@pytest.mark.unit
def test_index_stats_missing_index_is_zeroed(tmp_path):
    from src.core.rag.stats import index_stats

    stats = index_stats(tmp_path / "nope")
    assert stats.n_docs == 0
    assert stats.n_chunks == 0
    assert stats.dim == 0
    assert stats.embed_model == "?"
    assert stats.embed_scheme == "?"
    assert stats.disk_bytes == 0
    assert stats.updated_at is None
    assert stats.per_doc == ()


@pytest.mark.unit
def test_index_stats_unknown_embed_model_when_sidecar_missing(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "index_info.json").unlink()  # simulate a pre-PR7.2 index
    stats = index_stats(tmp_path)
    assert stats.embed_model == "?"
    assert stats.n_chunks == 3  # the rest is still readable


@pytest.mark.unit
def test_index_stats_null_embed_model_falls_back_to_question_mark(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path, embed_model=None)  # persisted with embed_model=None
    stats = index_stats(tmp_path)
    assert stats.embed_model == "?"


@pytest.mark.unit
def test_index_stats_corrupt_meta_is_zeroed(tmp_path):
    from src.core.rag.stats import index_stats

    (tmp_path / "meta.json").write_text("{ not json", encoding="utf-8")
    stats = index_stats(tmp_path)
    assert stats.n_docs == 0
    assert stats.per_doc == ()


@pytest.mark.unit
def test_index_stats_updated_at_matches_vectors_mtime(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    expected = (tmp_path / "vectors.npz").stat().st_mtime
    assert index_stats(tmp_path).updated_at == pytest.approx(expected)


@pytest.mark.unit
def test_index_stats_corrupt_info_sidecar_falls_back(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "index_info.json").write_text("{ broken", encoding="utf-8")
    assert index_stats(tmp_path).embed_model == "?"


@pytest.mark.unit
def test_index_stats_meta_without_vectors(tmp_path):
    """meta.json present but vectors.npz absent → dim 0, no updated_at."""
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "vectors.npz").unlink()
    stats = index_stats(tmp_path)
    assert stats.dim == 0
    assert stats.updated_at is None
    assert stats.n_chunks == 3  # meta still readable


@pytest.mark.unit
def test_index_stats_trusts_sidecar_dim_even_if_vectors_content_is_corrupt(tmp_path):
    """dim is read from the sidecar without decompressing vectors.npz to
    double-check it — bit rot in the matrix's binary content is not this
    field's job to detect, as long as the sidecar is present and valid."""
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "vectors.npz").write_bytes(b"not a real npz archive")
    assert index_stats(tmp_path).dim == 3


@pytest.mark.unit
def test_index_stats_dim_falls_back_to_npz_when_sidecar_missing(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "index_info.json").unlink()
    assert index_stats(tmp_path).dim == 3


@pytest.mark.unit
def test_index_stats_dim_zero_when_both_vectors_and_sidecar_are_corrupt(tmp_path):
    from src.core.rag.stats import index_stats

    _persist_store(tmp_path)
    (tmp_path / "vectors.npz").write_bytes(b"not a real npz archive")
    (tmp_path / "index_info.json").write_text("{ broken", encoding="utf-8")
    assert index_stats(tmp_path).dim == 0


# ---------------------------------------------------------------------------
# embed_space_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_embed_space_id_combines_model_dim_and_scheme(tmp_path):
    from src.core.rag.stats import embed_space_id

    _persist_store(tmp_path, embed_model="nomic-embed-custom", embed_scheme="v2")
    assert embed_space_id(tmp_path) == "nomic-embed-custom:3:v2"


@pytest.mark.unit
def test_embed_space_id_stable_placeholder_for_index_without_sidecar(tmp_path):
    from src.core.rag.stats import embed_space_id

    _persist_store(tmp_path)
    (tmp_path / "index_info.json").unlink()
    assert embed_space_id(tmp_path) == "?:3:?"  # falls back to the npz shape


@pytest.mark.unit
def test_embed_space_id_missing_index_is_question_mark_zero(tmp_path):
    from src.core.rag.stats import embed_space_id

    assert embed_space_id(tmp_path) == "?:0:?"


@pytest.mark.unit
def test_embed_space_id_changes_when_model_changes(tmp_path):
    from src.core.rag.stats import embed_space_id

    _persist_store(tmp_path, embed_model="nomic-embed-custom")
    id_a = embed_space_id(tmp_path)
    _persist_store(tmp_path, embed_model="bge-m3")
    id_b = embed_space_id(tmp_path)
    assert id_a != id_b


@pytest.mark.unit
def test_embed_space_id_changes_when_scheme_changes(tmp_path):
    from src.core.rag.stats import embed_space_id

    _persist_store(tmp_path, embed_scheme="v1")
    id_a = embed_space_id(tmp_path)
    _persist_store(tmp_path, embed_scheme="v2")
    id_b = embed_space_id(tmp_path)
    assert id_a != id_b


@pytest.mark.unit
def test_embed_space_id_question_mark_scheme_for_index_predating_the_field(tmp_path):
    """An index persisted before this field existed has no ``embed_scheme``
    key at all in its sidecar — must degrade to "?", not KeyError/None."""
    from src.core.rag.stats import embed_space_id

    _persist_store(tmp_path, embed_model="nomic-embed-custom", embed_scheme=None)
    assert embed_space_id(tmp_path) == "nomic-embed-custom:3:?"


# ---------------------------------------------------------------------------
# is_stale_scheme
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_stale_scheme_true_when_scheme_differs(tmp_path):
    from src.core.rag.stats import index_stats, is_stale_scheme

    _persist_store(tmp_path, embed_scheme="old-scheme")
    stats = index_stats(tmp_path)
    assert is_stale_scheme(stats, "new-scheme") is True


@pytest.mark.unit
def test_is_stale_scheme_false_when_scheme_matches(tmp_path):
    from src.core.rag.stats import index_stats, is_stale_scheme

    _persist_store(tmp_path, embed_scheme="current-scheme")
    stats = index_stats(tmp_path)
    assert is_stale_scheme(stats, "current-scheme") is False


@pytest.mark.unit
def test_is_stale_scheme_false_for_empty_index(tmp_path):
    from src.core.rag.stats import index_stats, is_stale_scheme

    stats = index_stats(tmp_path / "nope")
    assert is_stale_scheme(stats, "current-scheme") is False


# ---------------------------------------------------------------------------
# fmt_status_line
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fmt_status_line_thousands_and_month(tmp_path):
    from src.core.rag.stats import IndexStats, fmt_status_line

    # 20 jun 2026 20:45 local time.
    ts = time.mktime(time.struct_time((2026, 6, 20, 20, 45, 0, 0, 0, -1)))
    stats = IndexStats(
        n_docs=28,
        n_chunks=4654,
        dim=768,
        embed_model="nomic-embed-custom",
        disk_bytes=1234,
        updated_at=ts,
        per_doc=(),
    )
    line = fmt_status_line(stats)
    assert "28 docs" in line
    assert "4.654 chunks" in line  # dot thousands separator
    assert "20 jun 20:45" in line


@pytest.mark.unit
def test_fmt_status_line_empty_index():
    from src.core.rag.stats import IndexStats, fmt_status_line

    empty = IndexStats(0, 0, 0, "?", 0, None, ())
    assert fmt_status_line(empty) == "Índice vazio"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, "0"), (999, "999"), (1000, "1.000"), (4654, "4.654"), (1234567, "1.234.567")],
)
def test_fmt_thousands(n, expected):
    from src.core.rag.stats import fmt_thousands

    assert fmt_thousands(n) == expected


@pytest.mark.unit
def test_fmt_datetime_pt_month():
    from src.core.rag.stats import fmt_datetime

    ts = time.mktime(time.struct_time((2026, 1, 5, 9, 3, 0, 0, 0, -1)))
    assert fmt_datetime(ts) == "5 jan 09:03"


@pytest.mark.unit
def test_fmt_status_line_without_timestamp():
    from src.core.rag.stats import IndexStats, fmt_status_line

    stats = IndexStats(3, 3000, 768, "m", 10, None, ())
    line = fmt_status_line(stats)
    assert line == "3 docs · 3.000 chunks"  # no trailing date


# ---------------------------------------------------------------------------
# fmt_disk_size
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0 B"),
        (512, "512 B"),
        (1536, "1.5 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (3 * 1024 * 1024 * 1024, "3.0 GB"),
    ],
)
def test_fmt_disk_size(num_bytes, expected):
    from src.core.rag.stats import fmt_disk_size

    assert fmt_disk_size(num_bytes) == expected


# ---------------------------------------------------------------------------
# chunks_for
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chunks_for_returns_ordered_pairs(tmp_path):
    from src.core.rag.stats import chunks_for

    _persist_store(tmp_path)
    rows = chunks_for(tmp_path, "a.txt")
    assert rows == [(0, "hello"), (1, "world!")]


@pytest.mark.unit
def test_chunks_for_unknown_source_is_empty(tmp_path):
    from src.core.rag.stats import chunks_for

    _persist_store(tmp_path)
    assert chunks_for(tmp_path, "missing.txt") == []


@pytest.mark.unit
def test_chunks_for_missing_index_is_empty(tmp_path):
    from src.core.rag.stats import chunks_for

    assert chunks_for(tmp_path / "nope", "a.txt") == []


@pytest.mark.unit
def test_chunks_for_corrupt_meta_is_empty(tmp_path):
    from src.core.rag.stats import chunks_for

    (tmp_path / "meta.json").write_text("nope", encoding="utf-8")
    assert chunks_for(tmp_path, "a.txt") == []
