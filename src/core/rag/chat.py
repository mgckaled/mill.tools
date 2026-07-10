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
from src.llm_utils import extract_llm_text

if TYPE_CHECKING:
    from src.core.rag.types import RetrievedChunk

DEFAULT_MODEL = "gemma3-4b-custom"

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

    The citation number ``[n]`` is keyed to the *distinct source document*, not
    to the chunk position: several chunks from the same file share one ``[n]``.
    This keeps the model's ``[n]`` markers in lock-step with the ``sources`` list
    shown in the UI — otherwise, with k chunks from fewer documents, the model
    would cite ``[5]``/``[6]`` while only 4 source badges exist.

    Returns ``(context_text, sources)`` where ``sources`` lists the distinct
    source paths in first-seen order, parallel to the ``[n]`` markers.
    """
    blocks: list[str] = []
    sources: list[Path] = []
    number_of: dict[str, int] = {}
    for h in retrieved:
        path = Path(h.meta.source_path)
        key = str(path)
        if key not in number_of:
            sources.append(path)
            number_of[key] = len(sources)  # 1-based, per distinct document
        blocks.append(f"[{number_of[key]}] ({path.name})\n{h.meta.text}")
    context = "\n\n".join(blocks) if blocks else "(sem contexto)"
    return context, sources


def answer(
    query: str,
    retrieved: list[RetrievedChunk],
    *,
    model_name: str = DEFAULT_MODEL,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> AnswerResult:
    """Answer ``query`` strictly from ``retrieved`` chunks, citing sources.

    Args:
        query: The question to answer — the raw one, or (Fase 2, PLANO_CONVERSA_
            MULTITURNO.md) the standalone rewrite ``condense.condense_query``
            produces for a follow-up. ``answer`` itself is agnostic to which;
            it just needs a question and the context to answer it from.
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
    return AnswerResult(text=extract_llm_text(resp.content), sources=sources)
