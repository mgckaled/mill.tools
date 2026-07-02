"""Construct-smoke + lifecycle for the Observatório hub module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect gui.settings and the ML activity/failure logs to tmp_path.

    _on_mount() writes to both (last_ml_activity_seen/last_observatory_tab via
    settings.set, plus reads the activity log) — neither may touch the real
    ~/.mill-tools during a test. Status is now the default tab, so its
    apply() also runs on every on_mount() — isolate ml.store.model_dir() too.
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
    """Status is the default tab — its apply() reads ml.store.model_dir()."""
    mocker.patch("src.core.ml.classify.model_dir", return_value=tmp_path / "ml")


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
def test_on_mount_defaults_to_status_tab_and_does_not_raise():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})  # must not raise with an empty activity/failure log

    status_view, activity_view, logs_view, timing_view = module.control.controls[
        2
    ].content.controls
    assert status_view.visible is True
    assert activity_view.visible is False
    assert logs_view.visible is False
    assert timing_view.visible is False


@pytest.mark.unit
def test_switching_to_logs_tab_does_not_raise():
    from src.gui.modules.observatory.view import build_observatory_module

    module = build_observatory_module(
        MagicMock(), MagicMock(), MagicMock(), [False], []
    )
    module.on_mount({})
    module.control.controls[0].controls[2].on_click(MagicMock())  # tab_logs


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
    module.control.controls[0].controls[3].on_click(MagicMock())  # tab_timing


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
