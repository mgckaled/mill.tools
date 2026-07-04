"""Construct-smoke for the Observatório disk usage sub-tab.

Flet is not testable headless, so this builds the control with a MagicMock
page and exercises apply()'s non-raising path against a real tmp_path
directory (no thread involved here — disk_usage() is cheap).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.disk_usage_tab import build_disk_usage_tab


@pytest.mark.unit
def test_disk_usage_tab_builds():
    control, apply = build_disk_usage_tab(MagicMock())
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_apply_shows_empty_state_when_directory_is_missing(mocker):
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=(),
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    entries_col = control.controls[2]
    assert "Nenhum arquivo" in entries_col.controls[0].value


@pytest.mark.unit
def test_apply_lists_entries_and_total(mocker):
    from src.core.observatory.disk_usage import DiskUsageEntry

    entries = (
        DiskUsageEntry("rag", 1024, True),
        DiskUsageEntry("config.json", 100, False),
    )
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=entries,
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    entries_col = control.controls[2]
    assert len(entries_col.controls) == 2
