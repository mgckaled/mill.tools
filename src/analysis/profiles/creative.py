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

PROFILES = (LITERARY,)
