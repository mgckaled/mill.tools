"""
prompts.py: Generate analysis and merge prompts from a profile's fields.

The system message is assembled with the persona, source hint, a JSON skeleton
derived from the fields, and one rule line per field. Because LangChain's
f-string templates treat ``{`` / ``}`` as variable delimiters, every literal
brace in the generated system text is escaped (``{`` -> ``{{``). The only real
template variable is ``{text}`` (analysis) / ``{analyses}`` (merge), carried by
the human message.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from src.analysis.types import KIND_PARAGRAPH, AnalysisProfile, Field


def _skeleton_value(kind: str) -> str:
    """Return the JSON skeleton placeholder for a field kind."""
    if kind == KIND_PARAGRAPH:
        return '"..."'
    return '["...", "..."]'


def _json_skeleton(fields: tuple[Field, ...]) -> str:
    """Build the obligatory JSON skeleton block from the profile fields."""
    lines = ["{"]
    for i, f in enumerate(fields):
        comma = "," if i < len(fields) - 1 else ""
        lines.append(f'  "{f.key}": {_skeleton_value(f.kind)}{comma}')
    lines.append("}")
    return "\n".join(lines)


def _rules_block(fields: tuple[Field, ...]) -> str:
    """Build the per-field rules block."""
    return "\n".join(f"- {f.key}: {f.rule}" for f in fields)


def _escape_braces(text: str) -> str:
    """Escape literal braces so LangChain does not treat them as variables."""
    return text.replace("{", "{{").replace("}", "}}")


def build_analysis_prompt(profile: AnalysisProfile) -> ChatPromptTemplate:
    """Build the per-chunk analysis prompt for *profile*.

    Args:
        profile: The active analysis profile.

    Returns:
        A ChatPromptTemplate whose human message expects a ``text`` variable.
    """
    system = (
        f"{profile.persona} Você recebe a {profile.source_hint} e deve produzir "
        "uma análise estruturada em formato JSON. "
        "Responda APENAS com JSON válido, sem texto extra antes ou depois. "
        "Responda SEMPRE em português brasileiro.\n\n"
        "Estrutura JSON obrigatória:\n"
        f"{_json_skeleton(profile.fields)}\n\n"
        "Regras:\n"
        f"{_rules_block(profile.fields)}"
    )
    return ChatPromptTemplate.from_messages(
        [
            ("system", _escape_braces(system)),
            ("human", "Transcrição:\n\n{text}"),
        ]
    )


def build_merge_prompt(profile: AnalysisProfile) -> ChatPromptTemplate:
    """Build the consolidation prompt that merges partial analyses for *profile*.

    Args:
        profile: The active analysis profile.

    Returns:
        A ChatPromptTemplate whose human message expects an ``analyses`` variable.
    """
    system = (
        f"{profile.persona} Você recebe múltiplas análises parciais de uma única "
        f"{profile.source_hint}, dividida em partes. Sua tarefa é consolidar tudo "
        "em UMA análise final coerente e bem escrita.\n\n"
        "Regras de consolidação:\n"
        "- Elimine itens duplicados ou semanticamente equivalentes — mantenha "
        "apenas a versão mais completa\n"
        "- Unifique itens que tratam do mesmo assunto em um único item abrangente\n"
        "- Use português brasileiro correto — sem neologismos, sem palavras inventadas\n\n"
        "Responda APENAS com JSON válido, sem texto extra antes ou depois.\n\n"
        "Estrutura JSON obrigatória:\n"
        f"{_json_skeleton(profile.fields)}\n\n"
        "Regras por campo:\n"
        f"{_rules_block(profile.fields)}"
    )
    return ChatPromptTemplate.from_messages(
        [
            ("system", _escape_braces(system)),
            ("human", "Análises parciais para consolidar:\n\n{analyses}"),
        ]
    )
