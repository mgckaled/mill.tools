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
