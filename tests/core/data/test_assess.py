"""Tests for the IA data-quality assessment + its on-disk cache.

The LLM is mocked with ``GenericFakeChatModel`` (a real Runnable), so the
``prompt | llm`` chain validates and runs without Ollama.
"""

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str):
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


@pytest.mark.unit
def test_assess_invokes_chain_and_returns_markdown():
    from src.core.data import assess

    out = assess.assess(
        schema="vendas (3 linhas): produto VARCHAR, valor VARCHAR",
        profile_text="valor: VARCHAR · 0 nulos",
        sample_text="produto,valor\nmaca,R$ 1,50",
        make_llm_fn=lambda *a, **k: _fake_llm("- coluna valor é texto\n- consistente"),
    )
    assert "coluna valor é texto" in out


@pytest.mark.unit
def test_assess_prompt_has_no_unescaped_braces():
    from src.core.data.assess import build_assessment_prompt

    # The template fills schema/profile/sample; passing a value that contains
    # braces must not raise (values are never re-parsed for placeholders).
    prompt = build_assessment_prompt()
    msgs = prompt.format_messages(
        schema="t (1): meta STRUCT(x INT)",
        profile="meta: STRUCT",
        sample='{"meta": {"x": 10}}',  # braces in a value — safe
    )
    assert any("STRUCT" in m.content for m in msgs)


@pytest.mark.unit
def test_assessment_cache_round_trip(tmp_path):
    from src.core.data import assess

    src = tmp_path / "vendas.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    cache = tmp_path / "cache.json"

    assert assess.load_cached_assessment(src, cache_file=cache) is None
    assess.save_assessment(src, "## Avaliação\nok", cache_file=cache)
    assert assess.load_cached_assessment(src, cache_file=cache) == "## Avaliação\nok"


@pytest.mark.unit
def test_assessment_cache_invalidated_on_mtime_change(tmp_path):
    import os

    from src.core.data import assess

    src = tmp_path / "vendas.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    cache = tmp_path / "cache.json"
    assess.save_assessment(src, "antigo", cache_file=cache)

    # Bump the file's mtime → the cached entry is considered stale.
    future = os.stat(src).st_mtime + 1000
    os.utime(src, (future, future))
    assert assess.load_cached_assessment(src, cache_file=cache) is None


@pytest.mark.unit
def test_assessment_cache_tolerates_malformed_file(tmp_path):
    from src.core.data import assess

    cache = tmp_path / "cache.json"
    cache.write_text("not json at all", encoding="utf-8")
    src = tmp_path / "x.csv"
    src.write_text("a\n1\n", encoding="utf-8")
    # A corrupt cache must not raise — just behaves as a cache miss.
    assert assess.load_cached_assessment(src, cache_file=cache) is None


@pytest.mark.unit
def test_save_assessment_missing_file_is_noop(tmp_path):
    from src.core.data import assess

    cache = tmp_path / "cache.json"
    # Saving for a nonexistent source cannot stamp an mtime → silently skips.
    assess.save_assessment(tmp_path / "ghost.csv", "x", cache_file=cache)
    assert not cache.exists()
