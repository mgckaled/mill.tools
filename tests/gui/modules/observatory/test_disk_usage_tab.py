"""Construct-smoke for the Observatório disk usage sub-tab.

Flet is not testable headless, so this builds the control with a MagicMock
page and exercises apply()'s non-raising path against a real tmp_path
directory (no thread involved here — disk_usage() is cheap).

``build_disk_usage_tab`` returns a ``ft.Container`` (extra right padding so
the scrollbar doesn't crowd the right-aligned size values) wrapping the real
``ft.Column`` body — tests reach the body via ``control.content``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
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
    entries_col = control.content.controls[1]
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
    entries_col = control.content.controls[1]
    assert len(entries_col.controls) == 2


@pytest.mark.unit
def test_apply_renders_children_indented_below_their_parent(mocker):
    from src.core.observatory.disk_usage import DiskUsageEntry

    entries = (
        DiskUsageEntry(
            "rag",
            120,
            True,
            children=(
                DiskUsageEntry("vectors.npz", 100, False),
                DiskUsageEntry("meta.json", 20, False),
            ),
        ),
    )
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=entries,
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    entries_col = control.content.controls[1]
    assert len(entries_col.controls) == 3  # rag + 2 children, all flattened

    # The parent has no left padding; children are indented past it.
    assert entries_col.controls[0].padding.left == 0
    assert entries_col.controls[1].padding.left > 0
    assert entries_col.controls[2].padding.left == entries_col.controls[1].padding.left


@pytest.mark.unit
def test_icon_for_dispatches_by_extension():
    from src.core.observatory.disk_usage import DiskUsageEntry
    from src.gui.modules.observatory.disk_usage_tab import _icon_for

    assert _icon_for(DiskUsageEntry("rag", 0, True)) == ft.Icons.FOLDER_OUTLINED
    assert (
        _icon_for(DiskUsageEntry("config.json", 0, False))
        == ft.Icons.DATA_OBJECT_OUTLINED
    )
    assert _icon_for(DiskUsageEntry("vectors.npz", 0, False)) == ft.Icons.DATA_ARRAY
    assert (
        _icon_for(DiskUsageEntry("something.bin", 0, False))
        == ft.Icons.INSERT_DRIVE_FILE_OUTLINED
    )


@pytest.mark.unit
def test_apply_populates_glossary_only_for_known_present_files(mocker):
    from src.core.observatory.disk_usage import DiskUsageEntry

    entries = (
        DiskUsageEntry("config.json", 10, False),
        DiskUsageEntry("mystery_file.bin", 5, False),  # no glossary entry
    )
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=entries,
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    glossary_col = control.content.controls[4]
    names = [c.controls[0].value for c in glossary_col.controls]
    assert names == ["config.json"]  # mystery_file.bin silently omitted


def _walk(control):
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                yield from _walk(c)
        elif child is not None and not isinstance(child, (str, bytes)):
            yield from _walk(child)


@pytest.mark.unit
def test_apply_wraps_a_described_folder_in_an_accent_bordered_card(mocker):
    from src.core.observatory.disk_usage import DiskUsageEntry

    entries = (
        DiskUsageEntry(
            "rag",
            120,
            True,
            children=(
                DiskUsageEntry("vectors.npz", 100, False),
                DiskUsageEntry("meta.json", 20, False),
            ),
        ),
        DiskUsageEntry("config.json", 10, False),
    )
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=entries,
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    glossary_col = control.content.controls[4]

    # One card for rag/, one plain row for config.json.
    assert len(glossary_col.controls) == 2
    card = glossary_col.controls[0]
    assert card.border is not None
    assert card.border.left.color == ft.Colors.with_opacity(0.6, ft.Colors.PRIMARY)

    texts = [getattr(c, "value", "") for c in _walk(card)]
    assert any("Pasta RAG" in str(t) for t in texts)
    assert any("Índice semântico do RAG" in str(t) for t in texts)
    assert any("vectors.npz" in str(t) for t in texts)
    assert any("meta.json" in str(t) for t in texts)

    plain_row = glossary_col.controls[1]
    assert not isinstance(plain_row, ft.Container)


@pytest.mark.unit
def test_header_shows_path_beside_help_icon_not_as_its_own_row(mocker):
    """The path moved off its own row to save vertical space (lives in the
    header, next to the help icon) — this is the layout contract other tests
    rely on via fixed indices into control.content.controls."""
    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=(),
    )
    control, apply = build_disk_usage_tab(MagicMock())
    apply()
    body = control.content
    header_row = body.controls[0]
    texts = [getattr(c, "value", "") for c in header_row.controls]
    assert "~/.mill-tools/" in texts
    # 5 rows total: header, entries, hairline, glossary label, glossary — no
    # standalone path row eating a 6th slot.
    assert len(body.controls) == 5
