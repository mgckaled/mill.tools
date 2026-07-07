"""Construct-smoke for the AI hub module (Conversa + Comandos CLI, Fase 3).

Flet is not testable headless, so this builds the control with a MagicMock
page and exercises the mode toggle / lifecycle without a live UI. External
reads (embedder, RAG stats, Ollama inventory) are mocked so no Ollama/network
call happens during the test.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _walk(control):
    """Yield a control and its descendants (best-effort, for smoke assertions)."""
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                yield from _walk(c)
        elif child is not None and not isinstance(child, (str, bytes)):
            yield from _walk(child)


def _find_clickable_by_text(control, text: str):
    """Find the clickable ancestor whose `.content` is (or wraps) `text`."""
    for c in _walk(control):
        content = getattr(c, "content", None)
        if content == text:
            return c
        if getattr(content, "value", None) == text and callable(
            getattr(c, "on_click", None)
        ):
            return c
    raise LookupError(f"no clickable control found for {text!r}")


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    import src.gui.settings as settings_mod

    cfg_dir = tmp_path / ".mill-tools"
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_dir / "config.json")


@pytest.fixture(autouse=True)
def isolate_reads(mocker, tmp_path):
    """Mount/mode-switch spawn background reads — keep them off real Ollama/disk."""
    mocker.patch("src.core.rag.embedder.is_available", return_value=True)
    mocker.patch("src.core.rag.indexer.index_dir", return_value=tmp_path / "rag")
    mocker.patch(
        "src.core.observatory.status.ollama_inventory",
        return_value=MagicMock(reachable=True),
    )


def _build_module():
    from src.gui.modules.ai.view import build_ai_module

    return build_ai_module(
        MagicMock(), MagicMock(), MagicMock(), [False], [MagicMock()]
    )


@pytest.mark.unit
def test_ai_module_builds_and_mounts():
    module = _build_module()
    assert module.id == "ai"
    module.on_mount({})  # must not raise


@pytest.mark.unit
def test_corpus_session_is_visible_by_default():
    module = _build_module()
    module.on_mount({})
    panel = module.control.controls[2].content
    session_stack = panel.controls[-1]
    answer_area, command_area = session_stack.controls
    assert answer_area.visible is True
    assert command_area.visible is False


@pytest.mark.unit
def test_switching_to_cli_mode_swaps_the_session_area():
    module = _build_module()
    module.on_mount({})

    cli_chip = _find_clickable_by_text(module.control, "Comandos CLI")
    cli_chip.on_click(MagicMock())

    panel = module.control.controls[2].content
    session_stack = panel.controls[-1]
    answer_area, command_area = session_stack.controls
    assert answer_area.visible is False
    assert command_area.visible is True


@pytest.mark.unit
def test_switching_back_to_corpus_restores_the_answer_session():
    module = _build_module()
    module.on_mount({})

    _find_clickable_by_text(module.control, "Comandos CLI").on_click(MagicMock())
    _find_clickable_by_text(module.control, "Corpus").on_click(MagicMock())

    panel = module.control.controls[2].content
    session_stack = panel.controls[-1]
    answer_area, command_area = session_stack.controls
    assert answer_area.visible is True
    assert command_area.visible is False


@pytest.mark.unit
def test_ask_button_dispatches_to_command_flow_in_cli_mode(mocker):
    mocker.patch(
        "src.gui.modules.ai.view.spinner",
        return_value=(MagicMock(), lambda: None, lambda: None),
    )
    start_mock = mocker.patch("src.gui.modules.ai.command_view.start_ai_command")
    module = _build_module()
    module.on_mount({})

    _find_clickable_by_text(module.control, "Comandos CLI").on_click(MagicMock())

    form = module.control.controls[0].content
    question_field = next(
        c for c in _walk(form) if getattr(c, "label", None) == "Pergunta"
    )
    question_field.value = "corta o silêncio do podcast.mp3"

    ask_btn = next(c for c in _walk(form) if getattr(c, "content", None) == "Perguntar")
    ask_btn.on_click(MagicMock())

    start_mock.assert_called_once()


@pytest.mark.unit
def test_ask_button_dispatches_to_answer_flow_in_corpus_mode(mocker):
    mocker.patch(
        "src.gui.modules.ai.view.spinner",
        return_value=(MagicMock(), lambda: None, lambda: None),
    )
    start_mock = mocker.patch("src.gui.modules.ai.answer_view.start_ai_answer")
    module = _build_module()
    module.on_mount({})

    form = module.control.controls[0].content
    question_field = next(
        c for c in _walk(form) if getattr(c, "label", None) == "Pergunta"
    )
    question_field.value = "o que eu falei sobre X?"

    ask_btn = next(c for c in _walk(form) if getattr(c, "content", None) == "Perguntar")
    ask_btn.on_click(MagicMock())

    start_mock.assert_called_once()


@pytest.mark.unit
def test_persisted_cli_mode_is_restored_on_mount():
    import src.gui.settings as settings_mod

    settings_mod.set("last_ai_mode", "cli")

    module = _build_module()
    module.on_mount({})

    panel = module.control.controls[2].content
    session_stack = panel.controls[-1]
    answer_area, command_area = session_stack.controls
    assert answer_area.visible is False
    assert command_area.visible is True
