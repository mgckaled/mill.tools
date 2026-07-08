"""Unit tests for src/analysis/prompts.py."""

import pytest

pytestmark = pytest.mark.unit


def _profile():
    from src.analysis.types import AnalysisProfile, Field

    return AnalysisProfile(
        id="sample",
        label="Amostra",
        icon="ARTICLE_OUTLINED",
        persona="Você é um analista de teste.",
        source_hint="transcrição de teste",
        fields=(
            Field(key="summary", title="Resumo", kind="paragraph", rule="3-5 frases."),
            Field(key="points", title="Pontos", kind="list", rule="pontos principais."),
            Field(key="quotes", title="Citações", kind="quotes", rule="até 3 falas."),
            Field(
                key="glossary",
                title="Glossário",
                kind="keyvalue",
                rule="Termo: definição.",
            ),
        ),
        temperature=0.3,
    )


def _fake_llm(*responses: str):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def test_analysis_prompt_invokes_without_keyerror():
    """The generated JSON skeleton contains literal braces; if they were not
    escaped, ``chain.invoke`` would raise KeyError on the missing variables."""
    from src.analysis.prompts import build_analysis_prompt

    chain = build_analysis_prompt(_profile()) | _fake_llm('{"summary": "ok"}')
    out = chain.invoke({"text": "corpo da transcrição"})
    assert out.content == '{"summary": "ok"}'


def test_merge_prompt_invokes_without_keyerror():
    from src.analysis.prompts import build_merge_prompt

    chain = build_merge_prompt(_profile()) | _fake_llm('{"summary": "merged"}')
    out = chain.invoke({"analyses": "[{...}, {...}]"})
    assert out.content == '{"summary": "merged"}'


def test_analysis_prompt_input_variables_only_text():
    from src.analysis.prompts import build_analysis_prompt

    tmpl = build_analysis_prompt(_profile())
    assert tmpl.input_variables == ["text"]


def test_merge_prompt_input_variables_only_analyses():
    from src.analysis.prompts import build_merge_prompt

    tmpl = build_merge_prompt(_profile())
    assert tmpl.input_variables == ["analyses"]


def test_system_message_includes_every_field_key_and_rule():
    from src.analysis.prompts import build_analysis_prompt

    tmpl = build_analysis_prompt(_profile())
    system_text = tmpl.format_messages(text="x")[0].content
    for key in ("summary", "points", "quotes", "glossary"):
        assert key in system_text
    assert "3-5 frases." in system_text
    assert "Termo: definição." in system_text
    assert "Você é um analista de teste." in system_text
    assert "transcrição de teste" in system_text


def test_paragraph_skeleton_differs_from_list_skeleton():
    from src.analysis.prompts import build_analysis_prompt

    system_text = build_analysis_prompt(_profile()).format_messages(text="x")[0].content
    # paragraph -> "..."; list-like -> ["...", "..."]
    assert '"summary": "..."' in system_text
    assert '"points": ["...", "..."]' in system_text


# --- Fase 3 do PLANO_CORRECOES_SRC_ANALYSIS: refinos de prompt -------------


def test_analysis_prompt_warns_against_placeholder_echo():
    from src.analysis.prompts import build_analysis_prompt

    system_text = build_analysis_prompt(_profile()).format_messages(text="x")[0].content
    assert "Não copie os placeholders" in system_text


def test_merge_prompt_warns_against_placeholder_echo():
    from src.analysis.prompts import build_merge_prompt

    system_text = (
        build_merge_prompt(_profile()).format_messages(analyses="[]")[0].content
    )
    assert "Não copie os placeholders" in system_text


def test_merge_prompt_lists_always_fields_as_mandatory():
    from src.analysis.prompts import build_merge_prompt
    from src.analysis.types import AnalysisProfile, Field

    profile = AnalysisProfile(
        id="sample",
        label="Amostra",
        icon="ARTICLE_OUTLINED",
        persona="Você é um analista de teste.",
        source_hint="transcrição de teste",
        fields=(
            Field(
                key="summary",
                title="Resumo",
                kind="paragraph",
                rule="3-5 frases.",
                always=True,
                empty_text="N/A",
            ),
            Field(key="points", title="Pontos", kind="list", rule="pontos."),
        ),
    )
    system_text = build_merge_prompt(profile).format_messages(analyses="[]")[0].content
    assert "Nunca deixe os campos obrigatórios vazios: summary" in system_text


def test_merge_prompt_omits_mandatory_rule_when_no_always_fields():
    from src.analysis.prompts import build_merge_prompt

    system_text = (
        build_merge_prompt(_profile()).format_messages(analyses="[]")[0].content
    )
    assert "Nunca deixe os campos obrigatórios" not in system_text
