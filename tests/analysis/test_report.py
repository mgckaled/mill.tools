"""Unit tests for src/analysis/report.py."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _profile(fields, *, disclaimer=""):
    from src.analysis.types import AnalysisProfile

    return AnalysisProfile(
        id="p",
        label="P",
        icon="ARTICLE_OUTLINED",
        persona="Você é um analista.",
        source_hint="transcrição",
        fields=tuple(fields),
        disclaimer=disclaimer,
    )


def test_paragraph_and_list_and_quotes_and_keyvalue_render():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [
            Field("summary", "Resumo", "paragraph", "r"),
            Field("points", "Pontos", "list", "r"),
            Field("quotes", "Citações", "quotes", "r"),
            Field("glossary", "Glossário", "keyvalue", "r"),
        ]
    )
    analysis = {
        "summary": "Um resumo.",
        "points": ["Ponto um.", "Ponto dois."],
        "quotes": ["Frase marcante."],
        "glossary": ["Termo: definição."],
    }
    out = format_report(prof, analysis, Path("t.txt"))
    assert "## Resumo\n\nUm resumo." in out
    assert "## Pontos\n\n- Ponto um.\n- Ponto dois." in out
    assert "## Citações\n\n> Frase marcante." in out
    assert "## Glossário\n\n- Termo: definição." in out


def test_non_always_empty_field_is_omitted():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [
            Field("summary", "Resumo", "paragraph", "r"),
            Field("tools", "Ferramentas", "list", "r"),
        ]
    )
    out = format_report(prof, {"summary": "S", "tools": []}, Path("t.txt"))
    assert "## Ferramentas" not in out


def test_always_list_with_empty_text_shows_placeholder():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [
            Field(
                "action_items",
                "Ações sugeridas",
                "list",
                "r",
                always=True,
                empty_text="Nenhuma ação identificada.",
            ),
        ]
    )
    out = format_report(prof, {"action_items": []}, Path("t.txt"))
    assert "## Ações sugeridas\n\nNenhuma ação identificada." in out


def test_always_paragraph_empty_uses_empty_text():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [
            Field("summary", "Resumo", "paragraph", "r", always=True, empty_text="N/A"),
        ]
    )
    out = format_report(prof, {}, Path("t.txt"))
    assert "## Resumo\n\nN/A" in out


def test_disclaimer_rendered_at_top_before_first_section():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [Field("summary", "Resumo", "paragraph", "r")],
        disclaimer="⚠ Aviso de teste.",
    )
    out = format_report(prof, {"summary": "S"}, Path("t.txt"))
    assert "> ⚠ Aviso de teste." in out
    assert out.index("⚠ Aviso de teste.") < out.index("## Resumo")


def test_header_meta_and_transcription_appendix():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("summary", "Resumo", "paragraph", "r")])
    out = format_report(
        prof,
        {"summary": "S"},
        Path("video.txt"),
        video_meta={
            "title": "Título",
            "channel": "Canal",
            "duration": "01:00",
            "url": "https://yt/x",
        },
        transcription="CORPO COMPLETO",
    )
    assert "# Título" in out
    assert "**Canal:** Canal | **Duração:** 01:00" in out
    assert "[Assistir no YouTube](https://yt/x)" in out
    assert "## Transcrição\n\nCORPO COMPLETO" in out


def test_title_falls_back_to_stem():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("summary", "Resumo", "paragraph", "r")])
    out = format_report(prof, {"summary": "S"}, Path("meu_arquivo.txt"))
    assert "# Análise: meu_arquivo" in out
