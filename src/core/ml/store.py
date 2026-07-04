"""Versioned persistence for trained models — convention, not a model yet.

The future semantic/tabular waves (Plans 4/5) train a model once and reuse it.
scikit-learn is explicit that pickle-based artifacts (joblib included) are **not**
portable across library versions, and the docs recommend storing metadata —
notably the scikit-learn version — alongside the pickle. So this module writes a
JSON sidecar (mirroring the RAG's ``index_info.json``) and ``load_model`` returns
``None`` on any mismatch, forcing the consumer to retrain rather than load an
artifact that could crash or silently misbehave.

* ``joblib`` for v1 — efficient memory-mapping for large numpy arrays.
* ``skops.io`` is the documented *secure* upgrade (does not execute arbitrary
  code on load); intentionally **not** adopted now to avoid a new dependency.

The model and its sidecar are keyed by ``name``; ``signature`` follows the same
``(path, mtime, params)`` principle as the RAG/assess caches — a digest of the
training corpus so a changed corpus invalidates the saved model.
"""

from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.core.io_atomic import write_group


def model_dir() -> Path:
    """Return the canonical on-disk model location (``~/.mill-tools/ml/``)."""
    return Path.home() / ".mill-tools" / "ml"


def _sklearn_version() -> str:
    """Return the installed scikit-learn version (empty string if absent)."""
    try:
        import sklearn

        return sklearn.__version__
    except ImportError:  # pragma: no cover — store is only used under the [ml] extra
        return ""


def save_model(
    model: Any, name: str, *, signature: str, directory: Path | None = None
) -> Path:
    """Persist ``model`` with a version + signature sidecar; return the model path.

    Writes ``<name>.joblib`` (the model) and ``<name>.json`` (``sklearn_version``,
    ``signature``, ``created_at``) under ``directory`` (default ``model_dir()``),
    as one atomic unit (:func:`src.core.io_atomic.write_group`) — a crash
    mid-write never leaves a fresh model paired with a stale/missing sidecar.
    """
    import joblib

    directory = directory or model_dir()
    model_buf = io.BytesIO()
    joblib.dump(model, model_buf)
    info_bytes = json.dumps(
        {
            "sklearn_version": _sklearn_version(),
            "signature": signature,
            "created_at": time.time(),
        },
        ensure_ascii=False,
    ).encode("utf-8")

    model_path = directory / f"{name}.joblib"
    write_group(
        [
            (model_path, model_buf.getvalue()),
            (directory / f"{name}.json", info_bytes),
        ]
    )
    return model_path


def load_model(
    name: str, *, signature: str, directory: Path | None = None
) -> Any | None:
    """Load ``<name>`` only if its sidecar matches the current sklearn + signature.

    Returns ``None`` (forcing a retrain) when the sidecar is absent, the
    scikit-learn version changed (pickles are not portable across versions), or
    the training-corpus signature differs. A genuine load error also yields
    ``None`` rather than propagating — the consumer just retrains.
    """
    directory = directory or model_dir()
    sidecar = directory / f"{name}.json"
    model_path = directory / f"{name}.joblib"
    if not sidecar.exists() or not model_path.exists():
        return None
    try:
        info = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if info.get("sklearn_version") != _sklearn_version():
        logging.debug("[d] Model %s: sklearn version mismatch → retrain.", name)
        return None
    if info.get("signature") != signature:
        logging.debug("[d] Model %s: corpus signature mismatch → retrain.", name)
        return None
    try:
        import joblib

        return joblib.load(model_path)
    except Exception as exc:  # corrupt/incompatible artifact → retrain
        logging.debug("[d] Could not load model %s: %s", name, exc)
        return None
