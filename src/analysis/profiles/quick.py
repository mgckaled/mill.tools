"""
quick.py: Lightweight profiles for short captures (voice memos, brainstorms).
"""

from __future__ import annotations

from src.analysis.types import (
    KIND_KEYVALUE,
    KIND_LIST,
    KIND_PARAGRAPH,
    AnalysisProfile,
    Field,
)

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

TLDR = AnalysisProfile(
    id="tldr",
    label="TL;DR",
    icon="SHORT_TEXT",
    persona="Você é um assistente que vai direto ao ponto.",
    source_hint="transcrição de qualquer conteúdo",
    temperature=0.3,
    fields=(
        Field(
            "tldr",
            "TL;DR",
            KIND_PARAGRAPH,
            "o conteúdo todo em 1-3 frases diretas, sem rodeios",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "key_takeaways",
            "Pontos principais",
            KIND_LIST,
            "3-5 conclusões/aprendizados mais importantes, cada um uma frase curta",
        ),
        Field(
            "one_liner",
            "Em uma linha",
            KIND_PARAGRAPH,
            "uma única frase que captura a essência (estilo manchete)",
        ),
    ),
)

FLASHCARDS = AnalysisProfile(
    id="flashcards",
    label="Flashcards",
    icon="QUIZ",
    persona="Você é um tutor que cria material de revisão rápida.",
    source_hint="transcrição de uma aula ou conteúdo educacional",
    temperature=0.3,
    fields=(
        Field(
            "summary",
            "Resumo",
            KIND_PARAGRAPH,
            "2-3 frases com o tema central",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "flashcards",
            "Flashcards",
            KIND_KEYVALUE,
            "pares 'Pergunta: resposta' cobrindo os pontos testáveis; 5-12 "
            "cartões; resposta curta e correta",
        ),
        Field(
            "key_terms",
            "Termos-chave",
            KIND_KEYVALUE,
            "formato 'Termo: definição curta'. (lista vazia se nenhum)",
        ),
    ),
)

PROFILES = (NOTES, TLDR, FLASHCARDS)
