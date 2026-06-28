"""Construct-smoke + behavior for the Library semantic map panel (Plano 4A).

Flet is not testable headless, so this builds the panel with a MagicMock page
(construct-smoke catches __init__ errors that an import-smoke misses) and drives
the non-rendering branches of ``refresh`` (gates / empty index), which do not
need sklearn or matplotlib.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.library.semantic_map_panel import build_semantic_map_panel


@pytest.mark.unit
def test_panel_builds():
    panel, refresh = build_semantic_map_panel(MagicMock())
    assert panel is not None
    assert callable(refresh)


@pytest.mark.unit
def test_refresh_hint_when_ml_missing(mocker):
    panel, refresh = build_semantic_map_panel(MagicMock())
    mocker.patch("src.core.ml.deps.is_available", return_value=False)
    refresh()  # gate path: must not raise and must not render a map
    # The map image stays hidden; the status carries the setup hint.
    assert any(
        getattr(c, "value", "") and "indisponível" in str(getattr(c, "value", ""))
        for c in _walk(panel)
    )


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
def test_refresh_hint_when_index_empty(tmp_path, monkeypatch, mocker):
    import src.core.rag.indexer as indexer

    panel, refresh = build_semantic_map_panel(MagicMock())
    mocker.patch("src.core.ml.deps.is_available", return_value=True)
    mocker.patch("src.gui.modules._charts.extras_available", return_value=True)
    monkeypatch.setattr(indexer, "index_dir", lambda: tmp_path / "empty")
    refresh()  # empty index → status set, no render, no raise
