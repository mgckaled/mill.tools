"""Unit tests for src/core/rag/indexer.py — chunking, incremental, reconcile.

split_text runs for real (cheap, no network); only the embedding function is a
stand-in that returns fixed-width ones and counts its calls.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_EMBED_W = 8  # narrow vectors keep the fake store tiny


class _Embedder:
    """Fake embed_fn: returns ones, records call count and seen texts."""

    def __init__(self) -> None:
        self.calls = 0
        self.texts: list[str] = []

    def __call__(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        self.texts.extend(texts)
        return np.ones((len(texts), _EMBED_W), dtype=np.float32)


def _item(path: Path, *, kind: str = "transcription", mtime: float = 1.0):
    from src.core.library.types import LibraryItem

    return LibraryItem(
        path=path,
        kind=kind,
        category="text",
        size_bytes=path.stat().st_size if path.exists() else 0,
        modified=mtime,
        stem=path.stem,
        suffix=path.suffix.lower(),
    )


def _store():
    from src.core.rag.store import VectorStore

    return VectorStore(dim=_EMBED_W)


@pytest.mark.unit
def test_build_index_embeds_text_item(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    emb = _Embedder()
    store = build_index([_item(f)], _store(), emb)

    assert len(store) == 1
    assert emb.calls == 1
    assert store.meta[0].source_path == str(f)
    assert store.meta[0].text == "hello world"
    assert store.meta[0].kind == "transcription"


@pytest.mark.unit
def test_build_index_chunks_long_text(tmp_path):
    from src.core.rag.indexer import CHUNK_SIZE, build_index

    f = tmp_path / "long.txt"
    body = ". ".join(f"sentence number {i} with some filler words" for i in range(200))
    assert len(body) > CHUNK_SIZE
    f.write_text(body, encoding="utf-8")

    store = build_index([_item(f)], _store(), _Embedder())
    assert len(store) >= 2
    # chunk_idx is sequential within the source.
    assert [m.chunk_idx for m in store.meta] == list(range(len(store)))


@pytest.mark.unit
def test_build_index_strips_transcription_header(tmp_path):
    from src.core.rag.indexer import build_index

    sep = "-" * 64
    f = tmp_path / "t.txt"
    f.write_text(f"title: X\nurl: Y\n{sep}\nactual body text", encoding="utf-8")

    store = build_index([_item(f)], _store(), _Embedder())
    assert store.meta[0].text == "actual body text"


@pytest.mark.unit
def test_indexable_items_keeps_only_text_kinds_and_suffixes(tmp_path):
    from src.core.rag.indexer import indexable_items

    items = [
        _item(tmp_path / "a.txt", kind="transcription"),
        _item(tmp_path / "song.mp3", kind="audio"),
        _item(tmp_path / "pic_description.txt", kind="image"),
        _item(tmp_path / "photo.png", kind="image"),
        _item(tmp_path / "extract.md", kind="document"),
        _item(tmp_path / "scan.pdf", kind="document"),
    ]
    out = indexable_items(items)
    assert {it.path.name for it in out} == {
        "a.txt",
        "pic_description.txt",
        "extract.md",
    }


@pytest.mark.unit
def test_build_index_skips_unchanged_on_rerun(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    item = _item(f, mtime=5.0)
    store = _store()
    emb = _Embedder()

    build_index([item], store, emb)
    assert emb.calls == 1
    # Same (path, mtime) → skipped, no second embedding call.
    build_index([item], store, emb)
    assert emb.calls == 1
    assert len(store) == 1


@pytest.mark.unit
def test_build_index_reembeds_on_mtime_change(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    store = _store()
    emb = _Embedder()

    build_index([_item(f, mtime=1.0)], store, emb)
    assert emb.calls == 1 and len(store) == 1

    f.write_text("changed content", encoding="utf-8")
    build_index([_item(f, mtime=2.0)], store, emb)
    assert emb.calls == 2
    assert len(store) == 1  # stale chunk dropped, new one added
    assert store.meta[0].text == "changed content"


@pytest.mark.unit
def test_build_index_reconciles_removed_source(tmp_path):
    from src.core.rag.indexer import build_index

    a = tmp_path / "a.txt"
    a.write_text("aaa", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("bbb", encoding="utf-8")
    store = _store()

    build_index([_item(a), _item(b)], store, _Embedder())
    assert len(store) == 2

    # b no longer in the scan → its chunks are reconciled away.
    build_index([_item(a)], store, _Embedder())
    assert {m.source_path for m in store.meta} == {str(a)}


@pytest.mark.unit
def test_build_index_reports_progress_per_item(tmp_path):
    from src.core.rag.indexer import build_index

    a = tmp_path / "a.txt"
    a.write_text("x", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("y", encoding="utf-8")
    calls: list[tuple[int, int]] = []

    build_index(
        [_item(a), _item(b)],
        _store(),
        _Embedder(),
        progress_cb=lambda c, t: calls.append((c, t)),
    )
    assert calls == [(1, 2), (2, 2)]


@pytest.mark.unit
def test_build_index_skips_whitespace_only_text(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "empty.txt"
    f.write_text("   \n  ", encoding="utf-8")
    emb = _Embedder()

    store = build_index([_item(f)], _store(), emb)
    assert len(store) == 0
    assert emb.calls == 0


@pytest.mark.unit
def test_build_index_reports_progress_even_when_skipped(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "a.txt"
    f.write_text("hi", encoding="utf-8")
    item = _item(f, mtime=1.0)
    store = _store()
    build_index([item], store, _Embedder())  # first pass indexes it

    calls: list[tuple[int, int]] = []
    build_index(
        [item], store, _Embedder(), progress_cb=lambda c, t: calls.append((c, t))
    )
    # Item is skipped (unchanged) but progress is still reported.
    assert calls == [(1, 1)]


@pytest.mark.unit
def test_index_dir_resolves_under_home(monkeypatch, tmp_path):
    from src.core.rag.indexer import index_dir

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert index_dir() == tmp_path / ".mill-tools" / "rag"
