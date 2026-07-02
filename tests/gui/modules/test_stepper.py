"""Unit tests for src/gui/modules/_stepper.py — stage chip highlighting."""

from __future__ import annotations

import flet as ft
import pytest

from src.gui.modules._stepper import build_stepper

_STAGES = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]


@pytest.mark.unit
def test_builds_one_chip_per_stage():
    row, _set_active = build_stepper(_STAGES)
    assert len(row.controls) == 3


@pytest.mark.unit
def test_set_active_highlights_current_and_checks_earlier():
    row, set_active = build_stepper(_STAGES)
    set_active("b")

    texts = [c.content for c in row.controls]
    assert texts[0].value == "✓ Alpha"
    assert texts[1].value == "Beta"
    assert texts[1].color == ft.Colors.PRIMARY
    assert texts[2].value == "Gamma"


@pytest.mark.unit
def test_set_active_none_resets_every_chip():
    row, set_active = build_stepper(_STAGES)
    set_active("c")
    set_active(None)

    texts = [c.content for c in row.controls]
    assert [t.value for t in texts] == ["Alpha", "Beta", "Gamma"]


@pytest.mark.unit
def test_set_active_unknown_key_resets_every_chip():
    row, set_active = build_stepper(_STAGES)
    set_active("a")
    set_active("not-a-stage")

    texts = [c.content for c in row.controls]
    assert [t.value for t in texts] == ["Alpha", "Beta", "Gamma"]
