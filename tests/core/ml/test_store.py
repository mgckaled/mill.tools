"""Unit tests for src/core/ml/store.py — versioned model persistence.

Requires scikit-learn (the [ml] extra) for a realistic round-trip; the sidecar
mismatch logic is exercised by patching ``_sklearn_version``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from sklearn.preprocessing import StandardScaler  # noqa: E402

from src.core.ml import store as ml_store  # noqa: E402
from src.core.ml.store import load_model, model_dir, save_model  # noqa: E402


def _fitted_model():
    """Return a small fitted sklearn estimator (joblib-serializable)."""
    return StandardScaler().fit([[0.0], [2.0], [4.0]])


@pytest.mark.unit
def test_round_trip_loads_with_matching_version_and_signature(tmp_path):
    model = _fitted_model()
    save_model(model, "scaler", signature="sig-1", directory=tmp_path)

    loaded = load_model("scaler", signature="sig-1", directory=tmp_path)
    assert loaded is not None
    # Same transform → same artifact.
    assert loaded.transform([[2.0]]) == pytest.approx(model.transform([[2.0]]))


@pytest.mark.unit
def test_save_writes_model_and_sidecar(tmp_path):
    save_model(_fitted_model(), "scaler", signature="sig-1", directory=tmp_path)
    assert (tmp_path / "scaler.joblib").exists()

    import json

    info = json.loads((tmp_path / "scaler.json").read_text(encoding="utf-8"))
    assert info["signature"] == "sig-1"
    assert info["sklearn_version"]  # non-empty
    assert "created_at" in info


@pytest.mark.unit
def test_version_mismatch_forces_retrain(tmp_path, monkeypatch):
    save_model(_fitted_model(), "scaler", signature="sig-1", directory=tmp_path)
    # Pretend a different sklearn is now installed.
    monkeypatch.setattr(ml_store, "_sklearn_version", lambda: "0.0.0-other")
    assert load_model("scaler", signature="sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_signature_mismatch_forces_retrain(tmp_path):
    save_model(_fitted_model(), "scaler", signature="sig-1", directory=tmp_path)
    assert load_model("scaler", signature="sig-2", directory=tmp_path) is None


@pytest.mark.unit
def test_absent_sidecar_returns_none(tmp_path):
    assert load_model("missing", signature="sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_corrupt_sidecar_returns_none(tmp_path):
    save_model(_fitted_model(), "scaler", signature="sig-1", directory=tmp_path)
    (tmp_path / "scaler.json").write_text("{not json", encoding="utf-8")
    assert load_model("scaler", signature="sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_corrupt_model_artifact_returns_none(tmp_path):
    # Sidecar stays valid but the .joblib is garbage → load fails → retrain.
    save_model(_fitted_model(), "scaler", signature="sig-1", directory=tmp_path)
    (tmp_path / "scaler.joblib").write_bytes(b"not a joblib payload")
    assert load_model("scaler", signature="sig-1", directory=tmp_path) is None


@pytest.mark.unit
def test_model_dir_is_under_mill_tools(monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert model_dir() == tmp_path / ".mill-tools" / "ml"
