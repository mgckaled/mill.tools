"""Construct-smoke for the Observatório nested Índice/RAG tab.

Flet is not testable headless, so this builds the control with a MagicMock
page and a fake ``nav`` list, exercising sub-tab switching and the
"Reindexar" bridge to the AI hub without a live UI.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.rag_tab import build_rag_tab


class _ImmediateThread:
    """Fake ``threading.Thread`` that runs ``target`` synchronously on `.start()`."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self) -> None:
        self._target()


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


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    import src.gui.settings as settings_mod

    cfg_dir = tmp_path / ".mill-tools"
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_dir / "config.json")


@pytest.mark.unit
def test_rag_tab_builds():
    control, apply = build_rag_tab(MagicMock(), nav=[MagicMock()])
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_indice_is_the_default_subtab():
    control, _apply = build_rag_tab(MagicMock(), nav=[MagicMock()])
    body_stack = control.controls[2].content
    index_view, analytics_view, disk_view = body_stack.controls
    assert index_view.visible is True
    assert analytics_view.visible is False
    assert disk_view.visible is False


@pytest.mark.unit
def test_switching_to_painel_subtab_does_not_raise():
    control, _apply = build_rag_tab(MagicMock(), nav=[MagicMock()])
    tab_painel = control.controls[0].controls[1]
    tab_painel.on_click(MagicMock())
    body_stack = control.controls[2].content
    index_view, analytics_view, disk_view = body_stack.controls
    assert analytics_view.visible is True
    assert index_view.visible is False


@pytest.mark.unit
def test_switching_to_disco_subtab_populates_entries(mocker):
    from src.core.observatory.disk_usage import DiskUsageEntry

    mocker.patch(
        "src.gui.modules.observatory.disk_usage_tab.disk_usage",
        return_value=(DiskUsageEntry("rag", 100, True),),
    )
    control, _apply = build_rag_tab(MagicMock(), nav=[MagicMock()])
    tab_disco = control.controls[0].controls[2]
    tab_disco.on_click(MagicMock())
    body_stack = control.controls[2].content
    _index_view, _analytics_view, disk_view = body_stack.controls
    assert disk_view.visible is True


@pytest.mark.unit
def test_apply_refreshes_index_and_analytics_via_background_thread(mocker):
    from src.core.rag.stats import IndexStats

    mocker.patch(
        "src.gui.modules.observatory.rag_tab.threading.Thread", _ImmediateThread
    )
    mocker.patch("src.core.rag.indexer.index_dir")
    fake_stats = IndexStats(
        n_docs=1,
        n_chunks=2,
        dim=768,
        embed_model="nomic-embed-custom",
        disk_bytes=100,
        updated_at=None,
        per_doc=(),
    )
    mocker.patch("src.core.rag.stats.index_stats", return_value=fake_stats)
    control, apply = build_rag_tab(MagicMock(), nav=[MagicMock()])
    apply()  # must not raise


@pytest.mark.unit
def test_reindex_button_bridges_to_the_ai_hub():
    nav_calls = []
    nav = [lambda target, payload: nav_calls.append((target, payload))]
    control, _apply = build_rag_tab(MagicMock(), nav=nav)

    reindex_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())

    assert nav_calls == [("ai", {"trigger_reindex": True})]
