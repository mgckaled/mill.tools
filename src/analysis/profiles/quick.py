"""
quick.py: Lightweight profiles for short captures (voice memos, brainstorms).
"""

from __future__ import annotations

from src.analysis.types import KIND_LIST, AnalysisProfile, Field

NOTES = AnalysisProfile(
    id="notes",
    label="Notas",
    icon="LIGHTBULB_OUTLINE",
    persona="Você é um assistente que organiza anotações e brainstorms.",
    source_hint="gravação de notas ou brainstorm",
    temperature=0.3,
    fields=(
        Field(
            "ideas",
            "Ideias",
            KIND_LIST,
            "ideias e propostas levantadas, cada uma em uma linha clara. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "decisions",
            "Decisões",
            KIND_LIST,
            "decisões ou escolhas feitas. (lista vazia se nenhuma)",
        ),
        Field(
            "todos",
            "Tarefas",
            KIND_LIST,
            "tarefas a fazer; comece cada item com um verbo no infinitivo. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "questions",
            "Perguntas em aberto",
            KIND_LIST,
            "dúvidas ou pontos a investigar. (lista vazia se nenhum)",
        ),
        Field(
            "insights",
            "Insights",
            KIND_LIST,
            "percepções ou conexões relevantes que emergiram. (lista vazia se nenhum)",
        ),
    ),
)

PROFILES = (NOTES,)
