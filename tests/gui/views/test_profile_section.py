"""Unit tests for the Transcription form's profile auto-suggestion section."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


def _fake_page() -> MagicMock:
    """A MagicMock page that runs page.run_task's coroutine synchronously."""
    page = MagicMock()
    captured: dict = {}
    page.run_task.side_effect = lambda coro_fn: captured.setdefault("coro", coro_fn)
    page._captured = captured
    return page


@pytest.mark.unit
def test_suggest_logs_activity_on_a_confident_match(mocker):
    from src.gui.views.profile_section import build_profile_section

    mocker.patch(
        "src.gui.views.profile_section._classify_path",
        return_value=("lecture", 0.82, 0.30),
    )
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    page = _fake_page()
    section = build_profile_section(page, initial_profile="default", visible=True)
    section.suggest("/some/doc.txt")
    asyncio.run(page._captured["coro"]())

    log_mock.assert_called_once()
    module, event, detail = log_mock.call_args.args
    assert module == "transcription"
    assert event == "profile_suggested"
    assert "doc.txt" in detail


@pytest.mark.unit
def test_suggest_does_not_log_when_there_is_no_match(mocker):
    from src.gui.views.profile_section import build_profile_section

    mocker.patch("src.gui.views.profile_section._classify_path", return_value=None)
    log_mock = mocker.patch("src.core.observatory.activity.log_activity")

    page = _fake_page()
    section = build_profile_section(page, initial_profile="default", visible=True)
    section.suggest("/some/doc.txt")
    asyncio.run(page._captured["coro"]())

    log_mock.assert_not_called()


@pytest.mark.unit
def test_suggest_survives_a_failing_activity_log(mocker):
    """A broken log_activity must never break the suggestion chip."""
    from src.gui.views.profile_section import build_profile_section

    mocker.patch(
        "src.gui.views.profile_section._classify_path",
        return_value=("lecture", 0.82, 0.30),
    )
    mocker.patch(
        "src.core.observatory.activity.log_activity",
        side_effect=RuntimeError("disk full"),
    )

    page = _fake_page()
    section = build_profile_section(page, initial_profile="default", visible=True)
    section.suggest("/some/doc.txt")
    asyncio.run(page._captured["coro"]())  # must not raise

    assert section.get_value() == "lecture"
