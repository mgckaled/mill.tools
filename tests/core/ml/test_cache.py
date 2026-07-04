"""Unit tests for src/core/ml/cache.py — corpus signature + map persistence."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml import cache as ml_cache
from src.core.ml.cache import corpus_signature, load_map, save_map
from src.core.ml.types import SemanticMap
from src.core.rag.types import ChunkMeta


def _metas(pairs: list[tuple[str, float]]) -> list[ChunkMeta]:
    return [ChunkMeta(p, "transcription", m, 0, "t") for p, m in pairs]


def _map() -> SemanticMap:
    return SemanticMap(
        coords=np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32),
        labels=np.array([0, -1]),
        cluster_names={0: ["whisper", "gpu"]},
        source_paths=["a.txt", "b.txt"],
        kinds=["transcription", "document"],
    )


@pytest.mark.unit
def test_corpus_signature_is_stable_to_reordering():
    a = corpus_signature(_metas([("a.txt", 1.0), ("b.txt", 2.0)]))
    b = corpus_signature(_metas([("b.txt", 2.0), ("a.txt", 1.0)]))
    assert a == b


@pytest.mark.unit
def test_corpus_signature_changes_with_mtime():
    a = corpus_signature(_metas([("a.txt", 1.0)]))
    b = corpus_signature(_metas([("a.txt", 2.0)]))
    assert a != b


@pytest.mark.unit
def test_corpus_signature_ignores_chunk_multiplicity():
    # Two chunks of the same (path, mtime) → same signature as one.
    one = corpus_signature(_metas([("a.txt", 1.0)]))
    two = corpus_signature(_metas([("a.txt", 1.0), ("a.txt", 1.0)]))
    assert one == two


@pytest.mark.unit
def test_save_load_round_trip(tmp_path):
    sm = _map()
    save_map(sm, "sig-1", directory=tmp_path)
    loaded = load_map("sig-1", directory=tmp_path)

    assert loaded is not None
    np.testing.assert_array_equal(loaded.coords, sm.coords)
    np.testing.assert_array_equal(loaded.labels, sm.labels)
    assert loaded.cluster_names == {0: ["whisper", "gpu"]}  # int key restored
    assert loaded.source_paths == ["a.txt", "b.txt"]
    assert loaded.kinds == ["transcription", "document"]


@pytest.mark.unit
def test_signature_mismatch_returns_none(tmp_path):
    save_map(_map(), "sig-1", directory=tmp_path)
    assert load_map("sig-2", directory=tmp_path) is None


@pytest.mark.unit
def test_version_mismatch_returns_none(tmp_path, monkeypatch):
    save_map(_map(), "sig-1", directory=tmp_path)
    monkeypatch.setattr(ml_cache, "_sklearn_version", lambda: "0.0.0-other")
    assert load_map("sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_missing_files_returns_none(tmp_path):
    assert load_map("sig-1", directory=tmp_path / "empty") is None


@pytest.mark.unit
def test_corrupt_sidecar_returns_none(tmp_path):
    save_map(_map(), "sig-1", directory=tmp_path)
    (tmp_path / "semantic_map_info.json").write_text("{bad", encoding="utf-8")
    assert load_map("sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_corrupt_npz_returns_none(tmp_path):
    # Sidecar/signature stay valid but the arrays are garbage → recompute.
    save_map(_map(), "sig-1", directory=tmp_path)
    (tmp_path / "semantic_map.npz").write_bytes(b"not an npz")
    assert load_map("sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_bad_zip_npz_returns_none(tmp_path):
    """A zip-signature-prefixed but truncated/malformed npz raises
    zipfile.BadZipFile, a distinct exception type from the plain ValueError
    np.load() raises for non-zip garbage (see test_corrupt_npz_returns_none)."""
    save_map(_map(), "sig-1", directory=tmp_path)
    (tmp_path / "semantic_map.npz").write_bytes(b"PK\x03\x04" + b"garbage" * 5)
    assert load_map("sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_npz_missing_expected_key_returns_none(tmp_path):
    save_map(_map(), "sig-1", directory=tmp_path)
    # A valid npz, but without the "coords"/"labels" keys load_map expects.
    np.savez_compressed(tmp_path / "semantic_map.npz", something_else=np.zeros(3))
    assert load_map("sig-1", directory=tmp_path) is None
