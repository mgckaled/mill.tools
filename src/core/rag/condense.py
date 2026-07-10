"""Query condensation: rewrite a follow-up question as a standalone one.

The Conversa is multi-turn only on screen — ``chat.answer()`` only ever sees
the current question, so a "e sobre a segunda parte?" embeds literally and
retrieves garbage. This module closes that gap: given the current question
and the last 1-2 finished turns, it asks a local LLM to rewrite the question
so it stands on its own, resolving references ("esse vídeo", "o segundo
ponto") using the conversation so far — including the *source stems* cited by
previous turns, since the contextual chunk header (``{stem} — {kind}``,
``indexer.CURRENT_EMBED_SCHEME``) means a well-resolved reference feeds
straight into what the embedding space already understands.

Mirrors the strict-prompt shape used by ``core/text/nl2cli.py``/``core/data/
nl2sql.py``, but with a plain-text output (a single rewritten question, not
JSON) and no retry: unlike a CLI command or SQL query, a bad condensation has
a natural, cheap fallback (the raw question), so a second LLM round-trip on
top of an already two-call flow (condense + answer) is not worth paying for.
Condensation always uses a local model regardless of the answer model chosen
(even a cloud one) — conversation history never has to leave the machine for
this step, and it keeps the extra latency bounded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from src.llm_factory import make_llm
from src.llm_utils import extract_llm_text

DEFAULT_MODEL = "gemma3-4b-custom"

_CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você reescreve a PERGUNTA ATUAL de uma conversa como uma pergunta "
            "independente (standalone), incorporando o contexto necessário do "
            "HISTÓRICO para que ela faça sentido sozinha, sem depender dos "
            'turnos anteriores. Resolva referências como "esse vídeo", "o '
            'segundo ponto", "e sobre isso?" pelo assunto real — use o nome '
            "dos documentos citados nas fontes do histórico quando ajudar a "
            "deixar a pergunta mais específica. Responda SOMENTE com a "
            "pergunta reescrita, sem aspas, sem explicações, sem prefixos. Se "
            "a pergunta atual já for autossuficiente (não depende do "
            "histórico), repita-a exatamente como está.",
        ),
        ("human", "HISTÓRICO:\n{history}\n\nPERGUNTA ATUAL: {question}"),
    ]
)


@dataclass(frozen=True, slots=True)
class Turn:
    """One finished conversation turn, as needed to condense a follow-up.

    ``sources`` mirrors the ``answer_done`` payload's ``sources`` list (cited
    source paths, first-seen order) — cheap to carry along, and it is what
    lets the condensation prompt resolve "esse vídeo" to the real document.
    """

    question: str
    answer: str
    sources: tuple[str, ...] = ()


def _fmt_history(history: list[Turn]) -> str:
    """Render finished turns as numbered blocks for the condensation prompt."""
    blocks = []
    for i, turn in enumerate(history, 1):
        stems = ", ".join(Path(s).stem for s in turn.sources) or "(nenhuma)"
        blocks.append(
            f"Turno {i}:\nPergunta: {turn.question}\nResposta: {turn.answer}\n"
            f"Fontes citadas: {stems}"
        )
    return "\n\n".join(blocks)


def condense_query(
    question: str,
    history: list[Turn],
    make_llm_fn: Callable = make_llm,
    *,
    model: str = DEFAULT_MODEL,
) -> str:
    """Rewrite ``question`` as standalone, using the last turns in ``history``.

    Args:
        question: The user's current question, verbatim.
        history: Finished turns, oldest first (the caller decides how many —
            2 is the recommended window). Empty history means the first
            question of the session.
        make_llm_fn: Injected LLM factory (default ``llm_factory.make_llm``),
            same pattern as ``nl2cli``/``nl2sql`` — keeps this unit-testable
            without a running Ollama.
        model: Local Ollama tag. Condensation always runs locally, independent
            of whichever model answers the question.

    Returns:
        The rewritten question, or ``question`` unchanged when the history is
        empty (no LLM call — zero cost in the common single-turn case) or when
        condensation fails for any reason (network error, malformed/empty
        response, timeout). The Conversa must never fail to answer because of
        this step, so every failure mode degrades to the raw question instead
        of propagating.
    """
    if not history:
        return question

    try:
        chain = _CONDENSE_PROMPT | make_llm_fn(model, temperature=0.0)
        resp = chain.invoke({"history": _fmt_history(history), "question": question})
        content = resp.content if hasattr(resp, "content") else resp
        rewritten = extract_llm_text(content).strip().strip('"').strip()
        return rewritten or question
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "[!] Query condensation failed, falling back to the raw question: %s", exc
        )
        return question
