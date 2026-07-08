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


def test_generated_at_override_is_deterministic():
    from datetime import datetime

    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("summary", "Resumo", "paragraph", "r")])
    out = format_report(
        prof,
        {"summary": "S"},
        Path("t.txt"),
        generated_at=datetime(2026, 1, 2, 3, 4),
    )
    assert "> Gerado em: 2026-01-02 03:04 | Fonte: `t.txt`" in out


def test_title_falls_back_to_stem():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("summary", "Resumo", "paragraph", "r")])
    out = format_report(prof, {"summary": "S"}, Path("meu_arquivo.txt"))
    assert "# Análise: meu_arquivo" in out


# --- Shape-drift tolerance (Fase 1 do PLANO_CORRECOES_SRC_ANALYSIS) --------


@pytest.mark.parametrize("kind", ["list", "quotes", "keyvalue"])
def test_string_where_list_expected_becomes_single_item_not_char_split(kind):
    """A bare string instead of a list must not be split character-by-character."""
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", kind, "r")])
    out = format_report(prof, {"items": "Uma frase só."}, Path("t.txt"))
    assert "Uma frase só." in out
    assert "- U\n- m\n- a" not in out
    assert "> U\n" not in out


def test_list_where_paragraph_expected_joins_instead_of_repr():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("summary", "Resumo", "paragraph", "r")])
    out = format_report(
        prof, {"summary": ["Primeira frase.", "Segunda frase."]}, Path("t.txt")
    )
    assert "Primeira frase.\n\nSegunda frase." in out
    assert "['Primeira frase.', 'Segunda frase.']" not in out


def test_dict_for_keyvalue_becomes_bullets_not_dropped():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("glossary", "Glossário", "keyvalue", "r")])
    out = format_report(
        prof, {"glossary": {"Termo": "Definição de uma linha."}}, Path("t.txt")
    )
    assert "- Termo: Definição de uma linha." in out


def test_empty_dict_for_keyvalue_is_treated_as_empty():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("glossary", "Glossário", "keyvalue", "r")])
    out = format_report(prof, {"glossary": {}}, Path("t.txt"))
    assert "## Glossário" not in out


def test_non_string_items_in_list_get_friendly_coercion():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", "list", "r")])
    out = format_report(
        prof,
        {"items": [{"termo": "Fermento", "definicao": "Agente levedante."}, "outro"]},
        Path("t.txt"),
    )
    assert "- Fermento: Agente levedante." in out
    assert "- outro" in out
    assert "{'termo'" not in out


def test_bare_scalar_where_list_expected_does_not_crash():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", "list", "r")])
    out = format_report(prof, {"items": 5}, Path("t.txt"))
    assert "- 5" in out


def test_quotes_multiline_prefixes_each_line():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("quotes", "Citações", "quotes", "r")])
    out = format_report(prof, {"quotes": ["linha um\nlinha dois"]}, Path("t.txt"))
    assert "> linha um" in out
    assert "> linha dois" in out


def test_double_leading_bullet_is_deduped():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", "list", "r")])
    out = format_report(prof, {"items": ["- já vem com bullet"]}, Path("t.txt"))
    assert "- já vem com bullet" in out
    assert "- - já vem com bullet" not in out


def test_blank_string_value_for_list_field_is_omitted_like_legacy():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", "list", "r")])
    out = format_report(prof, {"summary": "x", "items": "   "}, Path("t.txt"))
    assert "## Itens" not in out


@pytest.mark.parametrize("kind", ["list", "quotes", "keyvalue"])
def test_echoed_placeholder_items_are_dropped(kind):
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile([Field("items", "Itens", kind, "r")])
    out = format_report(prof, {"items": ["...", "Conteúdo real."]}, Path("t.txt"))
    assert "Conteúdo real." in out
    assert "..." not in out


def test_echoed_placeholder_paragraph_is_treated_as_blank():
    from src.analysis.report import format_report
    from src.analysis.types import Field

    prof = _profile(
        [Field("summary", "Resumo", "paragraph", "r", always=True, empty_text="N/A")]
    )
    out = format_report(prof, {"summary": "..."}, Path("t.txt"))
    assert "## Resumo\n\n" in out
    assert "..." not in out
