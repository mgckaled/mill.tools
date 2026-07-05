"""Tests for NL→SQL translation (LLM mocked via GenericFakeChatModel)."""

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str):
    """A real Runnable returning canned AIMessages, one per .invoke()."""
    msgs = iter([AIMessage(content=r) for r in responses])
    return GenericFakeChatModel(messages=msgs)


@pytest.mark.unit
def test_to_sql_parses_json_object():
    from src.core.data.nl2sql import to_sql

    payload = json.dumps(
        {"sql": "SELECT produto FROM vendas", "explicacao": "Lista os produtos."},
        ensure_ascii=False,
    )
    sql, explanation = to_sql(
        "vendas (3 linhas): produto VARCHAR",
        "quais produtos existem?",
        make_llm_fn=lambda *a, **k: _fake_llm(payload),
    )
    assert sql == "SELECT produto FROM vendas"
    assert explanation == "Lista os produtos."


@pytest.mark.unit
def test_to_sql_extracts_from_fenced_block():
    from src.core.data.nl2sql import to_sql

    response = (
        "Claro! Aqui está:\n```json\n"
        '{"sql": "SELECT 1 FROM vendas", "explicacao": "ok"}\n```'
    )
    sql, explanation = to_sql(
        "vendas: a INT",
        "pergunta",
        make_llm_fn=lambda *a, **k: _fake_llm(response),
    )
    assert sql == "SELECT 1 FROM vendas"


@pytest.mark.unit
def test_to_sql_accepts_fenced_sql_without_json():
    """Regression: a fenced ```sql block with no JSON wrapper must not raise.

    _extract_payload's bare-SQL fallback used to grab candidates[1] (the raw
    text with the surrounding fences/prose) instead of candidates[0] (the
    fenced block's actual content), so this exact shape always raised
    NL2SQLError even though it is the case the fallback exists for.
    """
    from src.core.data.nl2sql import to_sql

    response = "Aqui está a consulta:\n```sql\nSELECT a FROM vendas\n```"
    sql, explanation = to_sql(
        "vendas: a INT",
        "pergunta",
        make_llm_fn=lambda *a, **k: _fake_llm(response),
    )
    assert sql == "SELECT a FROM vendas"
    assert explanation == ""


@pytest.mark.unit
def test_to_sql_accepts_bare_sql_fallback():
    from src.core.data.nl2sql import to_sql

    sql, explanation = to_sql(
        "vendas: a INT",
        "pergunta",
        make_llm_fn=lambda *a, **k: _fake_llm("SELECT a FROM vendas"),
    )
    assert sql == "SELECT a FROM vendas"
    assert explanation == ""


@pytest.mark.unit
def test_to_sql_rejects_non_select_output():
    from src.core.data.nl2sql import to_sql
    from src.core.data.validate import UnsafeQueryError

    payload = json.dumps({"sql": "DELETE FROM vendas", "explicacao": "x"})
    with pytest.raises(UnsafeQueryError):
        to_sql(
            "vendas: a INT",
            "apague tudo",
            make_llm_fn=lambda *a, **k: _fake_llm(payload),
        )


@pytest.mark.unit
def test_to_sql_tolerates_content_as_list_of_text_blocks():
    """Some providers (Gemini/tool-call-shaped responses) return resp.content
    as a list of blocks instead of a plain str; to_sql must still parse it
    (mirrors rag.chat.answer's tolerance for the same shape)."""
    from src.core.data.nl2sql import to_sql

    payload = json.dumps({"sql": "SELECT 1 FROM vendas", "explicacao": "ok"})
    llm = _fake_llm("placeholder")
    llm.messages = iter([AIMessage(content=[{"type": "text", "text": payload}])])

    sql, explanation = to_sql(
        "vendas: a INT", "pergunta", make_llm_fn=lambda *a, **k: llm
    )
    assert sql == "SELECT 1 FROM vendas"
    assert explanation == "ok"


@pytest.mark.unit
def test_to_sql_unparseable_output_raises():
    from src.core.data.nl2sql import NL2SQLError, to_sql

    with pytest.raises(NL2SQLError):
        to_sql(
            "vendas: a INT",
            "pergunta",
            make_llm_fn=lambda *a, **k: _fake_llm("desculpe, não entendi"),
        )
