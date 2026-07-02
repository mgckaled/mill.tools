"""Read-only snapshot of every ML engine's status — the Observatório's status board.

Aggregates what already exists elsewhere (extra/embedder gates, classifier
label counts, hardcoded thresholds, per-model answer timings) into a single
read. Computes nothing new — this is transparency, not a fresh analysis.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateStatus:
    """Availability of one optional ML/NLP engine (or the embedder)."""

    name: str
    available: bool
    hint: str  # setup hint shown when unavailable; ignored when available


@dataclass(frozen=True, slots=True)
class DomainStatus:
    """Classifier health for one ``classify.py`` domain."""

    domain: str
    n_labels: int
    supervised: bool  # whether a trained model is currently in use


@dataclass(frozen=True, slots=True)
class MLConfigSnapshot:
    """Hardcoded parameters currently in effect — transparency, not a settings form."""

    text_dedup_threshold: float
    image_dedup_max_distance: int
    auto_k_min_corpus: int
    mmr_lambda: float


@dataclass(frozen=True, slots=True)
class OllamaModelStatus:
    """Whether one of the app's *-custom Ollama models is pulled locally."""

    name: str
    installed: bool


@dataclass(frozen=True, slots=True)
class OllamaInventoryStatus:
    """Snapshot of the local Ollama service's model inventory."""

    reachable: bool
    models: tuple[OllamaModelStatus, ...]


# The 6 *-custom models the app's Modelfiles create (ollama/Modelfile*), kept
# here as the single list this status reads against — see CLAUDE.md's Ollama
# section for what each one is for.
_KNOWN_CUSTOM_MODELS = (
    "phi4mini-custom",
    "gemma3-4b-custom",
    "gemma3-1b-custom",
    "qwen7b-custom",
    "nomic-embed-custom",
    "moondream-custom",
)


def gate_statuses() -> tuple[GateStatus, ...]:
    """Availability of every optional ML/NLP engine, plus the RAG embedder."""
    from src.core.ml import deps as ml_deps
    from src.core.rag import embedder
    from src.core.text import entities, keywords

    return (
        GateStatus("[ml] (scikit-learn)", ml_deps.is_available(), ml_deps.SETUP_HINT),
        GateStatus(
            "[ml-viz] (UMAP)", ml_deps.umap_available(), ml_deps.UMAP_SETUP_HINT
        ),
        GateStatus("[nlp] (YAKE)", keywords.is_available(), keywords.SETUP_HINT),
        GateStatus("[nlp] (spaCy)", entities.is_available(), entities.SETUP_HINT),
        GateStatus("Embedder (Ollama)", embedder.is_available(), embedder.SETUP_HINT),
    )


def domain_statuses(*, directory=None) -> tuple[DomainStatus, ...]:
    """Label count + supervised-active flag for every ``classify.py`` domain.

    ``directory`` overrides ``ml.store.model_dir()`` (injectable for tests,
    same convention as ``classify.py`` itself) — left ``None`` in production so
    every domain reads the real on-disk cache.
    """
    from src.core.ml.classify import (
        DOMAIN_DATA,
        DOMAIN_DOCUMENT,
        DOMAIN_TRANSCRIPTION_PROFILE,
        domain_label_count,
        has_supervised_model,
    )

    domains = (DOMAIN_TRANSCRIPTION_PROFILE, DOMAIN_DATA, DOMAIN_DOCUMENT)
    return tuple(
        DomainStatus(
            d,
            domain_label_count(d, directory=directory),
            has_supervised_model(d, directory=directory),
        )
        for d in domains
    )


def config_snapshot() -> MLConfigSnapshot:
    """The hardcoded thresholds currently in effect, read straight from their
    source modules (never duplicated as a second copy of the number) so this
    never drifts from the code that actually enforces them.

    Reaches into a couple of underscore-prefixed constants deliberately: this
    is a read-only introspection for transparency, not an API dependency.
    """
    from src.core.library.image_dedup import DEFAULT_MAX_DISTANCE
    from src.core.ml import dedup, recommend
    from src.core.ml.cluster import _MIN_FOR_AUTO_K

    threshold_default = (
        inspect.signature(dedup.near_duplicates).parameters["threshold"].default
    )

    return MLConfigSnapshot(
        text_dedup_threshold=threshold_default,
        image_dedup_max_distance=DEFAULT_MAX_DISTANCE,
        auto_k_min_corpus=_MIN_FOR_AUTO_K,
        mmr_lambda=recommend._MMR_LAMBDA,
    )


def ollama_inventory() -> OllamaInventoryStatus:
    """Which of the 6 *-custom Ollama models are pulled locally, right now.

    ``reachable=False`` (rather than raising) when the Ollama service isn't
    running — this is a transparency read, not a hard dependency check.
    """
    try:
        import ollama

        installed = {m.model.split(":")[0] for m in ollama.Client().list().models}
    except Exception:
        return OllamaInventoryStatus(reachable=False, models=())

    return OllamaInventoryStatus(
        reachable=True,
        models=tuple(
            OllamaModelStatus(name, name in installed) for name in _KNOWN_CUSTOM_MODELS
        ),
    )
