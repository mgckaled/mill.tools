"""
creative.py: Creative analysis profiles (literary criticism, …).

Interpretive profiles (higher temperature). No "ignore CTAs" rule — these target
literary/creative texts, not promotional video content.
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

LITERARY = AnalysisProfile(
    id="literary",
    label="Literatura",
    icon="MENU_BOOK_OUTLINED",
    persona="Você é um analista literário e crítico textual.",
    source_hint="transcrição de um texto literário (narrado ou lido)",
    temperature=0.55,
    fields=(
        Field(
            "summary",
            "Sinopse",
            KIND_PARAGRAPH,
            "3-5 frases resumindo o enredo/conteúdo sem revelar reviravoltas "
            "finais (evite spoilers do desfecho)",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "themes",
            "Temas centrais",
            KIND_LIST,
            "os temas e questões centrais da obra (amor, poder, identidade...); "
            "cada item explica COMO o tema aparece, não só o rótulo; "
            "mínimo 10 palavras",
        ),
        Field(
            "characters",
            "Personagens",
            KIND_KEYVALUE,
            "formato 'Nome: papel e arco'. Ex: 'Capitu: figura ambígua cujo olhar "
            "oblíquo sustenta a dúvida central da narrativa'. "
            "(lista vazia se não houver)",
        ),
        Field(
            "narrative_structure",
            "Estrutura narrativa",
            KIND_PARAGRAPH,
            "foco narrativo (1ª/3ª pessoa, narrador confiável?), tratamento do "
            "tempo (linear, flashback) e organização do enredo",
        ),
        Field(
            "style_tone",
            "Estilo e tom",
            KIND_PARAGRAPH,
            "registro (formal/coloquial), ritmo e tom predominante; cite recursos "
            "característicos do autor",
        ),
        Field(
            "literary_devices",
            "Figuras de linguagem",
            KIND_LIST,
            "metáforas, ironias, aliterações etc., cada uma com um exemplo curto "
            "do texto. (lista vazia se nenhuma)",
        ),
        Field(
            "symbolism",
            "Símbolos e motivos",
            KIND_LIST,
            "objetos/imagens recorrentes e o que representam. (lista vazia se nenhum)",
        ),
        Field(
            "setting",
            "Ambientação",
            KIND_PARAGRAPH,
            "tempo e espaço da narrativa e sua função no significado",
        ),
        Field(
            "notable_passages",
            "Passagens marcantes",
            KIND_QUOTES,
            "até 5 trechos quase literais esteticamente ou tematicamente "
            "significativos. (lista vazia se nenhum)",
        ),
        Field(
            "interpretation",
            "Leitura crítica",
            KIND_PARAGRAPH,
            "uma interpretação fundamentada do que a obra propõe; apresente como "
            "leitura possível, não como verdade única",
        ),
    ),
)

REVIEW = AnalysisProfile(
    id="review",
    label="Resenha",
    icon="RATE_REVIEW_OUTLINED",
    persona="Você é um crítico que escreve resenhas equilibradas.",
    source_hint=(
        "transcrição de uma resenha ou análise crítica "
        "(produto, livro, filme, ferramenta...)"
    ),
    temperature=0.4,
    fields=(
        Field(
            "subject",
            "Objeto",
            KIND_PARAGRAPH,
            "o que está sendo resenhado e o contexto, em 1-2 frases",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "verdict",
            "Veredito",
            KIND_PARAGRAPH,
            "a conclusão geral em 1-2 frases — recomenda ou não, e para quem",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "rating",
            "Nota / Selo",
            KIND_PARAGRAPH,
            "nota ou selo atribuído, se houver (ex.: '8/10', 'recomendado'); "
            "senão escreva 'sem nota explícita'",
        ),
        Field(
            "pros",
            "Pontos fortes",
            KIND_LIST,
            "aspectos positivos destacados, cada um concreto. (lista vazia se nenhum)",
        ),
        Field(
            "cons",
            "Pontos fracos",
            KIND_LIST,
            "críticas e limitações apontadas, cada uma concreta. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "comparisons",
            "Comparações",
            KIND_LIST,
            "alternativas/concorrentes citados e como se comparam. "
            "(lista vazia se nenhuma)",
        ),
        Field(
            "best_for",
            "Ideal para",
            KIND_LIST,
            "para quem/qual uso o objeto é mais indicado. (lista vazia se não dito)",
        ),
        Field(
            "notable_quotes",
            "Frases marcantes",
            KIND_QUOTES,
            "até 4 falas que sintetizam o juízo do crítico. (lista vazia se nenhuma)",
        ),
    ),
)

STORYTELLING = AnalysisProfile(
    id="storytelling",
    label="Narrativa",
    icon="AUTO_STORIES_OUTLINED",
    persona="Você é um roteirista que disseca a estrutura de histórias.",
    source_hint=(
        "transcrição de uma narrativa, roteiro ou conteúdo com arco narrativo"
    ),
    temperature=0.5,
    fields=(
        Field(
            "logline",
            "Logline",
            KIND_PARAGRAPH,
            "a história em 1-2 frases (quem quer o quê e qual o obstáculo)",
            always=True,
            empty_text="N/A",
        ),
        Field(
            "hook",
            "Gancho",
            KIND_PARAGRAPH,
            "como a abertura prende a atenção",
        ),
        Field(
            "arc",
            "Arco narrativo",
            KIND_LIST,
            "momentos-chave em ordem (início → conflito → virada → desfecho); "
            "cada item uma frase",
        ),
        Field(
            "characters",
            "Personagens e vozes",
            KIND_KEYVALUE,
            "formato 'Nome/papel: função na história'. (lista vazia se não houver)",
        ),
        Field(
            "conflict",
            "Conflito",
            KIND_PARAGRAPH,
            "a tensão central que move a narrativa",
        ),
        Field(
            "themes",
            "Temas",
            KIND_LIST,
            "ideias/mensagens sob a superfície. (lista vazia se nenhuma)",
        ),
        Field(
            "pacing",
            "Ritmo",
            KIND_PARAGRAPH,
            "como o ritmo varia e onde concentra tensão/alívio",
        ),
        Field(
            "takeaway",
            "Mensagem e payoff",
            KIND_PARAGRAPH,
            "o que fica ao final; a recompensa para quem acompanhou",
        ),
    ),
)

PROFILES = (LITERARY, REVIEW, STORYTELLING)
