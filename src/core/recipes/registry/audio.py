"""Audio step adapters for the recipe registry.

Each adapter gives a heterogeneous core function the uniform signature
``adapter(inputs, params, ctx) -> list[Path]`` and writes to the canonical
audio output dir, never to a shared dir — that is what keeps PR6's Library
classifying each artifact by kind. See ``registry/__init__.py`` for the rationale.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_AUDIO,
    KIND_URL,
    KIND_VIDEO,
    StepContext,
    StepSpec,
)


def _audio_download(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """URL → audio file in the canonical audio/source dir. Wraps download_audio.

    download_audio reports progress via ``progress_hook(dict)`` (yt-dlp); the
    adapter normalizes it to ``ctx.emit`` so the step shows progress like the rest.
    """
    from src.core.audio.downloader import download_audio
    from src.utils import AUDIO_SOURCE_DIR

    out = download_audio(
        str(inputs[0]),
        AUDIO_SOURCE_DIR,
        fmt=params.get("fmt", "mp3"),
        quality=params.get("quality", "best"),
        embed_meta=params.get("embed_meta", False),
        progress_hook=lambda d: ctx.emit("progress_update", d),
    )
    return [out]


def _audio_convert(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → re-encoded audio. Wraps convert_audio."""
    from src.core.audio.converter import convert_audio
    from src.utils import AUDIO_PROCESSED_DIR

    out = convert_audio(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        fmt=params.get("fmt", "mp3"),
        bitrate=params.get("bitrate"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _audio_extract(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """video → extracted audio track. Wraps extract_audio."""
    from src.core.audio.converter import extract_audio
    from src.utils import AUDIO_PROCESSED_DIR

    out = extract_audio(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        fmt=params.get("fmt", "mp3"),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


def _audio_denoise(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → spectral-gated denoised WAV. Wraps denoise (CPU, no progress cb)."""
    from src.core.audio.denoiser import denoise
    from src.utils import AUDIO_PROCESSED_DIR

    out = denoise(
        Path(inputs[0]), AUDIO_PROCESSED_DIR, stationary=params.get("stationary", True)
    )
    return [out]


def _audio_normalize(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio → loudness-normalized audio. Wraps normalize_lufs.

    normalize_lufs reports progress via ``progress_cb(float 0..1)`` and returns
    ``(path, stats)``; the adapter keeps only the path and normalizes progress.
    """
    from src.core.audio.normalizer import normalize_lufs
    from src.utils import AUDIO_PROCESSED_DIR

    out, _stats = normalize_lufs(
        Path(inputs[0]),
        AUDIO_PROCESSED_DIR,
        target_lufs=params.get("target_lufs", -14.0),
        progress_cb=lambda f: ctx.emit("progress_update", {"current": f, "total": 1.0}),
    )
    return [out]


AUDIO_STEPS: dict[str, StepSpec] = {
    "audio.download": StepSpec(
        _audio_download, frozenset({KIND_URL}), KIND_AUDIO, "Baixar áudio"
    ),
    "audio.convert": StepSpec(
        _audio_convert, frozenset({KIND_AUDIO}), KIND_AUDIO, "Converter áudio"
    ),
    "audio.extract": StepSpec(
        _audio_extract, frozenset({KIND_VIDEO}), KIND_AUDIO, "Extrair áudio"
    ),
    "audio.denoise": StepSpec(
        _audio_denoise, frozenset({KIND_AUDIO}), KIND_AUDIO, "Reduzir ruído"
    ),
    "audio.normalize": StepSpec(
        _audio_normalize, frozenset({KIND_AUDIO}), KIND_AUDIO, "Normalizar volume"
    ),
}
