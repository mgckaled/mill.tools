"""IA assessment of a data file's quality (single-responsibility prompt).

There is no separate "sub-agent" in this app — the assessment is a strict prompt
in the same style as the analysis profiles (``src/analysis/``). The IA receives
**only** the column names/types, the DuckDB ``SUMMARIZE`` and a ~10-row sample —
never the whole table — and narrates consistency issues, suspicious types,
poorly named columns, duplicates, out-of-range values and structural problems.

The result is cached on disk keyed by ``(path, mtime)`` so the (optional)
indexing step can reuse it without paying a second LLM call, and so re-opening
the preview modal is instant until the file changes.

Privacy: with Gemini selected, only the schema + statistics leave the machine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from src.llm_factory import make_llm

DEFAULT_MODEL = "gemma3-4b-custom"

# Strict, single-responsibility prompt. It carries no literal braces, so no
# escaping is needed (unlike the analysis profiles' JSON skeleton); the three
# template variables (schema/profile/sample) are filled with values, which
# ChatPromptTemplate never re-parses for placeholders.
_ASSESS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Você é um analista de qualidade de dados. Recebe APENAS o esquema "
            "(nomes e tipos de coluna), um resumo estatístico (SUMMARIZE do "
            "DuckDB) e uma pequena amostra de linhas — NUNCA a tabela inteira. "
            "Produza uma avaliação objetiva em português, em Markdown, apontando: "
            "consistência geral; colunas com tipo suspeito (ex.: número guardado "
            "como texto); colunas mal nomeadas; possíveis duplicatas; valores "
            "fora de faixa ou nulos em excesso; problemas de estrutura (cabeçalho "
            "deslocado, esquema irregular). Seja conciso: use tópicos curtos. "
            "Se os dados parecerem consistentes, diga isso claramente. Não invente "
            "colunas nem repita o esquema inteiro.",
        ),
        (
            "human",
            "ESQUEMA:\n{schema}\n\nPERFIL (SUMMARIZE):\n{profile}\n\n"
            "AMOSTRA:\n{sample}",
        ),
    ]
)


def build_assessment_prompt() -> ChatPromptTemplate:
    """Return the single-responsibility data-quality prompt template."""
    return _ASSESS_PROMPT


def assess(
    schema: str,
    profile_text: str,
    sample_text: str,
    *,
    model_name: str = DEFAULT_MODEL,
    make_llm_fn: Callable = make_llm,
) -> str:
    """Run the quality assessment and return the IA's Markdown narrative.

    The LLM factory is injectable (mirrors ``nl2sql.to_sql``) so the flow is
    unit-testable with a ``GenericFakeChatModel`` and never needs Ollama.
    """
    chain = _ASSESS_PROMPT | make_llm_fn(model_name, temperature=0.2)
    resp = chain.invoke(
        {"schema": schema, "profile": profile_text, "sample": sample_text}
    )
    content = resp.content if hasattr(resp, "content") else str(resp)
    return content.strip()


# ----------------------------------------------------------------------------
# Cache: ~/.mill-tools/data_assessments.json, keyed by absolute path → {mtime,
# text}. An entry is only returned when the source file's mtime still matches,
# so a changed file is re-assessed rather than served a stale narrative.
# ----------------------------------------------------------------------------


def _cache_file() -> Path:
    """Return the on-disk assessment cache path (~/.mill-tools/...)."""
    return Path.home() / ".mill-tools" / "data_assessments.json"


def _load_cache(cache_file: Path) -> dict:
    """Load the cache dict, tolerating a missing or malformed file."""
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_cached_assessment(path: Path, *, cache_file: Path | None = None) -> str | None:
    """Return a cached assessment for *path* if present and still fresh.

    Freshness is the source file's mtime: a cached entry whose ``mtime`` differs
    from the file on disk is ignored (the file changed → re-assess).
    """
    path = Path(path)
    cache_file = cache_file or _cache_file()
    entry = _load_cache(cache_file).get(str(path.resolve()))
    if not entry:
        return None
    try:
        if Path(path).stat().st_mtime != entry.get("mtime"):
            return None
    except OSError:
        return None
    return entry.get("text")


def save_assessment(path: Path, text: str, *, cache_file: Path | None = None) -> None:
    """Cache *text* as the assessment of *path*, stamped with its current mtime."""
    path = Path(path)
    cache_file = cache_file or _cache_file()
    try:
        mtime = Path(path).stat().st_mtime
    except OSError as exc:
        logging.debug("[d] Cannot stat %s for assessment cache: %s", path, exc)
        return
    data = _load_cache(cache_file)
    data[str(path.resolve())] = {"mtime": mtime, "text": text}
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        logging.debug("[d] Could not write assessment cache: %s", exc)
