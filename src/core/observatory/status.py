"""Read-only snapshot of every ML engine's status — the Observatório's status board.

Aggregates what already exists elsewhere (extra/embedder gates, classifier
label counts, hardcoded thresholds, per-model answer timings) into a single
read. Computes nothing new — this is transparency, not a fresh analysis.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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
    """Hardcoded parameters currently in effect — transparency, not a settings form.

    ``mmr_lambda`` (``core.ml.recommend``) and ``mmr_lambda_summary``
    (``core.text.summarize``) are two independent constants that happen to
    share both a name and a value today — ``core/text`` stays independent of
    ``core/ml`` by design (see ``docs/HISTORY.md``), so this reports both
    instead of picking one and hiding the other.
    """

    text_dedup_threshold: float
    image_dedup_max_distance: int
    auto_k_min_corpus: int
    mmr_lambda: float
    mmr_lambda_summary: float


@dataclass(frozen=True, slots=True)
class EntityGlossaryStatus:
    """Whether the optional NER domain glossary is configured, and its size."""

    exists: bool
    n_patterns: int


@dataclass(frozen=True, slots=True)
class BinaryStatus:
    """Resolution of one external binary dependency (yt-dlp, ffmpeg, ...)."""

    name: str
    path: str | None  # resolved path, or None if not found


@dataclass(frozen=True, slots=True)
class CloudProviderStatus:
    """Whether a cloud LLM provider's API key is configured (.env)."""

    name: str
    configured: bool


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
    """Availability of every optional ML/NLP/media engine, plus the RAG embedder."""
    from src.core.data import charts as data_charts
    from src.core.data import frames as data_frames
    from src.core.document import ocr as document_ocr
    from src.core.image import background as image_background
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
        GateStatus(
            "[ocr] (Tesseract)", document_ocr.is_available(), document_ocr.SETUP_HINT
        ),
        GateStatus(
            "[ai-image] (rembg)",
            image_background.is_available(),
            image_background.SETUP_HINT,
        ),
        GateStatus(
            "[analysis] (Polars/PyArrow)",
            data_frames.is_available(),
            data_frames.SETUP_HINT,
        ),
        GateStatus(
            "[data-plot] (matplotlib)",
            data_charts.is_available(),
            data_charts.SETUP_HINT,
        ),
    )


def domain_statuses(
    *, directory: Path | None = None, embed_space_id: str | None = None
) -> tuple[DomainStatus, ...]:
    """Label count + supervised-active flag for every ``classify.py`` domain.

    ``directory`` overrides ``ml.store.model_dir()`` (injectable for tests,
    same convention as ``classify.py`` itself) — left ``None`` in production so
    every domain reads the real on-disk cache. ``embed_space_id`` (model + dim
    of the RAG's current embedding space) is threaded into
    ``has_supervised_model`` so a domain whose model was trained on a
    since-changed embed model correctly reports ``supervised=False`` (M2);
    ``None`` reads it from the real RAG index sidecar.
    """
    from src.core.ml.classify import (
        DOMAIN_DATA,
        DOMAIN_DOCUMENT,
        DOMAIN_TRANSCRIPTION_PROFILE,
        domain_label_count,
        has_supervised_model,
    )

    if embed_space_id is None:
        from src.core.rag.indexer import index_dir
        from src.core.rag.stats import embed_space_id as read_embed_space_id

        embed_space_id = read_embed_space_id(index_dir())

    domains = (DOMAIN_TRANSCRIPTION_PROFILE, DOMAIN_DATA, DOMAIN_DOCUMENT)
    return tuple(
        DomainStatus(
            d,
            domain_label_count(d, directory=directory),
            has_supervised_model(d, directory=directory, embed_space_id=embed_space_id),
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
    from src.core.text import summarize

    threshold_default = (
        inspect.signature(dedup.near_duplicates).parameters["threshold"].default
    )

    return MLConfigSnapshot(
        text_dedup_threshold=threshold_default,
        image_dedup_max_distance=DEFAULT_MAX_DISTANCE,
        auto_k_min_corpus=_MIN_FOR_AUTO_K,
        mmr_lambda=recommend._MMR_LAMBDA,
        mmr_lambda_summary=summarize._MMR_LAMBDA,
    )


def entity_glossary_status() -> EntityGlossaryStatus:
    """Whether the optional ``~/.mill-tools/entity_glossary.json`` domain
    glossary is configured, and how many EntityRuler patterns it holds.

    Reuses ``core.text.entities``'s own path/parsing helpers (both already
    tolerant of an absent/malformed file) rather than duplicating them.
    """
    from src.core.text.entities import _glossary_path, _load_glossary_patterns

    return EntityGlossaryStatus(
        exists=_glossary_path().exists(),
        n_patterns=len(_load_glossary_patterns()),
    )


def binary_statuses() -> tuple[BinaryStatus, ...]:
    """Resolution of every external binary the app shells out to."""
    import shutil

    from src.core.document.ocr import resolve_tesseract_cmd

    return (
        BinaryStatus("yt-dlp", shutil.which("yt-dlp")),
        BinaryStatus("ffmpeg", shutil.which("ffmpeg")),
        BinaryStatus("ffprobe", shutil.which("ffprobe")),
        BinaryStatus("tesseract", resolve_tesseract_cmd()),
    )


def cloud_provider_statuses() -> tuple[CloudProviderStatus, ...]:
    """Whether the opt-in cloud providers (Gemini, GLM) have an API key set.

    Never reveals the key itself — presence/absence only. Reuses
    ``llm_factory``'s own ``.env`` loader (idempotent, same one ``make_llm``
    uses) rather than re-implementing ``.env`` parsing here; ``core/data/
    nl2sql.py`` already sets the precedent of ``core/`` importing
    ``src.llm_factory`` directly.
    """
    import os

    from src.llm_factory import _load_env_once

    _load_env_once()
    return (
        CloudProviderStatus(
            "Gemini (GOOGLE_API_KEY)", bool(os.getenv("GOOGLE_API_KEY"))
        ),
        CloudProviderStatus("GLM (ZHIPU_API_KEY)", bool(os.getenv("ZHIPU_API_KEY"))),
    )


# Bounds worst-case latency — this is a status read, not a workflow.
_OLLAMA_TIMEOUT_S = 5


def ollama_inventory() -> OllamaInventoryStatus:
    """Which of the 6 *-custom Ollama models are pulled locally, right now.

    ``reachable=False`` (rather than raising) when the Ollama service isn't
    running — this is a transparency read, not a hard dependency check. The
    client gets a bounded timeout so a slow/half-open service can't hang this
    read indefinitely (this runs off the UI thread, but still shouldn't stall
    forever).
    """
    try:
        import ollama

        client = ollama.Client(timeout=_OLLAMA_TIMEOUT_S)
        installed = {m.model.split(":")[0] for m in client.list().models}
    except Exception:
        return OllamaInventoryStatus(reachable=False, models=())

    return OllamaInventoryStatus(
        reachable=True,
        models=tuple(
            OllamaModelStatus(name, name in installed) for name in _KNOWN_CUSTOM_MODELS
        ),
    )
