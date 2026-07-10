"""Unit tests for src/core/rag/condense.py — query condensation contracts.

``condense_query`` takes ``make_llm_fn`` as an injectable default parameter
(mirrors ``nl2cli.to_command``'s shape) — the default is bound to the real
``make_llm`` at *function definition* time, so ``mocker.patch.object(condense,
"make_llm", ...)`` would silently miss any call that doesn't pass
``make_llm_fn`` explicitly (a real default-argument gotcha, not a mocking
convention choice). Every test below passes ``make_llm_fn`` directly, the same
way ``tests/core/text/test_nl2cli.py`` does for the same shape.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


def _fake_llm(*responses: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


@pytest.mark.unit
def test_condense_skips_llm_when_history_is_empty():
    from src.core.rag import condense

    calls: list[tuple] = []

    def _spy_make_llm(*a, **k):
        calls.append((a, k))
        return _fake_llm("não deveria ser usado")

    result = condense.condense_query("primeira pergunta?", [], _spy_make_llm)

    assert result == "primeira pergunta?"
    assert calls == []


@pytest.mark.unit
def test_condense_rewrites_using_history():
    from src.core.rag import condense

    history = [
        condense.Turn(
            question="Fala sobre xadrez.",
            answer="Xadrez é um jogo de tabuleiro [1].",
            sources=("output/transcriptions/text/xadrez.txt",),
        )
    ]

    result = condense.condense_query(
        "e quais as regras?",
        history,
        lambda *a, **k: _fake_llm("Quais as regras do xadrez?"),
    )

    assert result == "Quais as regras do xadrez?"


@pytest.mark.unit
def test_fmt_history_uses_source_stems_not_full_filenames():
    """The rendered history must carry the previous turn's source *stems*
    (no extension) — that's what lets the model resolve "esse vídeo" to the
    real document name, per the contextual-header synergy in the plan."""
    from src.core.rag.condense import Turn, _fmt_history

    text = _fmt_history(
        [
            Turn(
                question="do que fala o vídeo?",
                answer="Fala sobre RAG [1].",
                sources=("output/video/source/palestra_rag.mp4",),
            )
        ]
    )

    assert "palestra_rag" in text
    assert "palestra_rag.mp4" not in text


@pytest.mark.unit
def test_condense_falls_back_to_raw_question_on_llm_failure():
    from src.core.rag import condense

    def _raise(*_a, **_k):
        raise RuntimeError("Ollama indisponível")

    history = [condense.Turn(question="q1", answer="a1", sources=())]

    result = condense.condense_query("pergunta de acompanhamento", history, _raise)

    assert result == "pergunta de acompanhamento"


@pytest.mark.unit
def test_condense_falls_back_when_model_returns_empty_string():
    from src.core.rag import condense

    history = [condense.Turn(question="q1", answer="a1", sources=())]

    result = condense.condense_query(
        "pergunta de acompanhamento", history, lambda *a, **k: _fake_llm("")
    )

    assert result == "pergunta de acompanhamento"


@pytest.mark.unit
def test_condense_strips_surrounding_quotes():
    from src.core.rag import condense

    history = [condense.Turn(question="q1", answer="a1", sources=())]

    result = condense.condense_query(
        "acompanhamento",
        history,
        lambda *a, **k: _fake_llm('"pergunta reescrita entre aspas"'),
        model="gemma3-4b-custom",
    )

    assert result == "pergunta reescrita entre aspas"


@pytest.mark.unit
def test_condense_passes_configured_model_and_low_temperature():
    """Condensation always runs locally at a low (deterministic) temperature,
    regardless of the model chosen for the final answer."""
    from src.core.rag import condense

    calls: list[tuple] = []

    def _spy_make_llm(model_name, temperature=None, *a, **k):
        calls.append((model_name, temperature))
        return _fake_llm("pergunta reescrita")

    history = [condense.Turn(question="q1", answer="a1", sources=())]
    condense.condense_query(
        "acompanhamento", history, _spy_make_llm, model="gemma3-1b-custom"
    )

    assert calls == [("gemma3-1b-custom", 0.0)]


@pytest.mark.unit
def test_fmt_history_marks_turns_without_sources():
    from src.core.rag.condense import Turn, _fmt_history

    text = _fmt_history([Turn(question="q1", answer="a1", sources=())])

    assert "(nenhuma)" in text
