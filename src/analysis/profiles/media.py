"""
media.py: Content/media analysis profiles (video, lecture, podcast, tutorial).

The ``default`` profile carries the historical 10-field schema with the exact
section titles and rules, so the generated report reproduces the legacy output.
The "ignore CTAs/sponsors" rule is exclusive to media profiles (modelled inline
in the relevant field rules), never in document/meeting profiles.
"""

from __future__ import annotations

from src.analysis.types import (
    KIND_KEYVALUE,
    KIND_LIST,
    KIND_PARAGRAPH,
    KIND_QUOTES,
    AnalysisProfile,
    Field,
)

_IGNORE_CTA = "IGNORE CTAs (curtir, inscrever, comentar), patrocinadores e autopromoção"

DEFAULT = AnalysisProfile(
    id="default",
    label="Geral",
    icon="ARTICLE_OUTLINED",
    persona="Você é um analista especialista.",
    source_hint="transcrição de um vídeo do YouTube",
    temperature=0.4,
    fields=(
        Field(
            "summary",
            "Resumo",
            KIND_PARAGRAPH,
            "3-5 frases, capture a essência",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "key_points",
            "Pontos-chave",
            KIND_LIST,
            "5-10 pontos mais importantes; cada ponto deve ser uma frase completa "
            "com sujeito e verbo, com no mínimo 12 palavras; explique o 'como' ou "
            "'por que' sempre que possível, não apenas liste fatos; "
            "ERRADO: 'Bolo feito no liquidificador' | CERTO: 'O liquidificador "
            "substitui a batedeira ao emulsionar os ingredientes, resultando em "
            f"massa mais homogênea e fofa'; {_IGNORE_CTA}",
            always=True,
            empty_text="Nenhum ponto-chave identificado.",
        ),
        Field(
            "action_items",
            "Ações sugeridas",
            KIND_LIST,
            "passos práticos ou recomendações mencionados (lista vazia se nenhum); "
            "IGNORE pedidos de inscrição, curtida ou comentário",
            always=True,
            empty_text="Nenhuma ação identificada.",
        ),
        Field(
            "key_concepts",
            "Conceitos-chave",
            KIND_KEYVALUE,
            "conceitos abstratos ou técnicos centrais para entender o tema, formato "
            "obrigatório 'Termo: definição de uma linha'; Ex: 'Fermento químico: "
            "agente que libera CO2 durante o cozimento, tornando a massa mais leve'; "
            "(lista vazia se nenhum)",
        ),
        Field(
            "tools_mentioned",
            "Ferramentas mencionadas",
            KIND_LIST,
            "ferramentas, bibliotecas, plataformas ou tecnologias citadas "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "metrics",
            "Métricas e números",
            KIND_LIST,
            "números, estatísticas, durações, quantidades mencionadas com seu "
            "contexto (lista vazia se nenhuma)",
        ),
        Field(
            "quotes",
            "Citações notáveis",
            KIND_QUOTES,
            "até 5 frases marcantes ou citações quase literais do speaker que "
            "sintetizem bem uma ideia; inclua contexto mínimo entre parênteses se "
            "necessário; (lista vazia se nenhuma)",
        ),
        Field(
            "assumptions",
            "Premissas implícitas",
            KIND_LIST,
            "até 5 premissas implícitas que o speaker assume como verdade sem "
            "questionar; formule como afirmação, ex: 'O público já conhece os "
            "fundamentos de X'; (lista vazia se nenhuma)",
        ),
        Field(
            "vocabulary",
            "Vocabulário do nicho",
            KIND_KEYVALUE,
            "jargões, siglas ou termos de nicho usados pelo speaker, formato "
            "'Termo: definição inferida'; diferente de key_concepts — foco em "
            "linguagem específica do domínio/nicho; (lista vazia se nenhum)",
        ),
        Field(
            "sentiment_arc",
            "Arco de sentimento",
            KIND_PARAGRAPH,
            "UMA frase descrevendo como o tom evolui do início ao fim; ex: "
            "'Introdução técnica e expositiva → aprofundamento crítico → "
            "encerramento motivacional'",
        ),
    ),
)

LECTURE = AnalysisProfile(
    id="lecture",
    label="Aula",
    icon="SCHOOL_OUTLINED",
    persona="Você é um tutor que transforma aulas em material de estudo claro.",
    source_hint="transcrição de uma aula ou conteúdo educacional",
    temperature=0.3,
    fields=(
        Field(
            "summary",
            "Resumo",
            KIND_PARAGRAPH,
            f"3-5 frases com o que a aula ensina, no todo; {_IGNORE_CTA}",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "learning_objectives",
            "Objetivos de aprendizagem",
            KIND_LIST,
            "o que o aluno deve saber/fazer ao final; comece cada item com um verbo "
            "(compreender, calcular, aplicar...)",
        ),
        Field(
            "key_concepts",
            "Conceitos-chave",
            KIND_KEYVALUE,
            "formato 'Termo: definição clara de uma a duas linhas', em ordem didática",
        ),
        Field(
            "step_by_step",
            "Passo a passo",
            KIND_LIST,
            "se a aula ensina um procedimento, os passos em ordem; cada passo "
            "autoexplicativo. (lista vazia se não aplicável)",
        ),
        Field(
            "examples",
            "Exemplos",
            KIND_LIST,
            "exemplos concretos usados para ilustrar os conceitos. "
            "(lista vazia se nenhum)",
        ),
        Field(
            "formulas",
            "Fórmulas e regras",
            KIND_LIST,
            "fórmulas, leis ou regras enunciadas, com o que cada símbolo significa. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "common_mistakes",
            "Erros comuns",
            KIND_LIST,
            "equívocos/armadilhas que o professor alerta. (lista vazia se nenhum)",
        ),
        Field(
            "study_questions",
            "Perguntas de revisão",
            KIND_LIST,
            "3-7 perguntas que testam a compreensão do conteúdo (sem as respostas)",
        ),
        Field(
            "glossary",
            "Glossário",
            KIND_KEYVALUE,
            "termos técnicos do tema, formato 'Termo: definição'. "
            "(lista vazia se nenhum)",
        ),
    ),
)

INTERVIEW = AnalysisProfile(
    id="interview",
    label="Entrevista",
    icon="MIC_OUTLINED",
    persona="Você é um produtor de conteúdo que sintetiza conversas.",
    source_hint="transcrição de uma entrevista ou podcast",
    temperature=0.35,
    fields=(
        Field(
            "summary",
            "Resumo",
            KIND_PARAGRAPH,
            f"3-5 frases sobre o que foi conversado e os destaques; {_IGNORE_CTA}",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "participants",
            "Participantes",
            KIND_KEYVALUE,
            "formato 'Nome/papel: como contribui na conversa'. Se a transcrição não "
            "distinguir falantes, registre 'falantes não rotulados' e atribua no "
            "melhor esforço",
        ),
        Field(
            "main_topics",
            "Temas abordados",
            KIND_LIST,
            "os assuntos principais, na ordem em que surgem",
        ),
        Field(
            "positions",
            "Opiniões e posições",
            KIND_LIST,
            "posicionamentos defendidos; quando possível, atribua a quem "
            "('Fulano defende que...'). (lista vazia se nenhuma)",
        ),
        Field(
            "notable_quotes",
            "Frases marcantes",
            KIND_QUOTES,
            "até 6 falas quase literais que sintetizam bem uma ideia, com mínima "
            "atribuição. (lista vazia se nenhuma)",
        ),
        Field(
            "anecdotes",
            "Histórias e casos",
            KIND_LIST,
            "anedotas/relatos pessoais contados. (lista vazia se nenhum)",
        ),
        Field(
            "recommendations",
            "Recomendações",
            KIND_LIST,
            "livros, ferramentas, pessoas ou recursos citados como recomendação. "
            "(lista vazia se nenhum)",
        ),
        Field(
            "disagreements",
            "Divergências",
            KIND_LIST,
            "pontos de discordância ou tensão entre os participantes. "
            "(lista vazia se nenhum)",
        ),
    ),
)

TUTORIAL = AnalysisProfile(
    id="tutorial",
    label="Tutorial",
    icon="CHECKLIST",
    persona="Você é um redator técnico que documenta procedimentos.",
    source_hint="transcrição de um tutorial ou receita",
    temperature=0.2,
    fields=(
        Field(
            "goal",
            "Objetivo",
            KIND_PARAGRAPH,
            f"o que se constrói/alcança ao final, em uma a duas frases; {_IGNORE_CTA}",
        ),
        Field(
            "prerequisites",
            "Requisitos",
            KIND_LIST,
            "materiais, ingredientes, ferramentas ou conhecimentos prévios "
            "necessários. (lista vazia se nenhum)",
        ),
        Field(
            "steps",
            "Passo a passo",
            KIND_LIST,
            "os passos EM ORDEM, numerados implicitamente; cada passo é uma "
            "instrução acionável e completa; preserve quantidades/tempos citados",
        ),
        Field(
            "tips_warnings",
            "Dicas e avisos",
            KIND_LIST,
            "dicas, atalhos e advertências de segurança/erro. (lista vazia se nenhum)",
        ),
        Field(
            "common_mistakes",
            "Erros comuns",
            KIND_LIST,
            "o que costuma dar errado e como evitar. (lista vazia se nenhum)",
        ),
        Field(
            "expected_result",
            "Resultado esperado",
            KIND_PARAGRAPH,
            "como saber que deu certo (aparência, comportamento, métrica)",
        ),
        Field(
            "time_cost",
            "Tempo e custo",
            KIND_LIST,
            "tempo estimado, rendimento, custo ou dificuldade, se mencionados. "
            "(lista vazia se nenhum)",
        ),
    ),
)

PROFILES = (DEFAULT, LECTURE, INTERVIEW, TUTORIAL)
