"""Tests for NL→CLI translation (LLM mocked via GenericFakeChatModel)."""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

_REF = "video trim <file> --start <TIME> [--end <TIME>] — Trim video to a time range"


def _fake_llm(*responses: str):
    """A real Runnable returning canned AIMessages, one per .invoke()."""
    return GenericFakeChatModel(
        messages=iter([AIMessage(content=r) for r in responses])
    )


def _ok(*_a, **_k) -> str | None:
    return None


@pytest.mark.unit
def test_to_command_parses_json_object_first_try():
    from src.core.text.nl2cli import to_command

    payload = json.dumps(
        {
            "command": "uv run main.py video trim a.mp4 --start 0:30",
            "explanation": "Corta o vídeo a partir dos 30s.",
        },
        ensure_ascii=False,
    )
    command, explanation = to_command(
        "corta o vídeo a.mp4 a partir dos 30 segundos",
        _REF,
        make_llm_fn=lambda *a, **k: _fake_llm(payload),
        validate_fn=_ok,
    )
    assert command == "uv run main.py video trim a.mp4 --start 0:30"
    assert explanation == "Corta o vídeo a partir dos 30s."


@pytest.mark.unit
def test_to_command_extracts_from_fenced_block():
    from src.core.text.nl2cli import to_command

    response = (
        "Claro! Aqui está:\n```json\n"
        '{"command": "uv run main.py audio a.wav --fmt mp3", "explanation": "ok"}\n```'
    )
    command, _explanation = to_command(
        "converte a.wav pra mp3",
        _REF,
        make_llm_fn=lambda *a, **k: _fake_llm(response),
        validate_fn=_ok,
    )
    assert command == "uv run main.py audio a.wav --fmt mp3"


@pytest.mark.unit
def test_to_command_tolerates_content_as_list_of_text_blocks():
    """Some providers (Gemini/tool-call-shaped responses) return resp.content
    as a list of blocks instead of a plain str (mirrors rag.chat.answer /
    nl2sql's tolerance for the same shape, via the shared extract_llm_text)."""
    from src.core.text.nl2cli import to_command

    payload = json.dumps(
        {"command": "uv run main.py library dedup-images", "explanation": "ok"}
    )
    llm = _fake_llm("placeholder")
    llm.messages = iter([AIMessage(content=[{"type": "text", "text": payload}])])

    command, explanation = to_command(
        "acha imagens duplicadas",
        _REF,
        make_llm_fn=lambda *a, **k: llm,
        validate_fn=_ok,
    )
    assert command == "uv run main.py library dedup-images"
    assert explanation == "ok"


@pytest.mark.unit
def test_to_command_returns_refusal_without_validating():
    from src.core.text.nl2cli import to_command

    payload = json.dumps(
        {"command": "", "explanation": "Isso não é uma tarefa da CLI."}
    )

    def _boom(_command: str) -> str | None:
        raise AssertionError("validate_fn must not run on a refusal")

    command, explanation = to_command(
        "qual a previsão do tempo?",
        _REF,
        make_llm_fn=lambda *a, **k: _fake_llm(payload),
        validate_fn=_boom,
    )
    assert command == ""
    assert explanation == "Isso não é uma tarefa da CLI."


@pytest.mark.unit
def test_to_command_retries_once_after_validation_failure():
    from src.core.text.nl2cli import to_command

    bad = json.dumps({"command": "uv run main.py video trim a.mp4", "explanation": "x"})
    good = json.dumps(
        {
            "command": "uv run main.py video trim a.mp4 --start 0:30",
            "explanation": "corrigido",
        }
    )

    def _validate(command: str) -> str | None:
        return (
            None
            if "--start" in command
            else "the following arguments are required: --start"
        )

    command, explanation = to_command(
        "corta o vídeo",
        _REF,
        make_llm_fn=lambda *a, **k: _fake_llm(bad, good),
        validate_fn=_validate,
    )
    assert command == "uv run main.py video trim a.mp4 --start 0:30"
    assert explanation == "corrigido"


@pytest.mark.unit
def test_to_command_raises_after_two_validation_failures():
    from src.core.text.nl2cli import NL2CLIError, to_command

    bad = json.dumps({"command": "uv run main.py video trim a.mp4", "explanation": "x"})

    def _always_fails(_command: str) -> str | None:
        return "the following arguments are required: --start"

    with pytest.raises(NL2CLIError):
        to_command(
            "corta o vídeo",
            _REF,
            make_llm_fn=lambda *a, **k: _fake_llm(bad, bad),
            validate_fn=_always_fails,
        )


@pytest.mark.unit
def test_to_command_retries_after_unparseable_first_response():
    from src.core.text.nl2cli import to_command

    good = json.dumps(
        {"command": "uv run main.py video trim a.mp4 --start 0:30", "explanation": "ok"}
    )
    command, _explanation = to_command(
        "corta o vídeo",
        _REF,
        make_llm_fn=lambda *a, **k: _fake_llm("desculpe, não entendi", good),
        validate_fn=_ok,
    )
    assert command == "uv run main.py video trim a.mp4 --start 0:30"


@pytest.mark.unit
def test_to_command_raises_after_two_unparseable_responses():
    from src.core.text.nl2cli import NL2CLIError, to_command

    with pytest.raises(NL2CLIError):
        to_command(
            "corta o vídeo",
            _REF,
            make_llm_fn=lambda *a, **k: _fake_llm(
                "desculpe, não entendi", "ainda não entendi"
            ),
            validate_fn=_ok,
        )


@pytest.mark.unit
def test_to_command_uses_the_given_model_and_zero_temperature():
    from src.core.text.nl2cli import to_command

    payload = json.dumps({"command": "uv run main.py ai index", "explanation": "ok"})
    seen: dict = {}

    def _spy_make_llm(model_name, temperature=None, **_k):
        seen["model_name"] = model_name
        seen["temperature"] = temperature
        return _fake_llm(payload)

    to_command(
        "reindexa o acervo",
        _REF,
        make_llm_fn=_spy_make_llm,
        model="qwen7b-custom",
        validate_fn=_ok,
    )
    assert seen == {"model_name": "qwen7b-custom", "temperature": 0.0}
