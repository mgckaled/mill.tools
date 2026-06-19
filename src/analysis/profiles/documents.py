"""
documents.py: Academic/document analysis profiles (scientific, administrative).

These are factual profiles (low temperature) with no "ignore CTAs" rule — they
target papers and meeting recordings, not promotional video content.
"""

from __future__ import annotations

from src.analysis.types import (
    KIND_KEYVALUE,
    KIND_LIST,
    KIND_PARAGRAPH,
    AnalysisProfile,
    Field,
)

SCIENTIFIC = AnalysisProfile(
    id="scientific",
    label="Científico",
    icon="SCIENCE_OUTLINED",
    persona="Você é um revisor científico rigoroso.",
    source_hint="transcrição de uma apresentação ou artigo acadêmico",
    temperature=0.2,
    fields=(
        Field(
            "abstract",
            "Resumo",
            KIND_PARAGRAPH,
            "3-5 frases sintetizando objetivo, método e principal achado",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "research_question",
            "Pergunta/objetivo",
            KIND_PARAGRAPH,
            "a pergunta de pesquisa ou objetivo central, em uma a duas frases",
        ),
        Field(
            "hypotheses",
            "Hipóteses",
            KIND_LIST,
            "hipóteses testadas, formuladas como afirmação. (lista vazia se nenhuma)",
        ),
        Field(
            "methodology",
            "Metodologia",
            KIND_PARAGRAPH,
            "desenho do estudo, amostra/dados, instrumentos e procedimentos. Seja "
            "específico sobre N, técnicas e controles quando mencionados",
        ),
        Field(
            "results",
            "Resultados",
            KIND_LIST,
            "principais resultados COM os números/estatísticas citados (p-valor, "
            "efeito, %); cada item é uma frase completa. (lista vazia se nenhum)",
        ),
        Field(
            "conclusions",
            "Conclusões",
            KIND_LIST,
            "o que os autores concluem a partir dos resultados",
        ),
        Field(
            "limitations",
            "Limitações",
            KIND_LIST,
            "limites metodológicos reconhecidos ou inferíveis. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "contributions",
            "Contribuições",
            KIND_LIST,
            "o que há de novo/original frente ao estado da arte",
        ),
        Field(
            "key_concepts",
            "Conceitos-chave",
            KIND_KEYVALUE,
            "formato 'Termo: definição de uma linha'. (lista vazia se nenhum)",
        ),
        Field(
            "references_mentioned",
            "Referências citadas",
            KIND_LIST,
            "autores, obras ou trabalhos mencionados. (lista vazia se nenhuma)",
        ),
        Field(
            "future_work",
            "Trabalhos futuros",
            KIND_LIST,
            "direções de pesquisa sugeridas. (lista vazia se nenhuma)",
        ),
    ),
)

ADMINISTRATIVE = AnalysisProfile(
    id="administrative",
    label="Administrativo",
    icon="BUSINESS_CENTER_OUTLINED",
    persona="Você é um secretário executivo que produz atas precisas.",
    source_hint="gravação de uma reunião ou documento administrativo",
    temperature=0.2,
    fields=(
        Field(
            "executive_summary",
            "Resumo executivo",
            KIND_PARAGRAPH,
            "3-5 frases com o essencial do que foi tratado e decidido",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "decisions",
            "Decisões",
            KIND_LIST,
            "decisões efetivamente tomadas, cada uma como afirmação clara. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "action_items",
            "Ações",
            KIND_KEYVALUE,
            "formato 'Tarefa — responsável (prazo)'. Ex: 'Enviar proposta — Marina "
            "(até 20/06)'. Se responsável/prazo não forem ditos, escreva "
            "'responsável não definido'. (lista vazia se nenhuma)",
        ),
        Field(
            "participants",
            "Participantes",
            KIND_LIST,
            "pessoas/áreas mencionadas como presentes ou envolvidas. "
            "(lista vazia se não identificável)",
        ),
        Field(
            "deadlines",
            "Prazos e datas",
            KIND_LIST,
            "datas e prazos citados com seu contexto. (lista vazia se nenhum)",
        ),
        Field(
            "risks_issues",
            "Riscos e pendências",
            KIND_LIST,
            "problemas, bloqueios ou riscos levantados. (lista vazia se nenhum)",
        ),
        Field(
            "agreements",
            "Acordos",
            KIND_LIST,
            "consensos/combinados que não são decisões formais. "
            "(lista vazia se nenhum)",
        ),
        Field(
            "open_questions",
            "Questões em aberto",
            KIND_LIST,
            "pontos não resolvidos que ficaram pendentes. (lista vazia se nenhum)",
        ),
        Field(
            "next_steps",
            "Próximos passos",
            KIND_LIST,
            "encaminhamentos e próxima reunião, se mencionada",
        ),
    ),
)

PROFILES = (SCIENTIFIC, ADMINISTRATIVE)
