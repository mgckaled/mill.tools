"""Unit tests for src/core/ml/classify.py — zero-shot + supervised profiles."""

from __future__ import annotations

import numpy as np
import pytest

from src.core.ml import classify as cl
from src.core.ml.types import Classification, DocumentMatrix


def _unit(vec: list[float]) -> np.ndarray:
    """Return the L2-normalized float32 version of *vec*."""
    a = np.asarray(vec, dtype=np.float32)
    return (a / (np.linalg.norm(a) + 1e-8)).astype(np.float32)


# ---------------------------------------------------------------------------
# Prototypes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_profile_prototypes_embeds_once_and_caches(tmp_path):
    calls = {"n": 0}

    def fake_embed(texts):
        calls["n"] += 1
        # Deterministic distinct vector per seed text (length-based, then varied).
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    P, ids = cl.profile_prototypes(fake_embed, cache_dir=tmp_path)
    assert calls["n"] == 1
    assert len(ids) == len(P)
    assert "default" in ids  # the registry's default profile is present
    # Rows are L2-normalized.
    np.testing.assert_allclose(np.linalg.norm(P, axis=1), 1.0, atol=1e-5)

    # Second call hits the on-disk cache → embedder is not called again.
    P2, ids2 = cl.profile_prototypes(fake_embed, cache_dir=tmp_path)
    assert calls["n"] == 1
    assert ids2 == ids
    np.testing.assert_allclose(P2, P)


@pytest.mark.unit
def test_profile_prototypes_cache_miss_without_embedder_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not cached"):
        cl.profile_prototypes(None, cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# Zero-shot
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classify_zeroshot_picks_nearest_prototype():
    P = np.array([_unit([1, 0, 0]), _unit([0, 1, 0]), _unit([0, 0, 1])])
    ids = ["lecture", "interview", "tutorial"]
    out = cl.classify_zeroshot(_unit([0.9, 0.1, 0.0]), P, ids)

    assert isinstance(out, Classification)
    assert out.profile_id == "lecture"
    assert out.method == "zeroshot"
    assert out.confidence == pytest.approx(0.9938, abs=1e-3)
    assert out.margin > 0  # top1 clearly beats top2


@pytest.mark.unit
def test_classify_zeroshot_ambiguous_has_low_margin():
    P = np.array([_unit([1, 0]), _unit([0, 1])])
    ids = ["a", "b"]
    out = cl.classify_zeroshot(_unit([1, 1]), P, ids)  # exactly between
    assert out.margin == pytest.approx(0.0, abs=1e-5)


@pytest.mark.unit
def test_classify_falls_back_to_zeroshot_without_labels(tmp_path):
    def fake_embed(texts):
        return np.array([[i + 1.0, 0.0, 0.0] for i, _ in enumerate(texts)], dtype=float)

    out = cl.classify(_unit([1, 0, 0]), embed_fn=fake_embed, directory=tmp_path)
    assert out.method == "zeroshot"
    assert out.profile_id  # some profile chosen


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_record_and_load_labels_roundtrip(tmp_path):
    cl.record_label("/corpus/a.txt", "lecture", directory=tmp_path)
    cl.record_label("/corpus/b.txt", "tutorial", directory=tmp_path)
    labels = cl.load_labels(directory=tmp_path)
    assert (
        labels[str(__import__("pathlib").Path("/corpus/a.txt").resolve())] == "lecture"
    )
    assert len(labels) == 2


@pytest.mark.unit
def test_labels_signature_changes_with_labels():
    sig_a = cl.labels_signature({"a": "lecture"})
    sig_b = cl.labels_signature({"a": "tutorial"})
    assert sig_a != sig_b
    # Order-independent.
    assert cl.labels_signature({"a": "x", "b": "y"}) == cl.labels_signature(
        {"b": "y", "a": "x"}
    )


# ---------------------------------------------------------------------------
# Supervised
# ---------------------------------------------------------------------------


def _labelled_dm() -> tuple[DocumentMatrix, dict[str, str]]:
    """A clearly separable two-class corpus with enough docs per class."""
    rows = []
    labels = {}
    for i in range(4):  # class "lecture" near [1,0]
        p = f"/lec/{i}.txt"
        rows.append((p, _unit([1.0, 0.05 * i])))
        labels[p] = "lecture"
    for i in range(4):  # class "tutorial" near [0,1]
        p = f"/tut/{i}.txt"
        rows.append((p, _unit([0.05 * i, 1.0])))
        labels[p] = "tutorial"
    X = np.array([v for _, v in rows], dtype=np.float32)
    dm = DocumentMatrix(
        X=X, source_paths=[s for s, _ in rows], kinds=["transcription"] * len(rows)
    )
    return dm, labels


@pytest.mark.unit
def test_train_supervised_returns_none_when_too_few_per_class(tmp_path):
    pytest.importorskip("sklearn")
    dm = DocumentMatrix(
        X=np.array([_unit([1, 0]), _unit([0, 1])]),
        source_paths=["/a.txt", "/b.txt"],
        kinds=["transcription"] * 2,
    )
    labels = {"/a.txt": "lecture", "/b.txt": "tutorial"}  # 1 per class < MIN_PER_CLASS
    assert cl.train_supervised(dm, labels, directory=tmp_path) is None


@pytest.mark.unit
def test_supervised_model_trains_predicts_and_is_used(tmp_path):
    pytest.importorskip("sklearn")
    dm, labels = _labelled_dm()
    for path, profile in labels.items():
        cl.record_label(path, profile, directory=tmp_path)
    # record_label resolves paths; rebuild dm with the resolved keys.
    from pathlib import Path

    resolved = {str(Path(p).resolve()): v for p, v in labels.items()}
    dm = DocumentMatrix(
        X=dm.X,
        source_paths=[str(Path(p).resolve()) for p in dm.source_paths],
        kinds=dm.kinds,
    )

    model = cl.train_supervised(dm, resolved, directory=tmp_path)
    assert model is not None

    # A vector squarely in the lecture region → supervised prediction "lecture".
    out = cl.classify(_unit([1.0, 0.0]), directory=tmp_path)
    assert out.method == "supervised"
    assert out.profile_id == "lecture"
    assert 0.0 <= out.confidence <= 1.0


@pytest.mark.unit
def test_supervised_signature_mismatch_falls_back_to_zeroshot(tmp_path):
    pytest.importorskip("sklearn")
    dm, labels = _labelled_dm()
    from pathlib import Path

    resolved = {str(Path(p).resolve()): v for p, v in labels.items()}
    dm = DocumentMatrix(
        X=dm.X,
        source_paths=[str(Path(p).resolve()) for p in dm.source_paths],
        kinds=dm.kinds,
    )
    for path, profile in resolved.items():
        cl.record_label(path, profile, directory=tmp_path)
    cl.train_supervised(dm, resolved, directory=tmp_path)

    # Add a new label → the on-disk label signature no longer matches the model.
    cl.record_label("/new/c.txt", "interview", directory=tmp_path)

    def fake_embed(texts):
        return np.array([[i + 1.0, 0.0] for i, _ in enumerate(texts)], dtype=float)

    out = cl.classify(_unit([1.0, 0.0]), embed_fn=fake_embed, directory=tmp_path)
    assert out.method == "zeroshot"  # stale model ignored


@pytest.mark.unit
def test_maybe_train_without_labels_returns_none(tmp_path):
    assert cl.maybe_train(_labelled_dm()[0], directory=tmp_path) is None
