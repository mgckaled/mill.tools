"""Unit tests for src/core/library/tags.py — cached keyphrase auto-tags."""

from __future__ import annotations

import pytest

from src.core.library import tags
from src.core.library.types import LibraryItem


def _item(path) -> LibraryItem:
    st = path.stat()
    return LibraryItem(
        path=path,
        kind="transcription",
        category="text",
        size_bytes=st.st_size,
        modified=st.st_mtime,
        stem=path.stem,
        suffix=path.suffix.lower(),
    )


@pytest.mark.unit
def test_tags_for_text_uses_keyphrases(mocker):
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=True)
    mocker.patch(
        "src.core.library.tags.keywords.keyphrases",
        return_value=[("banco central", 0.01), ("taxa de juros", 0.03)],
    )
    assert tags.tags_for_text("qualquer texto") == ["banco central", "taxa de juros"]


@pytest.mark.unit
def test_tags_for_text_empty_without_nlp(mocker):
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=False)
    assert tags.tags_for_text("texto") == []


@pytest.mark.unit
def test_is_taggable_only_text(tmp_path):
    txt = _item(_write(tmp_path / "a.txt", "x"))
    assert tags.is_taggable(txt) is True
    png = LibraryItem(
        path=tmp_path / "b.png",
        kind="image",
        category="source",
        size_bytes=1,
        modified=1.0,
        stem="b",
        suffix=".png",
    )
    assert tags.is_taggable(png) is False


@pytest.mark.unit
def test_tags_for_item_computes_then_caches(tmp_path, mocker):
    f = _write(tmp_path / "doc.txt", "conteúdo sobre inflação e juros")
    cache = tmp_path / "tags.json"
    calls = {"n": 0}

    def fake_keyphrases(text, **kw):
        calls["n"] += 1
        return [("inflação", 0.01), ("juros", 0.02)]

    mocker.patch("src.core.library.tags.keywords.is_available", return_value=True)
    mocker.patch(
        "src.core.library.tags.keywords.keyphrases", side_effect=fake_keyphrases
    )

    out = tags.tags_for_item(_item(f), cache_file=cache)
    assert out == ["inflação", "juros"]
    assert calls["n"] == 1

    # Second call hits the cache → keyphrases not invoked again.
    out2 = tags.tags_for_item(_item(f), cache_file=cache)
    assert out2 == ["inflação", "juros"]
    assert calls["n"] == 1


@pytest.mark.unit
def test_cache_invalidated_on_mtime_change(tmp_path, mocker):
    f = _write(tmp_path / "doc.txt", "v1")
    cache = tmp_path / "tags.json"
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=True)
    kp = mocker.patch(
        "src.core.library.tags.keywords.keyphrases",
        return_value=[("a", 0.1)],
    )

    tags.tags_for_item(_item(f), cache_file=cache)
    # Rewrite with a new mtime → cache entry is stale → recompute.
    import os

    f.write_text("v2 changed", encoding="utf-8")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    tags.tags_for_item(_item(f), cache_file=cache)
    assert kp.call_count == 2


@pytest.mark.unit
def test_gate_off_result_is_not_cached_then_appears_when_gate_on(tmp_path, mocker):
    """Bug: [] do gate ausente não pode ser cacheado — senão nunca some depois."""
    f = _write(tmp_path / "doc.txt", "conteúdo qualquer sobre juros")
    cache = tmp_path / "tags.json"

    # [nlp] ausente: tags_for_item devolve [] mas NÃO deve gravar no cache.
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=False)
    out1 = tags.tags_for_item(_item(f), cache_file=cache)
    assert out1 == []
    assert tags.load_cached_tags(f, cache_file=cache) is None

    # [nlp] instalado depois, mesmo arquivo/mtime: tags reais devem aparecer.
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=True)
    mocker.patch(
        "src.core.library.tags.keywords.keyphrases",
        return_value=[("juros", 0.01)],
    )
    out2 = tags.tags_for_item(_item(f), cache_file=cache)
    assert out2 == ["juros"]


@pytest.mark.unit
def test_legitimately_empty_text_with_gate_on_is_still_cached(tmp_path, mocker):
    """[] de texto vazio (gate ligado) é resultado real — continua sendo cacheado."""
    f = _write(tmp_path / "empty.txt", "   ")
    cache = tmp_path / "tags.json"
    mocker.patch("src.core.library.tags.keywords.is_available", return_value=True)
    kp = mocker.patch("src.core.library.tags.keywords.keyphrases")

    out = tags.tags_for_item(_item(f), cache_file=cache)

    assert out == []
    kp.assert_not_called()  # tags_for_text short-circuits antes de chamar keyphrases
    assert tags.load_cached_tags(f, cache_file=cache) == []


@pytest.mark.unit
def test_non_text_item_yields_empty(tmp_path):
    png = LibraryItem(
        path=tmp_path / "b.png",
        kind="image",
        category="source",
        size_bytes=1,
        modified=1.0,
        stem="b",
        suffix=".png",
    )
    assert tags.tags_for_item(png) == []


def _write(path, content):
    path.write_text(content, encoding="utf-8")
    return path
