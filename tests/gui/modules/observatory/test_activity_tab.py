"""Construct-smoke + rendering for the Observatório activity feed tab."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.activity_tab import build_activity_tab


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
def test_activity_tab_builds():
    control, apply = build_activity_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_shows_empty_state_with_no_entries(mocker):
    mocker.patch(
        "src.gui.modules.observatory.activity_tab.load_activity", return_value=[]
    )
    control, apply = build_activity_tab(MagicMock())
    apply()
    texts = [getattr(c, "value", "") for c in _walk(control)]
    assert any("Nenhuma atividade" in str(t) for t in texts)


@pytest.mark.unit
def test_apply_renders_recent_entries(mocker):
    from src.core.observatory.activity import ActivityEntry

    entries = [
        ActivityEntry("data", "outliers_detected", "12 linhas atípicas", 100.0),
        ActivityEntry("library", "image_dedup", "3 grupos", 200.0),
    ]
    mocker.patch(
        "src.gui.modules.observatory.activity_tab.load_activity",
        return_value=entries,
    )
    control, apply = build_activity_tab(MagicMock())
    apply()
    texts = [getattr(c, "value", "") for c in _walk(control)]
    assert any("12 linhas atípicas" in str(t) for t in texts)
    assert any("3 grupos" in str(t) for t in texts)
