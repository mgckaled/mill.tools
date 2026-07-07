"""Construct-smoke + lifecycle for the Observatório hub module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect gui.settings and the ML activity/failure logs to tmp_path.

    _on_mount() writes to both (last_ml_activity_seen/last_observatory_tab via
    settings.set, plus reads the activity log) — neither may touch the real
    ~/.mill-tools during a test. Índice/RAG is now the default tab, so its
    apply() also runs on every on_mount() — isolate ml.store.model_dir() and
    the RAG index_dir() too.
    """
    import src.core.observatory.activity as activity_mod
    import src.core.observatory.logs as logs_mod
    import src.gui.settings as settings_mod

    cfg_dir = tmp_path / ".mill-tools"
    monkeypatch.setattr(settings_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "_CONFIG_FILE", cfg_dir / "config.json")
    monkeypatch.setattr(
        activity_mod, "_store_path", lambda: cfg_dir / "ml_activity.json"
    )
    monkeypatch.setattr(logs_mod, "_store_path", lambda: cfg_dir / "ml_logs.json")


@pytest.fixture(autouse=True)
def isolate_model_dir(mocker, tmp_path):
    """Status is a reachable tab from on_mount's click handlers — its apply()
    reads ml.store.model_dir()."""
    mocker.patch("src.core.ml.classify.labels.model_dir", return_value=tmp_path / "ml")


@pytest.fixture(autouse=True)
def isolate_rag_index_dir(mocker, tmp_path):
    """Índice/RAG is the default tab — its apply() reads the real RAG index
    dir unless isolated."""
    mocker.patch("src.core.rag.indexer.index_dir", return_value=tmp_path / "rag")


@pytest.mark.unit
def test_observatory_module_builds():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    assert module.id == "observatory"
    assert module.label == "Observatório"
    assert callable(module.on_mount)
    assert callable(module.on_unmount)


@pytest.mark.unit
def test_on_mount_defaults_to_rag_tab_and_does_not_raise():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})  # must not raise with an empty activity/failure log

    rag_view, status_view, activity_view, logs_view, timing_view = (
        module.control.controls[2].content.controls
    )
    assert rag_view.visible is True
    assert status_view.visible is False
    assert activity_view.visible is False
    assert logs_view.visible is False
    assert timing_view.visible is False


@pytest.mark.unit
def test_switching_to_status_tab_does_not_raise():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})
    module.control.controls[0].controls[1].on_click(MagicMock())  # tab_status


@pytest.mark.unit
def test_switching_to_logs_tab_does_not_raise():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})
    module.control.controls[0].controls[3].on_click(MagicMock())  # tab_logs


@pytest.mark.unit
def test_switching_to_timing_tab_does_not_raise(tmp_path, monkeypatch):
    import src.core.observatory.model_timing as model_timing_mod
    from src.gui.modules.observatory.view import build_observatory_module

    monkeypatch.setattr(
        model_timing_mod, "_store_path", lambda: tmp_path / "model_timings.json"
    )
    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})
    module.control.controls[0].controls[4].on_click(MagicMock())  # tab_timing


@pytest.mark.unit
def test_on_mount_records_last_seen_timestamp(tmp_path, monkeypatch):
    import src.core.observatory.activity as activity_mod
    from src.core.observatory.activity import log_activity
    from src.gui import settings
    from src.gui.modules.observatory.view import build_observatory_module

    activity_path = tmp_path / ".mill-tools" / "ml_activity.json"
    monkeypatch.setattr(activity_mod, "_store_path", lambda: activity_path)
    log_activity("data", "outliers_detected", "12 linhas", now=123.0)

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})

    assert settings.get("last_ml_activity_seen") == 123.0


@pytest.mark.unit
def test_reindex_button_starts_the_pipeline_instead_of_bridging(mocker):
    """Fase 0b (PLANO_NL2CLI_HUB_IA.md): reindex runs here now, no AI-hub bridge."""
    from src.gui.modules.observatory.view import build_observatory_module

    mocker.patch(
        "src.gui.modules.observatory.index_tab.spinner",
        return_value=(MagicMock(), lambda: None, lambda: None),
    )
    start_mock = mocker.patch("src.gui.modules.observatory.rag_tab.start_ai_index")

    pipeline_running = [False]
    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), pipeline_running, []
    )
    module.on_mount({})

    def _walk(control):
        yield control
        for attr in ("controls", "content"):
            child = getattr(control, attr, None)
            if isinstance(child, list):
                for c in child:
                    yield from _walk(c)
            elif child is not None and not isinstance(child, (str, bytes)):
                yield from _walk(child)

    reindex_btn = next(
        c for c in _walk(module.control) if getattr(c, "content", None) == "Reindexar"
    )
    reindex_btn.on_click(MagicMock())

    assert pipeline_running[0] is True
    start_mock.assert_called_once()
