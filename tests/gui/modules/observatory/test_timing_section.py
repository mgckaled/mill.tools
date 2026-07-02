"""Construct-smoke + apply() behavior for the reusable per-domain timing section.

Flet is not testable headless, so this builds the control directly (no page
needed — build_timing_section takes none) and exercises apply()'s effect on
the section's own controls (body rows, chart visibility) without a live UI.
"""

from __future__ import annotations

import pytest

from src.core.rag.analytics import ModelTiming
from src.gui.modules.observatory.timing_section import (
    _model_cell,
    build_timing_section,
)


@pytest.mark.unit
def test_build_timing_section_returns_control_and_apply():
    section = build_timing_section("LLM (texto)", show_chart=True)
    assert section.control is not None
    assert callable(section.apply)


@pytest.mark.unit
def test_apply_with_no_timings_shows_empty_state():
    section = build_timing_section("Embedder", show_chart=False)
    section.apply(())  # must not raise with an empty tuple
    body = section.control.controls[2]  # [section_label, header, body]
    assert len(body.controls) == 1  # the "nenhuma resposta" placeholder row


@pytest.mark.unit
def test_apply_with_timings_populates_one_row_per_model():
    section = build_timing_section("LLM (texto)", show_chart=True)
    timings = (
        ModelTiming(model="gemini-2.5-flash", count=3, mean=4.0, median=3.5, p90=5.0),
        ModelTiming(model="glm-4.7-flash", count=1, mean=6.0, median=6.0, p90=6.0),
    )
    section.apply(timings)
    body = section.control.controls[2]
    assert len(body.controls) == 2


@pytest.mark.unit
def test_show_chart_false_omits_chart_controls():
    section = build_timing_section("Embedder", show_chart=False)
    # Only [section_label, header, body] — no chart/chart_note appended.
    assert len(section.control.controls) == 3


@pytest.mark.unit
def test_show_chart_true_adds_chart_controls():
    section = build_timing_section("LLM (texto)", show_chart=True)
    # [section_label, header, body, chart, chart_note]
    assert len(section.control.controls) == 5


@pytest.mark.unit
def test_model_cell_shows_cloud_icon_for_a_cloud_model():
    cell = _model_cell("gemini-2.5-flash")
    row = cell.content
    assert len(row.controls) == 2  # icon + text
    assert row.controls[1].value == "gemini-2.5-flash"


@pytest.mark.unit
def test_model_cell_omits_cloud_icon_for_a_local_model():
    cell = _model_cell("gemma3-4b-custom")
    row = cell.content
    assert len(row.controls) == 1  # text only, no icon
    assert row.controls[0].value == "gemma3-4b-custom"


@pytest.mark.unit
def test_apply_without_chart_extras_shows_setup_hint(mocker):
    mocker.patch(
        "src.gui.modules.observatory.timing_section._charts.extras_available",
        return_value=False,
    )
    section = build_timing_section("LLM (texto)", show_chart=True)
    timings = (
        ModelTiming(model="gemini-2.5-flash", count=1, mean=1.0, median=1.0, p90=1.0),
    )
    section.apply(timings)
    chart, chart_note = section.control.controls[3], section.control.controls[4]
    assert chart.visible is False
    assert chart_note.visible is True
    assert chart_note.value  # setup hint text, non-empty
