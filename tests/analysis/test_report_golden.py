"""Golden test for the default profile's Markdown report.

``report.py``'s docstring promises this generator reproduces the historical
report byte-for-byte for well-formed input. ``EXPECTED`` was captured from
``format_report`` *before* the Fase 1 normalizer (docs/plans/active/
PLANO_CORRECOES_SRC_ANALYSIS.md) touched rendering, with ``datetime.now()``
frozen for determinism. Any phase of that plan must keep this test green —
it is the only mechanical guard that the happy path is untouched by the
shape-drift tolerance added around it.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

_ANALYSIS = {
    "summary": "Um resumo abrangente do conteúdo apresentado no vídeo.",
    "key_points": [
        "O primeiro ponto-chave explica um conceito central com detalhe suficiente.",
        "O segundo ponto-chave reforça uma aplicação prática do tema discutido.",
    ],
    "action_items": [
        "Revisar a documentação oficial antes de aplicar a técnica.",
        "Praticar o exercício proposto ao final do vídeo.",
    ],
    "key_concepts": [
        "Fermentação: processo bioquímico que libera CO2 durante o preparo.",
        "Emulsificação: técnica que homogeneíza líquidos imiscíveis.",
    ],
    "tools_mentioned": ["Batedeira planetária", "Termômetro culinário"],
    "metrics": ["200°C de temperatura do forno", "35 minutos de cozimento"],
    "quotes": [
        "A paciência é o ingrediente mais subestimado da cozinha.",
        "Errar a receita uma vez é normal; errar sempre é falta de atenção.",
    ],
    "assumptions": ["O espectador já sabe operar um forno doméstico comum."],
    "vocabulary": ["Sova: ato de trabalhar a massa manualmente até ficar elástica."],
    "sentiment_arc": (
        "Introdução didática → aprofundamento técnico → encerramento motivacional."
    ),
}

_VIDEO_META = {
    "title": "Como Fazer Pão Caseiro",
    "channel": "Canal Cozinha",
    "duration": "15:32",
    "url": "https://youtube.com/watch?v=abc123",
}

_TRANSCRIPTION = "Corpo completo da transcrição de exemplo."

_EXPECTED = "# Como Fazer Pão Caseiro\n\n**Canal:** Canal Cozinha | **Duração:** 15:32\n[Assistir no YouTube](https://youtube.com/watch?v=abc123)\n\n> Gerado em: 2026-07-08 12:00 | Fonte: `transcricao_pao_caseiro.txt`\n\n---\n\n## Resumo\n\nUm resumo abrangente do conteúdo apresentado no vídeo.\n\n## Pontos-chave\n\n- O primeiro ponto-chave explica um conceito central com detalhe suficiente.\n- O segundo ponto-chave reforça uma aplicação prática do tema discutido.\n\n## Ações sugeridas\n\n- Revisar a documentação oficial antes de aplicar a técnica.\n- Praticar o exercício proposto ao final do vídeo.\n\n## Conceitos-chave\n\n- Fermentação: processo bioquímico que libera CO2 durante o preparo.\n- Emulsificação: técnica que homogeneíza líquidos imiscíveis.\n\n## Ferramentas mencionadas\n\n- Batedeira planetária\n- Termômetro culinário\n\n## Métricas e números\n\n- 200°C de temperatura do forno\n- 35 minutos de cozimento\n\n## Citações notáveis\n\n> A paciência é o ingrediente mais subestimado da cozinha.\n\n> Errar a receita uma vez é normal; errar sempre é falta de atenção.\n\n\n## Premissas implícitas\n\n- O espectador já sabe operar um forno doméstico comum.\n\n## Vocabulário do nicho\n\n- Sova: ato de trabalhar a massa manualmente até ficar elástica.\n\n## Arco de sentimento\n\nIntrodução didática → aprofundamento técnico → encerramento motivacional.\n\n---\n\n## Transcrição\n\nCorpo completo da transcrição de exemplo.\n"


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 8, 12, 0)


def test_default_profile_report_matches_legacy_byte_for_byte():
    from src.analysis import format_report, get_profile

    with patch("src.analysis.report.datetime", _FixedDatetime):
        out = format_report(
            get_profile("default"),
            _ANALYSIS,
            Path("transcricao_pao_caseiro.txt"),
            _VIDEO_META,
            _TRANSCRIPTION,
        )
    assert out == _EXPECTED
