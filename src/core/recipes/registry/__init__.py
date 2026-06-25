"""Uniform step adapters wrapping existing pure core functions.

Each adapter gives a heterogeneous core function a uniform signature
``adapter(inputs, params, ctx) -> list[Path]`` and writes to the *canonical*
output dir of its module (``src/utils`` constants), never to a shared dir —
that is what keeps PR6's Library classifying each artifact by kind.

The core never changes: adding an operation to automation is a thin wrapper plus
one ``STEP_REGISTRY`` entry. The adapter is also the single layer that knows the
exact callback shape of each core function. The project has no single callback
style — ``transcribe``/``analyze`` use ``on_event(type, stage, payload)``,
``download_*`` use ``progress_hook(dict)`` and ``normalize_lufs`` uses
``progress_cb(float)`` — so the adapter is where those converge onto
``ctx.emit(...)``; without it, download/normalize steps would have no progress.

The adapters live in one submodule per module (audio/video/transcription/ai/
document/image/data); this package assembles them into the single
``STEP_REGISTRY`` source of truth. ``from src.core.recipes.registry import
STEP_REGISTRY`` keeps working because ``registry`` is now a package whose
``__init__`` re-exports it — runner, validate and external callers are unchanged.
"""

from __future__ import annotations

from src.core.recipes.registry.ai import AI_STEPS
from src.core.recipes.registry.audio import AUDIO_STEPS
from src.core.recipes.registry.data import DATA_STEPS
from src.core.recipes.registry.document import DOCUMENT_STEPS
from src.core.recipes.registry.image import IMAGE_STEPS
from src.core.recipes.registry.transcription import TRANSCRIPTION_STEPS
from src.core.recipes.registry.video import VIDEO_STEPS
from src.core.recipes.types import StepSpec

STEP_REGISTRY: dict[str, StepSpec] = {
    **AUDIO_STEPS,
    **VIDEO_STEPS,
    **TRANSCRIPTION_STEPS,
    **AI_STEPS,
    **DOCUMENT_STEPS,
    **IMAGE_STEPS,
    **DATA_STEPS,
}

__all__ = ["STEP_REGISTRY"]
