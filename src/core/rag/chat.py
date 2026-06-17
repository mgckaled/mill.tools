"""RAG answer synthesis: build a cited context from retrieved chunks and ask the LLM.

Reuses ``llm_factory.make_llm`` for provider routing (local Ollama or Gemini
opt-in) and the ``prompt | llm`` pattern already used by analyzer/prompter, so
PR7 does not introduce a second way of talking to an LLM.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from langchain_core.prompts import ChatPromptTemplate

from src.core.rag.types import AnswerResult
from src.llm_factory import make_llm

if TYPE_CHECKING:
    from src.core.rag.types import RetrievedChunk

DEFAULT_MODEL = "qwen7b-custom"

# Strict grounding prompt: answer only from the supplied context, cite sources by
# number, and admit when the context does not contain the answer. Reduces
# hallucination and keeps answers traceable to Library items.
RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você responde perguntas usando APENAS o CONTEXTO fornecido (trechos "
            "de documentos do usuário). Cite as fontes pelo número [n]. Se o "
            "contexto não contiver a resposta, diga claramente que não encontrou. "
            "Responda em português brasileiro, de forma objetiva.",
        ),
        ("human", "CONTEXTO:\n{context}\n\nPERGUNTA: {question}"),
    ]
)


def build_context(retrieved: list[RetrievedChunk]) -> tuple[str, list[Path]]:
    """Render numbered context blocks and the distinct source list.

    Returns ``(context_text, sources)`` where each block is prefixed with its
    citation number ``[n]`` and the originating filename, and ``sources`` lists
    the distinct source paths in first-seen order (parallel to the [n] markers).
    """
    blocks: list[str] = []
    sources: list[Path] = []
    for i, h in enumerate(retrieved, 1):
        path = Path(h.meta.source_path)
        blocks.append(f"[{i}] ({path.name})\n{h.meta.text}")
        sources.append(path)
    context = "\n\n".join(blocks) if blocks else "(sem contexto)"
    distinct = list(dict.fromkeys(sources))  # dedupe, preserve order
    return context, distinct


def answer(
    query: str,
    retrieved: list[RetrievedChunk],
    *,
    model_name: str = DEFAULT_MODEL,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> AnswerResult:
    """Answer ``query`` strictly from ``retrieved`` chunks, citing sources.

    Args:
        query: The user's question.
        retrieved: Top-k chunks from the retriever (may be empty).
        model_name: Local Ollama tag or Gemini name; provider resolved by prefix.
        on_event: Optional ``(type, stage, payload)`` emitter for the GUI/CLI bus.

    Returns:
        An ``AnswerResult`` with the model's text and the distinct cited sources.
    """

    def _emit(type: str, payload: dict | None = None) -> None:
        if on_event:
            on_event(type, "answer", payload or {})

    context, sources = build_context(retrieved)
    logging.info(
        "[*] Answering with %s | %d chunk(s), %d source(s)",
        model_name,
        len(retrieved),
        len(sources),
    )
    _emit("answer_start", {"model_name": model_name, "n_chunks": len(retrieved)})

    chain = RAG_PROMPT | make_llm(model_name, temperature=0.2)
    resp = chain.invoke({"context": context, "question": query})

    _emit("answer_done", {"n_sources": len(sources)})
    return AnswerResult(text=resp.content, sources=sources)
