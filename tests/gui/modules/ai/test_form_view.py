"""Unit tests for src/gui/modules/ai/form_view.py — the k (chunks retrieved
per question) selector (Fase 4, PLANO_CONVERSA_MULTITURNO.md).

Flet is not testable headless, so this builds the form with a MagicMock page
and drives it through the chip controls found in the tree — the same
traversal pattern tests/gui/modules/ai/test_view.py uses for the mode toggle.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _walk(control):
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                yield from _walk(c)
        elif child is not None and not isinstance(child, (str, bytes)):
            yield from _walk(child)


def _find_chip(control, label: str):
    """Find the clickable chip Container whose text content equals `label`."""
    for c in _walk(control):
        content = getattr(c, "content", None)
        if getattr(content, "value", None) == label and callable(
            getattr(c, "on_click", None)
        ):
            return c
    raise LookupError(f"no chip found for {label!r}")


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    import src.gui.settings as settings_mod

    cfg_dir = tmp_path / ".mill-tools"
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_dir / "config.json")


def _build_form():
    from src.gui.modules.ai.form_view import build_ai_form

    return build_ai_form(MagicMock(), on_ask=lambda: None)


@pytest.mark.unit
def test_get_k_defaults_to_six():
    form = _build_form()
    assert form.get_k() == 6


@pytest.mark.unit
def test_selecting_a_chip_updates_get_k_and_persists():
    import src.gui.settings as settings_mod

    form = _build_form()
    chip = _find_chip(form.control, "12")
    chip.on_click(MagicMock())

    assert form.get_k() == 12
    assert settings_mod.load()["last_ai_k"] == 12


@pytest.mark.unit
def test_k_selector_is_disabled_in_cli_mode():
    form = _build_form()

    _find_chip(form.control, "Comandos CLI").on_click(MagicMock())
    _find_chip(form.control, "8").on_click(MagicMock())

    assert form.get_k() == 6  # click ignored — the grid is disabled in CLI mode


@pytest.mark.unit
def test_k_selector_re_enables_when_switching_back_to_corpus():
    form = _build_form()

    _find_chip(form.control, "Comandos CLI").on_click(MagicMock())
    _find_chip(form.control, "Corpus").on_click(MagicMock())
    _find_chip(form.control, "8").on_click(MagicMock())

    assert form.get_k() == 8
