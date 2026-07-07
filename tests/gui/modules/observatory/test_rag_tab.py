"""Construct-smoke for the Observatório nested Índice/RAG tab.

Flet is not testable headless, so this builds the control with a MagicMock
page, exercising sub-tab switching and the reindex pipeline (Fase 0b,
PLANO_NL2CLI_HUB_IA.md: reindexing moved here from the AI hub) without a live
UI. Tests that trigger a real reindex click patch out ``spinner`` — the
factory's ``start()`` calls ``img.update()`` on a control that was never
actually mounted to a page, which raises headless.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from src.gui.modules.observatory.rag_tab import build_rag_tab


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


def _no_spin(mocker):
    """Replace the index tab's spinner with an inert stand-in (headless-safe)."""
    mocker.patch(
        "src.gui.modules.observatory.index_tab.spinner",
        return_value=(MagicMock(), lambda: None, lambda: None),
    )


@pytest.mark.unit
def test_rag_tab_builds():
    control, apply = build_rag_tab(MagicMock(), MagicMock(), MagicMock(), [False])
    assert control is not None
    assert callable(apply)


@pytest.mark.unit
def test_indice_is_the_default_subtab():
    control, _apply = build_rag_tab(MagicMock(), MagicMock(), MagicMock(), [False])
    body_stack = control.controls[2].content
    index_view, analytics_view, disk_view = body_stack.controls
    assert index_view.visible is True
    assert analytics_view.visible is False
    assert disk_view.visible is False


@pytest.mark.unit
def test_switching_to_painel_subtab_does_not_raise():
    control, _apply = build_rag_tab(MagicMock(), MagicMock(), MagicMock(), [False])
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
    control, _apply = build_rag_tab(MagicMock(), MagicMock(), MagicMock(), [False])
    tab_disco = control.controls[0].controls[2]
    tab_disco.on_click(MagicMock())
    body_stack = control.controls[2].content
    _index_view, _analytics_view, disk_view = body_stack.controls
    assert disk_view.visible is True


@pytest.mark.unit
def test_apply_refreshes_index_and_analytics_via_background_thread(mocker):
    from src.core.rag.stats import IndexStats

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
    control, apply = build_rag_tab(MagicMock(), MagicMock(), MagicMock(), [False])
    apply()  # must not raise


@pytest.mark.unit
def test_reindex_button_starts_the_index_pipeline(mocker):
    """Fase 0b: "Reindexar" now runs the pipeline itself (no more AI-hub bridge)."""
    _no_spin(mocker)
    start_mock = mocker.patch("src.gui.modules.observatory.rag_tab.start_ai_index")

    bus = MagicMock()
    cancel_event = threading.Event()
    pipeline_running = [False]
    control, _apply = build_rag_tab(MagicMock(), bus, cancel_event, pipeline_running)

    reindex_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())

    assert pipeline_running[0] is True
    assert reindex_btn.disabled is True
    start_mock.assert_called_once()
    _args, kwargs = start_mock.call_args
    assert kwargs["embed_model"]


@pytest.mark.unit
def test_reindex_button_is_a_noop_while_a_run_is_already_in_progress(mocker):
    _no_spin(mocker)
    start_mock = mocker.patch("src.gui.modules.observatory.rag_tab.start_ai_index")

    control, _apply = build_rag_tab(MagicMock(), MagicMock(), threading.Event(), [True])
    reindex_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())

    start_mock.assert_not_called()


@pytest.mark.unit
def test_cancel_button_sets_the_cancel_event(mocker):
    _no_spin(mocker)
    mocker.patch("src.gui.modules.observatory.rag_tab.start_ai_index")

    cancel_event = threading.Event()
    control, _apply = build_rag_tab(MagicMock(), MagicMock(), cancel_event, [False])

    reindex_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())
    cancel_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Cancelar"
    )
    cancel_btn.on_click(MagicMock())

    assert cancel_event.is_set()


@pytest.mark.unit
def test_task_done_event_clears_pipeline_running_and_refreshes_status(mocker):
    from src.gui.events import PipelineEvent

    _no_spin(mocker)
    mocker.patch("src.gui.modules.observatory.rag_tab.start_ai_index")
    mocker.patch("src.core.rag.indexer.index_dir")
    mocker.patch(
        "src.core.rag.stats.index_stats", side_effect=Exception("no index yet")
    )

    page = MagicMock()
    subscribers = []
    page.pubsub.subscribe.side_effect = lambda cb: subscribers.append(cb)

    pipeline_running = [False]
    control, _apply = build_rag_tab(
        page, MagicMock(), threading.Event(), pipeline_running
    )
    reindex_btn = next(
        c for c in _walk(control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())
    assert pipeline_running[0] is True

    handler = subscribers[0]
    handler(PipelineEvent("task_done", "observatory", {}, module_id="observatory"))

    assert pipeline_running[0] is False
    assert reindex_btn.disabled is False
