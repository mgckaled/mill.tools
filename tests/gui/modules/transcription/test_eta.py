"""Unit tests for the transcription ETA helper (format_eta)."""

from __future__ import annotations

import pytest

from src.gui.modules.transcription.pipeline_log import format_eta


@pytest.mark.unit
def test_eta_none_when_too_early():
    # frac = 2/100 = 0.02 < 0.05 → still too noisy to estimate.
    assert format_eta(elapsed=5.0, end=2.0, audio_duration=100.0) is None


@pytest.mark.unit
def test_eta_none_when_duration_unknown():
    assert format_eta(elapsed=10.0, end=5.0, audio_duration=0.0) is None
    assert format_eta(elapsed=10.0, end=5.0, audio_duration=-1.0) is None


@pytest.mark.unit
def test_eta_none_when_no_elapsed_or_progress():
    assert format_eta(elapsed=0.0, end=5.0, audio_duration=100.0) is None
    assert format_eta(elapsed=10.0, end=0.0, audio_duration=100.0) is None


@pytest.mark.unit
def test_eta_none_when_already_complete():
    # frac >= 1.0 → done, nothing left to estimate.
    assert format_eta(elapsed=120.0, end=120.0, audio_duration=120.0) is None
    assert format_eta(elapsed=130.0, end=130.0, audio_duration=120.0) is None


@pytest.mark.unit
def test_eta_computes_remaining_and_speed():
    # elapsed=60s covered end=30s of a 120s source → frac=0.25.
    # remaining = 60 * 0.75 / 0.25 = 180s = "3m 00s"; speed = 30/60 = 0.50×.
    out = format_eta(elapsed=60.0, end=30.0, audio_duration=120.0)
    assert out is not None
    assert "3m 00s" in out
    assert "restantes" in out
    assert "0,50× tempo-real" in out  # PT-BR comma decimal


@pytest.mark.unit
def test_eta_faster_than_realtime():
    # elapsed=10s covered end=30s → 3× real-time; frac=0.25, remaining=30s.
    out = format_eta(elapsed=10.0, end=30.0, audio_duration=120.0)
    assert out is not None
    assert "3,00× tempo-real" in out
    assert "30s restantes" in out


@pytest.mark.unit
def test_eta_at_threshold_is_shown():
    # Exactly 5% transcribed → estimate becomes available.
    out = format_eta(elapsed=10.0, end=5.0, audio_duration=100.0)
    assert out is not None
    assert "restantes" in out
