"""Gold labels + the supervised upgrade trained from them.

The user already picks ``--profile`` (or the equivalent domain choice) on
every run — that choice is a gold label. Recorded labels (``record_label``)
are joined with the document vectors and, once there are enough per class, a
calibrated linear model (``LinearSVC`` + ``CalibratedClassifierCV``) is
trained over ``dm.X`` and persisted via the versioned ``ml.store``. Until
then the zero-shot prototype path (``prototypes.py``) stands.

Split out of the former ``classify.py`` (471 lines > the architecture's ~400
ceiling); prototypes live in ``prototypes.py``, dispatch in ``inference.py``.
See ``classify/__init__.py`` for the still-flat public API.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from src.core.ml.classify._naming import (
    DOMAIN_TRANSCRIPTION_PROFILE,
    MIN_PER_CLASS,
    _labels_json_name,
    _model_name,
)
from src.core.ml.store import model_dir, save_model

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix


def _labels_file(
    directory: Path | None = None, *, domain: str = DOMAIN_TRANSCRIPTION_PROFILE
) -> Path:
    """Return the on-disk gold-label store (``~/.mill-tools/ml/profile_labels.json``)."""
    return (directory or model_dir()) / _labels_json_name(domain)


def load_labels(
    *, directory: Path | None = None, domain: str = DOMAIN_TRANSCRIPTION_PROFILE
) -> dict[str, str]:
    """Return the ``{source_path: class_id}`` gold labels, tolerating absence."""
    try:
        data = json.loads(
            _labels_file(directory, domain=domain).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_label(
    source_path: str,
    profile_id: str,
    *,
    directory: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
) -> None:
    """Record the user's confirmed/corrected class for a document.

    This is the only labelling step — it piggybacks on the choice the user
    already makes, so there is no dedicated annotation chore. A later
    ``maybe_train`` turns enough of these into a supervised model.
    """
    path = str(Path(source_path).resolve())
    labels = load_labels(directory=directory, domain=domain)
    labels[path] = profile_id
    out = _labels_file(directory, domain=domain)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logging.debug("[d] Could not write %s labels: %s", domain, exc)


def domain_label_count(
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE, *, directory: Path | None = None
) -> int:
    """Number of gold labels recorded for ``domain`` — used by the Observatório
    status board (item 3.5) to show classifier health without exposing the
    on-disk filename scheme."""
    return len(load_labels(directory=directory, domain=domain))


def labels_signature(labels: dict[str, str]) -> str:
    """Stable hash of the label set — invalidates the trained model when it changes."""
    payload = "\n".join(f"{p}\t{labels[p]}" for p in sorted(labels))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _training_xy(
    dm: DocumentMatrix, labels: dict[str, str]
) -> tuple[np.ndarray, list[str]]:
    """Join document vectors with gold labels into ``(X, y)`` for training."""
    rows: list[int] = []
    y: list[str] = []
    for i, source in enumerate(dm.source_paths):
        if source in labels:
            rows.append(i)
            y.append(labels[source])
    X = dm.X[rows] if rows else np.empty((0, dm.X.shape[1]), dtype=np.float32)
    return X, y


def train_supervised(
    dm: DocumentMatrix,
    labels: dict[str, str],
    *,
    signature: str | None = None,
    directory: Path | None = None,
    min_per_class: int = MIN_PER_CLASS,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
):
    """Train + persist a calibrated linear classifier; return it, or ``None``.

    Returns ``None`` (so the caller stays on zero-shot) when there are fewer than
    two classes or any class has fewer than ``min_per_class`` labelled documents.
    Otherwise fits ``LinearSVC(class_weight="balanced")`` wrapped in
    ``CalibratedClassifierCV`` (sigmoid — robust for the small label counts here)
    over ``dm.X`` and saves it via the versioned ``ml.store``.

    Raises:
        RuntimeError: if the ``[ml]`` extra (scikit-learn) is not installed.
    """
    from src.core.ml.deps import SETUP_HINT, is_available

    if not is_available():
        raise RuntimeError(SETUP_HINT)

    from collections import Counter

    X, y = _training_xy(dm, labels)
    counts = Counter(y)
    if len(counts) < 2 or (counts and min(counts.values()) < min_per_class):
        return None

    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.svm import LinearSVC

    cv = min(5, min(counts.values()))
    base = LinearSVC(class_weight="balanced", dual="auto", random_state=0)
    model = CalibratedClassifierCV(base, method="sigmoid", cv=cv)
    model.fit(X, y)

    sig = signature if signature is not None else labels_signature(labels)
    save_model(model, _model_name(domain), signature=sig, directory=directory)
    return model


def maybe_train(
    dm: DocumentMatrix,
    *,
    directory: Path | None = None,
    min_per_class: int = MIN_PER_CLASS,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
):
    """Train from the recorded labels if enough have accumulated; else ``None``."""
    labels = load_labels(directory=directory, domain=domain)
    if not labels:
        return None
    return train_supervised(
        dm, labels, directory=directory, min_per_class=min_per_class, domain=domain
    )
