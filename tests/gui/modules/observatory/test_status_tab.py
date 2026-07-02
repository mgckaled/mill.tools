"""Construct-smoke for the Observatório status tab.

Flet is not testable headless, so this builds the control with a MagicMock
page (catches __init__ errors an import-smoke misses) and exercises apply()'s
non-raising path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.status_tab import build_status_tab


@pytest.mark.unit
def test_status_tab_builds():
    control, apply = build_status_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_does_not_raise(tmp_path, mocker):
    # domain_statuses() reads ml.store.model_dir() by default — isolate it so
    # the test never touches the real ~/.mill-tools/ml directory.
    mocker.patch("src.core.ml.classify.model_dir", return_value=tmp_path)
    control, apply = build_status_tab(MagicMock())
    apply()  # must not raise, even with every gate/domain in its default state


@pytest.mark.unit
def test_apply_routes_each_domain_to_its_own_section(tmp_path, mocker):
    """A single log with 3 domains must populate 3 separate table sections."""
    from src.core.observatory.model_timing import record_timing

    mocker.patch("src.core.ml.classify.model_dir", return_value=tmp_path)
    timings_path = tmp_path / "model_timings.json"
    mocker.patch(
        "src.core.observatory.model_timing._store_path", return_value=timings_path
    )

    record_timing("gemini-2.5-flash", "llm", 4.0, path=timings_path)
    record_timing("moondream-custom", "vlm", 2.0, path=timings_path)
    record_timing("nomic-embed-custom", "embed", 0.3, path=timings_path)

    control, apply = build_status_tab(MagicMock())
    apply()

    # control's timing sections are the last 3 children, in LLM/VLM/embed order.
    llm_control, vlm_control, embed_control = control.controls[-3:]
    assert llm_control.controls[2].controls[0].content.controls[0].content.value == (
        "gemini-2.5-flash"
    )
    assert vlm_control.controls[2].controls[0].content.controls[0].content.value == (
        "moondream-custom"
    )
    assert embed_control.controls[2].controls[0].content.controls[0].content.value == (
        "nomic-embed-custom"
    )
