"""Unit tests for src/core/ml/mapviz.py — build + render the semantic map."""

from __future__ import annotations

import io

import numpy as np
import pytest

pytest.importorskip("sklearn")

from src.core.ml.mapviz import (  # noqa: E402
    cluster_display_name,
    build_semantic_map,
)
from src.core.rag.store import VectorStore  # noqa: E402
from src.core.rag.types import ChunkMeta  # noqa: E402


def _store_two_themes() -> VectorStore:
    """A store with two well-separated themes of single-chunk documents."""
    rng = np.random.default_rng(0)
    store = VectorStore(dim=6)
    for i in range(8):
        v = np.zeros(6, dtype=np.float32)
        v[0] = 1.0
        v += rng.normal(0, 0.03, 6).astype(np.float32)
        store.add(
            v[None],
            [
                ChunkMeta(
                    f"whisper_{i}.txt",
                    "transcription",
                    1.0,
                    0,
                    "whisper gpu transcription audio model",
                )
            ],
        )
    for i in range(8):
        v = np.zeros(6, dtype=np.float32)
        v[1] = 1.0
        v += rng.normal(0, 0.03, 6).astype(np.float32)
        store.add(
            v[None],
            [
                ChunkMeta(
                    f"duna_{i}.txt",
                    "document",
                    2.0,
                    0,
                    "duna herbert arrakis spice book",
                )
            ],
        )
    return store


@pytest.mark.unit
def test_cluster_display_name():
    names = {0: ["whisper", "gpu", "audio"], 1: []}
    assert cluster_display_name(-1, names) == "órfãos"
    assert cluster_display_name(0, names) == "whisper, gpu, audio"
    assert cluster_display_name(1, names) == "grupo 1"
    assert cluster_display_name(9, names) == "grupo 9"  # missing key → fallback


@pytest.mark.unit
def test_build_semantic_map_clusters_and_labels(tmp_path):
    sm = build_semantic_map(_store_two_themes(), cache_dir=tmp_path)

    assert len(sm) == 16
    assert sm.coords.shape == (16, 2)
    assert len(sm.labels) == 16
    # Two themes → at least one named cluster discovered.
    assert sm.cluster_names  # non-empty
    assert sm.source_paths[0].startswith("whisper_")


@pytest.mark.unit
def test_build_semantic_map_uses_cache(tmp_path, mocker):
    import src.core.ml.mapviz as mapviz

    spy = mocker.spy(mapviz, "cluster_documents")
    store = _store_two_themes()
    mapviz.build_semantic_map(store, cache_dir=tmp_path)
    mapviz.build_semantic_map(store, cache_dir=tmp_path)  # second hits the cache
    assert spy.call_count == 1  # clustering ran only once


@pytest.mark.unit
def test_build_semantic_map_no_cache_recomputes(tmp_path, mocker):
    import src.core.ml.mapviz as mapviz

    spy = mocker.spy(mapviz, "cluster_documents")
    store = _store_two_themes()
    mapviz.build_semantic_map(store, cache_dir=tmp_path, use_cache=False)
    mapviz.build_semantic_map(store, cache_dir=tmp_path, use_cache=False)
    assert spy.call_count == 2


@pytest.mark.unit
def test_render_semantic_map_png(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("pandas")
    from PIL import Image

    from src.core.ml.mapviz import render_semantic_map_png

    sm = build_semantic_map(_store_two_themes(), cache_dir=tmp_path)
    png = render_semantic_map_png(sm, title="Mapa")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    Image.open(io.BytesIO(png)).verify()


@pytest.mark.unit
def test_render_raises_when_charts_extra_missing(tmp_path, mocker):
    from src.core.ml.mapviz import render_semantic_map_png

    sm = build_semantic_map(_store_two_themes(), cache_dir=tmp_path)
    mocker.patch("src.core.data.charts.is_available", return_value=False)
    with pytest.raises(RuntimeError):
        render_semantic_map_png(sm)


@pytest.mark.unit
def test_render_empty_map_raises(tmp_path):
    pytest.importorskip("matplotlib")
    from src.core.ml.mapviz import render_semantic_map_png
    from src.core.ml.types import SemanticMap

    empty = SemanticMap(
        coords=np.empty((0, 2), dtype=np.float32),
        labels=np.empty((0,), dtype=int),
        cluster_names={},
        source_paths=[],
        kinds=[],
    )
    with pytest.raises(ValueError, match="vazio"):
        render_semantic_map_png(empty)
