"""Construct-smoke for the Observatório timing tab.

Flet is not testable headless, so this builds the control with a MagicMock
page (catches __init__ errors an import-smoke misses) and exercises apply()'s
non-raising path plus domain routing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.timing_tab import build_timing_tab


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


@pytest.mark.unit
def test_timing_tab_builds():
    control, apply = build_timing_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_does_not_raise_with_empty_log(tmp_path, mocker):
    mocker.patch(
        "src.core.observatory.model_timing._store_path",
        return_value=tmp_path / "model_timings.json",
    )
    control, apply = build_timing_tab(MagicMock())
    apply()  # must not raise with no timing data recorded yet


@pytest.mark.unit
def test_apply_routes_each_domain_to_its_own_section(tmp_path, mocker):
    """A single log with 3 domains must populate 3 separate table sections."""
    from src.core.observatory.model_timing import record_timing

    timings_path = tmp_path / "model_timings.json"
    mocker.patch(
        "src.core.observatory.model_timing._store_path", return_value=timings_path
    )

    record_timing("gemini-2.5-flash", "llm", 4.0, path=timings_path)
    record_timing("moondream-custom", "vlm", 2.0, path=timings_path)
    record_timing("nomic-embed-custom", "embed", 0.3, path=timings_path)

    control, apply = build_timing_tab(MagicMock())
    apply()

    # control's children are the 3 sections, in LLM/VLM/embed order.
    llm_control, vlm_control, embed_control = control.controls

    def _texts(section):
        return [getattr(c, "value", "") for c in _walk(section)]

    assert "gemini-2.5-flash" in _texts(llm_control)
    assert "moondream-custom" in _texts(vlm_control)
    assert "nomic-embed-custom" in _texts(embed_control)
