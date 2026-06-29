"""Descrição de imagem via Ollama vision (LangChain). Import lazy."""

from __future__ import annotations

import base64
from pathlib import Path

_DEFAULT_PROMPT = (
    "Descreva detalhadamente o que está nesta imagem em português: "
    "objetos presentes, contexto, cores dominantes, texto visível (se houver)."
)


def is_available() -> bool:
    """True se langchain_ollama instalado (já é dep do projeto)."""
    try:
        from langchain_ollama import ChatOllama  # noqa: F401

        return True
    except ImportError:
        return False


def describe_image(src: Path, model: str = "moondream-custom", prompt: str = "") -> str:
    """Send an image to an Ollama vision model and return its text description."""
    from langchain_core.messages import HumanMessage
    from langchain_ollama import ChatOllama

    from src.llm_factory import DEFAULT_OLLAMA_NUM_CTX

    with open(src, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    suffix = src.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix

    # Pin num_ctx: Ollama defaults to 2048, too small for the verbose PT prompt
    # plus the image tokens (a larger VLM like gemma3-4b would truncate the reply).
    llm = ChatOllama(model=model, num_ctx=DEFAULT_OLLAMA_NUM_CTX)
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
    return response.content


def save_description(src: Path, out_dir: Path, text: str) -> Path:
    """Salva descrição como <stem>_description.txt em out_dir."""
    out_path = out_dir / f"{src.stem}_description.txt"
    i = 1
    while out_path.exists():
        out_path = out_dir / f"{src.stem}_description_{i}.txt"
        i += 1
    out_path.write_text(text, encoding="utf-8")
    return out_path
