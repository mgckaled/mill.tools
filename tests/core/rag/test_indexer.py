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
    f.write_text("hello world.", encoding="utf-8")
    emb = _Embedder()
    store = build_index([_item(f)], _store(), emb)

    assert len(store) == 1
    assert emb.calls == 1
    assert store.meta[0].source_path == str(f)
    assert store.meta[0].text == "hello world."
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
    f.write_text(f"title: X\nurl: Y\n{sep}\nactual body text.", encoding="utf-8")

    store = build_index([_item(f)], _store(), _Embedder())
    assert store.meta[0].text == "actual body text."


@pytest.mark.unit
def test_read_indexable_text_ignores_separator_look_alike_deep_in_body(tmp_path):
    from src.core.rag.indexer import _read_indexable_text

    # A plain document with no real header can coincidentally contain a run
    # of 64+ dashes far into its own body — that must not be mistaken for a
    # header separator and silently discard everything before it.
    sep = "-" * 64
    body_before = "Paragrafo real com conteudo. " * 200
    text = f"{body_before}\n{sep}\nMais texto depois da linha."
    f = tmp_path / "doc.md"
    f.write_text(text, encoding="utf-8")

    result = _read_indexable_text(_item(f, kind="document"))
    # The header-window logic still keeps body_before intact (not mistaken for
    # a header); clean_document_text separately drops the dash-only line as
    # non-prose (filter_non_prose), so it — and only it — is gone from the result.
    assert result.startswith("Paragrafo real com conteudo.")
    assert "Mais texto depois da linha." in result
    assert sep not in result


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
    f.write_text("hello there.", encoding="utf-8")
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
    f.write_text("hello there.", encoding="utf-8")
    store = _store()
    emb = _Embedder()

    build_index([_item(f, mtime=1.0)], store, emb)
    assert emb.calls == 1 and len(store) == 1

    f.write_text("changed content.", encoding="utf-8")
    build_index([_item(f, mtime=2.0)], store, emb)
    assert emb.calls == 2
    assert len(store) == 1  # stale chunk dropped, new one added
    assert store.meta[0].text == "changed content."


@pytest.mark.unit
def test_build_index_reconciles_removed_source(tmp_path):
    from src.core.rag.indexer import build_index

    a = tmp_path / "a.txt"
    a.write_text("aaa content.", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("bbb content.", encoding="utf-8")
    store = _store()

    build_index([_item(a), _item(b)], store, _Embedder())
    assert len(store) == 2

    # b no longer in the scan → its chunks are reconciled away.
    build_index([_item(a)], store, _Embedder())
    assert {m.source_path for m in store.meta} == {str(a)}


@pytest.mark.unit
def test_indexed_source_path_matches_record_label_path_form(tmp_path):
    """M6: ChunkMeta.source_path (built by the real indexer) must be in the
    exact same form as classify.record_label's Path(...).resolve() — a
    mismatch (raw vs. resolved) silently matches zero labels in
    classify._training_xy's join, a real gap on Windows."""
    from src.core.ml.classify import record_label
    from src.core.rag.indexer import build_index

    f = tmp_path / "aula.txt"
    f.write_text("conteudo de teste.", encoding="utf-8")
    store = _store()
    build_index([_item(f)], store, _Embedder())

    record_label(str(f), "lecture", directory=tmp_path)
    from src.core.ml.classify import load_labels

    labels = load_labels(directory=tmp_path)

    assert store.meta[0].source_path in labels
    assert labels[store.meta[0].source_path] == "lecture"


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
    f.write_text("hi there.", encoding="utf-8")
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
    good.write_text("texto de teste.", encoding="utf-8")
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
    a.write_text("aaa conteudo de teste.", encoding="utf-8")
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
    good.write_text("texto valido de teste.", encoding="utf-8")
    bad = tmp_path / "broken.txt"
    bad.write_text("outro texto ruim de teste.", encoding="utf-8")

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
    f.write_text("versao um do documento.", encoding="utf-8")
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
    f.write_text("texto de teste para embed.", encoding="utf-8")

    def _failing_embed(_texts):
        raise RuntimeError("Ollama down")

    store = index_files([_item(f)], _store(), _failing_embed)
    assert len(store) == 0


@pytest.mark.unit
def test_index_dir_resolves_under_home(monkeypatch, tmp_path):
    from src.core.rag.indexer import index_dir

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert index_dir() == tmp_path / ".mill-tools" / "rag"


# ---------------------------------------------------------------------------
# Contextual chunk header + clean.py adoption (PLANO_RAG_ESPACO_EMBEDDING, Fase 3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_index_one_prepends_context_header_only_to_embedded_text(tmp_path):
    """The header ("{stem} — {kind}:\\n") must reach embed_fn but never
    ChunkMeta.text — BM25 and citations stay on the chunk's bare content."""
    from src.core.rag.indexer import build_index

    f = tmp_path / "aula_de_fisica.txt"
    f.write_text("Conteudo real do documento sobre fisica.", encoding="utf-8")
    emb = _Embedder()

    store = build_index([_item(f)], _store(), emb)

    assert store.meta[0].text == "Conteudo real do documento sobre fisica."
    assert emb.texts == [
        "aula_de_fisica — transcription:\nConteudo real do documento sobre fisica."
    ]


@pytest.mark.unit
def test_read_indexable_text_strips_pdf_page_markers(tmp_path):
    from src.core.text.clean import page_marker
    from src.core.rag.indexer import _read_indexable_text

    f = tmp_path / "extracted.txt"
    f.write_text(
        f"Primeira parte do texto real.\n{page_marker(1)}\nSegunda parte do texto real.",
        encoding="utf-8",
    )

    result = _read_indexable_text(_item(f, kind="document"))
    assert "Página" not in result
    assert "Primeira parte do texto real." in result
    assert "Segunda parte do texto real." in result
