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
def test_indexable_items_includes_data_kind(tmp_path):
    from src.core.rag.indexer import indexable_items

    items = [
        _item(tmp_path / "a.txt", kind="transcription"),
        _item(tmp_path / "vendas.csv", kind="data"),
        _item(tmp_path / "book.xlsx", kind="data"),
        _item(tmp_path / "song.mp3", kind="audio"),
    ]
    out = indexable_items(items)
    # Data items match by kind regardless of suffix; audio is still excluded.
    assert {it.path.name for it in out} == {"a.txt", "vendas.csv", "book.xlsx"}


@pytest.mark.unit
def test_build_index_uses_card_fn_for_data_items(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "vendas.csv"
    f.write_text("produto,qtd\nmaca,3\n", encoding="utf-8")
    emb = _Embedder()
    # The card_fn replaces "read the file as text" — the indexer embeds the card.
    store = build_index(
        [_item(f, kind="data")],
        _store(),
        emb,
        card_fn=lambda item: f"ARQUIVO: {item.path.name} · cartão de dados",
    )
    assert len(store) == 1
    assert store.meta[0].kind == "data"
    assert "cartão de dados" in store.meta[0].text


@pytest.mark.unit
def test_build_index_skips_data_items_without_card_fn(tmp_path):
    from src.core.rag.indexer import build_index

    f = tmp_path / "vendas.csv"
    f.write_text("produto,qtd\nmaca,3\n", encoding="utf-8")
    emb = _Embedder()
    # No card_fn → data items produce no text and are not embedded.
    store = build_index([_item(f, kind="data")], _store(), emb)
    assert len(store) == 0
    assert emb.calls == 0


@pytest.mark.unit
def test_build_index_skips_data_item_when_card_fn_raises(tmp_path):
    from src.core.rag.indexer import build_index

    good = tmp_path / "ok.txt"
    good.write_text("texto", encoding="utf-8")
    bad = tmp_path / "broken.csv"
    bad.write_text("x", encoding="utf-8")

    def _card(item):
        raise RuntimeError("DuckDB exploded")

    store = build_index(
        [_item(good), _item(bad, kind="data")], _store(), _Embedder(), card_fn=_card
    )
    # The failing data item is skipped; the healthy text item still indexes.
    assert {m.source_path for m in store.meta} == {str(good)}


@pytest.mark.unit
def test_index_files_is_additive_no_reconciliation(tmp_path):
    from src.core.rag.indexer import build_index, index_files

    a = tmp_path / "a.txt"
    a.write_text("aaa", encoding="utf-8")
    b = tmp_path / "vendas.csv"
    b.write_text("produto,qtd\nmaca,3\n", encoding="utf-8")

    store = _store()
    build_index([_item(a)], store, _Embedder())  # library has 'a'
    assert {m.source_path for m in store.meta} == {str(a)}

    # Indexing only 'b' must ADD it without dropping 'a' (no reconciliation).
    index_files(
        [_item(b, kind="data")],
        store,
        _Embedder(),
        card_fn=lambda item: f"cartão de {item.path.name}",
    )
    assert {m.source_path for m in store.meta} == {str(a), str(b)}


@pytest.mark.unit
def test_index_files_reembeds_each_time(tmp_path):
    from src.core.rag.indexer import index_files

    f = tmp_path / "vendas.csv"
    f.write_text("produto\nmaca\n", encoding="utf-8")
    store = _store()
    emb = _Embedder()
    card = {"text": "cartão v1"}

    index_files([_item(f, kind="data")], store, emb, card_fn=lambda _i: card["text"])
    assert emb.calls == 1 and len(store) == 1

    # Same file, asked again → re-embedded (explicit user action, no skip).
    card["text"] = "cartão v2 mais longo"
    index_files([_item(f, kind="data")], store, emb, card_fn=lambda _i: card["text"])
    assert emb.calls == 2
    assert len(store) == 1  # old chunk replaced
    assert store.meta[0].text == "cartão v2 mais longo"


@pytest.mark.unit
def test_index_files_skips_failing_card(tmp_path):
    from src.core.rag.indexer import index_files

    f = tmp_path / "broken.csv"
    f.write_text("x", encoding="utf-8")

    def _card(_item):
        raise RuntimeError("DuckDB boom")

    store = index_files([_item(f, kind="data")], _store(), _Embedder(), card_fn=_card)
    assert len(store) == 0


@pytest.mark.unit
def test_build_index_skips_item_when_embed_fn_raises(tmp_path):
    """One document's embed failure (e.g. Ollama restarting mid-job) must not
    abort the whole indexing run — the healthy item still indexes."""
    from src.core.rag.indexer import build_index

    good = tmp_path / "ok.txt"
    good.write_text("texto", encoding="utf-8")
    bad = tmp_path / "broken.txt"
    bad.write_text("outro texto", encoding="utf-8")

    def _embed(texts):
        if any("outro" in t for t in texts):
            raise RuntimeError("Ollama down mid-batch")
        return np.ones((len(texts), _EMBED_W), dtype=np.float32)

    store = build_index([_item(good), _item(bad)], _store(), _embed)
    assert {m.source_path for m in store.meta} == {str(good)}


@pytest.mark.unit
def test_build_index_embed_failure_leaves_previous_chunks_dropped(tmp_path):
    """A re-embed failure on a changed file leaves it de-indexed (its stale
    chunks were already dropped) rather than crashing — same outcome as if
    the file's content had gone blank; it recovers on the next successful run."""
    from src.core.rag.indexer import build_index

    f = tmp_path / "doc.txt"
    f.write_text("v1", encoding="utf-8")
    store = build_index([_item(f, mtime=1.0)], _store(), _Embedder())
    assert len(store) == 1

    def _failing_embed(_texts):
        raise RuntimeError("Ollama down")

    store = build_index([_item(f, mtime=2.0)], store, _failing_embed)
    assert len(store) == 0


@pytest.mark.unit
def test_index_files_skips_item_when_embed_fn_raises(tmp_path):
    from src.core.rag.indexer import index_files

    f = tmp_path / "broken.txt"
    f.write_text("texto", encoding="utf-8")

    def _failing_embed(_texts):
        raise RuntimeError("Ollama down")

    store = index_files([_item(f)], _store(), _failing_embed)
    assert len(store) == 0


@pytest.mark.unit
def test_index_dir_resolves_under_home(monkeypatch, tmp_path):
    from src.core.rag.indexer import index_dir

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert index_dir() == tmp_path / ".mill-tools" / "rag"
