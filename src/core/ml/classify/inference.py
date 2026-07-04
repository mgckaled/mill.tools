"""Dispatch: trained supervised model when valid, else the zero-shot prototypes.

Split out of the former ``classify.py`` (471 lines > the architecture's ~400
ceiling); prototypes live in ``prototypes.py``, labels+training in
``labels.py``. See ``classify/__init__.py`` for the still-flat public API.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import numpy as np

from src.core.ml.classify._naming import DOMAIN_TRANSCRIPTION_PROFILE, _model_name
from src.core.ml.classify.labels import load_labels, model_signature
from src.core.ml.classify.prototypes import classify_zeroshot, profile_prototypes
from src.core.ml.store import load_model
from src.core.ml.types import Classification

if TYPE_CHECKING:
    from src.core.ml.types import DocumentMatrix


def classify(
    doc_vec: np.ndarray,
    *,
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
    dm: DocumentMatrix | None = None,  # noqa: ARG001 — reserved for future routing
    directory: Path | None = None,
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
    embed_space_id: str = "?",
) -> Classification:
    """Classify ``doc_vec`` within ``domain``: trained model if available + valid,
    else zero-shot.

    The supervised model is used only when ``ml.store`` holds one whose signature
    still matches the current label set *and* embedding space; any mismatch
    (labels changed, embed model changed, or sklearn upgraded) transparently
    falls back to the zero-shot prototypes. Passing a non-default ``domain``
    (``DOMAIN_DATA``/``DOMAIN_DOCUMENT``) reuses this exact infrastructure for
    a different class set — see the package docstring.

    Args:
        embed_space_id: Identifies the RAG's current embedding space (model +
            dim, from ``rag.stats.embed_space_id``) — see ``model_signature``/
            ``profile_prototypes`` for why this matters. Defaults to ``"?"``
            for callers that don't track it; production call sites pass the
            real value (see ``cli/ai.py``/``gui/views/profile_section.py``).
    """
    labels = load_labels(directory=directory, domain=domain)
    if labels:
        model = load_model(
            _model_name(domain),
            signature=model_signature(labels, embed_space_id),
            directory=directory,
        )
        if model is not None:
            proba = model.predict_proba(
                np.asarray(doc_vec, dtype=np.float32).reshape(1, -1)
            )[0]
            order = np.argsort(proba)[::-1]
            classes = model.classes_
            confidence = float(proba[order[0]])
            margin = (
                float(proba[order[0]] - proba[order[1]])
                if len(order) > 1
                else confidence
            )
            return Classification(
                str(classes[order[0]]), confidence, margin, "supervised"
            )

    P, ids = profile_prototypes(
        embed_fn, cache_dir=directory, domain=domain, embed_space_id=embed_space_id
    )
    return classify_zeroshot(doc_vec, P, ids)


def has_supervised_model(
    domain: str = DOMAIN_TRANSCRIPTION_PROFILE,
    *,
    directory: Path | None = None,
    embed_space_id: str = "?",
) -> bool:
    """True if ``domain`` currently has a valid trained model in use (not just
    labels recorded) — i.e. ``classify()`` would take the supervised branch."""
    labels = load_labels(directory=directory, domain=domain)
    if not labels:
        return False
    model = load_model(
        _model_name(domain),
        signature=model_signature(labels, embed_space_id),
        directory=directory,
    )
    return model is not None
