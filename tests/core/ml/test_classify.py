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

    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.unit
def test_profile_prototypes_cache_miss_without_embedder_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not cached"):
        cl.profile_prototypes(None, cache_dir=tmp_path)


@pytest.mark.unit
def test_profile_prototypes_invalidated_by_embed_space_change(tmp_path):
    """M2: switching the embed model (and reindexing) must not silently reuse
    a prototype matrix embedded in a different model's vector space."""
    calls = {"n": 0}

    def fake_embed(texts):
        calls["n"] += 1
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    cl.profile_prototypes(fake_embed, cache_dir=tmp_path, embed_space_id="model-a:768")
    assert calls["n"] == 1

    # Same class set, same cache_dir, but a different embedding space → miss
    # (the cache holds one slot per domain, so this also overwrites it).
    cl.profile_prototypes(fake_embed, cache_dir=tmp_path, embed_space_id="model-b:1024")
    assert calls["n"] == 2

    # Re-requesting the now-overwritten space is a cache hit again.
    cl.profile_prototypes(fake_embed, cache_dir=tmp_path, embed_space_id="model-b:1024")
    assert calls["n"] == 2


@pytest.mark.unit
def test_profile_prototypes_bad_zip_npz_re_embeds(tmp_path):
    """A zip-signature-prefixed but malformed npz raises zipfile.BadZipFile —
    a distinct exception type from the plain ValueError np.load() raises for
    non-zip garbage. Both must be treated as a cache miss, not propagate."""
    calls = {"n": 0}

    def fake_embed(texts):
        calls["n"] += 1
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    cl.profile_prototypes(fake_embed, cache_dir=tmp_path)
    assert calls["n"] == 1

    (tmp_path / cl._PROTO_NPZ).write_bytes(b"PK\x03\x04" + b"garbage" * 5)

    cl.profile_prototypes(fake_embed, cache_dir=tmp_path)
    assert calls["n"] == 2  # cache miss → re-embedded, not raised


@pytest.mark.unit
@pytest.mark.parametrize("domain", [cl.DOMAIN_DATA, cl.DOMAIN_DOCUMENT])
def test_domain_seeds_are_bilingual(domain):
    """PLANO_CORRECOES_RAG_ML_2, Fase 3: data/document prototypes must carry a
    PT-BR sentence alongside the EN one — nomic-embed is weak cross-language
    against the mostly PT-BR corpus these two domains classify. (The
    transcription profile seeds are already PT — derived from label/source_hint
    — so this only applies to the two hand-written catalogs.)"""
    accented = set("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ")
    for _, text in cl._seeds_for_domain(domain):
        assert accented & set(text), f"seed looks English-only: {text!r}"


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
def test_supervised_model_ignored_after_embed_space_changes(tmp_path):
    """M2: a supervised model trained on one embedding space must not be
    reused after the embed model changes and the corpus is reindexed — dm.X
    then holds vectors from a different space the model was never fit on."""
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
    cl.train_supervised(dm, resolved, directory=tmp_path, embed_space_id="model-a:2")

    def fake_embed(texts):
        return np.array([[i + 1.0, 0.0] for i, _ in enumerate(texts)], dtype=float)

    # Same labels, but the embedding space changed (embed model swapped +
    # corpus reindexed) → the old model must be rejected, not silently reused.
    out = cl.classify(
        _unit([1.0, 0.0]),
        embed_fn=fake_embed,
        directory=tmp_path,
        embed_space_id="model-b:2",
    )
    assert out.method == "zeroshot"


@pytest.mark.unit
def test_has_supervised_model_respects_embed_space_id(tmp_path):
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
    cl.train_supervised(dm, resolved, directory=tmp_path, embed_space_id="model-a:2")

    from src.core.ml.classify import has_supervised_model

    assert has_supervised_model(directory=tmp_path, embed_space_id="model-a:2") is True
    assert has_supervised_model(directory=tmp_path, embed_space_id="model-b:2") is False


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


# ---------------------------------------------------------------------------
# Multi-domain reuse (Tier A, item 3.4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_domain_keeps_the_pre_existing_filenames():
    """Regression: the default domain must not invalidate anyone's existing
    on-disk prototype/model/label cache."""
    assert cl._proto_filenames(cl.DOMAIN_TRANSCRIPTION_PROFILE) == (
        cl._PROTO_NPZ,
        cl._PROTO_JSON,
    )
    assert cl._model_name(cl.DOMAIN_TRANSCRIPTION_PROFILE) == cl._MODEL_NAME
    assert cl._labels_json_name(cl.DOMAIN_TRANSCRIPTION_PROFILE) == cl._LABELS_JSON


@pytest.mark.unit
def test_new_domains_get_their_own_filenames():
    assert cl._proto_filenames(cl.DOMAIN_DATA) == (
        "data_domain_prototypes.npz",
        "data_domain_prototypes.json",
    )
    assert cl._model_name(cl.DOMAIN_DATA) == "data_domain_classifier"
    assert cl._labels_json_name(cl.DOMAIN_DATA) == "data_domain_labels.json"


@pytest.mark.unit
def test_data_domain_prototypes_use_the_data_domain_seeds(tmp_path):
    def fake_embed(texts):
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    _, ids = cl.profile_prototypes(
        fake_embed, cache_dir=tmp_path, domain=cl.DOMAIN_DATA
    )
    assert "financial" in ids
    assert "lecture" not in ids  # transcription profile ids must not leak in


@pytest.mark.unit
def test_document_domain_prototypes_use_the_document_type_seeds(tmp_path):
    def fake_embed(texts):
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    _, ids = cl.profile_prototypes(
        fake_embed, cache_dir=tmp_path, domain=cl.DOMAIN_DOCUMENT
    )
    assert "invoice" in ids
    assert "financial" not in ids  # a different domain's ids must not leak in


@pytest.mark.unit
def test_domains_keep_independent_prototype_cache_files(tmp_path):
    def fake_embed(texts):
        return np.array([[len(t), i, 1.0] for i, t in enumerate(texts)], dtype=float)

    cl.profile_prototypes(fake_embed, cache_dir=tmp_path)  # default domain
    cl.profile_prototypes(fake_embed, cache_dir=tmp_path, domain=cl.DOMAIN_DATA)

    names = {p.name for p in tmp_path.iterdir()}
    assert cl._PROTO_NPZ in names
    assert "data_domain_prototypes.npz" in names


@pytest.mark.unit
def test_record_label_isolates_by_domain(tmp_path):
    cl.record_label("/a.csv", "financial", directory=tmp_path, domain=cl.DOMAIN_DATA)

    assert cl.load_labels(directory=tmp_path) == {}  # default domain unaffected
    data_labels = cl.load_labels(directory=tmp_path, domain=cl.DOMAIN_DATA)
    assert len(data_labels) == 1
