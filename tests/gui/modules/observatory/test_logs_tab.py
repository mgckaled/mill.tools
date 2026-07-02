"""Construct-smoke + rendering for the Observatório failure-log feed tab."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.logs_tab import build_logs_tab


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
def test_logs_tab_builds():
    control, apply = build_logs_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_shows_empty_state_with_no_entries(mocker):
    mocker.patch("src.gui.modules.observatory.logs_tab.load_logs", return_value=[])
    control, apply = build_logs_tab(MagicMock())
    apply()
    texts = [getattr(c, "value", "") for c in _walk(control)]
    assert any("Nenhuma falha" in str(t) for t in texts)


@pytest.mark.unit
def test_apply_renders_recent_entries(mocker):
    from src.core.observatory.logs import LogEntry

    entries = [
        LogEntry("audio", "convert", "ffmpeg not found", 100.0),
        LogEntry("image", "resize", "invalid dimensions", 200.0),
    ]
    mocker.patch("src.gui.modules.observatory.logs_tab.load_logs", return_value=entries)
    control, apply = build_logs_tab(MagicMock())
    apply()
    texts = [getattr(c, "value", "") for c in _walk(control)]
    assert any("ffmpeg not found" in str(t) for t in texts)
    assert any("invalid dimensions" in str(t) for t in texts)
