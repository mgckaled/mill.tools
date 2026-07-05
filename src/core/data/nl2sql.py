"""Translate a Portuguese question into a read-only SQL query.

This is the *only* place the LLM is involved in the data module, and it never
sees a data row — just the table/column schema (names and types). It reuses
``llm_factory.make_llm`` (local Ollama or Gemini opt-in) and the
``prompt | llm`` pattern shared by analyzer/prompter, so PR9 does not introduce
a second way of talking to an LLM.

The model is asked for a strict JSON object ``{"sql": ..., "explicacao": ...}``;
parsing is defensive (fenced block / first-object fallback) because small local
models occasionally wrap the JSON in prose.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from src.core.data.validate import UnsafeQueryError, ensure_select
from src.llm_factory import make_llm
from src.llm_utils import extract_llm_text

DEFAULT_MODEL = "gemma3-4b-custom"

# Strict NL→SQL prompt. The literal braces of the JSON example are escaped
# (``{{``/``}}``) so ChatPromptTemplate does not treat them as variables — the
# same escaping the analysis profiles use.
_NL2SQL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você é um tradutor de português para SQL do DuckDB. Recebe APENAS o "
            "esquema das tabelas (nomes e tipos de coluna) e uma pergunta. Gere UMA "
            "única consulta SQL de LEITURA (somente SELECT) que responda à pergunta. "
            "Regras rígidas:\n"
            "- Use somente as tabelas e colunas do esquema.\n"
            "- Nunca use COPY, INSERT, UPDATE, DELETE, CREATE, ATTACH, INSTALL, "
            "PRAGMA ou qualquer comando que escreva.\n"
            "- Não invente colunas.\n"
            "Responda SOMENTE com um objeto JSON válido, sem texto extra, no formato:\n"
            '{{"sql": "<a consulta SELECT>", "explicacao": "<o que a consulta faz, '
            'em português>"}}',
        ),
        ("human", "ESQUEMA:\n{schema}\n\nPERGUNTA: {question}"),
    ]
)

_FENCED = re.compile(r"```(?:sql|json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_FIRST_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class NL2SQLError(RuntimeError):
    """Raised when the model output cannot be turned into a safe SELECT."""


def _extract_payload(text: str) -> tuple[str, str]:
    """Pull ``(sql, explanation)`` out of a model response.

    Tries strict JSON first, then a fenced block, then the first ``{...}`` found.
    Returns the SQL and a (possibly empty) Portuguese explanation.
    """
    candidates: list[str] = [text.strip()]
    fenced = _FENCED.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    obj = _FIRST_OBJECT.search(text)
    if obj:
        candidates.append(obj.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("sql"):
            return str(data["sql"]).strip(), str(data.get("explicacao", "")).strip()

    # Last resort: the model returned a bare SQL string (or a fenced SQL block).
    # candidates[0] is the fenced block's content when one was found (inserted
    # above); candidates[1] would be the raw text *with* the surrounding
    # fences/prose, which never starts with a SQL keyword.
    bare = candidates[0] if fenced else text.strip()
    if bare.lower().lstrip().startswith(("select", "with", "from")):
        return bare.strip(), ""

    raise NL2SQLError("A IA não retornou uma consulta SQL reconhecível.")


def to_sql(
    schema: str,
    question: str,
    *,
    model_name: str = DEFAULT_MODEL,
    make_llm_fn: Callable = make_llm,
) -> tuple[str, str]:
    """Translate *question* into ``(sql, explicacao_pt)`` given the *schema*.

    The returned SQL is validated by :func:`ensure_select` before being handed
    back, so a model that ignores the read-only instruction still cannot produce
    an executable mutating statement here.

    Raises:
        NL2SQLError: if the model output cannot be parsed into SQL.
        UnsafeQueryError: if the produced SQL is not a read-only SELECT.
    """
    chain = _NL2SQL_PROMPT | make_llm_fn(model_name, temperature=0.0)
    resp = chain.invoke({"schema": schema, "question": question})
    content = extract_llm_text(resp.content) if hasattr(resp, "content") else str(resp)
    sql, explanation = _extract_payload(content)

    try:
        ensure_select(sql)
    except UnsafeQueryError:
        logging.warning("[!] NL→SQL produced a non-SELECT query: %s", sql)
        raise

    return sql, explanation
