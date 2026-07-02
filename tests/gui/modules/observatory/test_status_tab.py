"""Construct-smoke for the Observatório status tab.

Flet is not testable headless, so this builds the control with a MagicMock
page (catches __init__ errors an import-smoke misses) and exercises apply()'s
non-raising path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
import pytest

from src.gui.modules.observatory.status_tab import (
    _ollama_rows,
    _section_header,
    build_status_tab,
)


@pytest.mark.unit
def test_status_tab_builds():
    control, apply = build_status_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_does_not_raise(tmp_path, mocker):
    # domain_statuses() reads ml.store.model_dir() by default — isolate it so
    # the test never touches the real ~/.mill-tools/ml directory. ollama_
    # inventory() would otherwise hit the real local Ollama service.
    mocker.patch("src.core.ml.classify.model_dir", return_value=tmp_path)
    mocker.patch("src.core.observatory.status.ollama_inventory")
    control, apply = build_status_tab(MagicMock())
    apply()  # must not raise, even with every gate/domain in its default state


@pytest.mark.unit
def test_ollama_rows_lists_every_known_model_when_reachable():
    from src.core.observatory.status import OllamaInventoryStatus, OllamaModelStatus

    inventory = OllamaInventoryStatus(
        reachable=True,
        models=(
            OllamaModelStatus("gemma3-4b-custom", True),
            OllamaModelStatus("moondream-custom", False),
        ),
    )
    rows = _ollama_rows(inventory)
    assert len(rows) == 2


@pytest.mark.unit
def test_ollama_rows_shows_a_single_message_when_unreachable():
    from src.core.observatory.status import OllamaInventoryStatus

    rows = _ollama_rows(OllamaInventoryStatus(reachable=False, models=()))
    assert len(rows) == 1
    assert "não está acessível" in rows[0].value


@pytest.mark.unit
def test_section_header_without_help_returns_plain_label():
    header = _section_header("Sem ajuda", "chave.inexistente", MagicMock())
    assert isinstance(header, ft.Text)


@pytest.mark.unit
def test_section_header_with_help_returns_row_with_icon():
    header = _section_header("Gates e extras", "observatory.gates", MagicMock())
    assert isinstance(header, ft.Row)
    assert len(header.controls) == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "help_key",
    [
        "observatory.gates",
        "observatory.ollama",
        "observatory.classify",
        "observatory.config",
    ],
)
def test_all_sections_have_help_content(help_key):
    from src.gui.help_content import help_for, help_long_for

    assert help_for(help_key)  # tooltip text present
    assert help_long_for(help_key)  # modal text present too — all 3 are dense
