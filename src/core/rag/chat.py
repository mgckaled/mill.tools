"""RAG answer synthesis: build a cited context from retrieved chunks and ask the LLM.

Reuses ``llm_factory.make_llm`` for provider routing (local Ollama or Gemini
opt-in) and the ``prompt | llm`` pattern already used by analyzer/prompter, so
PR7 does not introduce a second way of talking to an LLM.
"""

from __future__ import annotations

import logging
import re
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


# Citation markers the model emits: [n], possibly grouped ([1, 2]) or adjacent
# ([1][2]). This is the single home for parsing them — it lives next to
# build_context, which is what assigns the [n] in the first place, so GUI and
# CLI both consume one function instead of each re-parsing on its own
# (PLANO_FONTES_E_PISO_RELEVANCIA.md, Fase 1).
_CITATION_RE = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]")


def cited_source_numbers(text: str, n_sources: int) -> list[int]:
    """Distinct 1-based source numbers actually cited in ``text``, in order.

    Extracts ``[n]`` markers — including grouped ``[1, 2]`` and adjacent
    ``[1][2]`` forms — keeping only numbers within ``1..n_sources`` and
    de-duplicating by first appearance. Parsed defensively: numbers out of range
    and non-numeric brackets are ignored, so a "creative" model never fabricates
    a citation that can't be backed by a real retrieved source. Returns ``[]``
    when the answer cites nothing parseable — the caller then treats every
    source as consulted-but-not-cited (Fase 1.5) rather than inventing one.
    """
    seen: list[int] = []
    for group in _CITATION_RE.findall(text):
        for token in re.findall(r"\d+", group):
            n = int(token)
            if 1 <= n <= n_sources and n not in seen:
                seen.append(n)
    return seen


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
        An ``AnswerResult`` with the model's text, the distinct sources
        consulted (retrieved into context) and the subset actually cited via
        ``[n]`` in the text (see ``AnswerResult``).
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

    text = extract_llm_text(resp.content)
    # The cited subset, in citation-number order (a clean subset of `sources`);
    # empty when the model cited nothing parseable — never inventing a citation.
    cited_numbers = set(cited_source_numbers(text, len(sources)))
    cited_sources = [s for i, s in enumerate(sources, 1) if i in cited_numbers]

    _emit("answer_done", {"n_sources": len(sources), "n_cited": len(cited_sources)})
    return AnswerResult(text=text, sources=sources, cited_sources=cited_sources)
