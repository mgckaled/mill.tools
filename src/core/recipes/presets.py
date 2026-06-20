"""Built-in recipes — the showcase of cross-module automation value.

Every preset is type-coherent by construction: ``test_presets`` validates each
one against every kind its first step accepts, so a broken preset fails the suite.
Params are sensible defaults; the GUI builder/CLI may override per run.
"""

from __future__ import annotations

from src.core.recipes.types import Recipe, RecipeStep

PRESETS: list[Recipe] = [
    Recipe(
        name="YouTube → transcrição completa",
        description="Baixa o áudio, transcreve (com legendas), formata e analisa.",
        steps=[
            RecipeStep("audio.download"),
            RecipeStep(
                "transcription.transcribe",
                {"model": "small", "subtitles": ["srt", "vtt"]},
            ),
            RecipeStep("transcription.format"),
            RecipeStep("transcription.analyze", {"model": "gemini-2.5-flash"}),
        ],
    ),
    Recipe(
        name="Transcrever e analisar (arquivo local)",
        description="Transcreve um áudio/vídeo local, formata e gera a análise estruturada.",
        steps=[
            RecipeStep("transcription.transcribe", {"model": "small"}),
            RecipeStep("transcription.format"),
            RecipeStep("transcription.analyze", {"model": "gemma3-4b-custom"}),
        ],
    ),
    Recipe(
        name="Limpar áudio do YouTube",
        description="Baixa o áudio, reduz ruído e normaliza o volume (EBU R128).",
        steps=[
            RecipeStep("audio.download"),
            RecipeStep("audio.denoise"),
            RecipeStep("audio.normalize", {"target_lufs": -14.0}),
        ],
    ),
    Recipe(
        name="PDF escaneado → resumo",
        description="OCR do PDF e análise por LLM.",
        steps=[
            RecipeStep("document.ocr", {"lang": "por"}),
            RecipeStep("transcription.analyze", {"model": "gemma3-4b-custom"}),
        ],
    ),
    Recipe(
        name="Vídeo → legendado",
        description="Transcreve o vídeo, gera a .srt e embute no vídeo (mux soft).",
        steps=[
            # transcribe accepts video (PyAV) and produces text + .srt; video.subtitle
            # recovers the original video + .srt from the run context (multi-input).
            RecipeStep("transcription.transcribe", {"subtitles": ["srt"]}),
            RecipeStep("video.subtitle", {"mode": "soft"}),
        ],
    ),
]


def preset_by_name(name: str) -> Recipe | None:
    """Return the built-in recipe with the given name, or None."""
    return next((r for r in PRESETS if r.name == name), None)
