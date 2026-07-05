"""Image description via VLM — local Ollama or cloud Gemini/GLM (LangChain). Lazy import."""

from __future__ import annotations

import base64
from pathlib import Path

from src.core.image._paths import unique_path

_DEFAULT_PROMPT = (
    "Descreva detalhadamente o que está nesta imagem em português: "
    "objetos presentes, contexto, cores dominantes, texto visível (se houver)."
)
_SHORT_PROMPT = (
    "Descreva esta imagem em português numa frase curta e objetiva, como uma "
    "legenda (caption) — sem floreios."
)
_TECHNICAL_PROMPT = (
    "Analise esta imagem do ponto de vista técnico e artístico em português: "
    "composição, enquadramento, iluminação, estilo/técnica e paleta de cores."
)
_TEXT_PROMPT = (
    "Transcreva em português todo o texto visível nesta imagem, palavra por "
    "palavra, sem descrever o resto da cena. Se não houver texto, responda "
    '"Nenhum texto visível.".'
)
_OBJECTS_PROMPT = (
    "Liste em português, em tópicos e sem prosa, todos os objetos e elementos "
    "identificáveis nesta imagem."
)
_NARRATIVE_PROMPT = (
    "Descreva esta imagem em português de forma criativa e narrativa, "
    "capturando a atmosfera, a emoção e a história que ela parece contar."
)

# Preset prompts selectable by id (CLI --preset, GUI card selector). "detailed"
# is the historical default — same text describe_image() falls back to when no
# prompt is given at all, so leaving prompt="" is still equivalent to it.
DESCRIBE_PRESETS: dict[str, str] = {
    "detailed": _DEFAULT_PROMPT,
    "short": _SHORT_PROMPT,
    "technical": _TECHNICAL_PROMPT,
    "text": _TEXT_PROMPT,
    "objects": _OBJECTS_PROMPT,
    "narrative": _NARRATIVE_PROMPT,
}


def is_available() -> bool:
    """True if langchain_ollama is installed (already a project dependency)."""
    try:
        from langchain_ollama import ChatOllama  # noqa: F401

        return True
    except ImportError:
        return False


def describe_image(src: Path, model: str = "moondream-custom", prompt: str = "") -> str:
    """Send an image to a vision model (local Ollama or Gemini/GLM cloud) and
    return its text description."""
    from langchain_core.messages import HumanMessage

    from src.llm_factory import (
        DEFAULT_OLLAMA_NUM_CTX,
        is_gemini_model,
        is_glm_model,
        make_llm,
        timing_callbacks,
    )
    from src.llm_utils import extract_llm_text

    with open(src, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    suffix = src.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix

    if is_glm_model(model) or is_gemini_model(model):
        # GLM-4.6V-Flash (Zhipu/Z.ai) and every Gemini model (natively multimodal,
        # no separate vision variant) accept the same multimodal message shape
        # used below, no request changes needed. Both are free-tier eligible.
        llm = make_llm(model, domain="vlm")
    else:
        from langchain_ollama import ChatOllama

        # Pin num_ctx: Ollama defaults to 2048, too small for the verbose PT prompt
        # plus the image tokens (a larger VLM like gemma3-4b would truncate the reply).
        # This branch bypasses make_llm() (different temperature default), so the
        # timing callback is attached manually to still record VLM latency.
        llm = ChatOllama(
            model=model,
            num_ctx=DEFAULT_OLLAMA_NUM_CTX,
            callbacks=timing_callbacks(model, "vlm"),
        )
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt or _DEFAULT_PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{mime};base64,{img_b64}"},
            },
        ]
    )
    response = llm.invoke([message])
    return extract_llm_text(response.content)


def save_description(src: Path, out_dir: Path, text: str) -> Path:
    """Save the description as <stem>_description.txt in out_dir."""
    out_path = unique_path(out_dir, f"{src.stem}_description", "txt")
    out_path.write_text(text, encoding="utf-8")
    return out_path
