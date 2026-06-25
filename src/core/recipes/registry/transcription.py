"""Transcription / LLM step adapters for the recipe registry.

Covers transcribe/format/analyze/prompt — the Whisper + LLM pipeline steps.
``ai.answer`` lives in ``registry/ai.py`` (the RAG world), not here.
"""

from __future__ import annotations

from pathlib import Path

from src.core.recipes.types import (
    KIND_AUDIO,
    KIND_MARKDOWN,
    KIND_TEXT,
    KIND_VIDEO,
    StepContext,
    StepSpec,
)


def _transcribe(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """audio/video → transcription .txt (+ optional .srt/.vtt). Wraps transcribe.

    transcribe() returns only elapsed time, so the adapter reconstructs the
    subtitle paths deterministically (the core writes them to
    ``TRANSCRIPTIONS_SUBTITLES_DIR / f"{stem}.{fmt}"``). Returning ``[txt, *subs]``
    lets a later video.subtitle step reach the .srt via ``ctx.outputs_by_op``.
    """
    from src import transcriber
    from src.utils import TRANSCRIPTIONS_SUBTITLES_DIR, TRANSCRIPTIONS_TEXT_DIR

    media = Path(inputs[0])  # audio OR video (faster-whisper decodes video via PyAV)
    out = TRANSCRIPTIONS_TEXT_DIR / f"transcription_{media.stem}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    subs = tuple(params.get("subtitles", ()))
    language = params.get("language", "auto")
    transcriber.transcribe(
        audio_path=media,
        output_path=out,
        meta={"title": media.stem, "duration": 0},
        url=str(media),
        model_size=params.get("model", "small"),
        language=None if language == "auto" else language,
        threads=params.get("threads", 2),
        beam_size=params.get("beam_size", 1),
        force_overwrite=True,
        subtitle_formats=subs,
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    sub_paths = [TRANSCRIPTIONS_SUBTITLES_DIR / f"{out.stem}.{fmt}" for fmt in subs]
    return [out, *sub_paths]


def _format(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription .txt → same .txt with paragraph breaks. Wraps format_transcription.

    format_transcription rewrites the file IN-PLACE and returns ``str | None``
    (the body), so the adapter returns ``[input_path]`` — the same, now-formatted
    .txt — discarding the string.
    """
    from src import formatter

    input_path = Path(inputs[0])
    formatter.format_transcription(
        input_path,
        model_name=params.get("model", formatter.DEFAULT_FORMAT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    return [input_path]


def _analyze(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription/text → structured analysis .md. Wraps analyzer.analyze."""
    from src import analyzer

    out = analyzer.analyze(
        input_path=Path(inputs[0]),
        model_name=params.get("model", analyzer.DEFAULT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
        profile=params.get("profile", analyzer.DEFAULT_PROFILE),
    )
    return [out]


def _prompt(inputs: list, params: dict, ctx: StepContext) -> list[Path]:
    """transcription/text → condensed prompt-ready .txt. Wraps build_prompt_ready."""
    from src import prompter

    out = prompter.build_prompt_ready(
        Path(inputs[0]),
        model_name=params.get("model", prompter.DEFAULT_PROMPT_MODEL),
        on_event=lambda t, s, p: ctx.emit(t, p),
    )
    return [out]


TRANSCRIPTION_STEPS: dict[str, StepSpec] = {
    "transcription.transcribe": StepSpec(
        _transcribe, frozenset({KIND_AUDIO, KIND_VIDEO}), KIND_TEXT, "Transcrever"
    ),
    "transcription.format": StepSpec(
        _format, frozenset({KIND_TEXT}), KIND_TEXT, "Formatar"
    ),
    "transcription.analyze": StepSpec(
        _analyze, frozenset({KIND_TEXT, KIND_MARKDOWN}), KIND_MARKDOWN, "Analisar"
    ),
    "transcription.prompt": StepSpec(
        _prompt, frozenset({KIND_TEXT}), KIND_TEXT, "Gerar prompt-ready"
    ),
}
